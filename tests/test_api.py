"""
Unit tests for the FastAPI server.

Scanner calls use temp directories; LLM calls are mocked.
"""

import os
import sys
import tempfile
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Patch load_config before importing server so __init__ of FileAnalyzer
# doesn't try to open the real config file during module load.
FAKE_CONFIG = {
    "llm": {
        "provider": "openrouter",
        "model": "google/gemini-2.0-flash-001",
        "api_key": "test-key",
        "base_url": "https://openrouter.ai/api/v1",
    },
    "scanner": {
        "default_root": "C:\\",
        "min_size_mb": 50,
        "max_depth": 4,
    },
}

from src.api.server import app, _file_info_to_response
from src.analyzer.models import AnalysisResult
from src.analyzer.models import SafetyRating as AnalyzerRating
from src.scanner.models import FileInfo, SafetyRating as ScannerRating

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/config
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_returns_200(self):
        with mock.patch("src.api.server.load_config", return_value=FAKE_CONFIG):
            resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_response_structure(self):
        with mock.patch("src.api.server.load_config", return_value=FAKE_CONFIG):
            resp = client.get("/api/config")
        data = resp.json()
        assert data["llm_model"] == "google/gemini-2.0-flash-001"
        assert data["llm_provider"] == "openrouter"
        assert data["scanner_min_size_mb"] == 50.0
        assert data["scanner_max_depth"] == 4

    def test_api_key_not_exposed(self):
        with mock.patch("src.api.server.load_config", return_value=FAKE_CONFIG):
            resp = client.get("/api/config")
        body = resp.text
        assert "test-key" not in body


# ---------------------------------------------------------------------------
# POST /api/scan
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_tree(tmp_path):
    """Small temp tree: one 2 MB file + one 10 KB file."""
    MB = 1024 * 1024
    big = tmp_path / "big.tmp"
    big.write_bytes(b"x" * (2 * MB))
    small = tmp_path / "small.txt"
    small.write_bytes(b"y" * 10240)
    return tmp_path


class TestScan:
    def test_scan_returns_200(self, tmp_tree):
        resp = client.post(
            "/api/scan",
            json={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        assert resp.status_code == 200

    def test_scan_response_structure(self, tmp_tree):
        resp = client.post(
            "/api/scan",
            json={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        data = resp.json()
        assert "root" in data
        assert "total_items" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_scan_finds_big_file(self, tmp_tree):
        resp = client.post(
            "/api/scan",
            json={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        data = resp.json()
        paths = [item["path"] for item in data["items"]]
        assert str(tmp_tree / "big.tmp") in paths

    def test_scan_min_size_filter(self, tmp_tree):
        # Filter to 1 MB — small.txt (10 KB) should be excluded
        resp = client.post(
            "/api/scan",
            json={"root": str(tmp_tree), "min_size_mb": 1.0, "max_depth": 1},
        )
        data = resp.json()
        paths = [item["path"] for item in data["items"]]
        assert str(tmp_tree / "small.txt") not in paths

    def test_scan_item_fields(self, tmp_tree):
        resp = client.post(
            "/api/scan",
            json={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        data = resp.json()
        item = next(i for i in data["items"] if i["path"] == str(tmp_tree / "big.tmp"))
        assert item["is_dir"] is False
        assert item["extension"] == ".tmp"
        assert item["size_bytes"] == 2 * 1024 * 1024
        assert "safety_rating" in item
        assert "safety_reason" in item


# ---------------------------------------------------------------------------
# POST /api/explain
# ---------------------------------------------------------------------------

FAKE_RESULT = AnalysisResult(
    explanation="这是个临时文件，放心删",
    safety_rating=AnalyzerRating.SAFE,
    confidence=0.92,
    cached=False,
)


class TestExplain:
    def test_explain_returns_200(self):
        with mock.patch("src.api.server._get_analyzer") as mock_get:
            mock_analyzer = mock.MagicMock()
            mock_analyzer.explain.return_value = FAKE_RESULT
            mock_get.return_value = mock_analyzer

            resp = client.post(
                "/api/explain",
                json={
                    "path": r"C:\Windows\Temp\foo.tmp",
                    "size_bytes": 1024 * 1024,
                    "is_dir": False,
                    "parent_folder": r"C:\Windows\Temp",
                },
            )
        assert resp.status_code == 200

    def test_explain_response_fields(self):
        with mock.patch("src.api.server._get_analyzer") as mock_get:
            mock_analyzer = mock.MagicMock()
            mock_analyzer.explain.return_value = FAKE_RESULT
            mock_get.return_value = mock_analyzer

            resp = client.post(
                "/api/explain",
                json={
                    "path": r"C:\Windows\Temp\foo.tmp",
                    "size_bytes": 1024 * 1024,
                    "is_dir": False,
                },
            )
        data = resp.json()
        assert data["safety_rating"] == "safe"
        assert data["confidence"] == pytest.approx(0.92)
        assert data["cached"] is False
        assert "临时" in data["explanation"]

    def test_explain_llm_error_returns_502(self):
        with mock.patch("src.api.server._get_analyzer") as mock_get:
            mock_analyzer = mock.MagicMock()
            mock_analyzer.explain.side_effect = RuntimeError("LLM timeout")
            mock_get.return_value = mock_analyzer

            resp = client.post(
                "/api/explain",
                json={"path": r"C:\foo", "size_bytes": 0, "is_dir": False},
            )
        assert resp.status_code == 502

    def test_explain_cached_result(self):
        cached_result = AnalysisResult(
            explanation="缓存结果",
            safety_rating=AnalyzerRating.CAUTION,
            confidence=0.7,
            cached=True,
        )
        with mock.patch("src.api.server._get_analyzer") as mock_get:
            mock_analyzer = mock.MagicMock()
            mock_analyzer.explain.return_value = cached_result
            mock_get.return_value = mock_analyzer

            resp = client.post(
                "/api/explain",
                json={"path": r"C:\foo", "size_bytes": 0, "is_dir": True},
            )
        assert resp.json()["cached"] is True


# ---------------------------------------------------------------------------
# GET /api/scan/progress (SSE)
# ---------------------------------------------------------------------------

class TestScanProgress:
    def test_progress_returns_event_stream(self, tmp_tree):
        resp = client.get(
            "/api/scan/progress",
            params={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_progress_contains_done_event(self, tmp_tree):
        resp = client.get(
            "/api/scan/progress",
            params={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        body = resp.text
        assert '"done": true' in body or '"done":true' in body

    def test_progress_streams_items(self, tmp_tree):
        resp = client.get(
            "/api/scan/progress",
            params={"root": str(tmp_tree), "min_size_mb": 0.0, "max_depth": 1},
        )
        # Each SSE event is "data: {...}\n\n"
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        assert len(lines) >= 1


# ---------------------------------------------------------------------------
# _file_info_to_response helper
# ---------------------------------------------------------------------------

class TestFileInfoToResponse:
    def test_converts_correctly(self):
        info = FileInfo(
            path=r"C:\foo\bar.tmp",
            size_bytes=1024 * 1024,
            is_dir=False,
            last_modified=0.0,
            extension=".tmp",
            safety_rating=ScannerRating.SAFE,
            safety_reason="临时文件",
        )
        resp = _file_info_to_response(info)
        assert resp.path == r"C:\foo\bar.tmp"
        assert resp.size_mb == pytest.approx(1.0, abs=0.001)
        assert resp.safety_rating == "safe"
        assert resp.safety_reason == "临时文件"
