# Runs each server test on its own fresh demo database, so no test depends on what another left behind:
# for each test, scripts/demo_replay.py into a new FS_DATA_DIR, a server on its own port, the test, then the server
# is stopped by its PID.   python scripts/run_tests.py [--dir /tmp/fs_tests] [--port 8030] [test ...]
import argparse, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ["flow_test", "api_v1_test", "pilot_test", "webhook_test"]
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="/tmp/fs_tests")
ap.add_argument("--port", type=int, default=8030)
ap.add_argument("--day", default="2026-04-15")
ap.add_argument("tests", nargs="*", default=TESTS)
a = ap.parse_args()
KEY, SECRET = "testkey", "hooksecret"
ENV = dict(os.environ, FS_DEMO_NOW=f"{a.day}T12:30:00Z", FS_SERVICE_KEYS=KEY, FS_FSI_PORTAL="0", FS_BHUVAN="0", FS_SCAR_LIVE="0",
           FS_DIRECTION="0", FS_RUNWAY="0")
template = Path(a.dir) / "template"
if not (template / "field.db").exists():
    subprocess.run([sys.executable, str(ROOT / "scripts/demo_replay.py"), a.day], env=dict(ENV, FS_DATA_DIR=str(template)),
                   check=True, stdout=subprocess.DEVNULL)
results = {}
for k, name in enumerate(a.tests):
    d, port = Path(a.dir) / name, a.port + 2 * k
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    shutil.copy(template / "field.db", d / "field.db")
    env = dict(ENV, FS_DATA_DIR=str(d), FS_PORT=str(port))
    if name == "webhook_test":
        env |= {"FS_WEBHOOK_URL": f"http://127.0.0.1:{port + 1}/", "FS_WEBHOOK_SECRET": SECRET}
    log = open(d / "server.log", "w")
    srv = subprocess.Popen([sys.executable, str(ROOT / "run.py")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/field", timeout=2); break
            except Exception:
                time.sleep(0.5)
        t = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{name}.py")], cwd=ROOT, capture_output=True, text=True,
                           env=dict(os.environ, FS_URL=f"http://127.0.0.1:{port}", FS_KEY=KEY, FS_HOOK_PORT=str(port + 1),
                                    FS_HOOK_SECRET=SECRET), timeout=900)
        (d / "test.out").write_text(t.stdout + t.stderr)
        results[name] = t.returncode
        print(f"{name}: {'PASS' if t.returncode == 0 else 'FAIL (see ' + str(d / 'test.out') + ')'}", flush=True)
    finally:
        srv.terminate()
        srv.wait(20)
sys.exit(0 if all(v == 0 for v in results.values()) else 1)
