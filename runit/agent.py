import os
import sys
import json
import subprocess
import random
import string
from pathlib import Path

from runit.config import load_config, save_key
from runit.llm import llm_call
from runit.web_tools import web_search
from runit.cli import _console, print_step, FORCE_PLAIN

AGENT_SYSTEM_PROMPT = """You are Runit Agent v1.2, an autonomous AI coding agent.
Your job is to analyze projects, plan execution steps, run commands, modify code, and handle complex setup instructions.

You have these tools available:
1. read_file(path) - Read file contents
2. search_web(query) - Search for solutions online
3. list_dir(path) - List directory contents
4. run_command(cmd, cwd) - Execute a shell command
5. edit_file(path, old_string, new_string) - Modify a file
6. write_file(path, content) - Write a new file
7. set_env(name, value) - Set an environment variable
8. install_package(name) - Install a system package via apt
9. write_env_file(entries) - Write a .env file with key=value pairs (entries is a list of {key, val})

When given complex natural language instructions like:
- "use python3 instead of python" -> set _user_instructions
- "use grok api key = sk-xxx" -> set env var
- "install redis and postgres" -> run commands to install/setup
- "set all other env random" -> generate random values for missing env vars
- "set up all env" -> read .env.example, generate values for each var

Always respond in this JSON format:
{"thought": "brief analysis", "action": "tool_name", "args": {...}, "done": false}
When complete:
{"thought": "summary", "action": "done", "result": "...", "done": true}

Be concise. Execute one step at a time. For complex instructions, break into multiple steps."""


def _safe_read(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        if p.stat().st_size > 50000:
            return f"File too large, showing first 1000 lines:\n" + p.read_text(encoding="utf-8", errors="replace")[:50000]
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {path}: {e}"


def _safe_list_dir(path: str) -> str:
    try:
        p = Path(path)
        if not p.is_dir():
            return f"Not a directory: {path}"
        items = []
        for entry in sorted(p.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            size = entry.stat().st_size if entry.is_file() else 0
            items.append(f"{entry.name}{suffix} ({size} bytes)" if size else f"{entry.name}{suffix}")
        return "\n".join(items) if items else "(empty directory)"
    except Exception as e:
        return f"Error listing {path}: {e}"


def _run_cmd(command: str, cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=180, cwd=cwd
        )
        output = result.stdout or ""
        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr[-2000:]
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"
        return output[-3000:] if len(output) > 3000 else output
    except subprocess.TimeoutExpired:
        return "Command timed out (180s)"
    except Exception as e:
        return f"Error running command: {e}"


def _edit_file(path: str, old_string: str, new_string: str) -> str:
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        if old_string not in content:
            return f"Could not find target text in {path}"
        content = content.replace(old_string, new_string)
        Path(path).write_text(content, encoding="utf-8")
        return f"File {path} updated successfully"
    except Exception as e:
        return f"Error editing {path}: {e}"


def _write_file(path: str, content: str) -> str:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return f"File {path} written successfully"
    except Exception as e:
        return f"Error writing {path}: {e}"


def _search_web(query: str) -> str:
    try:
        results = web_search(query)
        if not results:
            return "No web results found"
        return "\n".join(
            f"- {r.get('title','?')}: {r.get('url','?')}"
            for r in results[:5]
        )
    except Exception as e:
        return f"Web search failed: {e}"


def _set_env(name: str, value: str) -> str:
    try:
        os.environ[name] = value
        save_key(name, value)
        return f"Environment variable {name} set"
    except Exception as e:
        return f"Error setting env var {name}: {e}"


def _install_package(name: str) -> str:
    try:
        result = subprocess.run(
            f"apt-get install -y {name} 2>/dev/null || pip install {name} 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return f"Package {name} installed successfully"
        return f"Could not install {name}: {result.stderr[:500]}"
    except Exception as e:
        return f"Error installing {name}: {e}"


def _write_env_file(entries: list[dict]) -> str:
    try:
        lines = []
        for entry in entries:
            key = entry.get("key", "")
            val = entry.get("val", "")
            lines.append(f"{key}={val}")
        content = "\n".join(lines)
        Path(".env").write_text(content)
        return f"Written .env with {len(entries)} entries"
    except Exception as e:
        return f"Error writing .env: {e}"


TOOL_DISPATCH = {
    "read_file": lambda args: _safe_read(args.get("path", "")),
    "list_dir": lambda args: _safe_list_dir(args.get("path", "")),
    "run_command": lambda args: _run_cmd(
        args.get("command", ""),
        args.get("cwd")
    ),
    "edit_file": lambda args: _edit_file(
        args.get("path", ""),
        args.get("old_string", ""),
        args.get("new_string", "")
    ),
    "write_file": lambda args: _write_file(
        args.get("path", ""),
        args.get("content", "")
    ),
    "search_web": lambda args: _search_web(args.get("query", "")),
    "set_env": lambda args: _set_env(args.get("name", ""), args.get("value", "")),
    "install_package": lambda args: _install_package(args.get("name", "")),
    "write_env_file": lambda args: _write_env_file(args.get("entries", [])),
}


def agent_run(
    task: str,
    project_path: str,
    max_steps: int = 30,
    console=None,
    plan: dict | None = None,
) -> dict:
    cfg = load_config()
    if not cfg.get("api_key"):
        return {"status": "no_api", "result": "AI agent requires an API key"}

    c = console or _console()

    def cprint(msg):
        if c:
            c.print(msg)

    system = AGENT_SYSTEM_PROMPT + f"\nProject path: {project_path}"

    context = f"""Task: {task}
Project: {project_path}
Project plan: {json.dumps(plan or {})}

Work through this step by step. Use tools to explore, understand, and execute."""

    steps_taken = 0
    last_result = None

    while steps_taken < max_steps:
        steps_taken += 1

        prompt = f"""{context}

Previous result: {last_result if last_result else 'Starting...'}

Step {steps_taken}/{max_steps}. What should I do next?
Respond with JSON: {{"thought": "...", "action": "tool_name or done", "args": {{}}, "done": bool}}"""

        try:
            response = llm_call(prompt, system=system)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
                response = response.rsplit("\n", 1)[0] if response.endswith("```") else response
                response = response.rsplit("```", 1)[0] if "```" in response else response

            action = json.loads(response)
        except Exception as e:
            if c:
                cprint(f"  [yellow]Agent parse error: {e}[/]")
            break

        thought = action.get("thought", "")
        if c:
            cprint(f"  [dim]> Agent: {thought}[/]")

        if action.get("done"):
            return {
                "status": "success",
                "result": action.get("result", ""),
                "steps": steps_taken,
            }

        tool = action.get("action")
        args = action.get("args", {})

        if tool in TOOL_DISPATCH:
            try:
                result = TOOL_DISPATCH[tool](args)
                last_result = result[:2000]
            except Exception as e:
                last_result = f"Tool error: {e}"
        else:
            last_result = f"Unknown tool: {tool}"

    return {
        "status": "max_steps",
        "result": f"Reached max steps ({max_steps})",
        "steps": steps_taken,
        "last_result": last_result,
    }


def agent_process_instructions(
    instructions: str,
    project_path: str,
    plan: dict | None = None,
    console=None,
) -> dict:
    cfg = load_config()
    if not cfg.get("api_key"):
        return {"status": "no_api", "message": "AI agent requires an API key for processing instructions"}

    c = console or _console()

    if c:
        c.print(f"  [cyan]Agent processing your instructions: {instructions[:100]}...[/]")

    result = agent_run(
        f"Process these setup instructions step by step: {instructions}\n\n"
        f"Read the project structure first, then execute each instruction.\n"
        f"If the instruction mentions setting an API key like 'use X api key = Y', "
        f"set it as an environment variable with set_env.\n"
        f"If the instruction says 'install redis' or 'install postgres', use install_package.\n"
        f"If the instruction says 'set all other env random', read .env.example, "
        f"then use write_env_file with random values for each entry.\n"
        f"If the instruction says 'use python3' or similar, use set_env for RUNIT_PYTHON.",
        project_path,
        max_steps=25,
        console=c,
        plan=plan,
    )

    return result


def agent_analyze_project(project_path: str, plan: dict | None = None) -> dict:
    cfg = load_config()
    if not cfg.get("api_key"):
        return {}

    c = _console()

    steps = [
        "Scan project structure and list all files",
        "Read key configuration files (package.json, requirements.txt, Dockerfile, etc.)",
        "Identify the programming language, framework, and entry point",
        "Detect required environment variables and their purpose",
        "Identify required services (databases, caches, message queues)",
        "Create a detailed execution plan with setup steps",
    ]

    findings = {}

    for i, step_task in enumerate(steps, 1):
        if c:
            c.print(f"  [cyan]Agent analyzing: {step_task}[/]")
        result = agent_run(
            step_task,
            project_path,
            max_steps=5,
            console=c,
            plan=plan,
        )
        findings[f"step_{i}"] = result.get("result", "")

    return findings
