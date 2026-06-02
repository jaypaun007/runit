import os
import re
import time
import signal
import subprocess
import threading
from pathlib import Path


class ProcessMonitor:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.processes = {}
        self.log_dir = Path(project_path) / ".runit"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start(self, cmd: str, env: dict | None = None, cwd: str | None = None,
              timeout: int = 300, background: bool = True) -> dict:
        workdir = cwd or self.project_path
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        logfile = self.log_dir / "app.log"
        log_path = str(logfile)

        if background:
            with open(log_path, "w") as f:
                proc = subprocess.Popen(
                    cmd, shell=True, stdout=f, stderr=subprocess.STDOUT,
                    cwd=workdir, env=merged_env, preexec_fn=os.setsid,
                )
            self.processes[proc.pid] = {
                "proc": proc,
                "cmd": cmd,
                "cwd": workdir,
                "logfile": log_path,
                "started": time.time(),
                "timeout": timeout,
            }

            self._detect_ports(proc.pid)

            result = {
                "ok": True,
                "pid": proc.pid,
                "background": True,
                "logfile": log_path,
            }
            if proc.pid in self.processes and "ports" in self.processes[proc.pid]:
                result["ports"] = self.processes[proc.pid]["ports"]
            return result
        else:
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    cwd=workdir, env=merged_env, timeout=timeout,
                )
                return {
                    "ok": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-3000:],
                    "stderr": result.stderr[-3000:],
                    "background": False,
                }
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": f"Command timed out ({timeout}s)", "background": False}

    def _detect_ports(self, pid: int) -> list[int]:
        try:
            result = subprocess.run(
                ["ss", "-tlnp", f"pid={pid}"],
                capture_output=True, text=True, timeout=5,
            )
            ports = re.findall(r":(\d+)", result.stdout)
            self.processes[pid]["ports"] = [int(p) for p in ports if p.isdigit()]
            return self.processes[pid]["ports"]
        except Exception:
            self.processes[pid]["ports"] = []
            return []

    def poll_ports(self, pid: int, known_ports: list[int] | None = None,
                   timeout: int = 30) -> dict:
        if pid not in self.processes:
            return {"ok": False, "error": "Process not found"}

        if known_ports:
            for port in known_ports:
                for _ in range(timeout):
                    if self._port_open(port):
                        self.processes[pid].setdefault("ports", []).append(port)
                        return {"ok": True, "port": port, "url": f"http://localhost:{port}"}
                    time.sleep(1)
            return {"ok": False, "error": f"No port opened within {timeout}s"}

        for _ in range(timeout):
            ports = self._detect_ports(pid)
            if ports:
                return {"ok": True, "ports": ports, "url": f"http://localhost:{ports[0]}"}
            time.sleep(1)
        return {"ok": False, "error": f"No ports detected within {timeout}s"}

    def _port_open(self, port: int, host: str = "localhost") -> bool:
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def stop(self, pid: int, force: bool = False) -> bool:
        if pid not in self.processes:
            return False
        try:
            proc = self.processes[pid]["proc"]
            if force:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                for _ in range(10):
                    if not self.is_running(pid):
                        break
                    time.sleep(0.5)
                else:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
            del self.processes[pid]
            return True
        except Exception:
            return False

    def read_log(self, pid: int, tail: int = 50) -> str:
        logfile = self.processes.get(pid, {}).get("logfile", "")
        if not logfile:
            return ""
        try:
            lines = Path(logfile).read_text().splitlines()
            return "\n".join(lines[-tail:])
        except Exception:
            return ""

    def stop_all(self):
        for pid in list(self.processes.keys()):
            self.stop(pid, force=True)

    def detect_server_url(self, cmd: str, env: dict | None = None) -> dict:
        pid_result = self.start(cmd, env=env, background=True)
        if not pid_result.get("ok"):
            return pid_result

        pid = pid_result["pid"]

        known_patterns = [
            (r"http://localhost:(\d+)", None),
            (r"listening on (?:port )?(\d+)", None),
            (r"Server running at http://localhost:(\d+)", None),
            (r"port (\d+)", None),
        ]

        detected_ports = set()
        for _ in range(30):
            log = self.read_log(pid)
            for pattern, _ in known_patterns:
                match = re.search(pattern, log, re.IGNORECASE)
                if match:
                    port = int(match.group(1))
                    detected_ports.add(port)
            pids = self._detect_ports(pid)
            if pids and detected_ports:
                break
            time.sleep(1)

        if detected_ports:
            port = list(detected_ports)[0]
            return {
                "ok": True,
                "pid": pid,
                "port": port,
                "url": f"http://localhost:{port}",
                "logfile": pid_result.get("logfile", ""),
                "detected_ports": list(detected_ports),
            }

        port_result = self.poll_ports(pid, timeout=20)
        if port_result.get("ok"):
            port_result["pid"] = pid
            port_result["logfile"] = pid_result.get("logfile", "")
            return port_result

        return {
            "ok": True,
            "pid": pid,
            "port": None,
            "url": None,
            "logfile": pid_result.get("logfile", ""),
            "note": "Process running but no port detected",
        }
