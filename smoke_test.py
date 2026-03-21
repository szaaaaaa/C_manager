"""Smoke test: start backend, verify endpoints, test production static serving."""
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DEV_PORT = 8767
PROD_PORT = 8768
PYTHON = sys.executable

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"  {status}  {name}: {detail}")


# ── dev-mode backend ──────────────────────────────────────────────────────────
print(f"Starting backend (dev mode) on port {DEV_PORT}...")
env_dev = {**os.environ, "PORT": str(DEV_PORT)}
proc = subprocess.Popen(
    [PYTHON, "-m", "src.api.server"],
    cwd=ROOT,
    env=env_dev,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(3)
BASE = f"http://localhost:{DEV_PORT}"

try:
    # /api/health
    with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
        body = json.loads(r.read())
        check("health status=ok", body.get("status") == "ok", str(body))
        check("health has version", "version" in body, str(body))

    # /api/scan (project dir — NOT C:\)
    scan_path = urllib.parse.quote(ROOT, safe="")
    with urllib.request.urlopen(
        f"{BASE}/api/scan?path={scan_path}&top_n=10", timeout=10
    ) as r:
        body = json.loads(r.read())
        check("scan returns entries", "entries" in body, f"count={body.get('entry_count')}")
        check("scan has total_size_human", "total_size_human" in body, body.get("total_size_human"))
        if body.get("entries"):
            first = body["entries"][0]
            check("entry has safety", "safety" in first, str(list(first.keys())))
            check("safety has emoji", "emoji" in first.get("safety", {}), str(first.get("safety")))

    # /api/rate
    system32 = urllib.parse.quote(r"C:\Windows\System32", safe="")
    with urllib.request.urlopen(
        f"{BASE}/api/rate?path={system32}", timeout=5
    ) as r:
        body = json.loads(r.read())
        check("rate System32=red", body.get("level") == "red", str(body))

    # /api/explain (offline, no API key)
    with urllib.request.urlopen(
        f"{BASE}/api/explain?path={system32}", timeout=5
    ) as r:
        body = json.loads(r.read())
        check("explain returns text", len(body.get("explanation", "")) > 0, body.get("explanation", "")[:60])

finally:
    proc.terminate()

# ── production mode (static file serving) ────────────────────────────────────
print(f"\nStarting backend (PRODUCTION=1) on port {PROD_PORT}...")
env_prod = {**os.environ, "PRODUCTION": "1", "PORT": str(PROD_PORT)}
proc2 = subprocess.Popen(
    [PYTHON, "-m", "src.api.server"],
    cwd=ROOT,
    env=env_prod,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(3)
BASE_PROD = f"http://localhost:{PROD_PORT}"

try:
    with urllib.request.urlopen(f"{BASE_PROD}/", timeout=5) as r:
        html = r.read().decode("utf-8", errors="replace")
        check(
            "production serves index.html",
            "<!doctype" in html.lower() or "<html" in html.lower(),
            f"first 80 chars: {html[:80].strip()}",
        )

    # /api/health still works in production mode
    with urllib.request.urlopen(f"{BASE_PROD}/api/health", timeout=5) as r:
        body = json.loads(r.read())
        check("prod health ok", body.get("status") == "ok", str(body))

finally:
    proc2.terminate()

# ── summary ───────────────────────────────────────────────────────────────────
print()
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"Smoke test: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
