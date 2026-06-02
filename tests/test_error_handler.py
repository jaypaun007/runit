import tempfile
from pathlib import Path

from runit.error_handler import (
    _extract_missing_modules, _detect_missing_key, _detect_port_conflict,
    _extract_missing_env_vars, _extract_port_from_error,
    fix_error, apply_fix,
)


def test_extract_missing_modules_python():
    log = "ModuleNotFoundError: No module named 'flask'"
    modules = _extract_missing_modules(log)
    assert "flask" in modules


def test_extract_missing_modules_js():
    log = "Error: Cannot find module 'express'"
    modules = _extract_missing_modules(log)
    assert "express" in modules


def test_extract_missing_modules_none():
    assert _extract_missing_modules("everything is fine") == []


def test_detect_missing_key():
    assert _detect_missing_key("API_KEY is missing") is not None
    assert _detect_missing_key("token required for access") is not None
    assert _detect_missing_key("everything is fine") is None


def test_detect_port_conflict():
    assert _detect_port_conflict("Address already in use") is True
    assert _detect_port_conflict("EADDRINUSE") is True
    assert _detect_port_conflict("everything is fine") is False


def test_extract_missing_env_vars():
    known = ["API_KEY", "DATABASE_URL"]
    log = "Error: API_KEY environment variable not set"
    missing = _extract_missing_env_vars(log, known)
    assert "API_KEY" in missing


def test_extract_port_from_error():
    assert _extract_port_from_error("port 3000 in use") == "3000"
    assert _extract_port_from_error("8000 occupied") == "8000"
    assert _extract_port_from_error("nothing here") is None


def test_apply_fix_install_module():
    plan = {"type": "python"}
    fix = {"fix_type": "install_module", "target": "requests", "explanation": "Missing requests"}
    with tempfile.TemporaryDirectory() as tmp:
        result = apply_fix(fix, plan, tmp)
        assert result["applied"] is True
        assert "requests" in plan.get("_installed_modules", [])


def test_apply_fix_change_entry():
    plan = {"type": "python", "entry": "main.py", "fallbacks": []}
    fix = {"fix_type": "change_entry", "target": "app.py", "value": "app.py", "explanation": "Wrong entry"}
    with tempfile.TemporaryDirectory() as tmp:
        result = apply_fix(fix, plan, tmp)
        assert result["applied"] is True
        assert plan["entry"] == "app.py"


def test_apply_fix_change_port():
    plan = {"type": "python"}
    fix = {"fix_type": "change_port", "target": "8000", "value": "8001", "explanation": "Port in use"}
    with tempfile.TemporaryDirectory() as tmp:
        result = apply_fix(fix, plan, tmp)
        assert result["applied"] is True


def test_apply_fix_need_api_key():
    plan = {"type": "python"}
    fix = {"fix_type": "need_api_key", "target": "API_KEY", "explanation": "Missing API key"}
    with tempfile.TemporaryDirectory() as tmp:
        result = apply_fix(fix, plan, tmp)
        assert result["applied"] is True
        assert result["ask_user"] is True
