import time, csv, subprocess, re, os, sys, shutil
from datetime import datetime

try:
    import board, busio
except ModuleNotFoundError:
    print("✗ Missing 'board'/'busio' modules (Adafruit Blinka not installed)")
    print("  Fix with: sudo apt update && sudo apt install python3-rpi.gpio python3-dev i2c-tools")
    print("             pip3 install --break-system-packages adafruit-blinka")
    print("  Or use venv: python3 -m venv venv && source venv/bin/activate && pip install adafruit-blinka")
    sys.exit(1)

try:
    from adafruit_ina260 import INA260
except ModuleNotFoundError:
    print("✗ Missing 'adafruit_ina260' module")
    print("  Fix with: pip3 install --break-system-packages adafruit-circuitpython-ina260")
    print("  Or use venv: python3 -m venv venv && source venv/bin/activate && pip install adafruit-circuitpython-ina260")
    sys.exit(1)

# ================= CONFIG =================
# Baseline: 20s provides stable idle power measurement
# Sufficient for averaging transient system processes
BASELINE_DURATION = 20

# 5 Hz sampling rate provides good temporal resolution
SAMPLE_INTERVAL = 0.2

# 10s cooldown allows system to return to idle between tests
COOLDOWN_BETWEEN_ENDPOINTS = 10

# Moderate concurrency appropriate for Raspberry Pi
AB_CONCURRENCY = 1

SERVERS = {
    "spring": {
        "cmd": ["java", "-jar", "target/energy-test-1.0.0.jar"],
        "cwd": "java-spring",
        "url": "http://localhost:8080",
        "warmup": 10  # JVM warmup for JIT compilation
    },
    "node": {
        "cmd": ["node", "index.js"],
        "cwd": "nodejs",
        "url": "http://localhost:3000",
        "warmup": 8  # V8 engine stabilization
    }
}

# Request counts provide sufficient samples (n>300) for each endpoint
# Balanced for ~15-25s test duration - enough for stable energy measurements
ENDPOINTS = {
    "/cpu": 400,       # CPU-intensive: ~15-20s @ ~40-50 req/s
    "/memory": 1000,   # Memory ops: ~15-20s @ ~100-120 req/s  
    "/io": 150,        # I/O-bound: ~15-20s @ ~15-20 req/s
    "/mixed": 500      # Balanced: ~15-20s @ ~50-60 req/s
}
# =========================================

# Optional: override INA260 I2C address via env var (e.g., "0x40" or "64")
def _parse_addr(val: str | None):
    if not val:
        return None
    try:
        return int(val, 0)
    except Exception:
        print(f"⚠️  Invalid INA260_ADDR '{val}' - using default address")
        return None

INA260_ADDR_ENV = _parse_addr(os.environ.get("INA260_ADDR"))

# Basic preflight to ensure required tools and I2C device exist
def ensure_prereqs():
    missing_cmds = [cmd for cmd in ("curl", "ab") if shutil.which(cmd) is None]
    if missing_cmds:
        print(f"✗ Missing required tools: {', '.join(missing_cmds)}")
        print("  Install with: sudo apt install curl apache2-utils")
        sys.exit(1)
    if not os.path.exists("/dev/i2c-1"):
        print("✗ I2C device not found at /dev/i2c-1")
        print("  Enable I2C via 'sudo raspi-config' → Interfacing Options → I2C, then reboot.")
        sys.exit(1)

# Create results directory
os.makedirs("results", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_dir = os.path.join("results", f"ab_real_{timestamp}")
os.makedirs(results_dir, exist_ok=True)

# Preflight checks
ensure_prereqs()

# INA260 init (with optional address override) and quick probe
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ina = INA260(i2c) if INA260_ADDR_ENV is None else INA260(i2c, address=INA260_ADDR_ENV)
    _ = ina.voltage  # probe once to surface init issues early
except Exception as e:
    print(f"✗ Failed to initialize INA260 over I2C: {e}")
    print("  Check wiring, I2C enablement, and sensor address (env INA260_ADDR).")
    sys.exit(1)

def sample_power(csv_file, duration):
    """Sample real power from INA260 sensor"""
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "voltage_V", "current_A", "power_W"])
        start = time.time()
        while time.time() - start < duration:
            ts = time.time()
            w.writerow([
                ts,
                ina.voltage,
                ina.current / 1000.0,  # mA to A
                ina.power / 1000.0     # mW to W
            ])
            time.sleep(SAMPLE_INTERVAL)

def sample_power_while_running(csv_writer, process, sample_interval):
    """Sample power while a process is running"""
    while process.poll() is None:
        ts = time.time()
        csv_writer.writerow([
            ts,
            ina.voltage,
            ina.current / 1000.0,
            ina.power / 1000.0
        ])
        time.sleep(sample_interval)
    
    # Add final sample
    ts = time.time()
    csv_writer.writerow([
        ts,
        ina.voltage,
        ina.current / 1000.0,
        ina.power / 1000.0
    ])

def compute_energy(csv_file):
    """Calculate energy and average power metrics from measurements"""
    t, v, c, p = [], [], [], []
    with open(csv_file) as f:
        r = csv.DictReader(f)
        for row in r:
            t.append(float(row["timestamp"]))
            v.append(float(row["voltage_V"]))
            c.append(float(row["current_A"]))
            p.append(float(row["power_W"]))
    
    if len(t) < 2:
        return 0, 0, 0, 0, 0, 0
    
    energy = sum(p[i] * (t[i] - t[i-1]) for i in range(1, len(t)))
    duration = t[-1] - t[0]
    avg_voltage = sum(v) / len(v)
    avg_current = sum(c) / len(c)
    avg_power = sum(p) / len(p)
    return energy, duration, avg_voltage, avg_current, avg_power

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
print("RUNNING BASELINE MEASUREMENT")
print("=" * 60)
baseline_csv = os.path.join(results_dir, "baseline.csv")
sample_power(baseline_csv, BASELINE_DURATION)
baseline_energy, baseline_dur, baseline_avg_v, baseline_avg_c, baseline_avg_power = compute_energy(baseline_csv)
print(f"✓ Baseline complete: {baseline_avg_v:.2f}V, {baseline_avg_c:.3f}A, {baseline_avg_power:.2f}W average\n")

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
    # Spring jar presence check to avoid silent failures
    if server_name == "spring":
        jar_path = os.path.join(server_config["cwd"], "target", "energy-test-1.0.0.jar")
        if not os.path.exists(jar_path):
            print(f"✗ Spring Boot JAR missing: {jar_path}")
            print("  Rebuild or adjust path, skipping Spring tests.\n")
            continue
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
    for attempt in range(30):  # Increased from 10 to 30 attempts (30 seconds total)
        if attempt % 5 == 0 and attempt > 0:
            print(f"   Still waiting... (attempt {attempt}/30)")
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", server_config["url"]],
                capture_output=True,
                timeout=3  # Increased timeout from 2 to 3 seconds
            )
            http_code = result.stdout.decode().strip()
            if result.returncode == 0 and http_code in ["200", "404"]:
                server_ready = True
                print(f"✓ Server is ready! (HTTP {http_code})")
                break
            elif http_code and attempt > 15:  # Show codes after 15s to help debug
                print(f"   Got HTTP {http_code}, retrying...")
        except subprocess.TimeoutExpired:
            if attempt > 15:
                print(f"   Curl timeout, server may be starting slowly...")
        except Exception as e:
            if attempt > 15:
                print(f"   Connection error: {type(e).__name__}")
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
        ab_cmd = ["ab", "-n", str(request_count), "-c", str(AB_CONCURRENCY), "-s", "60", url]
        
        print(f"📊 Measuring power while ab runs {request_count} requests...")
        
        with open(ab_out, "w") as ab_file:
            ab_proc = subprocess.Popen(ab_cmd, stdout=ab_file, stderr=subprocess.PIPE)
            
            # Sample power while ab is running
            sample_power_while_running(csv_writer, ab_proc, SAMPLE_INTERVAL)
            ab_proc.wait()
        
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
        test_energy, test_dur, test_avg_v, test_avg_c, test_avg_power = compute_energy(test_csv)
        baseline_scaled = baseline_avg_power * test_dur
        corrected_energy = test_energy - baseline_scaled
        corrected_power = test_avg_power - baseline_avg_power
        
        completed_requests, ab_duration = parse_ab(ab_out)
        
        # Skip if no requests were completed
        if completed_requests == 0:
            print(f"⚠️  No requests completed - skipping this test")
            if endpoint_idx < len(ENDPOINTS) - 1:
                print(f"⏳ Cooling down for {COOLDOWN_BETWEEN_ENDPOINTS}s...")
                time.sleep(COOLDOWN_BETWEEN_ENDPOINTS)
            continue
        
        j_per_req = corrected_energy / completed_requests
        w_per_req = corrected_power / completed_requests
        a_per_req = test_avg_c / completed_requests if completed_requests > 0 else 0
        
        result = {
            "server": server_name,
            "endpoint": endpoint,
            "target_requests": request_count,
            "completed_requests": completed_requests,
            "duration_s": ab_duration,
            "avg_voltage_v": test_avg_v,
            "avg_current_a": test_avg_c,
            "avg_power_w": corrected_power,
            "total_energy_j": corrected_energy,
            "j_per_req": j_per_req,
            "w_per_req": w_per_req,
            "a_per_req": a_per_req,
            "req_per_sec": completed_requests / ab_duration if ab_duration > 0 else 0
        }
        all_results.append(result)
        
        print(f"✓ Complete: {completed_requests}/{request_count} requests in {ab_duration:.2f}s")
        print(f"   Power: {test_avg_v:.2f}V × {test_avg_c:.3f}A = {corrected_power:.2f}W avg")
        print(f"   Energy: {corrected_energy:.2f}J total, {j_per_req:.6f}J/req")
        print(f"   Per-request: {w_per_req:.6f}W, {a_per_req:.6f}A, {result['req_per_sec']:.2f}req/s")
        
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

print("\n{:<10} {:<12} {:>8} {:>8} {:>8} {:>8} {:>10} {:>10} {:>10} {:>10}".format(
    "Server", "Endpoint", "Reqs", "V(avg)", "A(avg)", "W(avg)", "Total J", "J/req", "W/req", "A/req"
))
print("-" * 108)
for r in all_results:
    print("{:<10} {:<12} {:>8} {:>8.2f} {:>8.3f} {:>8.2f} {:>10.2f} {:>10.6f} {:>10.6f} {:>10.6f}".format(
        r["server"], r["endpoint"], r["completed_requests"], 
        r["avg_voltage_v"], r["avg_current_a"], r["avg_power_w"], 
        r["total_energy_j"], r["j_per_req"], r["w_per_req"], r["a_per_req"]
    ))

summary_csv = os.path.join(results_dir, "summary.csv")
with open(summary_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["server", "endpoint", "target_requests", "completed_requests", 
                                      "duration_s", "req_per_sec", "avg_voltage_v", "avg_current_a", 
                                      "avg_power_w", "total_energy_j", "j_per_req", "w_per_req", "a_per_req"])
    w.writeheader()
    w.writerows(all_results)

latex_file = os.path.join(results_dir, "results.tex")
with open(latex_file, "w") as f:
    f.write("\\begin{tabular}{llrrrrrrrrr}\n\\hline\n")
    f.write("Server & Endpoint & Reqs & V(avg) & A(avg) & W(avg) & Total J & J/req & W/req & A/req \\\\\n\\hline\n")
    for r in all_results:
        f.write(f"{r['server']} & {r['endpoint']} & {r['completed_requests']} & "
                f"{r['avg_voltage_v']:.2f} & {r['avg_current_a']:.3f} & {r['avg_power_w']:.2f} & "
                f"{r['total_energy_j']:.2f} & {r['j_per_req']:.6f} & "
                f"{r['w_per_req']:.6f} & {r['a_per_req']:.6f} \\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

print(f"\n📁 All results saved to: {results_dir}/")
print(f"   - summary.csv")
print(f"   - results.tex")
print(f"   - Individual CSV and ab output files")
print("\n✅ Test suite complete!")
