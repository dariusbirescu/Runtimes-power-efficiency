import time, csv, subprocess, re, os
from datetime import datetime

# ================= CONFIG =================
BASELINE_DURATION = 5
SAMPLE_INTERVAL = 0.2
COOLDOWN_BETWEEN_ENDPOINTS = 5

AB_CONCURRENCY = 5

# ===== MOCK INA260 SENSOR DATA =====
BASELINE_VOLTAGE = 5.1
BASELINE_CURRENT = 0.6
BASELINE_POWER = 3.06

TEST_VOLTAGE = 5.0
TEST_CURRENT = 1.8
TEST_POWER = 9.0

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

# Request counts chosen for balanced completion times
ENDPOINTS = {
    "/cpu": 50,
    "/memory": 200,
    "/io": 20,
    "/mixed": 100
}
# =========================================

# Create results directory
os.makedirs("results", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_dir = os.path.join("results", f"ab_mocked_{timestamp}")
os.makedirs(results_dir, exist_ok=True)

def mock_sample_power(csv_file, duration, is_baseline=True):
    """Mock power sampling with realistic simulated data"""
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        start = time.time()
        
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
    """Calculate energy from power measurements"""
    t, p = [], []
    with open(csv_file) as f:
        r = csv.DictReader(f)
        for row in r:
            t.append(float(row["timestamp"]))
            p.append(float(row["power_W"]))
    
    if len(t) < 2:
        return 0, 0
    
    energy = sum(p[i] * (t[i] - t[i-1]) for i in range(1, len(t)))
    duration = t[-1] - t[0]
    avg_power = sum(p) / len(p)
    return energy, duration, avg_power

def parse_ab(file):
    """Parse Apache Bench output for requests and duration"""
    with open(file) as f:
        txt = f.read()
    
    requests_match = re.search(r"Complete requests:\s+(\d+)", txt)
    time_match = re.search(r"Time taken for tests:\s+([\d.]+)\s+seconds", txt)
    
    if not requests_match or not time_match:
        print(f"⚠️  Could not parse ab output. File content:")
        print(f"--- {file} ---")
        print(txt[:500])
        print("---")
        return 0, 0
    
    return int(requests_match.group(1)), float(time_match.group(1))

# ========== BASELINE ==========
print("=" * 60)
print("RUNNING BASELINE MEASUREMENT (MOCKED)")
print("=" * 60)
baseline_csv = os.path.join(results_dir, "baseline.csv")
mock_sample_power(baseline_csv, BASELINE_DURATION, is_baseline=True)
baseline_energy, baseline_dur, baseline_avg_power = compute_energy(baseline_csv)
print(f"✓ Baseline complete: {baseline_avg_power:.2f}W average\n")

all_results = []
test_count = 0
total_tests = len(SERVERS) * len(ENDPOINTS)

# ========== RUN ALL TESTS ==========
for server_name, server_config in SERVERS.items():
    print("=" * 60)
    print(f"STARTING {server_name.upper()} SERVER")
    print("=" * 60)
    
    # Start server once for all endpoints
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
        print(f"Skipping all {server_name} tests\n")
        continue
    
    # Warmup
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
    
    # Wait for server to be ready
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
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        continue
    
    # Run all endpoints for this server
    for endpoint_idx, (endpoint, request_count) in enumerate(ENDPOINTS.items()):
        test_count += 1
        
        print("\n" + "=" * 60)
        print(f"TEST {test_count}/{total_tests}: {server_name.upper()} - {endpoint}")
        print(f"Running {request_count} requests with concurrency {AB_CONCURRENCY}")
        print("=" * 60)
        
        test_csv = os.path.join(results_dir, f"test_{server_name}_{endpoint[1:]}.csv")
        ab_out = os.path.join(results_dir, f"ab_{server_name}_{endpoint[1:]}.txt")
        
        url = server_config["url"] + endpoint
        print(f"🔥 Running load test: {url}")
        
        # Start power measurement in background
        csv_file_handle = open(test_csv, "w", newline="")
        csv_writer = csv.writer(csv_file_handle)
        csv_writer.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        
        # Start ab test
        ab_cmd = ["ab", "-n", str(request_count), "-c", str(AB_CONCURRENCY), url]
        
        print(f"📊 Measuring power while ab runs {request_count} requests...")
        
        with open(ab_out, "w") as ab_file:
            ab_proc = subprocess.Popen(ab_cmd, stdout=ab_file, stderr=subprocess.PIPE)
            
            # Sample power while ab is running
            start_time = time.time()
            while ab_proc.poll() is None:
                ts = time.time()
                csv_writer.writerow([ts, TEST_VOLTAGE, TEST_CURRENT, TEST_POWER])
                time.sleep(SAMPLE_INTERVAL)
            
            ab_proc.wait()
            
            # Add final sample
            ts = time.time()
            csv_writer.writerow([ts, TEST_VOLTAGE, TEST_CURRENT, TEST_POWER])
        
        csv_file_handle.close()
        
        # Check if ab failed
        if ab_proc.returncode != 0:
            print(f"⚠️  ab failed with return code {ab_proc.returncode}")
            # Show ab stderr
            stderr = ab_proc.stderr.read() if ab_proc.stderr else b""
            if stderr:
                print(f"   ab stderr: {stderr.decode()[:500]}")
            # Show ab output file content
            try:
                with open(ab_out, 'r') as f:
                    content = f.read()
                    if content:
                        print(f"   ab output: {content[:500]}")
            except:
                pass
            if endpoint_idx < len(ENDPOINTS) - 1:
                print(f"⏳ Cooling down for {COOLDOWN_BETWEEN_ENDPOINTS}s...")
                time.sleep(COOLDOWN_BETWEEN_ENDPOINTS)
            continue
        
        # Check ab output file size
        if os.path.getsize(ab_out) == 0:
            print(f"⚠️  ab output is empty - server may not be responding")
            if endpoint_idx < len(ENDPOINTS) - 1:
                print(f"⏳ Cooling down for {COOLDOWN_BETWEEN_ENDPOINTS}s...")
                time.sleep(COOLDOWN_BETWEEN_ENDPOINTS)
            continue
        
        # Calculate results
        test_energy, test_dur, test_avg_power = compute_energy(test_csv)
        baseline_scaled = baseline_avg_power * test_dur
        corrected_energy = test_energy - baseline_scaled
        
        completed_requests, ab_duration = parse_ab(ab_out)
        
        # Skip if no requests were completed
        if completed_requests == 0:
            print(f"⚠️  No requests completed - skipping this test")
            if endpoint_idx < len(ENDPOINTS) - 1:
                print(f"⏳ Cooling down for {COOLDOWN_BETWEEN_ENDPOINTS}s...")
                time.sleep(COOLDOWN_BETWEEN_ENDPOINTS)
            continue
        
        j_per_req = corrected_energy / completed_requests
        
        result = {
            "server": server_name,
            "endpoint": endpoint,
            "target_requests": request_count,
            "completed_requests": completed_requests,
            "duration_s": ab_duration,
            "energy_j": corrected_energy,
            "j_per_req": j_per_req,
            "req_per_sec": completed_requests / ab_duration if ab_duration > 0 else 0
        }
        all_results.append(result)
        
        print(f"✓ Complete: {completed_requests}/{request_count} requests in {ab_duration:.2f}s")
        print(f"   Energy: {corrected_energy:.2f}J, {j_per_req:.6f}J/req, {result['req_per_sec']:.2f}req/s")
        
        # Cooldown between endpoints (except after last one)
        if endpoint_idx < len(ENDPOINTS) - 1:
            print(f"⏳ Cooling down for {COOLDOWN_BETWEEN_ENDPOINTS}s...")
            time.sleep(COOLDOWN_BETWEEN_ENDPOINTS)
        
        print()
    
    # Stop server after all endpoints for this server
    print(f"🛑 Stopping {server_name} server...")
    server.terminate()
    try:
        server.wait(timeout=5)
        print("✓ Server stopped\n")
    except subprocess.TimeoutExpired:
        print("⚠️  Server didn't stop gracefully, force killing...")
        server.kill()
        server.wait()
        print("✓ Server killed\n")

# ========== SUMMARY ==========
print("=" * 60)
print("ALL TESTS COMPLETE - SUMMARY")
print("=" * 60)

all_results.sort(key=lambda x: x["j_per_req"])

print("\n{:<10} {:<12} {:>10} {:>10} {:>10} {:>12} {:>15}".format(
    "Server", "Endpoint", "Requests", "Duration", "Req/s", "Energy (J)", "J/request"
))
print("-" * 85)
for r in all_results:
    print("{:<10} {:<12} {:>10} {:>10.2f} {:>10.2f} {:>12.2f} {:>15.6f}".format(
        r["server"], r["endpoint"], r["completed_requests"], 
        r["duration_s"], r["req_per_sec"], r["energy_j"], r["j_per_req"]
    ))

summary_csv = os.path.join(results_dir, "summary.csv")
with open(summary_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["server", "endpoint", "target_requests", "completed_requests", 
                                      "duration_s", "req_per_sec", "energy_j", "j_per_req"])
    w.writeheader()
    w.writerows(all_results)

latex_file = os.path.join(results_dir, "results.tex")
with open(latex_file, "w") as f:
    f.write("\\begin{tabular}{llrrrrrr}\n\\hline\n")
    f.write("Server & Endpoint & Requests & Duration (s) & Req/s & Energy (J) & J/request \\\\\n\\hline\n")
    for r in all_results:
        f.write(f"{r['server']} & {r['endpoint']} & {r['completed_requests']} & "
                f"{r['duration_s']:.2f} & {r['req_per_sec']:.2f} & "
                f"{r['energy_j']:.2f} & {r['j_per_req']:.6f} \\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

print(f"\n📁 All results saved to: {results_dir}/")
print(f"   - summary.csv")
print(f"   - results.tex")
print(f"   - Individual CSV and ab output files")
print("\n✅ Test suite complete!")
