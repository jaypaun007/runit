import os
import sys
import json
import subprocess
from pathlib import Path

from runit.config import load_config
from runit.llm import llm_call
from runit.web_tools import web_search
from runit.cli import _console, print_step, FORCE_PLAIN

AGENT_SYSTEM_PROMPT = """You are Runit Agent v1.2, an autonomous AI coding agent.
Your job is to analyze projects, plan execution steps, run commands, and modify code.

You have these tools available:
1. read_file(path) - Read file contents
2. search_web(query) - Search for solutions online  
3. list_dir(path) - List directory contents
4. run_command(cmd) - Execute a shell command
5. edit_file(path, old, new) - Modify a file
6. write_file(path, content) - Write a new file

Always respond in this JSON format:
{"thought": "brief analysis", "action": "tool_name", "args": {...}, "done": false}
Or when complete:
{"thought": "task complete", "action": "done", "result": "...", "done": true}

Be concise. Execute one step at a time."""


def _safe_read(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        if p.stat().st_size > 50000:
            return f"File too large ({p.stat().st_size} bytes), showing first 1000 lines:\n" + p.read_text(encoding="utf-8", errors="replace")[:50000]
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
            timeout=120, cwd=cwd
        )
        output = result.stdout or ""
        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr[-2000:]
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"
        return output[-3000:] if len(output) > 3000 else output
    except subprocess.TimeoutExpired:
        return "Command timed out (120s)"
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



