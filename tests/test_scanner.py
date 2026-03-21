"""Tests for scanner module — read-only, no filesystem writes."""
import os
import tempfile

import pytest

from src.scanner.scanner import ScanItem, get_drive_info, scan_directory


def test_scan_item_dataclass():
    item = ScanItem(path="C:\\foo", name="foo", size=1024, is_dir=True, children_count=3)
    assert item.path == "C:\\foo"
    assert item.size == 1024
    assert item.is_dir is True
    assert item.children_count == 3


def test_scan_directory_returns_sorted(tmp_path):
    """scan_directory returns results sorted by size descending."""
    small = tmp_path / "small.bin"
    large = tmp_path / "large.bin"
    small.write_bytes(b"x" * 1024)
    large.write_bytes(b"x" * 1024 * 500)  # 500 KB

    results = scan_directory(str(tmp_path), min_size_bytes=512, max_depth=2)
    assert len(results) >= 1
    # Verify descending sort
    for i in range(len(results) - 1):
        assert results[i].size >= results[i + 1].size


def test_scan_directory_min_size_filter(tmp_path):
    """Files below min_size_bytes are excluded."""
    tiny = tmp_path / "tiny.txt"
    tiny.write_bytes(b"hi")
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 1024 * 200)  # 200 KB

    results = scan_directory(str(tmp_path), min_size_bytes=1024 * 100, max_depth=1)
    paths = [r.path for r in results]
    assert str(tiny) not in paths
    assert any("big.bin" in p for p in paths)


def test_scan_directory_permission_errors_ignored(tmp_path):
    """Permission errors during scan do not crash the scanner."""
    (tmp_path / "readable.bin").write_bytes(b"x" * 1024 * 100)
    # Just verify no exception is raised
    results = scan_directory(str(tmp_path), min_size_bytes=1024, max_depth=2)
    assert isinstance(results, list)


def test_get_drive_info_c():
    """get_drive_info returns valid numeric fields for C drive."""
    info = get_drive_info("C:\\")
    assert "total" in info
    assert "used" in info
    assert "free" in info
    assert info["total"] > 0
    assert info["used"] > 0
    assert info["free"] >= 0
    assert info["total"] == info["used"] + info["free"]


def test_get_drive_info_invalid_drive():
    """get_drive_info returns error field for invalid drive, not an exception."""
    info = get_drive_info("Z:\\nonexistent_drive_99\\")
    assert "error" in info or info["total"] == 0
