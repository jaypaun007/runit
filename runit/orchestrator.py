import os
import json
import time
from pathlib import Path

from runit.cli import _console, print_step, AUTO_YES
from runit.agent_core import AgentCore
from runit.agent_tools import TOOLS, _init_state, _shared_state
from runit.agent_prompts import AGENT_SYSTEM_PROMPT, FIX_ERROR_PROMPT
from runit.error_classifier import classify_error, get_auto_heal
from runit.config import load_config


class Orchestrator:
    def __init__(self, project_path: str, env_type: str = "local", auto_yes: bool = False,
                 max_retries: int = 10, max_steps: int = 50):
        self.project_path = project_path
        self.env_type = env_type
        self.auto_yes = auto_yes
        self.max_retries = max_retries
        self.max_steps = max_steps
        self.c = _console()
        self.project_name = Path(project_path).name
        self.project_url = ""
        self.agent = AgentCore(
            project_path, console=self.c, auto_yes=auto_yes,
            max_steps=max_steps, system_prompt=AGENT_SYSTEM_PROMPT,
        )
        _init_state(project_path, env_type)

    def run(self) -> dict:
        cfg = load_config()

        if not cfg.get("api_key"):
            print("  \u26a0\ufe0f  No API key configured. Use --setup or set RUNIT_API_KEY")
            print("  \U0001f4a1  Runit needs an API key for the AI agent.")
            return {"ok": False, "error": "No API key"}

        print(f"\n  \U0001f916  Runit v2.0.1 — Autonomous Agent")
        print(f"  \U0001f4c1  Project: {self.project_name}")
        print(f"  \U0001f4cd  Path: {self.project_path}")
        print()

        result = self._agent_loop()

        if result.get("status") == "success":
            self._print_dashboard(result.get("result", {}))
        else:
            self._print_failure(result)

        self._cleanup()
        return result

    def _agent_loop(self) -> dict:
        task = f"""Your goal: Make the project at {self.project_path} runnable and verify it works.

1. ANALYZE: Read README.md, package.json, config files, CI config
2. RESEARCH: Use research_project to understand how to set up this project
3. INSTALL SERVICES: Detect what services (PostgreSQL, Redis, MySQL, etc.) are needed and install them
4. RESOLVE ENV: Read .env.example, resolve all env vars (ask user for secrets, auto-fill service URLs)
5. INSTALL DEPS: Install project dependencies
6. BUILD & RUN: Build and run the project
7. VERIFY: Check it's running, detect the port/URL
8. REPORT: Return the final result with URL, port, services info

Project name: {self.project_name}
Project path: {self.project_path}
Environment: {self.env_type}

IMPORTANT: 
- Use research_project() first to understand the project
- For API keys and secrets, use ask_user(question, secret=true)
- Write all resolved env vars to .env using write_env()
- When the project is running successfully, call done with full result details"""

        max_rounds = 3
        for round_num in range(max_rounds):
            if self.c:
                self.c.print(f"\n  [bold cyan]\U0001f3e0  Agent Round {round_num + 1}/{max_rounds}[/]")

            result = self.agent.run(task, TOOLS)

            if result.get("status") == "success":
                return result

            if round_num < max_rounds - 1:
                last = result.get("result", "") or result.get("last_result", "")
                task = f"""Continue making the project at {self.project_path} runnable.

Previous attempt result: {last}

Try a different approach. Focus on what hasn't been tried yet.
- If services need installing, use install_service()
- If env vars are missing, use resolve_env() 
- If dependencies need installing, use install_deps()
- If the project needs configuration changes, use edit_file()
- If you need information from the user, use ask_user()"""

                self.agent.steps_taken = 0
                self.agent.error_history = []

        return result

    def _print_dashboard(self, result):
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {}

        url = result.get("url", "") if isinstance(result, dict) else ""
        port = result.get("port", "") if isinstance(result, dict) else ""
        pid = result.get("pid", "") if isinstance(result, dict) else ""
        services = result.get("services", []) if isinstance(result, dict) else []
        env_file = result.get("env_file", "") if isinstance(result, dict) else ""

        print(f"\n  \u2705  {self.project_name} is running!")
        print(f"  {'=' * 50}")
        print(f"  \U0001f310  URL:    {url or 'http://localhost:' + str(port) if port else 'unknown'}")
        if port:
            print(f"  \U0001f5a5  Port:   {port}")
        if pid:
            print(f"  \U0001f9f9  PID:    {pid}")
        print(f"  \U0001f4c2  Path:   {self.project_path}")
        if env_file:
            print(f"  \U0001f511  Env:    {env_file}")
        else:
            env_path = Path(self.project_path) / ".env"
            if env_path.exists():
                print(f"  \U0001f511  Env:    {env_path}")
        state_path = Path(self.project_path) / ".runit" / "state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
                svcs = state.get("services", {})
                if svcs:
                    print(f"  \U0001f6e0  Services:")
                    for sname, sinfo in svcs.items():
                        print(f"    \u2514 {sname}: {sinfo.get('url', 'running')}")
            except Exception:
                pass
        print(f"  \U0001f4cb  Log:    {self.project_path}/.runit/app.log")
        print(f"  {'=' * 50}")
        print(f"  \U0001f4a1  To stop: runit stop {self.project_path}")
        print(f"  \U0001f4bb  To develop: cd {self.project_path}")

    def _print_failure(self, result):
        print(f"\n  \u274c  Could not complete setup for {self.project_name}")
        last = result.get("result", "") or result.get("last_result", "")
        if last:
            print(f"  \U0001f50d  Last result: {last[:500]}")

    def _cleanup(self):
        if _shared_state.get("service_manager"):
            _shared_state["service_manager"].stop_all()
