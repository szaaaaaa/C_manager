"""Tests for the safety rating module."""
import pytest
from src.analyzer.safety import rate_path


def test_system32_is_red():
    result = rate_path("C:/Windows/System32")
    assert result["rating"] == "red"
    assert result["reason"]


def test_syswow64_is_red():
    result = rate_path("C:/Windows/SysWOW64")
    assert result["rating"] == "red"


def test_winsxs_is_red():
    result = rate_path("C:/Windows/WinSxS")
    assert result["rating"] == "red"


def test_program_files_is_yellow():
    result = rate_path("C:/Program Files")
    assert result["rating"] == "yellow"


def test_program_files_x86_is_yellow():
    result = rate_path("C:/Program Files (x86)")
    assert result["rating"] == "yellow"


def test_temp_is_green():
    result = rate_path("C:/Windows/Temp")
    assert result["rating"] == "green"


def test_recycle_bin_is_green():
    result = rate_path("C:/$Recycle.Bin")
    assert result["rating"] == "green"


def test_unknown_path_is_yellow():
    result = rate_path("C:/SomeMysteryFolder/random")
    assert result["rating"] == "yellow"


def test_tmp_extension_is_green():
    result = rate_path("C:/SomePath/somefile.tmp")
    assert result["rating"] == "green"


def test_log_extension_is_green():
    result = rate_path("C:/SomePath/error.log")
    assert result["rating"] == "green"


def test_rate_path_returns_dict_with_keys():
    result = rate_path("C:/Windows")
    assert "rating" in result
    assert "reason" in result
    assert result["rating"] in ("red", "yellow", "green")


def test_windows_installer_is_yellow():
    result = rate_path("C:/Windows/Installer")
    assert result["rating"] == "yellow"


def test_software_distribution_is_yellow():
    result = rate_path("C:/Windows/SoftwareDistribution")
    assert result["rating"] == "yellow"
