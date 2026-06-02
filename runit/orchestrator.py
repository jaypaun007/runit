import os
import json
import re
import time
import socket
import shutil
import urllib.parse
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from runit.cli import _console, print_step, confirm, AUTO_YES
from runit.agent_tools import _init_state, _shared_state
from runit.agent_core import AgentCore
from runit.agent_prompts import AGENT_SYSTEM_PROMPT, FIX_ERROR_PROMPT
from runit.service_manager import ServiceManager, service_name_from_env
from runit.service_defs import SERVICE_DEFS
from runit.env_resolver import EnvResolver, is_critical
from runit.process_monitor import ProcessMonitor
from runit.error_classifier import classify_error, get_auto_heal
from runit.config import load_config
from runit.skills import match_skills, detect_package_manager, get_skill, FRAMEWORK_ALIASES
from runit.environment import is_notebook_env
from runit.llm import llm_call
from runit.executor import ensure_runtime


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
        self.run_command = ""
        self.dev_scripts = []
        self.required_services = []
        self.env_vars = {}
        self.server_info = {}
        _init_state(project_path, env_type)

    def run(self) -> dict:
        if self.c:
            self.c.print(f"\n  [bold]Runit v2.0.1 — Pipeline[/]")
            self.c.print(f"  [dim]Project: {self.project_name}  |  Path: {self.project_path}[/]")
            self.c.print()

        print_step(1, 5, "Analyzing project structure...")
        self._analyze()

        print_step(2, 5, "Detecting and setting up services...")
        self._setup_services()

        print_step(3, 5, "Resolving environment variables...")
        self._resolve_env()

        cfg = load_config()
        if self.auto_yes and not is_notebook_env() and cfg.get("api_key"):
            self._ai_generate_env()

        print_step(4, 5, "Installing dependencies...")
        install_ok = self._install_deps()
        if not install_ok:
            print("  \u26a0\ufe0f  Install had issues, continuing anyway...")

        print_step(5, 5, "Running project...")
        result = self._run_project()

        if result.get("ok"):
            port = result.get("port")
            pid = result.get("pid")
            if not port and pid:
                print(f"  \U0001f50d  Scanning for port...")
                port = self._detect_port_from_process(pid)
                if port:
                    result["port"] = port
                    result["url"] = f"http://localhost:{port}"
            public_url = self._start_cloudflare_tunnel(port or result.get("port"))
            if public_url:
                result["public_url"] = public_url
            self._dashboard(result)
            return {"status": "success", "result": result}

        print("  \u274c  Automatic setup failed. Trying AI agent...")
        agent_result = self._agent_repair(result.get("error", ""))
        if agent_result.get("ok"):
            port = agent_result.get("port")
            pid = agent_result.get("pid")
            if not port and pid:
                port = self._detect_port_from_process(pid)
                if port:
                    agent_result["port"] = port
                    agent_result["url"] = f"http://localhost:{port}"
            public_url = self._start_cloudflare_tunnel(port)
            if public_url:
                agent_result["public_url"] = public_url
            self._dashboard(agent_result)
            return {"status": "success", "result": agent_result}

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
                self.dev_scripts = [s for s in ["dev", "start", "serve"] if s in scripts]
                print(f"  \U0001f4e6  Node.js project detected")
                self.project_type = "node"
                if self.dev_scripts:
                    print(f"  \U0001f527  Scripts: {', '.join(self.dev_scripts)}")
            except Exception:
                pass

        req_txt = root / "requirements.txt"
        if req_txt.exists():
            self.project_type = "python"
            print(f"  \U0001f4e6  Python project detected")

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
                print(f"    \u2705  {svc}: {url}")
            else:
                print(f"    \u26a0\ufe0f  {result.get('error', 'failed')}")

    def _resolve_env(self):
        env_example = self.er.scan_env_example()
        if not env_example:
            print("  \u2705  No .env.example found")
            return

        print(f"  \U0001f511  Resolving {len(env_example)} env vars...")
        self.env_vars = {}

        pending_critical = []
        for var in env_example:
            val = self.er.resolve(var, env_example)
            if val is None:
                if is_critical(var) and (not self.auto_yes or is_notebook_env()):
                    pending_critical.append(var)
                if not val:
                    from runit.env_resolver import random_string
                    val = random_string(16)
                    self.er.categories[var] = "auto_generated"
            self.env_vars[var] = val or ""

        if pending_critical and is_notebook_env():
            print(f"    \U0001f4e1  Opening web UI for {len(pending_critical)} env vars...")
            submitted = self._env_ui_server(pending_critical)
            for var, val in submitted.items():
                self.env_vars[var] = val
                self.er.categories[var] = "user_provided"
        else:
            for var in pending_critical:
                try:
                    val = input(f"    \U0001f511  Enter {var}: ")
                    if val.strip():
                        self.env_vars[var] = val.strip()
                        self.er.categories[var] = "user_provided"
                except (EOFError, KeyboardInterrupt):
                    pass

        written = self.er.generate_env_file(self.env_vars)
        print(f"    \u2705  Written {written} ({len(self.env_vars)} vars)")

        critical = [v for v in self.env_vars if is_critical(v)]
        auto = [v for v, c in self.er.categories.items() if c == "auto_generated"]
        if critical:
            print(f"    \U0001f511  {len(critical)} sensitive vars set (API keys, secrets)")
        if auto:
            print(f"    \U0001f504  {len(auto)} vars auto-generated")

    def _ai_generate_env(self):
        critical = [v for v in self.env_vars if is_critical(v)]
        if not critical:
            return

        env_example = self.er.scan_env_example()
        current_vals = {v: self.env_vars[v] for v in critical}
        prompt_lines = [
            "Generate realistic-looking placeholder values for these environment variables.",
            "Follow the expected format for each type:",
            "- API keys should match the service's key format (e.g., 'sk-...' for OpenAI, 'ghp_...' for GitHub)",
            "- URLs should be valid connection strings (e.g., 'postgresql://user:pass@localhost:5432/db')",
            "- Passwords and secrets should be strong random strings",
            "- Never use 'your-api-key-here' or 'changeme' — generate a real-looking value",
            "",
            "Current random values (replace these with realistic ones):",
        ]
        for v in critical:
            example_val = env_example.get(v, "")
            hint = f"  [example: {example_val[:30]}]" if example_val and example_val != v.lower() else ""
            prompt_lines.append(f"- {v} = {current_vals[v]}{hint}")

        prompt_lines.extend([
            "",
            "Return ONLY a valid JSON object like: {\"VAR_NAME\": \"realistic_value\", ...}",
            "No markdown, no backticks, no explanation.",
        ])

        try:
            raw = llm_call("\n".join(prompt_lines))
            raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
            ai_vals = json.loads(raw)
            if not isinstance(ai_vals, dict):
                return
            for v in critical:
                if v in ai_vals and ai_vals[v]:
                    self.env_vars[v] = ai_vals[v]
                    self.er.categories[v] = "ai_generated"
            updated = {v: self.env_vars[v] for v in critical if v in ai_vals}
            if updated:
                self.er.update_env_file(updated)
                print(f"    \U0001f916  AI generated {len(updated)} env values")
        except Exception:
            pass

    def _install_deps(self) -> bool:
        root = Path(self.project_path)
        cmds = []

        if self.project_type == "node":
            pm = self.package_manager
            if not shutil.which(pm):
                print(f"    \u26a0\ufe0f  {pm} not found, installing...")
                if pm == "pnpm":
                    subprocess.run("npm install -g pnpm 2>/dev/null || npm i -g pnpm@latest",
                                   shell=True, capture_output=True, text=True, timeout=60)
                    if not shutil.which("pnpm"):
                        print(f"    \u26a0\ufe0f  Falling back to npm")
                        pm = "npm"
                        self.package_manager = "npm"
                elif pm == "yarn":
                    subprocess.run("npm install -g yarn 2>/dev/null",
                                   shell=True, capture_output=True, text=True, timeout=60)
                    if not shutil.which("yarn"):
                        print(f"    \u26a0\ufe0f  Falling back to npm")
                        pm = "npm"
                        self.package_manager = "npm"
            lock_files = {"pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "npm": "package-lock.json"}
            lock = lock_files.get(pm, "package-lock.json")
            if (root / lock).exists() or (root / "package.json").exists():
                cmds.append(f"{pm} install")
                cmds.append(f"{pm} run build 2>/dev/null || true")

        elif self.project_type == "python":
            if (root / "requirements.txt").exists():
                cmds.append("pip install -r requirements.txt -q 2>/dev/null || pip install -r requirements.txt")
            if (root / "pyproject.toml").exists():
                cmds.append("pip install -e . -q 2>/dev/null || pip install .")

        if not cmds:
            print("  \u2705  No install commands needed")
            return True

        all_ok = True
        for cmd in cmds:
            print(f"    $ {cmd[:80]}...")
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                   cwd=self.project_path, timeout=300)
                if r.returncode == 0:
                    print(f"    \u2705  OK")
                else:
                    print(f"    \u26a0\ufe0f  Exit {r.returncode}: {r.stderr[-200:]}")
                    all_ok = False
            except subprocess.TimeoutExpired:
                print(f"    \u26a0\ufe0f  Timed out (300s)")
                all_ok = False

        return all_ok

    def _run_project(self) -> dict:
        dev_cmd = self._get_run_command()
        if not dev_cmd:
            print("  \u26a0\ufe0f  No run command determined")
            return {"ok": False, "error": "No run command"}

        print(f"  \U0001f680  Running: {dev_cmd}")
        env = {**os.environ, **{k: v for k, v in self.env_vars.items() if k not in os.environ}}

        result = self.pm.detect_server_url(dev_cmd, env=env)
        if result.get("ok") or result.get("port") or result.get("pid"):
            self.server_info = result
            return {
                "ok": True,
                "url": result.get("url", ""),
                "port": result.get("port"),
                "pid": result.get("pid"),
                "logfile": result.get("logfile", ""),
                "command": dev_cmd,
            }

        try:
            r = subprocess.run(dev_cmd, shell=True, capture_output=True, text=True,
                               cwd=self.project_path, env=env, timeout=30)
            if r.returncode == 0:
                return {"ok": True, "output": r.stdout[:1000]}
            return {"ok": False, "error": r.stderr[:2000], "stdout": r.stdout[:1000],
                    "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            result = self.pm.detect_server_url(dev_cmd, env=env)
            if result.get("ok"):
                return {
                    "ok": True,
                    "url": result.get("url", ""),
                    "port": result.get("port"),
                    "pid": result.get("pid"),
                    "logfile": result.get("logfile", ""),
                }
            return {"ok": False, "error": "Timed out with no output"}

    def _get_run_command(self) -> str:
        root = Path(self.project_path)

        if self.project_type == "node":
            pm = self.package_manager
            for script in self.dev_scripts:
                return f"{pm} run {script}"

            pkg = root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text())
                    main = data.get("main", "index.js")
                    bin_entry = data.get("bin", {})
                    if isinstance(bin_entry, dict) and bin_entry:
                        return f"{pm} run start"
                    return f"node {main}"
                except Exception:
                    pass

            return f"node index.js"

        if self.project_type == "python":
            for entry in ["app.py", "main.py", "server.py", "run.py", "index.py", "cli.py"]:
                if (root / entry).exists():
                    return f"python {entry}"
            return "python main.py 2>/dev/null || python app.py 2>/dev/null || python server.py"

        return ""

    def _agent_repair(self, error: str) -> dict:
        cfg = load_config()
        if not cfg.get("api_key"):
            return {"ok": False}

        print(f"  \U0001f916  AI agent analyzing failure...")

        agent = AgentCore(
            self.project_path, console=self.c, auto_yes=self.auto_yes,
            max_steps=20, system_prompt=FIX_ERROR_PROMPT,
        )

        task = f"""The project at {self.project_path} failed to run with this error:

{error[:2000]}

Fix this error and get the project running.
1. Read the error and project files to understand the issue
2. Fix the problem (install missing deps, fix config, set env vars, etc.)
3. Try running the project again
4. If successful, call done with the result info

Services running: {list(self.sm.running.keys())}
Env vars set: {list(self.env_vars.keys())[:20]}"""

        from runit.agent_tools import TOOLS
        result = agent.run(task, TOOLS)

        if result.get("status") == "success":
            r = result.get("result", {})
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except Exception:
                    r = {"ok": True, "info": r}
            return r

        return {"ok": False}

    def _find_free_port(self, start=8000):
        for port in range(start, start + 100):
            try:
                with socket.socket() as s:
                    s.bind(("", port))
                    return port
            except OSError:
                continue
        return start

    def _env_ui_form_html(self, var_names):
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
  * {{ box-sizing:border-box; margin:0; padding:0 }}
  body {{ font:16px/1.5 system-ui,sans-serif; background:#0f172a; color:#e2e8f0; min-height:100vh; display:flex; align-items:center; justify-content:center }}
  .card {{ background:#1e293b; padding:2rem; border-radius:12px; width:90%; max-width:520px }}
  h1 {{ font-size:1.3rem; margin-bottom:.25rem }}
  p {{ color:#94a3b8; margin-bottom:1.5rem; font-size:.9rem }}
  .field {{ margin-bottom:1rem }}
  label {{ display:block; font-size:.8rem; font-weight:600; color:#94a3b8; margin-bottom:.3rem; word-break:break-all }}
  input {{ width:100%; padding:.6rem .8rem; background:#0f172a; border:1px solid #334155; border-radius:8px; color:#e2e8f0; font-size:.9rem; outline:none; transition:border-color .15s }}
  input:focus {{ border-color:#6366f1 }}
  button {{ width:100%; padding:.7rem; background:#6366f1; border:none; border-radius:8px; color:#fff; font-size:.95rem; font-weight:600; cursor:pointer; margin-top:.5rem }}
  button:hover {{ background:#4f46e5 }}
  .small {{ font-size:.75rem; color:#64748b; text-align:center; margin-top:1rem }}
</style>
</head>
<body>
<div class="card">
  <h1>⚡ Runit — Environment Variables</h1>
  <p>Review and fill the <strong>{len(var_names)}</strong> required variables, then click Save.</p>
  <form method="POST" action="/">{"".join(rows)}
    <button type="submit">Save &amp; Continue</button>
    <button type="submit" name="_skip" value="1" style="background:#334155;margin-top:.5rem">Skip — use defaults</button>
  </form>
  <div class="small">Values already have random defaults — edit or leave as-is.</div>
</div>
</body>
</html>"""

    def _env_ui_server(self, var_names):
        result_file = Path(self.project_path) / ".runit" / "env_ui_result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        if result_file.exists():
            result_file.unlink()

        form_html = self._env_ui_form_html(var_names)
        submitted = {}

        class EnvUIHandler(BaseHTTPRequestHandler):
            def do_GET(self_):
                if self_.path == "/favicon.ico":
                    self_.send_response(204)
                    self_.end_headers()
                    return
                self_.send_response(200)
                self_.send_header("Content-Type", "text/html; charset=utf-8")
                self_.end_headers()
                self_.wfile.write(form_html.encode())

            def do_POST(self_):
                length = int(self_.headers.get("Content-Length", 0))
                body = self_.rfile.read(length).decode()
                parsed = urllib.parse.parse_qs(body)
                if "_skip" in parsed:
                    submitted["_skip"] = True
                    result_file.write_text(json.dumps({"__skip__": True}))
                else:
                    for var in var_names:
                        vals = parsed.get(var, [])
                        if vals and vals[0].strip():
                            submitted[var] = vals[0].strip()
                    result_file.write_text(json.dumps(submitted))
                self_.send_response(200)
                self_.send_header("Content-Type", "text/html; charset=utf-8")
                self_.end_headers()
                if "_skip" in parsed:
                    self_.wfile.write(b"<h2>Skipped - using defaults.</h2><script>window.close()</script>")
                else:
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
            print(f"    \u23f3  Fill the form in your browser, then click Save (or Skip to use defaults)")
        else:
            print(f"    \U0001f5a5  Local: http://localhost:{port}")

        poll = 0
        while True:
            if result_file.exists():
                try:
                    data = json.loads(result_file.read_text())
                    if "__skip__" in data:
                        submitted = {}
                    else:
                        submitted = data
                    break
                except Exception:
                    pass
            poll += 1
            if poll == 60:
                print(f"    \u23f3  Still waiting... (or click 'Skip' on the form to use defaults)")
            elif poll % 300 == 0:
                print(f"    \u23f3  Still waiting... ({poll // 60}min)")
            time.sleep(1)

        server.shutdown()
        return submitted

    def _detect_port_from_process(self, pid):
        for _ in range(30):
            try:
                r = subprocess.run(
                    ["ss", "-tlnp"],
                    capture_output=True, text=True, timeout=5,
                )
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
            time.sleep(1)
        return None

    def _start_cloudflare_tunnel(self, port):
        if not port:
            return None
        bin_path = shutil.which("cloudflared") or shutil.which("/tmp/cloudflared")
        if not bin_path:
            print(f"  \U0001f4e1  Downloading cloudflared for public tunnel...")
            try:
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                subprocess.run(f"curl -sL {url} -o /tmp/cloudflared && chmod +x /tmp/cloudflared",
                               shell=True, capture_output=True, text=True, timeout=30)
                bin_path = "/tmp/cloudflared"
                if not os.path.isfile(bin_path):
                    return None
            except Exception:
                return None

        print(f"  \U0001f4e1  Starting public tunnel on port {port}...")
        try:
            proc = subprocess.Popen(
                [bin_path, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, preexec_fn=os.setsid,
            )
            # Read output until we get the URL
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
            if public_url:
                self.pm.add_process("cloudflared", proc)
                print(f"    \U0001f310  Public URL: {public_url}")
                return public_url
            # Give up but leave it running
            self.pm.add_process("cloudflared", proc)
            return None
        except Exception:
            return None

    def _dashboard(self, result: dict):
        url = result.get("url", "")
        port = result.get("port", "")
        pid = result.get("pid", "")
        logfile = result.get("logfile", "")
        public_url = result.get("public_url", "")

        print(f"\n  \u2705  {self.project_name} is running!")
        print(f"  {'=' * 50}")
        if public_url:
            print(f"  \U0001f310  Public: {public_url}")
        if url:
            print(f"  \U0001f310  Local:  {url}")
        if port:
            print(f"  \U0001f5a5  Port: {port}")
        if pid:
            print(f"  \U0001f9f9  PID:  {pid}")
        print(f"  \U0001f4c2  Path: {self.project_path}")
        env_path = Path(self.project_path) / ".env"
        if env_path.exists():
            print(f"  \U0001f511  Env:  {env_path}")
        if logfile:
            print(f"  \U0001f4cb  Log:  {logfile}")
        elif pid:
            print(f"  \U0001f4cb  Log:  {self.project_path}/.runit/app.log")
        svcs = list(self.sm.running.keys())
        if svcs:
            print(f"  \U0001f6e0  Services: {', '.join(svcs)}")
        print(f"  {'=' * 50}")
        print(f"  \U0001f4bb  cd {self.project_path}")
        if pid:
            print(f"  \U0001f6d1  Stop: kill {pid}")

    def _print_failure(self, result: dict):
        print(f"\n  \u274c  Could not run {self.project_name}")
        error = result.get("error", "") or result.get("output", "")
        if error:
            print(f"  \U0001f50d  {error[:500]}")

    def cleanup(self):
        self.sm.stop_all()
        self.pm.stop_all()
