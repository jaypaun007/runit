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

from runit.cli import _console, print_step, AUTO_YES
from runit.agent_tools import _init_state
from runit.agent_core import AgentCore
from runit.agent_prompts import AGENT_SYSTEM_PROMPT
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
        _init_state(project_path, env_type)

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

        critical_missing = [v for v in all_vars if is_critical(v) and not self.env_vars.get(v)]

        if self.auto_yes and is_notebook_env() and all_vars:
            self._env_web_ui(all_vars)
            env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")
        elif not self.auto_yes and critical_missing:
            if is_notebook_env():
                self._env_web_ui(all_vars)
            else:
                for var in critical_missing:
                    try:
                        val = input(f"  \U0001f511  Enter {var}: ")
                        if val.strip():
                            self.env_vars[var] = val.strip()
                    except (EOFError, KeyboardInterrupt):
                        pass
            env_file.write_text("\n".join(f"{k}={v}" for k, v in self.env_vars.items()) + "\n")

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
        env_path = Path(self.project_path) / ".env.example"
        if not env_path.exists():
            return {}
        result = {}
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip("\"'")
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
        if not api_key:
            print("  \u26a0\ufe0f  No API key configured. Run with --setup or set RUNIT_API_KEY")
            return {"ok": False, "error": "No API key"}

        env = self._resolve_env_pass()
        self.env_vars = env
        if env:
            env_file = Path(self.project_path) / ".env"
            env_file.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")

        services_info = {}
        for name, entry in self.sm.running.items():
            port = entry.get("port", entry["defs"]["port"])
            url = entry["defs"].get("connection_url", "").format(host="localhost", port=port)
            services_info[name] = {"url": url, "port": port}

        project_files = self._read_key_files()
        suggested_cmd = self._suggest_run_command(project_files)

        agent = AgentCore(
            self.project_path, console=self.c, auto_yes=self.auto_yes,
            max_steps=self.max_retries,
            system_prompt=AGENT_SYSTEM_PROMPT,
        )

        task = f"""Project: {self.project_path}
Type: {self.project_type} | PM: {self.package_manager}
Services: {json.dumps(services_info)}
Env: {json.dumps(env)[:1000]}
Key files: {json.dumps(project_files)[:3000]}

Run it.
- Already have key files above, do NOT read them again
- {suggested_cmd or "Figure out and run the start command"}
- Call done({{"ok":true,"urls":["http://localhost:PORT"],"pids":[PID]}}) when running"""

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

        return {"ok": False, "error": "Agent failed"}

    def _read_key_files(self):
        files = {}
        for name in ["README.md", "README.rst", "requirements.txt", "main.py", "app.py",
                      "package.json", "Procfile", "Makefile", "Dockerfile", "docker-compose.yml",
                      "index.js", "server.js", "app.js", "manage.py", "wsgi.py", "index.html"]:
            p = Path(self.project_path) / name
            if p.exists() and p.stat().st_size < 50000:
                try:
                    files[name] = p.read_text(errors="replace")[:3000]
                except Exception:
                    pass
        return files

    def _suggest_run_command(self, files):
        for name, content in files.items():
            if name == "Procfile":
                m = re.search(r"web:\s*(.+)", content)
                if m:
                    return f"Run: {m.group(1).strip()}"
            if name == "Makefile":
                if re.search(r"^run:", content, re.MULTILINE):
                    return "Run: make run"
            if name == "package.json":
                try:
                    pkg = json.loads(content)
                    for s in ["dev", "start", "serve"]:
                        if s in pkg.get("scripts", {}):
                            return f"Run: npm run {s}  (or: {pkg['scripts'][s][:80]})"
                except Exception:
                    pass
            if name == "requirements.txt":
                if "flask" in content.lower():
                    return "Run: python app.py or python main.py  (Flask app)"
                if "django" in content.lower():
                    return "Run: python manage.py runserver 0.0.0.0:8000"
                if "fastapi" in content.lower() or "uvicorn" in content.lower():
                    return "Run: uvicorn main:app --host 0.0.0.0 --port 8000"
            if name in ("main.py", "app.py"):
                if "flask" in content.lower() or "FastAPI" in content or "uvicorn" in content.lower():
                    return "Run: python " + name
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
        print(f"  {'=' * 50}")
        if dashboard_url:
            print(f"  \U0001f4ca  Dashboard: {dashboard_url}")
        if public_url:
            print(f"  \U0001f310  Public: {public_url}")
        for port_str, url in sorted(public_urls.items()):
            if url != public_url:
                print(f"  \U0001f310  Port {port_str}: {url}")
        if result.get("url"):
            print(f"  \U0001f310  Local:  {result['url']}")
        if result.get("port"):
            print(f"  \U0001f5a5  Port: {result['port']}")
        if result.get("pids"):
            print(f"  \U0001f9f9  PIDs: {', '.join(str(p) for p in result['pids'])}")
        if result.get("pid"):
            print(f"  \U0001f9f9  PID:  {result['pid']}")
        print(f"  \U0001f4c2  Path: {self.project_path}")
        logfile = result.get("logfile", "")
        if logfile:
            print(f"  \U0001f4cb  Log:  {logfile}")
        elif result.get("pid"):
            print(f"  \U0001f4cb  Log:  {self.project_path}/.runit/app.log")
        svcs = list(self.sm.running.keys())
        if svcs:
            print(f"  \U0001f6e0  Services: {', '.join(svcs)}")
        print(f"  {'=' * 50}")
        print(f"  \U0001f4bb  cd {self.project_path}")
        if result.get("pid"):
            print(f"  \U0001f6d1  Stop: kill {result['pid']}")

    def _print_failure(self, result: dict):
        print(f"\n  \u274c  Could not run {self.project_name}")
        error = result.get("error", "") or result.get("output", "")
        if error:
            print(f"  \U0001f50d  {error[:500]}")

    def cleanup(self):
        self.sm.stop_all()
        self.pm.stop_all()
