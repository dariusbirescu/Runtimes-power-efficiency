import time, csv, subprocess, re, os, random, shutil, sys
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

def check_prerequisites():
    """Check and provide guidance on missing prerequisites"""
    issues = []
    
    # Check wrk
    has_wrk = shutil.which("wrk") is not None
    if not has_wrk:
        issues.append("wrk is not installed. Install with: brew install wrk (macOS) or apt install wrk (Linux)")
    
    # Check server JAR/files
    if SERVER_TYPE == "spring":
        jar_path = os.path.join("java-spring", "target", "energy-test-1.0.0.jar")
        if not os.path.exists(jar_path):
            issues.append(f"Spring Boot JAR not found. Build it with: cd java-spring && mvn clean package")
    else:
        index_path = os.path.join("nodejs", "index.js")
        if not os.path.exists(index_path):
            issues.append(f"Node.js server file not found at {index_path}")
    
    return issues, has_wrk

def run_load_test_with_curl(url, duration):
    """Fallback load test using curl when wrk is not available"""
    print(f"  Using curl for load testing (install wrk for better results)...")
    start = time.time()
    count = 0
    while time.time() - start < duration:
        try:
            subprocess.run(["curl", "-s", "-o", "/dev/null", url], 
                         timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            count += 1
        except:
            pass
    return count

# ========== CHECK PREREQUISITES ==========
issues, has_wrk = check_prerequisites()
if issues:
    print("⚠️  Prerequisites missing:")
    for issue in issues:
        print(f"  ❌ {issue}")
    print("\n💡 Run this script after fixing the above issues, or it will use fallback methods.\n")
    if not has_wrk:
        response = input("Continue with curl fallback? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

# ========== BASELINE ==========
print("Running baseline with mocked sensor...")
mock_sample_power(BASELINE_CSV, DURATION, is_baseline=True)

# ========== START SERVER ==========
print("Starting server...")
server_cmd = SPRING_CMD if SERVER_TYPE == "spring" else NODE_CMD
server_cwd = "java-spring" if SERVER_TYPE == "spring" else "nodejs"
try:
    server = subprocess.Popen(server_cmd, cwd=server_cwd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(10)  # warmup
    
    # Check if server started successfully
    if server.poll() is not None:
        _, stderr = server.communicate()
        print(f"❌ Server failed to start: {stderr.decode()}")
        sys.exit(1)
    
    print("✓ Server started successfully")
except FileNotFoundError as e:
    print(f"❌ Failed to start server: {e}")
    sys.exit(1)

url = (SPRING_URL if SERVER_TYPE == "spring" else NODE_URL) + ENDPOINT

# ========== TEST ==========
print("Running test with mocked sensor...")

if has_wrk:
    # Use wrk for load testing
    wrk_cmd = [
        "wrk",
        f"-t{WRK_THREADS}",
        f"-c{WRK_CONN}",
        f"-d{DURATION}s",
        url
    ]
    wrk = subprocess.Popen(wrk_cmd, stdout=open(WRK_OUT, "w"), stderr=subprocess.DEVNULL)
    mock_sample_power(TEST_CSV, DURATION, is_baseline=False)
    wrk.wait()
else:
    # Fallback to curl-based load testing
    request_count = 0
    with open(WRK_OUT, "w") as f:
        f.write(f"Running {DURATION}s test @ {url}\n")
        f.write(f"  Fallback mode using curl\n")
        
    request_count = run_load_test_with_curl(url, DURATION)
    
    # Write mock wrk-style output
    with open(WRK_OUT, "a") as f:
        f.write(f"  {request_count} requests in {DURATION}.00s\n")
        f.write(f"Requests/sec: {request_count/DURATION:.2f}\n")

server.terminate()
server.wait()
print("✓ Server stopped.")

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
