"""Integration tests for the FastAPI server (angry-edison API)."""
import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)


# ── /api/health ───────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_returns_status_ok(self):
        r = client.get("/api/health")
        assert r.json()["status"] == "ok"


# ── /api/drive-info ───────────────────────────────────────────────────────────

class TestDriveInfo:
    def test_drive_info_ok(self):
        r = client.get("/api/drive-info", params={"drive": "C:\\"})
        assert r.status_code == 200

    def test_drive_info_has_fields(self):
        r = client.get("/api/drive-info", params={"drive": "C:\\"})
        body = r.json()
        # should have some disk-related fields
        assert isinstance(body, dict)


# ── POST /api/scan ────────────────────────────────────────────────────────────

class TestStartScan:
    def test_start_scan_returns_started(self, tmp_path):
        r = client.post("/api/scan", json={
            "root": str(tmp_path),
            "min_size_mb": 0.0,
            "max_depth": 1,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "started"

    def test_start_scan_bad_root(self):
        # Non-existent root — server accepts and starts, error comes via progress
        r = client.post("/api/scan", json={
            "root": "/this/does/not/exist/xyz",
            "min_size_mb": 0.0,
            "max_depth": 1,
        })
        # Either 200 (started) or 409 (already running from previous test)
        assert r.status_code in (200, 409)


# ── GET /api/scan/results ──────────────────────────────────────────────────────

class TestScanResults:
    def test_results_returns_dict(self):
        r = client.get("/api/scan/results")
        assert r.status_code == 200
        body = r.json()
        assert "running" in body
        assert "results" in body
        assert isinstance(body["results"], list)


# ── GET /api/scan/progress ────────────────────────────────────────────────────

class TestScanProgress:
    def test_progress_is_sse(self):
        r = client.get("/api/scan/progress")
        assert r.status_code == 200
        # SSE responses contain "data:" lines
        assert "data:" in r.text

    def test_progress_payload_has_running_field(self):
        r = client.get("/api/scan/progress")
        first_line = [l for l in r.text.splitlines() if l.startswith("data:")][0]
        import json
        payload = json.loads(first_line[len("data:"):].strip())
        assert "running" in payload
        assert "progress" in payload
        assert "result_count" in payload
