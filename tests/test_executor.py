import tempfile
from pathlib import Path
from unittest.mock import patch

from runit.executor import (
    _find_entry, _run, run_docker,
    _detect_docker_ports,
)


def test_find_entry_found():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "main.py").write_text("print('hello')")
        result = _find_entry(tmp, "main.py")
        assert result == "main.py"


def test_find_entry_in_src():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "src").mkdir()
        (Path(tmp) / "src" / "main.py").write_text("print('hello')")
        result = _find_entry(tmp, "main.py")
        assert result == "src/main.py"


def test_find_entry_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        result = _find_entry(tmp, "nonexistent.py")
        assert result is None


def test_run_command_not_found():
    result = _run(["nonexistent_command_xyz"], cwd="/")
    assert result.returncode == 127


def test_run_timeout():
    result = _run(["sleep", "10"], cwd="/", timeout=1)
    assert result.returncode == 124


def test_detect_docker_ports_no_docker_files():
    with tempfile.TemporaryDirectory() as tmp:
        ports = _detect_docker_ports(tmp)
        assert ports == []


def test_detect_docker_ports_from_dockerfile():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Dockerfile").write_text("""
FROM python:3.11
EXPOSE 8080
EXPOSE 3000
CMD ["python", "app.py"]
""")
        ports = _detect_docker_ports(tmp)
        assert "8080:8080" in ports
        assert "3000:3000" in ports


def test_docker_not_installed():
    with patch("shutil.which", return_value=None):
        result = run_docker("some/image")
        assert result.returncode == 1
        assert "docker not found" in result.stderr
