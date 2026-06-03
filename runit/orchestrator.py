import os
import json
import re
import time
import socket
import shutil
import ast
import urllib.parse
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from runit.cli import _console, print_step, AUTO_YES
from runit.service_manager import ServiceManager, service_name_from_env
from runit.service_defs import SERVICE_DEFS
from runit.env_resolver import EnvResolver, is_critical
from runit.process_monitor import ProcessMonitor
from runit.config import load_config
from runit.skills import detect_package_manager
from runit.environment import is_notebook_env


class Pipeline:
    def __init__(self, project_path: str, env_type: str = "local",
                 auto_yes: bool = False, max_retries: int = 10):
        self.project_path = project_path
        self.env_type = env_type
        self.auto_yes = auto_yes
        self.max_retries = max_retries
        self.c = _console()
        self.project_name = Path(project_path).name
        self.sm = ServiceManager(env_type=env_type)
        self.sm.set_project_path(project_path)
        self.pm = ProcessMonitor(project_path)
        self.er = EnvResolver(project_path, self.sm)
        self.project_type = "python"
        self.package_manager = "npm"
        self.required_services = []
        self.env_vars = {}
        self.tunnel_urls = {}

    def run(self) -> dict:
        if self.c:
            self.c.print(f"\n  [bold]Runit v2.1.2 — Pipeline[/]")
            self.c.print(f"  [dim]Project: {self.project_name}  |  Path: {self.project_path}[/]")
            self.c.print()

        print_step(1, 4, "Analyzing project structure...")
        self._analyze()

        print_step(2, 4, "Setting up services...")
        self._setup_services()

        print_step(3, 4, "Resolving environment variables...")
        self._resolve_env()

        print_step(4, 4, "Running with AI agent...")
        result = self._agent_run()

        if result.get("ok"):
            self._tunnel_all_ports(result)
            self._start_dashboard_server()
            self._dashboard(result)
            return {"status": "success", "result": result}

        self._print_failure(result)
        return {"status": "failed", "result": result}

    def _analyze(self):
        root = Path(self.project_path)
        readme = root / "README.md"
        if readme.exists():
            print(f"  \U0001f4d6  README found ({readme.stat().st_size} bytes)")

        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                scripts = pkg.get("scripts", {})
                print(f"  \U0001f4e6  Node.js project detected")
                self.project_type = "node"
                if [s for s in ["dev", "start", "serve"] if s in scripts]:
                    print(f"  \U0001f527  Scripts: {', '.join(s for s in ['dev', 'start', 'serve'] if s in scripts)}")
            except Exception:
                pass

        req_txt = root / "requirements.txt"
        if req_txt.exists():
            self.project_type = "python"
            print(f"  \U0001f4e6  Python project detected")
            content = req_txt.read_text().lower()
            req_svc_map = {
                "psycopg2": "postgresql", "asyncpg": "postgresql",
                "redis": "redis", "aioredis": "redis",
                "mysqlclient": "mysql", "pymysql": "mysql",
                "pymongo": "mongodb", "motor": "mongodb",
                "elasticsearch": "elasticsearch",
                "clickhouse": "clickhouse",
                "neo4j": "neo4j",
            }
            for pkg, svc in req_svc_map.items():
                if pkg in content and svc not in self.required_services:
                    self.required_services.append(svc)
                    print(f"  \U0001f6e0  Service detected from requirements: {svc}")

        env_example = root / ".env.example"
        if env_example.exists():
            count = sum(1 for line in env_example.read_text().splitlines()
                       if "=" in line and not line.strip().startswith("#"))
            print(f"  \U0001f511  .env.example found ({count} vars)")

        docker_compose = root / "docker-compose.yml"
        if docker_compose.exists():
            content = docker_compose.read_text().lower()
            for svc_name in SERVICE_DEFS:
                if svc_name in content:
                    self.required_services.append(svc_name)
                    print(f"  \U0001f6e0  Required service detected: {svc_name}")

        self.package_manager = detect_package_manager(self.project_path) or "npm"
        if self.package_manager != "npm":
            print(f"  \U0001f4e6  Package manager: {self.package_manager}")

        self._detect_services_from_env()

    def _detect_services_from_env(self):
        env_path = Path(self.project_path) / ".env.example"
        if not env_path.exists():
            return
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                svc = service_name_from_env(key)
                if svc and svc not in self.required_services:
                    self.required_services.append(svc)
                    print(f"  \U0001f6e0  Service detected from env: {svc}")

    def _setup_services(self):
        if not self.required_services:
            print("  \u2705  No services required")
            return

        for svc in self.required_services:
            print(f"  \U0001f6e0  Setting up {svc}...")
            result = self.sm.install(svc)
            if result.get("ok"):
                url = result.get("url", "")
                creds = result.get("credentials", "")
                label = f"{url}  {creds}" if creds else url
                print(f"    \u2705  {svc}: {label}")
                self._tunnel_service_port(svc)
            else:
                print(f"    \u26a0\ufe0f  {result.get('error', 'failed')}")

    def _tunnel_service_port(self, svc_name):
        entry = self.sm.running.get(svc_name)
        if not entry:
            return
        port = entry.get("port", entry["defs"]["port"])
        url = self._start_cloudflare_tunnel(port)
        if url:
            self.tunnel_urls[svc_name] = url
            print(f"    \U0001f310  Public: {url}")

    def _resolve_env(self):
        env_path = Path(self.project_path) / ".env.example"
        if not env_path.exists():
            print("  \u2705  No .env.example found")
            return

        self.env_vars = self._resolve_env_pass()

        all_vars = []
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                all_vars.append(key)

        if not all_vars:
            print("    \u2705  No vars to resolve")
            return

        env_file = Path(self.project_path) / ".env"
        env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")
        print(f"    \u2705  Written {len(self.env_vars)} vars to .env")

        if is_notebook_env():
            self._env_web_ui(all_vars)
            env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")
        elif not self.auto_yes:
            critical_missing = [v for v in all_vars if is_critical(v) and not self.env_vars.get(v)]
            for var in critical_missing:
                try:
                    val = input(f"  \U0001f511  Enter {var}: ")
                    if val.strip():
                        self.env_vars[var] = val.strip()
                except (EOFError, KeyboardInterrupt):
                    pass
            env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")


    def _env_web_ui(self, var_names):
        result_file = Path(self.project_path) / ".runit" / "env_ui_result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        if result_file.exists():
            result_file.unlink()

        submitted = {}

        class EnvUIHandler(BaseHTTPRequestHandler):
            def do_GET(self_):
                self_.send_response(200)
                self_.send_header("Content-Type", "text/html; charset=utf-8")
                self_.end_headers()
                self_.wfile.write(self_._form_html().encode())

            def _form_html(self_):
                rows = []
                for v in var_names:
                    current = self.env_vars.get(v, "")
                    val_attr = f' value="{current}"' if current else ""
                    rows.append(f"""
        <div class="field">
          <label for="{v}">{v}</label>
          <input id="{v}" name="{v}" type="text"{val_attr}>
        </div>""")
                return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runit - Set Environment Variables</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font:16px/1.5 system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}}
  .card{{background:#1e293b;padding:2rem;border-radius:12px;width:90%;max-width:520px}}
  h1{{font-size:1.3rem;margin-bottom:.25rem}}
  p{{color:#94a3b8;margin-bottom:1.5rem;font-size:.9rem}}
  .field{{margin-bottom:1rem}}
  label{{display:block;font-size:.8rem;font-weight:600;color:#94a3b8;margin-bottom:.3rem;word-break:break-all}}
  input{{width:100%;padding:.6rem .8rem;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:.9rem;outline:none;transition:border-color .15s}}
  input:focus{{border-color:#6366f1}}
  button{{width:100%;padding:.7rem;background:#6366f1;border:none;border-radius:8px;color:#fff;font-size:.95rem;font-weight:600;cursor:pointer;margin-top:.5rem}}
  button:hover{{background:#4f46e5}}
  .small{{font-size:.75rem;color:#64748b;text-align:center;margin-top:1rem}}
</style>
</head>
<body>
<div class="card">
  <h1>⚡ Runit — Environment Variables</h1>
  <p>Fill the <strong>{len(var_names)}</strong> required variables, then click Save.</p>
  <form method="POST" action="/">{"".join(rows)}
    <button type="submit">Save &amp; Continue</button>
  </form>
  <div class="small">Values already set are pre-filled. Edit or leave as-is.</div>
</div>
</body>
</html>"""

            def do_POST(self_):
                length = int(self_.headers.get("Content-Length", 0))
                body = self_.rfile.read(length).decode()
                parsed = urllib.parse.parse_qs(body)
                for var in var_names:
                    vals = parsed.get(var, [])
                    if vals and vals[0].strip():
                        self.env_vars[var] = vals[0].strip()
                result_file.write_text(json.dumps(self.env_vars))
                self_.send_response(200)
                self_.send_header("Content-Type", "text/html; charset=utf-8")
                self_.end_headers()
                self_.wfile.write(b"<h2>Saved!</h2><script>window.close()</script>")

            def log_message(self_, *a):
                pass

        port = self._find_free_port(8000)
        server = HTTPServer(("0.0.0.0", port), EnvUIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        public_url = self._start_cloudflare_tunnel(port)
        if public_url:
            print(f"    \U0001f310  Open: {public_url}")
        else:
            print(f"    \U0001f5a5  Local: http://localhost:{port}")
        print("    \u23f3  Waiting for env vars — click Save when done (or press Ctrl+C to skip)...")

        try:
            while True:
                if result_file.exists():
                    try:
                        submitted = json.loads(result_file.read_text())
                        self.env_vars.update(submitted)
                        break
                    except Exception:
                        pass
                time.sleep(1)
        except KeyboardInterrupt:
            print("    \u23f3  Skipped env UI, continuing...")

        server.shutdown()

    def _resolve_env_pass(self):
        result = {}
        existing = Path(self.project_path) / ".env"
        if existing.exists():
            for line in existing.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip().strip("\"'")
        for k in list(result.keys()):
            if k in os.environ:
                result[k] = os.environ[k]
        return result

    def _agent_run(self) -> dict:
        cfg = load_config()
        api_key = cfg.get("api_key")

        self.env_vars = self._resolve_env_pass()
        if self.env_vars:
            env_file = Path(self.project_path) / ".env"
            env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")

        project_files = self._read_key_files()
        suggested_cmd = self._suggest_run_command(project_files)

        result = self._deterministic_run(project_files, suggested_cmd)
        if result.get("ok"):
            self._generate_restart_script(result, suggested_cmd)
            return result

        if api_key:
            err = result.get("error", "")
            logfile = result.get("logfile", "")
            result = self._ai_fix_run(err, logfile, project_files, suggested_cmd)
            if result.get("ok"):
                self._generate_restart_script(result, suggested_cmd)
                return result

        return {"ok": False, "error": "Could not run project"}

    def _print_cmd(self, cmd: str):
        print(f"  \U0001f4bb  ! {cmd}")

    def _run_cmd(self, cmd: str, cwd: str | None = None, timeout: int = 180) -> dict:
        self._print_cmd(cmd)
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=cwd or self.project_path, timeout=timeout,
            )
            out = (r.stdout or "")[:3000]
            err = (r.stderr or "")[:1000]
            if out.strip():
                print(f"{out}")
            if err.strip():
                print(f"  [stderr] {err}")
            if r.returncode != 0:
                print(f"  \u274c  exit code {r.returncode}")
            return {"ok": r.returncode == 0, "output": out, "error": err, "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Timed out ({timeout}s)"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _clean_requirements(self) -> str | None:
        req_path = Path(self.project_path) / "requirements.txt"
        if not req_path.exists():
            return None
        bad_names = {"install", "setup", "test", "nose", "wheel", "setuptools", "pip"}
        lines = []
        for line in req_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r'[=<>~!\[\];]', line)[0].strip()
            name_lower = name.lower()
            if name_lower in bad_names:
                print(f"    \u26a0\ufe0f  Skipping bad pkg: {name}")
                continue
            if name_lower == "psycopg2":
                line = "psycopg2-binary" + (line[len(name):] if len(line) > len(name) else "")
                print(f"    \u26a0\ufe0f  Replacing psycopg2 with psycopg2-binary")
            if line not in lines:
                lines.append(line)
        cleaned = "\n".join(lines) + "\n"
        req_path.write_text(cleaned)
        return cleaned

    def _detect_imports(self) -> list[str]:
        KNOWN_THIRD_PARTY = {
            "fastapi", "uvicorn", "flask", "django", "sqlalchemy", "psycopg2",
            "psycopg2-binary", "asyncpg", "alembic", "pydantic", "pydantic-settings",
            "python-dotenv", "python-multipart", "httptools", "httpx", "requests",
            "aiohttp", "aiofiles", "PIL", "Pillow", "numpy", "pandas", "scipy",
            "matplotlib", "seaborn", "scikit-learn", "torch", "tensorflow",
            "transformers", "tokenizers", "redis", "pymongo", "motor", "celery",
            "rabbitmq", "kombu", "boto3", "botocore", "s3fs", "gcsfs", "fsspec",
            "bcrypt", "cryptography", "jwt", "PyJWT", "python-jose", "passlib",
            "email-validator", "dnspython", "python-multipart", "orjson",
            "ujson", "python-dotenv", "sentry-sdk", "opentelemetry", "prometheus-client",
            "click", "typer", "rich", "colorama", "tqdm", "loguru", "structlog",
            "pytest", "coverage", "mypy", "black", "ruff", "isort", "flake8",
            "python-dateutil", "pytz", "tzdata", "pyyaml", "toml", "tomli",
            "watchfiles", "websockets", "starlette", "anyio", "h11", "idna",
            "certifi", "chardet", "charset-normalizer", "urllib3", "cffi",
            "ecdsa", "greenlet", "sniffio", "typing-extensions", "typing-inspect",
            "annotated-types", "pydantic-core", "multipart",
        }
        detected = set()
        py_files = list(Path(self.project_path).rglob("*.py"))
        py_files = [f for f in py_files if "site-packages" not in str(f)
                     and ".runit" not in str(f)]
        for f in py_files:
            try:
                tree = ast.parse(f.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.name.split(".")[0]
                            if name.lower() in KNOWN_THIRD_PARTY:
                                detected.add(name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            name = node.module.split(".")[0]
                            if name.lower() in KNOWN_THIRD_PARTY:
                                detected.add(name)
            except Exception:
                pass
        return sorted(detected)

    def _install_deps(self, files: dict) -> bool:
        if self.project_type == "node":
            r = self._run_cmd(
                f"{self.package_manager} install --no-optional --legacy-peer-deps",
                timeout=300,
            )
            return r.get("ok")

        self._run_cmd(
            "pip install --upgrade pip setuptools wheel -q --no-build-isolation"
            " 2>/dev/null || "
            "pip install --upgrade pip setuptools wheel -q --break-system-packages"
            " 2>/dev/null || true",
            timeout=120,
        )

        req_path = Path(self.project_path) / "requirements.txt"
        if req_path.exists():
            self._clean_requirements()
            print(f"  \U0001f4e6  Installing dependencies...")
            r = self._run_cmd(
                "pip install --no-build-isolation -r requirements.txt -q",
                timeout=300,
            )
            if r.get("ok"):
                self._run_cmd(
                    "pip install -q 'pydantic>=1.9.0,<2' 2>/dev/null"
                    " || pip install -q --break-system-packages 'pydantic>=1.9.0,<2'",
                    timeout=120,
                )
                return True
            print(f"  \u26a0\ufe0f  Batch install failed — trying import-based install...")

        imports = self._detect_imports()
        if not imports:
            imports = ["fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary",
                       "python-dotenv", "alembic", "pydantic", "requests", "flask"]
        print(f"  \U0001f50d  Installing {len(imports)} detected packages...")
        r = self._run_cmd(f"pip install -q --no-build-isolation {' '.join(imports)}", timeout=300)
        if r.get("ok"):
            self._run_cmd(
                "pip install -q 'pydantic>=1.9.0,<2' 2>/dev/null"
                " || pip install -q --break-system-packages 'pydantic>=1.9.0,<2'",
                timeout=120,
            )
            return True

        print(f"  \u26a0\ufe0f  Group install failed — trying individually...")
        for pkg in imports:
            self._run_cmd(f"pip install -q --no-build-isolation {pkg}", timeout=120)
        return True

    def _deterministic_run(self, files: dict, suggested_cmd: str) -> dict:
        self._install_deps(files)

        run_cmd = suggested_cmd or self._detect_run_cmd(files)
        if run_cmd:
            print(f"  \U000025b6  Starting project...")
            result = self._run_project_in_background(run_cmd)
            return result

        return {"ok": False, "error": "No run command detected"}

    def _detect_run_cmd(self, files: dict) -> str | None:
        app_main = files.get("app/main.py", "")
        if "FastAPI" in app_main or "fastapi" in app_main.lower():
            return "uvicorn app.main:app --host 0.0.0.0 --port 8000"
        main_py = files.get("main.py", "")
        if "FastAPI" in main_py or "fastapi" in main_py.lower():
            return "uvicorn main:app --host 0.0.0.0 --port 8000"
        app_py = files.get("app.py", "")
        if "FastAPI" in app_py or "fastapi" in app_py.lower():
            return "uvicorn app:app --host 0.0.0.0 --port 8000"
        for f, content in files.items():
            if f in ("manage.py",):
                return f"python {f} runserver 0.0.0.0:8000"
            if ".py" in f and "flask" in content.lower():
                return f"python {f}"
        return None

    def _run_project_in_background(self, cmd: str) -> dict:
        self._print_cmd(cmd)
        port = self._detect_port_from_cmd(cmd)
        if port:
            self._kill_port(port)

        env = os.environ.copy()
        env.update(self.env_vars)
        log_dir = Path(self.project_path) / ".runit"
        log_dir.mkdir(parents=True, exist_ok=True)
        logfile = log_dir / "app.log"
        log_path = str(logfile)

        try:
            with open(log_path, "w") as f:
                proc = subprocess.Popen(
                    cmd, shell=True, stdout=f, stderr=subprocess.STDOUT,
                    cwd=self.project_path, env=env,
                    preexec_fn=os.setsid,
                )
            self.pm.add_process("app", proc)

            for _ in range(10):
                if proc.poll() is not None:
                    return self._process_crashed(log_path)
                if port and self._port_open(port):
                    print(f"    \u2705  Running on port {port}")
                    return {"ok": True, "pid": proc.pid, "port": port,
                            "url": f"http://localhost:{port}", "logfile": log_path}
                time.sleep(0.5)

            if not port:
                port = self._scan_for_port(proc.pid)

            if port:
                print(f"    \u2705  Running on port {port}")
                return {"ok": True, "pid": proc.pid, "port": port,
                        "url": f"http://localhost:{port}", "logfile": log_path}

            return self._process_crashed(log_path)

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _process_crashed(self, log_path: str) -> dict:
        log = self._read_last_log(log_path, 40)
        error_line = self._extract_error(log)
        if not error_line:
            error_line = log.strip().split("\n")[-1] if log.strip() else "Process crashed"
        print(f"    \U0001f4cb  {error_line[:200]}")
        return {"ok": False, "error": error_line, "log": log, "logfile": log_path}

    def _extract_error(self, log: str) -> str:
        for line in log.splitlines():
            line = line.strip()
            for keyword in ["ModuleNotFoundError", "ImportError", "SyntaxError",
                            "AttributeError", "TypeError", "ValueError", "KeyError",
                            "FileNotFoundError", "PermissionError", "ConnectionError",
                            "RuntimeError", "NameError", "OSError", "Error"]:
                if line.startswith(keyword):
                    return line[:200]
        return ""

    def _kill_port(self, port: int):
        try:
            r = subprocess.run(["fuser", "-k", f"{port}/tcp"],
                               capture_output=True, timeout=5)
        except Exception:
            try:
                r = subprocess.run(
                    f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true",
                    shell=True, capture_output=True, timeout=5)
            except Exception:
                pass

    def _detect_port_from_cmd(self, cmd: str) -> int | None:
        m = re.search(r"--port\s+(\d+)", cmd)
        if m:
            return int(m.group(1))
        m = re.search(r":(\d+)", cmd.split()[-1] if " " in cmd else "")
        if m:
            return int(m.group(1))
        return None

    def _port_open(self, port: int) -> bool:
        try:
            with socket.create_connection(("localhost", port), timeout=2):
                return True
        except (OSError, socket.timeout):
            return False

    def _scan_for_port(self, pid: int) -> int | None:
        try:
            r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if str(pid) in line:
                    m = re.search(r":(\d+)", line)
                    if m:
                        return int(m.group(1))
        except Exception:
            pass
        try:
            with open(f"/proc/{pid}/net/tcp") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) > 1 and parts[1] != "local_address":
                        hex_port = parts[1].split(":")[1]
                        port = int(hex_port, 16)
                        if 1024 <= port <= 65535:
                            return port
        except Exception:
            pass
        return None

    def _read_last_log(self, log_path: str, n: int = 10) -> str:
        try:
            r = subprocess.run(["tail", f"-{n}", log_path], capture_output=True, text=True, timeout=5)
            return r.stdout
        except Exception:
            return ""

    def _ai_fix_run(self, error: str, logfile_path: str, files: dict, suggested_cmd: str) -> dict:
        cfg = load_config()
        api_key = cfg.get("api_key")
        if not api_key:
            return {"ok": False, "error": "No AI fix available"}

        from runit.llm import llm_call

        full_log = ""
        if logfile_path and os.path.exists(logfile_path):
            try:
                full_log = Path(logfile_path).read_text()[-3000:]
            except Exception:
                pass

        file_list = list(files.keys()) if files else []
        py_files = []
        try:
            root = Path(self.project_path)
            for f in sorted(root.rglob("*.py")):
                rel = str(f.relative_to(root))
                if not any(p in rel for p in [".runit", "__pycache__", "site-packages"]):
                    if len(py_files) < 30:
                        py_files.append(rel)
        except Exception:
            pass

        max_rounds = 3
        for attempt in range(max_rounds):
            prompt = f"""Project at {self.project_path} failed to run.
Attempt {attempt + 1}/{max_rounds}.

Error: {error[:500]}
Log tail:
{full_log[:2000]}

Key files: {json.dumps(file_list)}
Python files: {json.dumps(py_files[:15])}
Suggested cmd: {suggested_cmd}

Diagnose the problem. Return ONLY JSON:
{{"action":"install"|"run"|"apt"|"done","param":"...","reason":"..."}}

- "install": pip install package(s). USE == NOT < > (shell-safe). param = "pkg1 pkg2==version"
- "apt": apt-get install. param = "pkg1 pkg2"  
- "run": try this run command. param = full command
- "done": mark as fixed, try running again. param = ""

JSON only, no markdown:"""
            try:
                raw = llm_call(prompt)
                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
                plan = json.loads(raw)
                action = plan.get("action", "")
                param = plan.get("param", "")

                if action == "done":
                    result = self._run_project_in_background(suggested_cmd)
                    if result.get("ok"):
                        return result
                    error = result.get("error", "")
                    full_log = ""
                    if result.get("logfile") and os.path.exists(result["logfile"]):
                        full_log = Path(result["logfile"]).read_text()[-3000:]
                    continue

                if action == "install":
                    safe_param = param.replace("<", "=").replace(">", "=").replace("|", " ").replace("&", " ")
                    self._run_cmd(f"pip install -q --no-build-isolation '{safe_param}'", timeout=300)
                    result = self._run_project_in_background(suggested_cmd)
                    if result.get("ok"):
                        return result
                    error = result.get("error", "")
                    if result.get("logfile"):
                        full_log = Path(result["logfile"]).read_text()[-3000:]
                    continue

                if action == "apt":
                    self._run_cmd(f"apt-get install -y -qq {param}", timeout=120)
                    continue

                if action == "run":
                    result = self._run_project_in_background(param)
                    if result.get("ok"):
                        return result
                    error = result.get("error", "")
                    if result.get("logfile"):
                        full_log = Path(result["logfile"]).read_text()[-3000:]
                    continue

            except json.JSONDecodeError:
                continue
            except Exception as e:
                if attempt == max_rounds - 1:
                    return {"ok": False, "error": f"AI fix failed: {e}"}
                continue

        return {"ok": False, "error": "Could not fix after 3 attempts"}

    def _generate_restart_script(self, result: dict, cmd: str):
        lines = ["#!/bin/bash", "# Runit restart script", f"# Project: {self.project_path}", ""]
        env_file = Path(self.project_path) / ".env"
        if env_file.exists():
            lines.append(f"# Source .env")
            lines.append(f"set -a && source {env_file} && set +a")
            lines.append("")
        if cmd:
            lines.append(f"# Start the project")
            lines.append(f"cd {self.project_path}")
            lines.append(f"{cmd} &")
            lines.append(f"echo 'PID: $!'")
            lines.append("")

        script_path = Path(self.project_path) / "restart.sh"
        script_path.write_text("\n".join(lines) + "\n")
        os.chmod(str(script_path), 0o755)
        print(f"  \U0001f4c4  Restart script: {script_path}")
        print(f"  \U0001f4bb  ! bash {script_path}")

    def _read_key_files(self):
        files = {}
        candidates = ["README.md", "README.MD", "README.rst", "requirements.txt",
                      "main.py", "app.py", "app/main.py", "app/__init__.py",
                      "package.json", "Procfile", "Makefile", "Dockerfile",
                      "docker-compose.yml", "index.js", "server.js", "app.js",
                      "manage.py", "wsgi.py", "index.html"]
        for name in candidates:
            p = Path(self.project_path) / name
            if p.exists() and p.stat().st_size < 50000:
                try:
                    files[name] = p.read_text(errors="replace")[:3000]
                except Exception:
                    pass
        return files

    def _suggest_run_command(self, files):
        app_main = files.get("app/main.py", "")
        main_py = files.get("main.py", "")
        app_py = files.get("app.py", "")
        reqs = files.get("requirements.txt", "")

        if "app/main.py" in files:
            if "FastAPI" in app_main or "fastapi" in app_main.lower():
                return "uvicorn app.main:app --host 0.0.0.0 --port 8000"
            if "flask" in app_main.lower():
                return "uvicorn app.main:app --host 0.0.0.0 --port 8000" if "app=Flask" in app_main else "python app/main.py"

        if "app.py" in files:
            if "FastAPI" in app_py or "fastapi" in app_py.lower():
                return "uvicorn app:app --host 0.0.0.0 --port 8000"
            if "flask" in app_py.lower():
                return "python app.py"

        if "main.py" in files:
            if "FastAPI" in main_py or "fastapi" in main_py.lower():
                return "uvicorn main:app --host 0.0.0.0 --port 8000"
            if "flask" in main_py.lower():
                return "python main.py"

        for name, content in files.items():
            if name == "Procfile":
                m = re.search(r"web:\s*(.+)", content)
                if m:
                    return m.group(1).strip()
            if name == "Makefile":
                if re.search(r"^run:", content, re.MULTILINE):
                    return "make run"
            if name == "package.json":
                try:
                    pkg = json.loads(content)
                    for s in ["dev", "start", "serve"]:
                        if s in pkg.get("scripts", {}):
                            return f"npm run {s}"
                except Exception:
                    pass
            if name == "requirements.txt":
                if "uvicorn" in content.lower() and "fastapi" in content.lower():
                    if "app/main.py" in files:
                        return "uvicorn app.main:app --host 0.0.0.0 --port 8000"
                    if "main.py" in files or "app.py" in files:
                        continue
                    return "uvicorn main:app --host 0.0.0.0 --port 8000"
                if "uvicorn" in content.lower():
                    return "uvicorn main:app --host 0.0.0.0 --port 8000"
                if "flask" in content.lower():
                    return "python app.py"
                if "django" in content.lower():
                    return "python manage.py runserver 0.0.0.0:8000"

        return ""

    def _tunnel_all_ports(self, result):
        pids = result.get("pids", [])
        if not pids:
            pid = result.get("pid")
            if pid:
                pids = [pid]
        all_ports = set()
        for pid in pids:
            ports = self._detect_all_ports(pid)
            all_ports.update(ports)
        app_urls = result.get("urls", [])
        for url in app_urls:
            m = re.search(r":(\d+)", url)
            if m:
                all_ports.add(int(m.group(1)))
        if result.get("port"):
            all_ports.add(result["port"])
        tunneled = []
        for port in sorted(all_ports):
            url = self._start_cloudflare_tunnel(port)
            if url:
                tunneled.append((port, url))
        if tunneled:
            result["public_urls"] = {str(p): u for p, u in tunneled}
            result["public_url"] = tunneled[0][1]

    def _detect_all_ports(self, pid):
        ports = set()
        try:
            r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if str(pid) in line:
                    m = re.search(r":(\d+)", line)
                    if m:
                        ports.add(int(m.group(1)))
        except Exception:
            pass
        try:
            with open(f"/proc/{pid}/net/tcp") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) > 1 and parts[1] != "local_address":
                        hex_port = parts[1].split(":")[1]
                        port = int(hex_port, 16)
                        if 1024 <= port <= 65535:
                            ports.add(port)
        except Exception:
            pass
        return list(ports)

    def _start_cloudflare_tunnel(self, port):
        if not port:
            return None
        bin_path = shutil.which("cloudflared") or shutil.which("/tmp/cloudflared")
        if not bin_path:
            print(f"  \U0001f4e1  Downloading cloudflared...")
            print(f"  \U0001f4bb  ! curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared && chmod +x /tmp/cloudflared")
            try:
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                subprocess.run(f"curl -sL {url} -o /tmp/cloudflared && chmod +x /tmp/cloudflared",
                               shell=True, capture_output=True, text=True, timeout=30)
                bin_path = "/tmp/cloudflared"
                if not os.path.isfile(bin_path):
                    return None
            except Exception:
                return None
        print(f"  \U0001f4e1  Tunnel port {port}...")
        try:
            proc = subprocess.Popen(
                [bin_path, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, preexec_fn=os.setsid,
            )
            start = time.time()
            public_url = None
            while time.time() - start < 15:
                line = proc.stdout.readline()
                if not line:
                    break
                m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if m:
                    public_url = m.group(0)
                    break
            self.pm.add_process("cloudflared", proc)
            if public_url:
                return public_url
            return None
        except Exception:
            return None

    def _dashboard_html(self):
        cards = []
        if self.tunnel_urls:
            for name, url in sorted(self.tunnel_urls.items()):
                cards.append(f"""
      <div class="card">
        <h3>{name}</h3>
        <p class="url"><a href="{url}" target="_blank">{url}</a></p>
      </div>""")
        for name, entry in self.sm.running.items():
            port = entry.get("port", entry["defs"]["port"])
            local_url = entry["defs"].get("connection_url", "").format(host="localhost", port=port)
            cards.append(f"""
      <div class="card">
        <h3>{name} (local)</h3>
        <p class="url"><a href="{local_url}" target="_blank">{local_url}</a></p>
        <p class="meta">{entry.get('mode', '')} | port {port}</p>
      </div>""")
        svc_rows = "\n".join(cards)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runit - {self.project_name}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font:14px/1.5 system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:2rem}}
  h1{{font-size:1.5rem}}
  .sub{{color:#94a3b8;margin-bottom:2rem}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}}
  .card{{background:#1e293b;padding:1rem 1.5rem;border-radius:10px}}
  h3{{font-size:1rem;color:#a5b4fc;text-transform:capitalize;margin-bottom:.3rem}}
  .url a{{color:#6366f1;text-decoration:none;font-size:.9rem}}
  .url a:hover{{text-decoration:underline}}
  .meta{{color:#64748b;font-size:.75rem;margin-top:.3rem}}
</style></head><body>
<h1>⚡ {self.project_name}</h1>
<p class="sub">Runit v2.1.2 — Public tunnels & services</p>
<div class="grid">{svc_rows}</div>
<p class="meta" style="margin-top:2rem;text-align:center;color:#475569">{self.project_path}</p>
</body></html>"""

    def _start_dashboard_server(self):
        html = self._dashboard_html()
        class DashHandler(BaseHTTPRequestHandler):
            def do_GET(self_):
                self_.send_response(200)
                self_.send_header("Content-Type", "text/html; charset=utf-8")
                self_.end_headers()
                self_.wfile.write(html.encode())
            def log_message(self_, *a): pass
        port = self._find_free_port(9000)
        try:
            server = HTTPServer(("0.0.0.0", port), DashHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = self._start_cloudflare_tunnel(port)
            if url:
                self.tunnel_urls["dashboard"] = url
        except Exception:
            pass

    def _find_free_port(self, start=8000):
        for port in range(start, start + 100):
            try:
                with socket.socket() as s:
                    s.bind(("", port))
                    return port
            except OSError:
                continue
        return start

    def _dashboard(self, result: dict):
        public_url = result.get("public_url", "")
        public_urls = result.get("public_urls", {})
        dashboard_url = self.tunnel_urls.get("dashboard", "")

        print(f"\n  \u2705  {self.project_name} is running!")
        print(f"  {'=' * 55}")
        if dashboard_url:
            print(f"  \U0001f4ca  Dashboard: {dashboard_url}")
        if public_url:
            print(f"  \U0001f310  Public URL: {public_url}")
        for port_str, url in sorted(public_urls.items()):
            if url != public_url:
                print(f"  \U0001f310  Port {port_str}: {url}")
        if result.get("url"):
            print(f"  \U0001f310  Local:      {result['url']}")
        if result.get("port"):
            print(f"  \U0001f5a5  Port:       {result['port']}")
        if result.get("pid"):
            print(f"  \U0001f9f9  PID:        {result['pid']}")
        print(f"  \U0001f4c2  Path:       {self.project_path}")
        logfile = result.get("logfile", "")
        if logfile:
            print(f"  \U0001f4cb  Log:        {logfile}")
            log_tail = self._read_last_log(logfile, 5)
            if log_tail.strip():
                for line in log_tail.strip().splitlines()[-3:]:
                    print(f"         {line[:120]}")
        elif result.get("pid"):
            log_path = f"{self.project_path}/.runit/app.log"
            print(f"  \U0001f4cb  Log:        {log_path}")
        svcs = list(self.sm.running.keys())
        if svcs:
            print(f"  \U0001f6e0  Services:   {', '.join(svcs)}")
        restart_script = Path(self.project_path) / "restart.sh"
        if restart_script.exists():
            print(f"  \U0001f4c4  Restart:    bash {restart_script}")
            print(f"         ! bash {restart_script}")
        print(f"  {'=' * 55}")
        print(f"  \U0001f4bb  cd {self.project_path}")
        if result.get("pid"):
            print(f"  \U0001f6d1  Stop:       kill {result['pid']}")

    def _print_failure(self, result: dict):
        print(f"\n  \u274c  Could not run {self.project_name}")
        error = result.get("error", "") or result.get("output", "")
        if error:
            print(f"  \U0001f50d  {error[:500]}")

    def cleanup(self):
        self.sm.stop_all()
        self.pm.stop_all()
