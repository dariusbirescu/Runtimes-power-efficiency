import time, csv, subprocess, re, os
from datetime import datetime

import board, busio
from adafruit_ina260 import INA260

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

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BASELINE_CSV = f"baseline_{timestamp}.csv"
TEST_CSV = f"test_{SERVER_TYPE}_{timestamp}.csv"
WRK_OUT = f"wrk_{SERVER_TYPE}_{timestamp}.txt"

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
    return int(re.search(r"(\d+)\s+requests in", txt).group(1))

# ========== BASELINE ==========
print("Running baseline...")
sample_power(BASELINE_CSV, DURATION)

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
print("Running test...")
wrk = subprocess.Popen(wrk_cmd, stdout=open(WRK_OUT, "w"))
sample_power(TEST_CSV, DURATION)

wrk.wait()
server.terminate()

# ========== ANALYSIS ==========
baseline_energy, baseline_dur = compute_energy(BASELINE_CSV)
test_energy, test_dur = compute_energy(TEST_CSV)

baseline_avg_power = baseline_energy / baseline_dur
baseline_scaled = baseline_avg_power * test_dur
corrected_energy = test_energy - baseline_scaled

requests = parse_wrk(WRK_OUT)
j_per_req = corrected_energy / requests

# ========== OUTPUT ==========
print("\n=== FINAL RESULTS ===")
print("Server:", SERVER_TYPE)
print("Endpoint:", ENDPOINT)
print("Requests:", requests)
print(f"Corrected Energy: {corrected_energy:.2f} J")
print(f"Energy / Request: {j_per_req:.6f} J")

with open("results.tex", "w") as f:
    f.write("\\begin{tabular}{lcc}\n\\hline\n")
    f.write("Server & Energy (J) & J/request \\\\\n\\hline\n")
    f.write(f"{SERVER_TYPE} & {corrected_energy:.2f} & {j_per_req:.6f} \\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

print("LaTeX table written to results.tex")
