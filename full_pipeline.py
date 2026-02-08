import time, csv, subprocess, re, os
from datetime import datetime

import board, busio
from adafruit_ina260 import INA260

# ================= CONFIG =================
BASELINE_DURATION = 10
TEST_DURATION = 60
SAMPLE_INTERVAL = 0.2

WRK_THREADS = 4
WRK_CONN = 50

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

# Create results directory
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_dir = f"results_{timestamp}"
os.makedirs(results_dir, exist_ok=True)

# INA260 init
i2c = busio.I2C(board.SCL, board.SDA)
ina = INA260(i2c)

def sample_power(csv_file, duration):
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        start = time.time()
        while time.time() - start < duration:
            ts = time.time()
            w.writerow([
                ts,
                ina.voltage,
                ina.current / 1000,
                ina.power / 1000
            ])
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
    raise ValueError(f"Could not parse request count from wrk output")

# ========== BASELINE ==========
print("=" * 60)
print("RUNNING BASELINE MEASUREMENT")
print("=" * 60)
baseline_csv = os.path.join(results_dir, "baseline.csv")
sample_power(baseline_csv, BASELINE_DURATION)
baseline_energy, baseline_dur = compute_energy(baseline_csv)
baseline_avg_power = baseline_energy / baseline_dur
print(f"✓ Baseline complete: {baseline_avg_power:.2f}W average\n")

# Store all results
all_results = []

# ========== RUN ALL TESTS ==========
test_count = 0
total_tests = len(SERVERS) * len(ENDPOINTS)

for server_name, server_config in SERVERS.items():
    for endpoint in ENDPOINTS:
        test_count += 1
        
        print("=" * 60)
        print(f"TEST {test_count}/{total_tests}: {server_name.upper()} - {endpoint}")
        print("=" * 60)
        
        # File paths for this test
        test_csv = os.path.join(results_dir, f"test_{server_name}_{endpoint[1:]}.csv")
        wrk_out = os.path.join(results_dir, f"wrk_{server_name}_{endpoint[1:]}.txt")
        
        # Start server
        print(f"▶ Starting {server_name} server...")
        server = subprocess.Popen(
            server_config["cmd"],
            cwd=server_config["cwd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Warmup
        warmup_time = server_config["warmup"]
        print(f"⏳ Warming up for {warmup_time}s...")
        time.sleep(warmup_time)
        
        # Run wrk load test + power measurement
        url = server_config["url"] + endpoint
        print(f"🔥 Running load test: {url}")
        print(f"📊 Measuring power for {TEST_DURATION}s...")
        
        wrk_cmd = [
            "wrk",
            f"-t{WRK_THREADS}",
            f"-c{WRK_CONN}",
            f"-d{TEST_DURATION}s",
            url
        ]
        
        wrk = subprocess.Popen(wrk_cmd, stdout=open(wrk_out, "w"), stderr=subprocess.DEVNULL)
        sample_power(test_csv, TEST_DURATION)
        wrk.wait()
        
        # Stop server
        print("🛑 Stopping server...")
        server.terminate()
        server.wait()
        
        # Calculate results
        test_energy, test_dur = compute_energy(test_csv)
        baseline_scaled = baseline_avg_power * test_dur
        corrected_energy = test_energy - baseline_scaled
        requests = parse_wrk(wrk_out)
        j_per_req = corrected_energy / requests
        
        # Store results
        result = {
            "server": server_name,
            "endpoint": endpoint,
            "requests": requests,
            "energy_j": corrected_energy,
            "j_per_req": j_per_req
        }
        all_results.append(result)
        
        print(f"✓ Complete: {requests:,} requests, {corrected_energy:.2f}J, {j_per_req:.6f}J/req\n")
        
        # Brief pause between tests
        if test_count < total_tests:
            time.sleep(3)

# ========== SUMMARY ==========
print("=" * 60)
print("ALL TESTS COMPLETE - SUMMARY")
print("=" * 60)

# Sort by energy per request
all_results.sort(key=lambda x: x["j_per_req"])

print("\n{:<10} {:<12} {:>12} {:>12} {:>15}".format(
    "Server", "Endpoint", "Requests", "Energy (J)", "J/request"
))
print("-" * 65)
for r in all_results:
    print("{:<10} {:<12} {:>12,} {:>12.2f} {:>15.6f}".format(
        r["server"], r["endpoint"], r["requests"], r["energy_j"], r["j_per_req"]
    ))

# Write CSV summary
summary_csv = os.path.join(results_dir, "summary.csv")
with open(summary_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["server", "endpoint", "requests", "energy_j", "j_per_req"])
    w.writeheader()
    w.writerows(all_results)

# Write LaTeX table
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
