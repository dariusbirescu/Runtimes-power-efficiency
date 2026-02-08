import time, csv, subprocess, re, os
from datetime import datetime

# ================= CONFIG =================
BASELINE_DURATION = 10
TEST_DURATION = 20
SAMPLE_INTERVAL = 0.2

WRK_THREADS = 4
WRK_CONN = 50

# ===== MOCK INA260 SENSOR DATA =====
# Baseline power: simulating idle Raspberry Pi
BASELINE_VOLTAGE = 5.1        # Typical USB-C voltage
BASELINE_CURRENT = 0.6        # Amperes (idle)
BASELINE_POWER = 3.06         # Watts (5.1V × 0.6A)

# Test power: simulating Raspberry Pi under load
TEST_VOLTAGE = 5.0            # Slight voltage drop under load
TEST_CURRENT = 1.8            # Amperes (under load)
TEST_POWER = 9.0              # Watts (5.0V × 1.8A)

SERVERS = {
    "spring": {
        "cmd": ["java", "-jar", "target/energy-test-1.0.0.jar"],
        "cwd": "java-spring",
        "url": "http://localhost:8080",
        "warmup": 10
    },
    "node": {
        "cmd": ["node", "index.js"],
        "cwd": "nodejs",
        "url": "http://localhost:3000",
        "warmup": 5
    }
}

ENDPOINTS = ["/cpu", "/memory", "/io", "/mixed"]
# =========================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_dir = f"results_mocked_{timestamp}"
os.makedirs(results_dir, exist_ok=True)

def mock_sample_power(csv_file, duration, is_baseline=True):
    """Mock power sampling with realistic simulated data"""
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        start = time.time()
        
        # Use realistic fixed values based on typical Raspberry Pi consumption
        if is_baseline:
            voltage = BASELINE_VOLTAGE
            current = BASELINE_CURRENT
            power = BASELINE_POWER
        else:
            voltage = TEST_VOLTAGE
            current = TEST_CURRENT
            power = TEST_POWER
        
        while time.time() - start < duration:
            ts = time.time()
            w.writerow([ts, voltage, current, power])
            time.sleep(SAMPLE_INTERVAL)

def compute_energy(csv_file):
    t, p = [], []
    with open(csv_file) as f:
        r = csv.DictReader(f)
        for row in r:
            t.append(float(row["timestamp"]))
            p.append(float(row["power_W"]))
    energy = sum(p[i] * (t[i] - t[i-1]) for i in range(1, len(t)))
    return energy, t[-1] - t[0]

def parse_wrk(file):
    with open(file) as f:
        txt = f.read()
    match = re.search(r"(\d+)\s+requests in", txt)
    if match:
        return int(match.group(1))
    # If we can't parse, print the file content for debugging
    print(f"⚠️  Could not parse wrk output. File content:")
    print(f"--- {file} ---")
    print(txt[:500])
    print("---")
    raise ValueError(f"Could not parse request count from wrk output")

# ========== BASELINE ==========
print("=" * 60)
print("RUNNING BASELINE MEASUREMENT (MOCKED)")
print("=" * 60)
baseline_csv = os.path.join(results_dir, "baseline.csv")
mock_sample_power(baseline_csv, BASELINE_DURATION, is_baseline=True)
baseline_energy, baseline_dur = compute_energy(baseline_csv)
baseline_avg_power = baseline_energy / baseline_dur
print(f"✓ Baseline complete: {baseline_avg_power:.2f}W average\n")

all_results = []
test_count = 0
total_tests = len(SERVERS) * len(ENDPOINTS)

# ========== RUN ALL TESTS ==========
for server_name, server_config in SERVERS.items():
    for endpoint in ENDPOINTS:
        test_count += 1
        
        print("=" * 60)
        print(f"TEST {test_count}/{total_tests}: {server_name.upper()} - {endpoint}")
        print("=" * 60)
        
        test_csv = os.path.join(results_dir, f"test_{server_name}_{endpoint[1:]}.csv")
        wrk_out = os.path.join(results_dir, f"wrk_{server_name}_{endpoint[1:]}.txt")
        
        print(f"▶ Starting {server_name} server...")
        try:
            server = subprocess.Popen(
                server_config["cmd"],
                cwd=server_config["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError as e:
            print(f"✗ Failed to start {server_name} server: {e}")
            continue
        
        warmup_time = server_config["warmup"]
        print(f"⏳ Warming up for {warmup_time}s...")
        time.sleep(warmup_time)
        
        # Check if server is still running
        if server.poll() is not None:
            stdout, stderr = server.communicate()
            print(f"✗ Server crashed during warmup!")
            print(f"   stdout: {stdout.decode()[:200]}")
            print(f"   stderr: {stderr.decode()[:200]}")
            continue
        
        # Wait for server to be ready by checking if port is listening
        url = server_config["url"] + endpoint
        print(f"⏱️  Checking if server is ready at {server_config['url']}...")
        
        server_ready = False
        for attempt in range(10):
            try:
                result = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", server_config["url"]],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.decode() in ["200", "404"]:
                    server_ready = True
                    print(f"✓ Server is ready!")
                    break
            except:
                pass
            time.sleep(1)
        
        if not server_ready:
            print(f"✗ Server did not become ready in time")
            stdout, stderr = server.communicate() if server.poll() else (b"still running", b"")
            print(f"   Server stdout: {stdout.decode()[:300] if stdout else 'N/A'}")
            print(f"   Server stderr: {stderr.decode()[:300] if stderr else 'N/A'}")
            server.terminate()
            server.wait()
            continue
        print(f"🔥 Running load test: {url}")
        print(f"📊 Measuring power for {TEST_DURATION}s (mocked)...")
        
        wrk_cmd = [
            "wrk",
            f"-t{WRK_THREADS}",
            f"-c{WRK_CONN}",
            f"-d{TEST_DURATION}s",
            url
        ]
        
        with open(wrk_out, "w") as wrk_file:
            wrk = subprocess.Popen(wrk_cmd, stdout=wrk_file, stderr=subprocess.PIPE)
            mock_sample_power(test_csv, TEST_DURATION, is_baseline=False)
            wrk.wait()
            
            # Check if wrk failed
            if wrk.returncode != 0:
                _, stderr = wrk.communicate()
                print(f"⚠️  wrk failed with error: {stderr.decode()}")
                print(f"   Check if server is responding at {url}")
                server.terminate()
                server.wait()
                continue
        
        print("🛑 Stopping server...")
        server.terminate()
        server.wait()
        
        test_energy, test_dur = compute_energy(test_csv)
        baseline_scaled = baseline_avg_power * test_dur
        corrected_energy = test_energy - baseline_scaled
        requests = parse_wrk(wrk_out)
        j_per_req = corrected_energy / requests
        
        result = {
            "server": server_name,
            "endpoint": endpoint,
            "requests": requests,
            "energy_j": corrected_energy,
            "j_per_req": j_per_req
        }
        all_results.append(result)
        
        print(f"✓ Complete: {requests:,} requests, {corrected_energy:.2f}J, {j_per_req:.6f}J/req\n")
        
        if test_count < total_tests:
            time.sleep(3)

# ========== SUMMARY ==========
print("=" * 60)
print("ALL TESTS COMPLETE - SUMMARY")
print("=" * 60)

all_results.sort(key=lambda x: x["j_per_req"])

print("\n{:<10} {:<12} {:>12} {:>12} {:>15}".format(
    "Server", "Endpoint", "Requests", "Energy (J)", "J/request"
))
print("-" * 65)
for r in all_results:
    print("{:<10} {:<12} {:>12,} {:>12.2f} {:>15.6f}".format(
        r["server"], r["endpoint"], r["requests"], r["energy_j"], r["j_per_req"]
    ))

summary_csv = os.path.join(results_dir, "summary.csv")
with open(summary_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["server", "endpoint", "requests", "energy_j", "j_per_req"])
    w.writeheader()
    w.writerows(all_results)

latex_file = os.path.join(results_dir, "results.tex")
with open(latex_file, "w") as f:
    f.write("\\begin{tabular}{llrrr}\n\\hline\n")
    f.write("Server & Endpoint & Requests & Energy (J) & J/request \\\\\n\\hline\n")
    for r in all_results:
        f.write(f"{r['server']} & {r['endpoint']} & {r['requests']:,} & {r['energy_j']:.2f} & {r['j_per_req']:.6f} \\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

print(f"\n📁 All results saved to: {results_dir}/")
print(f"   - summary.csv")
print(f"   - results.tex")
print(f"   - Individual CSV and wrk output files")
print("\n✅ Test suite complete!")
