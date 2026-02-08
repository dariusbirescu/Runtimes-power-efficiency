import time, csv, subprocess, re, os, random
from datetime import datetime

# ================= CONFIG =================
SERVER_TYPE = "spring"   # spring | node
ENDPOINT = "/cpu"
DURATION = 60
SAMPLE_INTERVAL = 0.2

SPRING_CMD = ["java", "-jar", "target/energy-test-1.0.0.jar"]
NODE_CMD = ["node", "index.js"]

SPRING_URL = "http://localhost:8080"
NODE_URL = "http://localhost:3000"

WRK_THREADS = 4
WRK_CONN = 50
# =========================================

# ===== MOCK INA260 SENSOR DATA =====
# Baseline power: simulating idle system power consumption
BASELINE_VOLTAGE = 12.0
BASELINE_CURRENT_MIN = 0.8  # Amperes
BASELINE_CURRENT_MAX = 1.0
BASELINE_POWER_MIN = 9.6    # Watts (V * I)
BASELINE_POWER_MAX = 12.0

# Test power: simulating system under load
TEST_VOLTAGE = 12.0
TEST_CURRENT_MIN = 2.5   # Amperes
TEST_CURRENT_MAX = 3.2
TEST_POWER_MIN = 30.0    # Watts
TEST_POWER_MAX = 38.4
# ============================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BASELINE_CSV = f"baseline_mocked_{timestamp}.csv"
TEST_CSV = f"test_{SERVER_TYPE}_mocked_{timestamp}.csv"
WRK_OUT = f"wrk_{SERVER_TYPE}_mocked_{timestamp}.txt"

def mock_sample_power(csv_file, duration, is_baseline=True):
    """Mock power sampling with realistic simulated data"""
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        start = time.time()
        
        # Select appropriate ranges
        if is_baseline:
            voltage = BASELINE_VOLTAGE
            current_min, current_max = BASELINE_CURRENT_MIN, BASELINE_CURRENT_MAX
            power_min, power_max = BASELINE_POWER_MIN, BASELINE_POWER_MAX
        else:
            voltage = TEST_VOLTAGE
            current_min, current_max = TEST_CURRENT_MIN, TEST_CURRENT_MAX
            power_min, power_max = TEST_POWER_MIN, TEST_POWER_MAX
        
        while time.time() - start < duration:
            ts = time.time()
            # Add some realistic variation
            current = random.uniform(current_min, current_max)
            power = random.uniform(power_min, power_max)
            
            w.writerow([
                ts,
                voltage + random.uniform(-0.1, 0.1),  # Small voltage fluctuation
                current,
                power
            ])
            time.sleep(SAMPLE_INTERVAL)
    
    print(f"  Mocked {int((time.time() - start) / SAMPLE_INTERVAL)} samples")

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
    return int(re.search(r"(\d+)\s+requests in", txt).group(1))

# ========== BASELINE ==========
print("Running baseline with mocked sensor...")
mock_sample_power(BASELINE_CSV, DURATION, is_baseline=True)

# ========== START SERVER ==========
print("Starting server...")
server_cmd = SPRING_CMD if SERVER_TYPE == "spring" else NODE_CMD
server_cwd = "java-spring" if SERVER_TYPE == "spring" else "nodejs"
server = subprocess.Popen(server_cmd, cwd=server_cwd)
time.sleep(10)  # warmup

url = (SPRING_URL if SERVER_TYPE == "spring" else NODE_URL) + ENDPOINT
wrk_cmd = [
    "wrk",
    f"-t{WRK_THREADS}",
    f"-c{WRK_CONN}",
    f"-d{DURATION}s",
    url
]

# ========== TEST ==========
print("Running test with mocked sensor...")
wrk = subprocess.Popen(wrk_cmd, stdout=open(WRK_OUT, "w"))
mock_sample_power(TEST_CSV, DURATION, is_baseline=False)

wrk.wait()
server.terminate()
print("Server stopped.")

# ========== ANALYSIS ==========
baseline_energy, baseline_dur = compute_energy(BASELINE_CSV)
test_energy, test_dur = compute_energy(TEST_CSV)

baseline_avg_power = baseline_energy / baseline_dur
baseline_scaled = baseline_avg_power * test_dur
corrected_energy = test_energy - baseline_scaled

requests = parse_wrk(WRK_OUT)
j_per_req = corrected_energy / requests

# ========== OUTPUT ==========
print("\n=== FINAL RESULTS (MOCKED DATA) ===")
print("Server:", SERVER_TYPE)
print("Endpoint:", ENDPOINT)
print("Requests:", requests)
print(f"Baseline Energy: {baseline_energy:.2f} J")
print(f"Test Energy: {test_energy:.2f} J")
print(f"Baseline Avg Power: {baseline_avg_power:.2f} W")
print(f"Corrected Energy: {corrected_energy:.2f} J")
print(f"Energy / Request: {j_per_req:.6f} J")

with open("results_mocked.tex", "w") as f:
    f.write("\\begin{tabular}{lcc}\n\\hline\n")
    f.write("Server & Energy (J) & J/request \\\\\n\\hline\n")
    f.write(f"{SERVER_TYPE} & {corrected_energy:.2f} & {j_per_req:.6f} \\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

print("\nLaTeX table written to results_mocked.tex")
print("\n📊 Generated files:")
print(f"  - {BASELINE_CSV}")
print(f"  - {TEST_CSV}")
print(f"  - {WRK_OUT}")
print(f"  - results_mocked.tex")
