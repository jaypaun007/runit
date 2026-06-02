import json
import re
from runit.llm import llm_call
from runit.deps import install
from runit.web_tools import search_error_online
from runit.cli import print_web_research

FIX_SYSTEM_PROMPT = """You are Runit, an AI error-fixing agent. Given an error log and project context, determine the fix.

Allowed fixes:
- install_module: Missing Python module
- change_entry: Wrong entry file
- set_env: Missing environment variable
- change_port: Port already in use
- install_npm: Missing npm package
- install_system: System tool required
- need_api_key: Error is due to missing API key or auth token
- other: Something else

Return ONLY valid JSON:
{
  "fix_type": "install_module|change_entry|set_env|change_port|install_npm|install_system|need_api_key|other",
  "target": "name of module/file/variable",
  "value": "value to set or file path",
  "explanation": "what went wrong in plain english"
}"""


def _extract_missing_modules(stderr: str) -> list[str]:
    modules = []
    patterns = [
        r"ModuleNotFoundError: No module named ['\"](.+?)['\"]",
        r"ImportError: No module named ['\"](.+?)['\"]",
        r"cannot import name ['\"](.+?)['\"]",
        r"Error: Cannot find module ['\"](.+?)['\"]",
        r"ERR_MODULE_NOT_FOUND.*['\"](.+?)['\"]",
    ]
    for p in patterns:
        modules.extend(re.findall(p, stderr))
    return modules


MISSING_KEY_PATTERNS = [
    r"(?:api[_-]?key|API[_-]?KEY|apikey).*?(?:not found|missing|required|not set|empty)",
    r"(?:missing|required|not found).*?(?:api[_-]?key|API[_-]?KEY|apikey)",
    r"environment variable.*?(?:not set|missing|required)",
    r"(?:token|TOKEN).*?(?:missing|required|not found|invalid)",
    r"Authentication.*?(?:required|failed|missing)",
    r"unauthorized",
    r"401",
    r"403",
    r"access.*?denied",
    r"no.*?credentials",
]


def _detect_missing_key(error_log: str) -> str | None:
    for pattern in MISSING_KEY_PATTERNS:
        m = re.search(pattern, error_log, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


_PORT_PATTERNS = [
    r"Address already in use",
    r"EADDRINUSE",
    r"port.*?(?:in use|occupied|taken)",
    r"Can't listen on port",
]


def _detect_port_conflict(error_log: str) -> bool:
    for p in _PORT_PATTERNS:
        if re.search(p, error_log, re.IGNORECASE):
            return True
    return False


def _extract_missing_env_vars(error_log: str, known_env: list[str]) -> list[str]:
    missing = []
    for var in known_env:
        if var.lower() in error_log.lower():
            missing.append(var)
    if not missing:
        m = re.search(r"(?:environment variable|env) ['\"]?(\w+)['\"]?", error_log, re.IGNORECASE)
        if m:
            missing.append(m.group(1))
    return missing


def _extract_port_from_error(error_log: str) -> str | None:
    m = re.search(r"(?:port\s+)(\d{4,5})", error_log, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4,5})\s*(?:in use|occupied)", error_log, re.IGNORECASE)
    return m.group(1) if m else None


def fix_error(error_log: str, plan: dict, project_path: str) -> dict:
    missing = _extract_missing_modules(error_log)
    if missing:
        return {
            "fix_type": "install_module",
            "target": missing[0],
            "value": missing[0],
            "explanation": f"Missing module: {missing[0]}"
        }

    if _detect_port_conflict(error_log):
        port = _extract_port_from_error(error_log) or "8000"
        return {
            "fix_type": "change_port",
            "target": port,
            "value": str(int(port) + 1),
            "explanation": f"Port {port} is in use, trying next port"
        }

    known_env = plan.get("required_env", [])
    missing_env = _extract_missing_env_vars(error_log, known_env)
    if missing_env:
        return {
            "fix_type": "need_api_key",
            "target": missing_env[0],
            "value": "",
            "explanation": f"Project requires environment variable: {missing_env[0]}"
        }

    key_hint = _detect_missing_key(error_log)
    if key_hint:
        return {
            "fix_type": "need_api_key",
            "target": "API_KEY",
            "value": "",
            "explanation": f"Error suggests missing API key or token. Hint: {key_hint[:100]}"
        }

    prompt = (
        f"Project: {json.dumps(plan, indent=2)}\n\n"
        f"Error log:\n{error_log[-3000:]}\n\n"
        "What fix should be applied? If this requires a user API key or token, respond with fix_type 'need_api_key'."
    )

    try:
        response = llm_call(prompt, system=FIX_SYSTEM_PROMPT)
        fix = json.loads(response)
    except (json.JSONDecodeError, Exception):
        fix = {
            "fix_type": "other",
            "target": "",
            "value": "",
            "explanation": "Could not determine fix automatically"
        }

    fix.setdefault("fix_type", "other")
    fix.setdefault("target", "")
    fix.setdefault("value", "")
    fix.setdefault("explanation", "No explanation")

    return fix


def apply_fix(fix: dict, plan: dict, project_path: str) -> dict:
    fix_type = fix.get("fix_type", "")
    target = fix.get("target", "")
    value = fix.get("value", "")
    explanation = fix.get("explanation", "")

    print(f"  \U0001f527 Applying fix: {explanation}")

    if fix_type == "install_module":
        install(plan, project_path, extra_modules=[target])
        plan.setdefault("_installed_modules", [])
        if target not in plan["_installed_modules"]:
            plan["_installed_modules"].append(target)
        return {"plan": plan, "applied": True}

    if fix_type == "install_npm":
        import subprocess as _subprocess
        try:
            _subprocess.check_call(
                ["npm", "install", target],
                cwd=project_path,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return {"plan": plan, "applied": True}
        except _subprocess.CalledProcessError:
            print(f"  \u26a0\ufe0f npm install {target} failed")
            return {"plan": plan, "applied": False}

    if fix_type == "change_entry":
        if value:
            plan["entry"] = value
        elif target and target not in plan.get("fallbacks", []):
            plan.setdefault("fallbacks", []).insert(0, target)
        return {"plan": plan, "applied": True}

    if fix_type == "change_port":
        new_port = value or "8080"
        print(f"  \U0001f4e1 Trying port {new_port}")
        import os
        os.environ["PORT"] = new_port
        os.environ["SERVER_PORT"] = new_port
        return {"plan": plan, "applied": True}

    if fix_type == "set_env":
        import os
        os.environ[target] = value
        return {"plan": plan, "applied": True}

    if fix_type == "need_api_key":
        print(f"  \U0001f511 Project requires: {target}")
        return {"plan": plan, "applied": True, "ask_user": True}

    return {"plan": plan, "applied": False}


def research_error_online(error_log: str, plan: dict) -> list[dict]:
    """Search the web for error solutions."""
    error_snippet = error_log[:200].strip()
    if not error_snippet:
        return []
    results = search_error_online(error_snippet)
    if results:
        print_web_research(results)
    return results
