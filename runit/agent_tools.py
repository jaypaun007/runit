import os
import re
import json
import time
import subprocess
from pathlib import Path

from runit.web_tools import web_search, fetch_github_readme
from runit.service_manager import ServiceManager, service_name_from_env
from runit.env_resolver import EnvResolver
from runit.process_monitor import ProcessMonitor
from runit.config import save_key


_shared_state = {
    "service_manager": None,
    "process_monitor": None,
    "env_resolver": None,
    "project_path": None,
}


def _init_state(project_path: str, env_type: str = "local"):
    _shared_state["project_path"] = project_path
    _shared_state["service_manager"] = ServiceManager(env_type=env_type)
    _shared_state["service_manager"].set_project_path(project_path)
    _shared_state["process_monitor"] = ProcessMonitor(project_path)
    _shared_state["env_resolver"] = EnvResolver(project_path, _shared_state["service_manager"])
    return _shared_state


# ── Analysis Tools ──

def tool_read_file(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    full = Path(project_path) / path if not path.startswith("/") else Path(path)
    try:
        if not full.exists():
            return {"ok": False, "error": f"File not found: {full}", "_text": f"File not found: {full}"}
        if full.stat().st_size > 100000:
            content = full.read_text(errors="replace")[:50000]
            return {"ok": True, "content": content, "truncated": True, "_text": content[:2000]}
        content = full.read_text(errors="replace")
        return {"ok": True, "content": content, "_text": content[:2000]}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Error: {e}"}


def tool_read_files(project_path: str, args: dict) -> dict:
    paths = args.get("paths", [])
    results = {}
    for p in paths:
        full = Path(project_path) / p if not p.startswith("/") else Path(p)
        try:
            if full.exists() and full.stat().st_size < 100000:
                results[p] = full.read_text(errors="replace")[:10000]
        except Exception:
            results[p] = "(error reading)"
    return {"ok": True, "files": results, "_text": f"Read {len(results)} files"}


def tool_list_dir(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    full = Path(project_path) / path if path else Path(project_path)
    try:
        if not full.is_dir():
            return {"ok": False, "error": f"Not a directory: {full}", "_text": f"Not a directory"}
        items = []
        for entry in sorted(full.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            items.append(f"{entry.name}{suffix}")
        return {"ok": True, "items": items, "_text": "\n".join(items[:50])}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Error: {e}"}


def tool_search_code(project_path: str, args: dict) -> dict:
    pattern = args.get("pattern", "")
    include = args.get("include", "*")
    matches = []
    try:
        for f in Path(project_path).rglob(include):
            if f.is_dir() or f.name in ("node_modules", ".git"):
                continue
            try:
                content = f.read_text(errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        matches.append({"file": str(f.relative_to(project_path)), "line": i, "text": line.strip()[:200]})
            except Exception:
                continue
        return {"ok": True, "matches": matches[:50], "_text": f"Found {len(matches)} matches"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Error: {e}"}


def tool_research_project(project_path: str, args: dict) -> dict:
    url = args.get("url", "")
    data = {"readme": "", "ci_config": "", "package_config": "", "scripts": [], "deps": [], "web_results": []}

    # FIRST: read local files — always works
    local_readme = Path(project_path) / "README.md"
    if local_readme.exists():
        data["readme"] = local_readme.read_text(errors="replace")[:5000]

    for pkg in ["package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Gemfile", "composer.json"]:
        full = Path(project_path) / pkg
        if full.exists():
            data["package_config"] = full.read_text(errors="replace")[:3000]
            break

    ci_paths = [".github/workflows/ci.yml", ".github/workflows/main.yml",
                ".gitlab-ci.yml", "Jenkinsfile"]
    for cp in ci_paths:
        full = Path(project_path) / cp
        if full.exists():
            data["ci_config"] = full.read_text(errors="replace")[:3000]
            break

    env_examples = list(Path(project_path).glob(".env*"))
    if env_examples:
        data["env_examples"] = [e.name for e in env_examples]

    data["file_tree"] = [str(f.relative_to(project_path)) for f in sorted(Path(project_path).iterdir())
                         if not f.name.startswith(".") and not f.name.startswith("node_modules")]

    # THEN: try remote
    try:
        if url and ("github.com" in url or "http" in url):
            readme = fetch_github_readme(url)
            if readme:
                data["readme_remote"] = readme[:3000]
    except Exception:
        pass

    try:
        name = url.rstrip("/").split("/")[-1] if url else Path(project_path).name
        results = web_search(f"how to run {name} {Path(project_path).name} setup guide")
        data["web_results"] = [r.get("title", "") + ": " + r.get("url", "") for r in results[:5]]
    except Exception:
        pass

    return {"ok": True, "research": data, "_text": f"Project analysis: {len(data.get('file_tree', []))} files, README: {len(data.get('readme', ''))} chars, config: {bool(data.get('package_config'))}"}


# ── Service Tools ──

def tool_install_service(project_path: str, args: dict) -> dict:
    name = args.get("name", "").lower()
    sm = _shared_state.get("service_manager")
    if not sm:
        return {"ok": False, "error": "Service manager not initialized", "_text": "Service manager not initialized"}
    result = sm.install(name)
    if result.get("ok"):
        return {"ok": True, "service": name, "url": result.get("url", ""), "message": result.get("message", ""),
                "_text": f"Installed {name}: {result.get('url', 'ok')}"}
    return {"ok": False, "error": result.get("error", f"Failed to install {name}"), "_text": result.get("error", f"Failed {name}")}


def tool_start_service(project_path: str, args: dict) -> dict:
    name = args.get("name", "").lower()
    sm = _shared_state.get("service_manager")
    if not sm:
        return {"ok": False, "error": "Service manager not initialized", "_text": "Not initialized"}
    result = sm.start(name)
    return {"ok": result.get("ok", False), "service": name, "url": result.get("url", ""),
            "_text": result.get("message", result.get("error", "unknown"))}


def tool_stop_service(project_path: str, args: dict) -> dict:
    name = args.get("name", "").lower()
    sm = _shared_state.get("service_manager")
    if not sm:
        return {"ok": False, "error": "Not initialized", "_text": "Not initialized"}
    result = sm.stop(name)
    return {"ok": result.get("ok", False), "_text": result.get("message", result.get("error", "unknown"))}


def tool_service_health(project_path: str, args: dict) -> dict:
    name = args.get("name", "").lower()
    sm = _shared_state.get("service_manager")
    if not sm:
        return {"ok": False, "error": "Not initialized", "_text": "Not initialized"}
    result = sm.health(name)
    return {"ok": result.get("ok", False), **result, "_text": f"{'Healthy' if result.get('ok') else 'Unhealthy'}: {name}"}


# ── Environment Tools ──

def tool_set_env(project_path: str, args: dict) -> dict:
    name = args.get("name", "")
    value = args.get("value", "")
    os.environ[name] = value
    save_key(name, value)
    return {"ok": True, "var": name, "set": True, "_text": f"Set {name}"}


def tool_write_env(project_path: str, args: dict) -> dict:
    entries = args.get("entries", [])
    env_path = Path(project_path) / ".env"
    lines = []
    for entry in entries:
        key = entry.get("key", "") or entry.get("name", "")
        val = entry.get("value", "") or entry.get("val", "")
        if key:
            lines.append(f"{key}={val}")
            os.environ[key] = val
    env_path.write_text("\n".join(lines) + "\n")
    return {"ok": True, "count": len(lines), "file": str(env_path), "_text": f"Wrote {len(lines)} entries to .env"}


def tool_resolve_env(project_path: str, args: dict) -> dict:
    er = _shared_state.get("env_resolver")
    if not er:
        er = EnvResolver(project_path, _shared_state.get("service_manager"))
        _shared_state["env_resolver"] = er

    var_names = args.get("vars", None)
    ask_user_cb = None

    def ask_cb(var):
        from runit.cli import AUTO_YES
        if AUTO_YES:
            return ""
        try:
            val = input(f"  \U0001f511 Enter value for {var}: ")
            return val.strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    resolved = er.resolve_all(var_names=var_names, ask_user_callback=ask_cb)
    if resolved:
        er.generate_env_file(resolved)
    return {"ok": True, "env": resolved, "categories": er.categories,
            "_text": f"Resolved {len(resolved)} env vars"}


# ── Execution Tools ──

def tool_run_command(project_path: str, args: dict) -> dict:
    cmd = args.get("command", "") or args.get("cmd", "")
    cwd = args.get("cwd") or project_path
    timeout = args.get("timeout", 180)
    print(f"  \U0001f4bb  {cmd[:200]}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, timeout=timeout,
        )
        output = result.stdout or ""
        if result.stderr:
            stderr = result.stderr[-2000:]
            if stderr.strip():
                output += "\nSTDERR:\n" + stderr
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"
        tail = output[-3000:]
        if tail.strip() and result.returncode == 0:
            print(f"    \u2b07  {tail[:500].strip()}")
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "output": tail,
            "_text": output[-1500:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out ({timeout}s)", "_text": f"Timed out ({timeout}s)"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Error: {e}"}


def tool_install_deps(project_path: str, args: dict) -> dict:
    cmd = args.get("command", "") or args.get("cmd", "")
    if not cmd:
        return {"ok": False, "error": "No command specified", "_text": "No command"}

    for attempt in range(3):
        time.sleep(attempt * 2)
        result = tool_run_command(project_path, {"command": cmd, "timeout": 300})
        if result.get("ok"):
            return {**result, "_text": f"Deps installed (attempt {attempt + 1})"}
        if "ERR_PNPM_NO_MATCHING_VERSION" in result.get("_text", ""):
            relaxed = cmd + " --ignore-scripts --no-optional --legacy-peer-deps"
            result = tool_run_command(project_path, {"command": relaxed, "timeout": 300})
            if result.get("ok"):
                return {**result, "_text": f"Deps installed with relaxed flags"}
        if attempt < 2:
            error = result.get("_text", "")
            heal = _try_heal(error, project_path)
            if heal:
                result = tool_run_command(project_path, {"command": cmd, "timeout": 300})
                if result.get("ok"):
                    return {**result, "_text": f"Deps installed after heal"}

    return {"ok": False, "error": "Install failed after 3 attempts", "_text": "Install failed after 3 attempts"}


def _try_heal(error: str, project_path: str) -> bool:
    if "command not found" in error.lower():
        for line in error.splitlines():
            m = re.search(r'(\S+): not found', line)
            if m:
                cmd = m.group(1)
                subprocess.run(f"apt-get install -y {cmd} 2>/dev/null || npm install -g {cmd} 2>/dev/null",
                               shell=True, capture_output=True, timeout=60)
                return True
    return False


def tool_run_project(project_path: str, args: dict) -> dict:
    cmd = args.get("command", "") or args.get("cmd", "")
    env = args.get("env", None)
    pm = _shared_state.get("process_monitor")
    if not pm:
        pm = ProcessMonitor(project_path)
        _shared_state["process_monitor"] = pm

    print(f"  \U000025b6  {cmd[:200]}")
    result = pm.detect_server_url(cmd, env=env)
    if result.get("ok"):
        msg = f"Running: PID {result.get('pid')}, URL: {result.get('url', 'unknown')}"
        print(f"    \u2705  {msg}")
        return {"ok": True, "pid": result.get("pid"), "port": result.get("port"),
                "url": result.get("url"), "logfile": result.get("logfile"),
                "_text": msg}
    return {"ok": False, "error": result.get("error", "Failed to start"), "_text": result.get("error", "Failed")}


def tool_check_process(project_path: str, args: dict) -> dict:
    pid = args.get("pid", 0)
    pm = _shared_state.get("process_monitor")
    if not pm:
        return {"ok": False, "error": "No process monitor", "_text": "No monitor"}
    running = pm.is_running(pid)
    log = pm.read_log(pid) if running else ""
    return {"ok": running, "running": running, "log": log[-1000:],
            "_text": f"Process {pid}: {'running' if running else 'stopped'}"}


def tool_stop_process(project_path: str, args: dict) -> dict:
    pid = args.get("pid", 0)
    pm = _shared_state.get("process_monitor")
    if not pm:
        return {"ok": False, "error": "No process monitor", "_text": "No monitor"}
    result = pm.stop(pid)
    return {"ok": result, "_text": f"Stopped PID {pid}" if result else f"Failed to stop PID {pid}"}


def tool_wait_for_port(project_path: str, args: dict) -> dict:
    port = args.get("port", 0)
    timeout = args.get("timeout", 30)
    pm = _shared_state.get("process_monitor")
    if not pm:
        return {"ok": False, "error": "No process monitor", "_text": "No monitor"}
    import socket
    for _ in range(timeout):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            r = s.connect_ex(("localhost", port))
            s.close()
            if r == 0:
                return {"ok": True, "port": port, "_text": f"Port {port} is open"}
        except Exception:
            pass
        time.sleep(1)
    return {"ok": False, "error": f"Port {port} not open after {timeout}s", "_text": f"Port {port} timeout"}


# ── File Tools ──

def tool_edit_file(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    old = args.get("old_string", "") or args.get("old", "")
    new = args.get("new_string", "") or args.get("new", "")
    full = Path(project_path) / path if not path.startswith("/") else Path(path)
    try:
        content = full.read_text(errors="replace")
        if old not in content:
            return {"ok": False, "error": "String not found", "_text": "Edit failed: string not found"}
        content = content.replace(old, new)
        full.write_text(content)
        return {"ok": True, "_text": f"Edited {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Edit error: {e}"}


def tool_write_file(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    content = args.get("content", "")
    full = Path(project_path) / path if not path.startswith("/") else Path(path)
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return {"ok": True, "_text": f"Written {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Write error: {e}"}


def tool_patch_file(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    old_lines = args.get("old_lines", [])
    new_lines = args.get("new_lines", [])
    full = Path(project_path) / path if not path.startswith("/") else Path(path)
    try:
        content = full.read_text(errors="replace")
        old_text = "\n".join(old_lines)
        new_text = "\n".join(new_lines)
        if old_text not in content:
            return {"ok": False, "error": "Lines not found", "_text": "Patch failed: lines not found"}
        content = content.replace(old_text, new_text)
        full.write_text(content)
        return {"ok": True, "_text": f"Patched {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Patch error: {e}"}


# ── User Interaction Tools ──

def tool_ask_user(project_path: str, args: dict) -> dict:
    question = args.get("question", "")
    secret = args.get("secret", False)
    from runit.cli import AUTO_YES
    if AUTO_YES:
        return {"ok": True, "value": "", "skipped": True, "_text": "Skipped (auto_yes)"}
    try:
        prompt = f"  \U0001f4ac Agent asks: {question}"
        if secret:
            val = input(f"{prompt}: ")
        else:
            val = input(f"{prompt}: ")
        return {"ok": True, "value": val.strip(), "_text": f"User responded ({'secret' if secret else val[:50]})"}
    except (EOFError, KeyboardInterrupt):
        return {"ok": True, "value": "", "skipped": True, "_text": "User skipped"}


def tool_notify(project_path: str, args: dict) -> dict:
    msg = args.get("message", "") or args.get("msg", "")
    print(f"  \U0001f514 {msg}")
    return {"ok": True, "_text": f"Notified: {msg[:100]}"}


# ── New v2.1.2 Tools ──

def tool_delete_file(project_path: str, args: dict) -> dict:
    path = args.get("path", "")
    full = Path(project_path) / path if not path.startswith("/") else Path(path)
    try:
        if not full.exists():
            return {"ok": False, "error": f"File not found: {full}", "_text": f"File not found: {full}"}
        full.unlink()
        return {"ok": True, "_text": f"Deleted: {full}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Error deleting: {e}"}


def tool_web_search(project_path: str, args: dict) -> dict:
    query = args.get("query", "") or args.get("q", "")
    if not query:
        return {"ok": False, "error": "No query", "_text": "No query provided"}
    try:
        result = web_search(query)
        return {"ok": True, "result": result, "_text": str(result)[:2000]}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Search error: {e}"}


def tool_detect_ports(project_path: str, args: dict) -> dict:
    try:
        r = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10
        )
        ports = re.findall(r":(\d+)", r.stdout)
        return {"ok": True, "ports": ports, "raw": r.stdout, "_text": f"Open ports: {', '.join(ports[:20])}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Port detection error: {e}"}


def tool_read_logs(project_path: str, args: dict) -> dict:
    log_path = args.get("path", "") or args.get("logfile", "")
    lines_n = args.get("lines", 50)
    if not log_path:
        return {"ok": False, "error": "No log path", "_text": "No log path provided"}
    full = Path(log_path) if log_path.startswith("/") else Path(project_path) / log_path
    try:
        if not full.exists():
            return {"ok": False, "error": f"Log not found: {full}", "_text": f"Log not found: {full}"}
        r = subprocess.run(
            ["tail", f"-{lines_n}", str(full)],
            capture_output=True, text=True, timeout=10
        )
        return {"ok": True, "content": r.stdout, "_text": r.stdout[:2000]}
    except Exception as e:
        return {"ok": False, "error": str(e), "_text": f"Log read error: {e}"}


# ── Tool Registry ──

TOOLS = {
    "read_file": tool_read_file,
    "read_files": tool_read_files,
    "list_dir": tool_list_dir,
    "search_code": tool_search_code,
    "research_project": tool_research_project,
    "install_service": tool_install_service,
    "start_service": tool_start_service,
    "stop_service": tool_stop_service,
    "service_health": tool_service_health,
    "set_env": tool_set_env,
    "write_env": tool_write_env,
    "resolve_env": tool_resolve_env,
    "run_command": tool_run_command,
    "install_deps": tool_install_deps,
    "run_project": tool_run_project,
    "check_process": tool_check_process,
    "stop_process": tool_stop_process,
    "wait_for_port": tool_wait_for_port,
    "edit_file": tool_edit_file,
    "write_file": tool_write_file,
    "delete_file": tool_delete_file,
    "patch_file": tool_patch_file,
    "web_search": tool_web_search,
    "detect_ports": tool_detect_ports,
    "read_logs": tool_read_logs,
    "ask_user": tool_ask_user,
    "notify": tool_notify,
}
