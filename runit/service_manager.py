import os
import re
import time
import shutil
import subprocess
import socket
from pathlib import Path

from runit.environment import has_docker, is_notebook_env
from runit.service_defs import SERVICE_DEFS, SERVICE_APT_MAP


class ServiceManager:
    def __init__(self, env_type: str = "local"):
        self.env_type = env_type
        self.running = {}
        self.project_path = None

    def set_project_path(self, path: str):
        self.project_path = path

    def install(self, name: str) -> dict:
        name = name.lower().strip()
        adjusted = SERVICE_APT_MAP.get(name, name)
        defs = SERVICE_DEFS.get(name) or SERVICE_DEFS.get(adjusted)
        if not defs:
            for key, val in SERVICE_APT_MAP.items():
                if val == adjusted:
                    defs = SERVICE_DEFS.get(key)
                    name = key
                    break
        if not defs:
            for key, sd in SERVICE_DEFS.items():
                if key in name or name in key:
                    defs = sd
                    name = key
                    break
        if not defs:
            return {"ok": False, "service": name, "error": f"Unknown service: {name}"}

        if self._check_alive(name, defs):
            url = self._make_url(defs)
            return {"ok": True, "service": name, "url": url, "message": f"{defs['name']} already running"}

        port = self._find_free_port(defs["port"])
        host = "localhost"

        if has_docker() and self.env_type == "local":
            result = self._start_via_docker(name, defs, port)
            if result["ok"]:
                self.running[name] = {"port": port, "defs": defs, "mode": "docker"}
                result["url"] = self._make_url(defs, host, port)
                return result

        if self.env_type in ("local", "kaggle", "colab"):
            if shutil.which("apt-get"):
                result = self._start_via_apt(name, defs, port)
                if result["ok"]:
                    self.running[name] = {"port": port, "defs": defs, "mode": "apt"}
                    result["url"] = self._make_url(defs, host, port)
                    return result

        if defs.get("binary_url"):
            result = self._start_via_binary(name, defs, port)
            if result["ok"]:
                self.running[name] = {"port": port, "defs": defs, "mode": "binary"}
                result["url"] = self._make_url(defs, host, port)
                return result

        if name == "redis":
            result = self._start_redislite(name, defs, port)
            if result["ok"]:
                self.running[name] = {"port": port, "defs": defs, "mode": "redislite"}
                result["url"] = self._make_url(defs, host, port)
                return result

        return {"ok": False, "service": name, "error": f"Could not install {defs['name']} (try Docker or install manually)"}

    def _start_via_docker(self, name: str, defs: dict, port: int) -> dict:
        container_name = f"runit_{name}"
        subprocess.run(["docker", "rm", "-f", container_name],
                       capture_output=True, timeout=15)

        env_flags = []
        for k, v in defs.get("docker_env", {}).items():
            env_flags += ["-e", f"{k}={v}"]

        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", container_name,
            "-p", f"{port}:{defs['port']}",
        ] + env_flags + [defs["docker_image"]]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return {"ok": False, "error": f"Docker: {result.stderr[:200]}"}
            for _ in range(15):
                if self._check_alive_port(defs, port):
                    return {"ok": True, "message": f"{defs['name']} started via Docker on port {port}"}
                time.sleep(1)
            return {"ok": False, "error": f"Docker {defs['name']} did not become ready"}
        except Exception as e:
            return {"ok": False, "error": f"Docker error: {e}"}

    def _start_via_apt(self, name: str, defs: dict, port: int) -> dict:
        apt_pkg = SERVICE_APT_MAP.get(name, name)
        try:
            subprocess.run(
                f"apt-get update -qq 2>/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {apt_pkg}",
                shell=True, capture_output=True, text=True, timeout=120,
            )
        except Exception:
            pass

        time.sleep(1)

        start_cmd = defs["start_cmd"].format(version="16", port=port)
        try:
            subprocess.run(start_cmd, shell=True, capture_output=True, text=True, timeout=30)
        except Exception:
            pass

        time.sleep(2)

        for cfg_cmd in defs.get("configure_cmds", []):
            try:
                subprocess.run(cfg_cmd, shell=True, capture_output=True, text=True, timeout=10)
            except Exception:
                pass

        for _ in range(10):
            if self._check_alive_port(defs, port):
                return {"ok": True, "message": f"{defs['name']} installed via apt on port {port}"}
            time.sleep(1)

        return {"ok": False, "error": f"apt-get {defs['name']} installed but not running"}

    def _start_via_binary(self, name: str, defs: dict, port: int) -> dict:
        binary_dir = Path(f"/tmp/runit_bin/{name}")
        binary_dir.mkdir(parents=True, exist_ok=True)
        binary_path = binary_dir / "bin"

        if name == "postgresql":
            return self._download_and_run_postgres(defs, port, binary_dir)

        return {"ok": False, "error": f"Binary install not available for {defs['name']}"}

    def _download_and_run_postgres(self, defs: dict, port: int, target_dir: Path) -> dict:
        url = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-linux-x64-binaries.tar.gz"
        tar_path = target_dir / "pg.tar.gz"
        pg_dir = target_dir / "pg"

        if not pg_dir.exists():
            try:
                subprocess.run(
                    f"curl -sL {url} -o {tar_path} && tar xzf {tar_path} -C {target_dir} && "
                    f"mv {target_dir}/pgsql {pg_dir} && rm {tar_path}",
                    shell=True, capture_output=True, text=True, timeout=120,
                )
            except Exception as e:
                return {"ok": False, "error": f"Download failed: {e}"}

        data_dir = target_dir / "data"
        logfile = target_dir / "logfile"

        if not (pg_dir / "bin" / "initdb").exists():
            return {"ok": False, "error": "PostgreSQL binary not found after download"}

        if not data_dir.exists():
            subprocess.run(
                f"{pg_dir}/bin/initdb -D {data_dir} --username=app --auth=trust 2>/dev/null",
                shell=True, capture_output=True, text=True, timeout=30,
            )

        subprocess.run(
            f"{pg_dir}/bin/pg_ctl -D {data_dir} -l {logfile} -o '-p {port} -k {target_dir}' start 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=15,
        )

        pg_sock = target_dir
        for _ in range(10):
            if self._port_open(port):
                try:
                    subprocess.run(
                        f"{pg_dir}/bin/createdb -h localhost -p {port} -U app app 2>/dev/null",
                        shell=True, capture_output=True, text=True, timeout=5,
                    )
                except Exception:
                    pass
                return {"ok": True, "message": f"PostgreSQL binary on port {port}"}
            time.sleep(1)
        return {"ok": False, "error": "PostgreSQL binary did not start"}

    def _start_redislite(self, name: str, defs: dict, port: int) -> dict:
        try:
            import redislite
            server = redislite.Redis(serverconfig={"port": str(port)})
            self.running[name + "_server"] = server
            return {"ok": True, "message": f"Redis via redislite on port {port}"}
        except ImportError:
            try:
                subprocess.run(["pip", "install", "redislite", "-q"],
                               capture_output=True, text=True, timeout=60)
                import redislite
                server = redislite.Redis(serverconfig={"port": str(port)})
                self.running[name + "_server"] = server
                return {"ok": True, "message": f"Redis via redislite on port {port}"}
            except Exception as e:
                return {"ok": False, "error": f"redislite failed: {e}"}

    def start(self, name: str) -> dict:
        if name in self.running:
            return {"ok": True, "service": name, "message": "Already running"}
        return self.install(name)

    def stop(self, name: str) -> dict:
        if name not in self.running:
            return {"ok": False, "error": f"{name} not running"}
        entry = self.running[name]

        if entry.get("mode") == "docker":
            subprocess.run(["docker", "rm", "-f", f"runit_{name}"],
                           capture_output=True, timeout=15)

        elif entry.get("mode") == "apt":
            defs = entry["defs"]
            stop_cmd = defs.get("stop_cmd", "").format(port=entry.get("port", defs["port"]))
            if stop_cmd:
                subprocess.run(stop_cmd, shell=True, capture_output=True, timeout=15)
            proc = subprocess.run(["pkill", "-f", name], capture_output=True, timeout=10)

        elif entry.get("mode") == "redislite":
            server_key = name + "_server"
            if server_key in self.running:
                server = self.running[server_key]
                try:
                    server.shutdown()
                except Exception:
                    pass
                del self.running[server_key]

        elif entry.get("mode") == "binary":
            proc = subprocess.run(["pkill", "-f", name], capture_output=True, timeout=10)

        del self.running[name]
        return {"ok": True, "message": f"{name} stopped"}

    def health(self, name: str) -> dict:
        entry = self.running.get(name)
        if not entry:
            return {"ok": False, "error": f"{name} not managed"}
        defs = entry["defs"]
        port = entry.get("port", defs["port"])
        alive = self._check_alive_port(defs, port)

        health_cmd = defs.get("health_cmd", [])
        healthy = False
        if health_cmd and alive:
            cmd = [c.format(port=port) for c in health_cmd]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                healthy = r.returncode == 0
            except Exception:
                healthy = False

        return {
            "ok": alive and healthy,
            "alive": alive,
            "healthy": healthy,
            "port": port,
            "url": self._make_url(defs, "localhost", port),
        }

    def stop_all(self):
        for name in list(self.running.keys()):
            if name.endswith("_server"):
                continue
            self.stop(name)

    def _check_alive(self, name: str, defs: dict) -> bool:
        port = defs["port"]
        if not self._port_open(port):
            return False
        health_cmd = defs.get("health_cmd", [])
        if not health_cmd:
            return True
        try:
            cmd = [c.format(port=port) for c in health_cmd]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _check_alive_port(self, defs: dict, port: int) -> bool:
        if not self._port_open(port):
            return False
        health_cmd = defs.get("health_cmd", [])
        if not health_cmd:
            return True
        try:
            cmd = [c.format(port=port) for c in health_cmd]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _port_open(self, port: int, host: str = "localhost") -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _find_free_port(self, preferred: int) -> int:
        for port in range(preferred, preferred + 50):
            if not self._port_open(port):
                return port
        return preferred

    def _make_url(self, defs: dict, host: str = "localhost", port: int | None = None) -> str:
        p = port or defs["port"]
        template = defs.get("connection_url", "")
        if self.project_path:
            template = template.replace("{project_path}", self.project_path)
        return template.format(host=host, port=p)


def service_name_from_env(var_name: str) -> str | None:
    lower = var_name.lower()
    for svc_name, defs in SERVICE_DEFS.items():
        for env_var in defs.get("env_vars", []):
            if lower == env_var.lower() or lower.startswith(env_var.lower().rstrip("s")) or env_var.lower() in lower:
                return svc_name
    return None
