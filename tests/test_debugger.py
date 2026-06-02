import tempfile
from pathlib import Path

from runit.debugger import (
    _detect_error_category, _detect_language_from_error,
    _extract_syntax_errors, _extract_module_error,
    _check_project_files, _suggest_code_patch,
    deep_debug,
)


def test_detect_error_category_missing_api_key():
    assert _detect_error_category("API_KEY is missing") == "missing_api_key"
    assert _detect_error_category("Authentication failed") == "missing_api_key"
    assert _detect_error_category("401 Unauthorized") == "missing_api_key"


def test_detect_error_category_port():
    assert _detect_error_category("Address already in use") == "port_conflict"
    assert _detect_error_category("EADDRINUSE") == "port_conflict"


def test_detect_error_category_disk():
    assert _detect_error_category("No space left on device") == "disk_space"
    assert _detect_error_category("ENOSPC") == "disk_space"


def test_detect_error_category_network():
    assert _detect_error_category("Connection refused") == "network"
    assert _detect_error_category("ECONNREFUSED") == "network"


def test_detect_error_category_permission():
    assert _detect_error_category("Permission denied") == "permission"
    assert _detect_error_category("EACCES") == "permission"


def test_detect_error_category_none():
    assert _detect_error_category("everything is fine") is None


def test_detect_language_from_error_python():
    lang = _detect_language_from_error("ModuleNotFoundError: No module named 'flask'")
    assert lang == "python"


def test_detect_language_from_error_node():
    lang = _detect_language_from_error("Error: Cannot find module 'express'")
    assert lang == "node"


def test_detect_language_from_error_rust():
    lang = _detect_language_from_error("error[E0308]: mismatched types")
    assert lang == "rust"


def test_detect_language_from_error_none():
    assert _detect_language_from_error("random message") is None


def test_extract_syntax_errors_python():
    log = "ModuleNotFoundError: No module named 'flask'\nSyntaxError: invalid syntax"
    errors = _extract_syntax_errors(log, "python")
    assert len(errors) >= 1


def test_extract_module_error_python():
    result = _extract_module_error("ModuleNotFoundError: No module named 'flask'")
    assert result is not None
    assert result["module"] == "flask"
    assert result["language"] == "python"


def test_extract_module_error_node():
    result = _extract_module_error("Error: Cannot find module 'express'")
    assert result is not None
    assert result["module"] == "express"
    assert result["language"] == "node"


def test_extract_module_error_ruby():
    result = _extract_module_error("cannot load such file -- sinatra")
    assert result is not None
    assert result["language"] == "ruby"


def test_extract_module_error_none():
    assert _extract_module_error("everything is fine") is None


def test_check_project_files_env():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".env.example").write_text("API_KEY=\n")
        issues = _check_project_files(tmp, "Error: environment variable not set")
        assert any("env.example" in i.lower() for i in issues)


def test_suggest_code_patch_port():
    patch = _suggest_code_patch("Error: port 3000 in use", "/tmp", {})
    assert patch is not None
    assert "3000" in patch or "3001" in patch


def test_suggest_code_patch_no_match():
    patch = _suggest_code_patch("everything is fine", "/tmp", {})
    assert patch is None


def test_deep_debug_module_not_found():
    result = deep_debug("ModuleNotFoundError: No module named 'flask'", {"type": "python"}, "/tmp")
    assert result["fix_type"] == "install_module"
    assert result["target"] == "flask"
    assert result["confidence"] == 0.9


def test_deep_debug_port_conflict():
    result = deep_debug("Error: listen EADDRINUSE: address already in use :::3000",
                        {"type": "node"}, "/tmp")
    assert result["category"] == "port_conflict"


def test_deep_debug_missing_key():
    result = deep_debug("API key is missing. Please set OPENAI_API_KEY",
                        {"type": "python"}, "/tmp")
    assert result["category"] == "missing_api_key"
    assert result["confidence"] > 0


def test_deep_debug_unknown():
    result = deep_debug("random gibberish that means nothing", {"type": "python"}, "/tmp")
    assert result["explanation"] is not None
