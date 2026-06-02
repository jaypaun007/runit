import re
import os


class ErrorType:
    MISSING_MODULE_NODE = "missing_module_node"
    MISSING_MODULE_PYTHON = "missing_module_python"
    MISSING_MODULE_OTHER = "missing_module_other"
    PORT_IN_USE = "port_in_use"
    SERVICE_UNREACHABLE = "service_unreachable"
    MISSING_ENV = "missing_env"
    SYNTAX_ERROR = "syntax_error"
    COMMAND_NOT_FOUND = "command_not_found"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    OUT_OF_MEMORY = "out_of_memory"
    DISK_FULL = "disk_full"
    GIT_ERROR = "git_error"
    NETWORK_ERROR = "network_error"
    VERSION_MISMATCH = "version_mismatch"
    INSTALL_FAILED = "install_failed"
    UNKNOWN = "unknown"


ERROR_PATTERNS = [
    (ErrorType.MISSING_MODULE_NODE, [
        r"Cannot find module ['\"](.+?)['\"]",
        r"Module not found: .+?['\"](.+?)['\"]",
        r"Error: Cannot find module",
        r"MODULE_NOT_FOUND",
    ]),
    (ErrorType.MISSING_MODULE_PYTHON, [
        r"ModuleNotFoundError: No module named ['\"](.+?)['\"]",
        r"ImportError: No module named ['\"](.+?)['\"]",
        r"Could not import ['\"](.+?)['\"]",
    ]),
    (ErrorType.MISSING_MODULE_OTHER, [
        r"cannot find package ['\"](.+?)['\"]",
        r"could not find crate ['\"](.+?)['\"]",
        r"package `(.+?)` not found",
    ]),
    (ErrorType.PORT_IN_USE, [
        r"EADDRINUSE",
        r"Address already in use",
        r"port .+? already in use",
        r"can't bind to port",
        r"Port (\d+) is not available",
        r"listen tcp .+:(\d+): bind: address already in use",
    ]),
    (ErrorType.SERVICE_UNREACHABLE, [
        r"ECONNREFUSED",
        r"Connection refused",
        r"could not connect to server",
        r"Can't connect to .+? server",
        r"connect ECONNREFUSED .+?:(\d+)",
        r"is the server running",
    ]),
    (ErrorType.MISSING_ENV, [
        r"Missing required env(ironment)?( variable)?:?\s*['\"]?(\w+)['\"]?",
        r"process\.env\.(\w+)(?:\s+is not defined|\s+not set)",
        r"env\(['\"](\w+)['\"]\)",
        r"required environment variable ['\"]?(\w+)['\"]? (is not set|not provided|missing)",
        r"Please set the (\w+) environment variable",
    ]),
    (ErrorType.SYNTAX_ERROR, [
        r"SyntaxError:",
        r"Syntax error",
        r"Unexpected token",
        r"Parse error",
        r"Unexpected identifier",
    ]),
    (ErrorType.COMMAND_NOT_FOUND, [
        r"command not found:?\s*(\S+)",
        r"(\S+): (command )?not found",
        r"Could not find command",
        r"is not recognized",
        r"which: no (\S+) in",
    ]),
    (ErrorType.TIMEOUT, [
        r"Timeout(Error)?",
        r"timed out",
        r"ETIMEDOUT",
        r"operation timed out",
    ]),
    (ErrorType.PERMISSION_DENIED, [
        r"Permission denied",
        r"EACCES",
        r"EPERM",
        r"not permitted",
    ]),
    (ErrorType.OUT_OF_MEMORY, [
        r"Out of memory",
        r"Killed",
        r"allocation failed",
        r"ENOMEM",
        r"JavaScript heap out of memory",
    ]),
    (ErrorType.DISK_FULL, [
        r"No space left on device",
        r"ENOSPC",
        r"disk quota exceeded",
    ]),
    (ErrorType.GIT_ERROR, [
        r"fatal: not a git repository",
        r"fatal: couldn't find remote ref",
        r"Could not read from remote repository",
        r"Repository not found",
    ]),
    (ErrorType.NETWORK_ERROR, [
        r"ENOTFOUND",
        r"ENETUNREACH",
        r"getaddrinfo ENOTFOUND",
        r"Network is unreachable",
        r"couldn't connect to host",
        r"socket hang up",
    ]),
    (ErrorType.VERSION_MISMATCH, [
        r"version mismatch",
        r"requires .+? but you have",
        r"incompatible",
        r"ERR_PNPM_NO_MATCHING_VERSION",
        r"doesn't satisfy",
        r"not a supported version",
    ]),
    (ErrorType.INSTALL_FAILED, [
        r"npm ERR!",
        r"ERR_PNPM_FETCH_404",
        r"ERR_PNPM_NO_MATCHING_VERSION",
        r"Could not resolve dependency",
        r"Conflicting peer dependency",
        r"pip .+? failed",
        r"failed to build",
    ]),
]


def classify_error(output: str) -> dict:
    if not output:
        return {"type": ErrorType.UNKNOWN, "detail": "", "hints": []}

    for error_type, patterns in ERROR_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                detail = match.group(0)
                groups = [g for g in match.groups() if g]
                return {
                    "type": error_type,
                    "detail": detail,
                    "captures": groups,
                    "pattern": pattern,
                }

    return {"type": ErrorType.UNKNOWN, "detail": output[:200], "captures": [], "pattern": ""}


AUTO_HEALERS = {}

def _heal_port_in_use(error: dict) -> dict:
    captured = error.get("captures", [])
    port = int(captured[0]) if captured and captured[0].isdigit() else 3000
    new_port = port + 1
    return {
        "action": "change_port",
        "old_port": port,
        "new_port": new_port,
        "cmd": None,
        "message": f"Port {port} in use, switching to {new_port}",
    }

def _heal_missing_module_node(error: dict) -> dict:
    captured = error.get("captures", [])
    module = captured[0] if captured else ""
    if module:
        return {
            "action": "install_module",
            "module": module,
            "cmd": f"npm install {module}",
            "message": f"Installing missing Node module: {module}",
        }
    return {"action": "install_all", "cmd": "npm install", "message": "Installing all dependencies"}

def _heal_missing_module_python(error: dict) -> dict:
    captured = error.get("captures", [])
    module = captured[0] if captured else ""
    if module:
        return {
            "action": "install_module",
            "module": module,
            "cmd": f"pip install {module}",
            "message": f"Installing missing Python module: {module}",
        }
    return {"action": "install_all", "cmd": "pip install -r requirements.txt 2>/dev/null || pip install .", "message": "Installing Python dependencies"}

def _heal_command_not_found(error: dict) -> dict:
    captured = error.get("captures", [])
    cmd = captured[0] if captured else ""
    installers = {
        "pnpm": "npm install -g pnpm",
        "yarn": "npm install -g yarn",
        "bun": "npm install -g bun",
        "ts-node": "npm install -g ts-node",
        "typescript": "npm install -g typescript",
        "nodemon": "npm install -g nodemon",
        "npx": "",  # comes with npm
        "python3": "apt-get install -y python3",
        "pip3": "apt-get install -y python3-pip",
        "pip": "apt-get install -y python3-pip",
        "node": "apt-get install -y nodejs",
        "npm": "apt-get install -y npm",
        "git": "apt-get install -y git",
        "make": "apt-get install -y build-essential",
        "gcc": "apt-get install -y build-essential",
        "g++": "apt-get install -y build-essential",
        "pg_isready": "apt-get install -y postgresql-client",
        "redis-cli": "apt-get install -y redis-tools",
        "mysql": "apt-get install -y mysql-client",
        "mongosh": "apt-get install -y mongodb-mongosh",
    }
    install_cmd = installers.get(cmd, f"apt-get install -y {cmd} 2>/dev/null || npm install -g {cmd}")
    return {
        "action": "install_command",
        "command": cmd,
        "cmd": install_cmd,
        "message": f"Installing missing command: {cmd}",
    }

def _heal_missing_env(error: dict) -> dict:
    captured = error.get("captures", [])
    var_name = captured[-1] if captured else ""
    return {
        "action": "set_env",
        "var": var_name,
        "cmd": None,
        "message": f"Need to set environment variable: {var_name}" if var_name else "Need to resolve env vars",
    }

def _heal_version_mismatch(error: dict) -> dict:
    return {
        "action": "retry_with_flags",
        "cmd": None,
        "flags": "--ignore-scripts --no-optional --legacy-peer-deps",
        "message": "Retrying with relaxed dependency flags",
    }


AUTO_HEALERS = {
    ErrorType.MISSING_MODULE_NODE: _heal_missing_module_node,
    ErrorType.MISSING_MODULE_PYTHON: _heal_missing_module_python,
    ErrorType.MISSING_MODULE_OTHER: _heal_missing_module_node,
    ErrorType.PORT_IN_USE: _heal_port_in_use,
    ErrorType.COMMAND_NOT_FOUND: _heal_command_not_found,
    ErrorType.MISSING_ENV: _heal_missing_env,
    ErrorType.VERSION_MISMATCH: _heal_version_mismatch,
    ErrorType.INSTALL_FAILED: _heal_version_mismatch,
}


def get_auto_heal(output: str) -> dict | None:
    error = classify_error(output)
    if error["type"] == ErrorType.UNKNOWN:
        return None
    healer = AUTO_HEALERS.get(error["type"])
    if not healer:
        return None
    heal_plan = healer(error)
    return {
        "error": error,
        "heal": heal_plan,
    }
