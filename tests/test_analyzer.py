"""Tests for analyzer module — local safety rating logic only."""
import pytest

from src.analyzer.analyzer import format_size, rate_safety


# ─── format_size ────────────────────────────────────────────────────────────

def test_format_size_bytes():
    assert "B" in format_size(512)


def test_format_size_kb():
    assert "KB" in format_size(2048)


def test_format_size_mb():
    result = format_size(5 * 1024 * 1024)
    assert "MB" in result


def test_format_size_gb():
    result = format_size(2 * 1024 * 1024 * 1024)
    assert "GB" in result


# ─── rate_safety ─────────────────────────────────────────────────────────────

def test_rate_safety_system32_is_red():
    assert rate_safety("C:\\Windows\\System32") == "red"


def test_rate_safety_winsxs_is_red():
    assert rate_safety("C:\\Windows\\WinSxS") == "red"


def test_rate_safety_pagefile_is_red():
    assert rate_safety("C:\\pagefile.sys") == "red"


def test_rate_safety_temp_is_green():
    assert rate_safety("C:\\Users\\Alice\\AppData\\Local\\Temp") == "green"


def test_rate_safety_windows_temp_is_green():
    assert rate_safety("C:\\Windows\\Temp") == "green"


def test_rate_safety_downloads_is_green():
    assert rate_safety("C:\\Users\\Alice\\Downloads\\video.mp4") == "green"


def test_rate_safety_dmp_file_is_green():
    assert rate_safety("C:\\crash.dmp") == "green"


def test_rate_safety_program_files_is_yellow():
    assert rate_safety("C:\\Program Files\\MyApp") == "yellow"


def test_rate_safety_appdata_roaming_is_yellow():
    assert rate_safety("C:\\Users\\Alice\\AppData\\Roaming\\Slack") == "yellow"


def test_rate_safety_unknown_defaults_yellow():
    assert rate_safety("C:\\Users\\Alice\\SomeRandomFolder") == "yellow"


def test_rate_safety_case_insensitive():
    """Paths with different casing should still match rules."""
    assert rate_safety("C:\\WINDOWS\\SYSTEM32\\ntoskrnl.exe") == "red"
    assert rate_safety("C:\\users\\alice\\downloads\\file.zip") == "green"
