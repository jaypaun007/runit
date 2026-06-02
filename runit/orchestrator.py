import os
import json
import re
import time
import subprocess
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

        print_step(4, 5, "Installing dependencies...")
        install_ok = self._install_deps()
        if not install_ok:
            print("  \u26a0\ufe0f  Install had issues, continuing anyway...")

        print_step(5, 5, "Running project...")
        result = self._run_project()

        if result.get("ok"):
            self._dashboard(result)
            return {"status": "success", "result": result}

        print("  \u274c  Automatic setup failed. Trying AI agent...")
        agent_result = self._agent_repair(result.get("error", ""))
        if agent_result.get("ok"):
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
        for var in env_example:
            val = self.er.resolve(var, env_example)
            if val is None:
                if is_critical(var) and not self.auto_yes:
                    try:
                        val = input(f"    \U0001f511  Enter {var}: ")
                        if val.strip():
                            self.er.categories[var] = "user_provided"
                    except (EOFError, KeyboardInterrupt):
                        pass
                if not val:
                    from runit.env_resolver import random_string
                    val = random_string(16)
                    self.er.categories[var] = "auto_generated"
            self.env_vars[var] = val or ""

        written = self.er.generate_env_file(self.env_vars)
        print(f"    \u2705  Written {written} ({len(self.env_vars)} vars)")

        critical = [v for v in self.env_vars if is_critical(v)]
        auto = [v for v, c in self.er.categories.items() if c == "auto_generated"]
        if critical:
            print(f"    \U0001f511  {len(critical)} sensitive vars set (API keys, secrets)")
        if auto:
            print(f"    \U0001f504  {len(auto)} vars auto-generated")

    def _install_deps(self) -> bool:
        root = Path(self.project_path)
        cmds = []

        if self.project_type == "node":
            pm = self.package_manager
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

    def _dashboard(self, result: dict):
        url = result.get("url", "")
        port = result.get("port", "")
        pid = result.get("pid", "")
        logfile = result.get("logfile", "")

        print(f"\n  \u2705  {self.project_name} is running!")
        print(f"  {'=' * 50}")
        if url:
            print(f"  \U0001f310  URL:  {url}")
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
