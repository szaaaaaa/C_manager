"""Tests for the explainer module."""
import pytest
from src.analyzer.explainer import explain_path, _rule_based_explain


def test_rule_based_explain_known_path():
    result = _rule_based_explain("Windows")
    assert "Windows" in result or "系统" in result


def test_rule_based_explain_temp():
    result = _rule_based_explain("Temp")
    assert result  # non-empty
    assert "临时" in result or "清理" in result


def test_rule_based_explain_unknown():
    result = _rule_based_explain("XYZMysteryFolder123")
    assert result  # always returns something
    assert len(result) > 5


def test_explain_path_no_llm():
    # With use_llm=False, should always use rule-based
    result = explain_path("C:/Windows/Temp", "Temp", use_llm=False)
    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_path_system32_no_llm():
    result = explain_path("C:/Windows/System32", "System32", use_llm=False)
    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_path_node_modules_no_llm():
    result = explain_path("C:/Projects/myapp/node_modules", "node_modules", use_llm=False)
    assert "node" in result.lower() or "npm" in result.lower() or "依赖" in result


def test_explain_path_returns_string():
    result = explain_path("/some/path", "SomeFolder", use_llm=False)
    assert isinstance(result, str)
