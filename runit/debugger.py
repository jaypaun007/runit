import json
import re
import os
import sys
from pathlib import Path

from runit.llm import llm_call
from runit.web_tools import search_error_online
from runit.cli import print_web_research, _console

DEBUGGER_SYSTEM_PROMPT = """You are Runit Debugger, an advanced AI debugging agent.
Given error logs, source code context, and project info, determine the root cause and fix.

Analyze deeply — check for:
- Import/module errors across all languages
- Syntax errors, type mismatches, null pointer risks
- Missing environment configs or API keys
- Version incompatibilities
- Port/address conflicts
- Permission or filesystem issues
- Network connectivity problems

Return ONLY valid JSON in this schema:
{
  "root_cause": "brief description of what went wrong",
  "confidence": 0.0-1.0,
  "fix_type": "install_module|change_entry|set_env|change_port|install_npm|install_system|need_api_key|patch_code|version_mismatch|other",
  "target": "module name / file path / variable",
  "value": "value to set or suggested fix",
  "code_patch": "suggested code diff or fix (if applicable)",
  "explanation": "detailed explanation for the user",
  "manual_steps": ["step 1", "step 2"]
}"""


LANGUAGE_ERROR_PATTERNS = {
    "python": {
        "syntax": [
            r"SyntaxError:.*",
            r"IndentationError:.*",
            r"TabError:.*",
            r"NameError: name ['\"](.+?)['\"] is not defined",
            r"TypeError:.*",
            r"ValueError:.*",
            r"KeyError:.*",
            r"AttributeError:.*",
            r"IndexError:.*",
            r"ImportError:.*",
            r"ModuleNotFoundError: No module named ['\"](.+?)['\"]",
            r"OSError:.*",
            r"PermissionError:.*",
            r"FileNotFoundError:.*",
            r"ConnectionError:.*",
            r"TimeoutError:.*",
            r"RecursionError:.*",
            r"RuntimeWarning:.*",
            r"DeprecationWarning:.*",
        ],
        "version": [
            r"RuntimeError:.*Python\s+\d+\.\d+.*",
            r"requires Python >=? (\d+\.\d+)",
            r"pip.*version.*(\d+\.\d+\.\d+)",
        ],
    },
    "node": {
        "syntax": [
            r"SyntaxError:.*",
            r"ReferenceError:.*",
            r"TypeError:.*",
            r"RangeError:.*",
            r"Error: Cannot find module ['\"](.+?)['\"]",
            r"ERR_MODULE_NOT_FOUND",
            r"ERR_REQUIRE_ESM",
            r"ERR_INVALID_ARG_TYPE",
            r"ERR_INVALID_URL",
            r"ERR_UNSUPPORTED_DIR_IMPORT",
            r"EACCES.*",
            r"EADDRINUSE",
            r"ECONNREFUSED",
            r"ECONNRESET",
            r"ENOENT.*",
            r"ERR_HTTP_HEADERS_SENT",
        ],
        "version": [
            r"requires Node\.js (\d+\.\d+\.\d+)",
            r"Minimum supported Node\.js version is (\d+\.\d+)",
        ],
    },
    "rust": {
        "syntax": [
            r"error\[E(\d+)\]:.*",
            r"error: aborting due to",
            r"could not compile",
            r"error: could not find",
            r"error\[E0308\]:.*mismatch",
            r"error\[E0432\]:.*import",
            r"error\[E0425\]:.*not found",
            r"error\[E0499\]:.*borrow",
            r"error\[E0502\]:.*borrow",
            r"error\[E0382\]:.*use after move",
        ],
        "version": [
            r"requires rustc (\d+\.\d+)",
            r"edition (\d+) is unstable",
        ],
    },
    "go": {
        "syntax": [
            r"undefined:.*",
            r"cannot find package",
            r"cannot use.*as.*",
            r"unexpected.*in.*",
            r"import cycle",
            r"unused variable",
            r"unused import",
            r"expected.*found.*",
            r"syntax error:.*",
        ],
        "version": [
            r"requires go (\d+\.\d+)",
        ],
    },
    "ruby": {
        "syntax": [
            r"syntax error,.*",
            r"undefined method.*",
            r"uninitialized constant.*",
            r"cannot load such file.*",
            r"Gem::LoadError:.*",
            r"bundler:.*",
            r"LoadError:.*",
        ],
    },
}


ERROR_HINTS = {
    "missing_api_key": [
        r"(?:api[_-]?key|API[_-]?KEY|apikey).*?(?:not found|missing|required|not set|empty|invalid)",
        r"(?:missing|required|not found|invalid).*?(?:api[_-]?key|API[_-]?KEY|apikey)",
        r"environment variable.*?(?:not set|missing|required)",
        r"(?:token|TOKEN|secret).*?(?:missing|required|not found|invalid)",
        r"Authentication.*?(?:required|failed|missing|invalid)",
        r"unauthorized",
        r"401|403",
        r"access.*?denied",
        r"no.*?credentials",
        r"credential.*?(?:missing|invalid|not found)",
        r"auth.*?(?:fail|required|missing)",
    ],
    "port_conflict": [
        r"Address already in use",
        r"EADDRINUSE",
        r"port.*?(?:in use|occupied|taken|already used)",
        r"Can't listen on port",
        r"bind.*(?:failed|error).*\d+",
        r"listen tcp.*bind.*already in use",
        r"port.*(\d+).*already",
    ],
    "disk_space": [
        r"disk full",
        r"no space left on device",
        r"ENOSPC",
        r"out of disk space",
    ],
    "memory": [
        r"OutOfMemoryError",
        r"memory.*(?:exceeded|limit|full)",
        r"cannot allocate memory",
        r"JavaScript heap out of memory",
        r"FATAL ERROR:.*heap",
    ],
    "network": [
        r"timeout.*(?:exceeded|expired)",
        r"connection refused",
        r"ECONNREFUSED",
        r"ECONNRESET",
        r"ENOTFOUND",
        r"getaddrinfo.*(?:failed|error)",
        r"network.*(?:error|unreachable|timeout)",
        r"Name or service not known",
    ],
    "version_mismatch": [
        r"requires.*version",
        r"version.*conflict",
        r"incompatible.*version",
        r"does not match.*version",
    ],
    "dependency_conflict": [
        r"Dependency conflict",
        r"conflicting dependencies",
        r"circular dependency",
        r"dependency.*(?:error|conflict|failed)",
        r"package.*conflict",
    ],
    "permission": [
        r"Permission denied",
        r"EACCES",
        r"EPERM",
        r"not (?:permitted|allowed)",
        r"operation not permitted",
    ],
    "config_error": [
        r"MissingConfig",
        r"Configuration.*(?:error|missing|invalid)",
        r"config.*(?:file|setting).*(?:missing|not found|invalid)",
        r"InvalidConfig",
        r"could not.*config",
    ],
}


def _detect_error_category(error_log: str) -> str | None:
    """Classify the error into a high-level category."""
    error_lower = error_log.lower()
    for category, patterns in ERROR_HINTS.items():
        for p in patterns:
            if re.search(p, error_lower, re.IGNORECASE):
                return category
    return None


def _detect_language_from_error(error_log: str) -> str | None:
    """Guess the programming language from error message patterns."""
    counts = {}
    for lang, patterns in LANGUAGE_ERROR_PATTERNS.items():
        for pattern_list in patterns.values():
            for p in pattern_list:
                if re.search(p, error_log, re.IGNORECASE):
                    counts[lang] = counts.get(lang, 0) + 1
                    break
    if counts:
        return max(counts, key=counts.get)
    return None


def _extract_syntax_errors(error_log: str, language: str | None = None) -> list[dict]:
    """Extract structured syntax error info from logs."""
    errors = []
    if language and language in LANGUAGE_ERROR_PATTERNS:
        for pattern in LANGUAGE_ERROR_PATTERNS[language].get("syntax", []):
            for m in re.finditer(pattern, error_log, re.IGNORECASE):
                errors.append({
                    "pattern": pattern,
                    "match": m.group(0),
                    "detail": m.group(1) if m.lastindex and m.lastindex >= 1 else "",
                })
    return errors


def _extract_module_error(error_log: str) -> dict | None:
    """Extract missing module info from various language error formats."""
    patterns = [
        (r"ModuleNotFoundError: No module named ['\"](.+?)['\"]", "python"),
        (r"ImportError: No module named ['\"](.+?)['\"]", "python"),
        (r"cannot import name ['\"](.+?)['\"]", "python"),
        (r"Error: Cannot find module ['\"](.+?)['\"]", "node"),
        (r"ERR_MODULE_NOT_FOUND.*['\"](.+?)['\"]", "node"),
        (r"cannot load such file(?:\s*[-]{1,2}\s*['\"]?)(.+?)['\"]?", "ruby"),
        (r"could not find.*?crate ['\"](.+?)['\"]", "rust"),
        (r"cannot find package ['\"](.+?)['\"]", "go"),
        (r"Error.*?not find package", "go"),
        (r"uninitialized constant.*?(\w+)", "ruby"),
        (r"undefined variable.*?(\w+)", "general"),
        (r"undefined method.*?`(\w+)'", "ruby"),
    ]
    for pattern, lang in patterns:
        m = re.search(pattern, error_log, re.IGNORECASE)
        if m:
            return {"module": m.group(1), "language": lang, "pattern": pattern}
    return None


def _check_project_files(project_path: str, error_log: str) -> list[str]:
    """Check for common project misconfigurations."""
    issues = []
    root = Path(project_path)

    missing_configs = {
        "requirements.txt": ("Python", "pip install -r requirements.txt"),
        "package.json": ("Node.js", "npm install"),
        "Cargo.toml": ("Rust", "cargo build"),
        "go.mod": ("Go", "go mod download"),
        "Gemfile": ("Ruby", "bundle install"),
        "CMakeLists.txt": ("C/C++", "cmake . && make"),
        "Makefile": ("C/C++", "make"),
        "composer.json": ("PHP", "composer install"),
        "pubspec.yaml": ("Dart/Flutter", "dart pub get"),
        "mix.exs": ("Elixir", "mix deps.get"),
        "Project.toml": ("Julia", "julia -e 'using Pkg; Pkg.instantiate()'"),
    }

    for config_file, (lang, cmd) in missing_configs.items():
        if not (root / config_file).exists():
            continue
        if lang.lower() in error_log.lower() or config_file.split(".")[0] in error_log.lower():
            issues.append(f"Run setup: {cmd}")
            break

    dot_env = root / ".env"
    dot_env_example = root / ".env.example"
    if dot_env_example.exists() and not dot_env.exists():
        if "env" in error_log.lower() or "environment" in error_log.lower():
            issues.append("Copy .env.example to .env and fill in the values")

    return issues


def _suggest_code_patch(error_log: str, project_path: str, plan: dict) -> str | None:
    """Suggest a code-level fix for common issues."""
    error_lower = error_log.lower()

    if "port" in error_lower and ("in use" in error_lower or "eaddrinuse" in error_lower):
        m = re.search(r"port\s+(\d+)", error_log, re.IGNORECASE)
        if m:
            old_port = m.group(1)
            new_port = str(int(old_port) + 1)
            return (
                f"Port {old_port} is already in use. "
                f"Set PORT={new_port} environment variable, "
                f"or update the hardcoded port in your entry file."
            )

    if "module not found" in error_lower or "cannot find module" in error_lower:
        return "Try installing the missing module with the appropriate package manager."

    if "permission denied" in error_lower or "eacces" in error_lower:
        return "Try running with appropriate permissions, or fix file ownership/permissions."

    return None


def deep_debug(error_log: str, plan: dict, project_path: str) -> dict:
    """Advanced multi-strategy debug analysis."""
    results = {
        "root_cause": "",
        "confidence": 0.0,
        "fix_type": "other",
        "target": "",
        "value": "",
        "code_patch": "",
        "explanation": "",
        "manual_steps": [],
        "category": None,
        "language": None,
        "syntax_errors": [],
        "module_error": None,
        "config_issues": [],
    }

    # 1. Detect language from error
    lang = _detect_language_from_error(error_log)
    if lang:
        results["language"] = lang

    # 2. Classify error category
    category = _detect_error_category(error_log)
    if category:
        results["category"] = category
        if category in ("missing_api_key", "port_conflict", "permission", "disk_space"):
            results["confidence"] = 0.7
            results["explanation"] = {
                "missing_api_key": "Error indicates missing or invalid API key or authentication token",
                "port_conflict": "Port conflict detected — the required port is already in use",
                "permission": "File or directory permission issue detected",
                "disk_space": "Disk space or storage limit issue detected",
                "memory": "Application ran out of memory",
                "network": "Network connectivity issue detected",
                "version_mismatch": "Version incompatibility detected",
                "dependency_conflict": "Dependency conflict detected",
                "config_error": "Configuration or settings error detected",
            }.get(category, results["explanation"])

    # 3. Extract syntax errors
    syntax_errors = _extract_syntax_errors(error_log, lang)
    if syntax_errors:
        results["syntax_errors"] = syntax_errors[:5]

    # 4. Extract module errors
    module_error = _extract_module_error(error_log)
    if module_error:
        results["module_error"] = module_error
        results["fix_type"] = "install_module"
        results["target"] = module_error["module"]
        results["explanation"] = f"Missing {module_error['language']} module: {module_error['module']}"
        results["confidence"] = 0.9

    # 5. Check project config issues
    config_issues = _check_project_files(project_path, error_log)
    if config_issues:
        results["config_issues"] = config_issues
        results["manual_steps"].extend(config_issues)

    # 6. Try AI-powered analysis if no clear match
    if not module_error and not syntax_errors:
        try:
            from runit.llm import llm_call
            context_parts = [
                f"Error:\n{error_log[:2000]}\n\n",
                f"Project type: {plan.get('type', 'unknown')}\n",
                f"Entry: {plan.get('entry', 'unknown')}\n",
            ]
            if plan.get("required_env"):
                context_parts.append(f"Known env vars: {', '.join(plan['required_env'])}\n")
            ai_prompt = "".join(context_parts) + "\nAnalyze this error deeply and return a fix as JSON."
            try:
                response = llm_call(ai_prompt, system=DEBUGGER_SYSTEM_PROMPT)
                ai_fix = json.loads(response)
                results.update({
                    k: ai_fix.get(k, results[k])
                    for k in ("root_cause", "fix_type", "target", "value",
                              "code_patch", "explanation", "manual_steps", "confidence")
                })
                if not results["explanation"] and ai_fix.get("explanation"):
                    results["explanation"] = ai_fix["explanation"]
            except Exception:
                pass
        except Exception:
            pass

    # 7. Suggest code patch for known patterns
    if not results["code_patch"]:
        patch = _suggest_code_patch(error_log, project_path, plan)
        if patch:
            results["code_patch"] = patch

    # 8. Fill fallback explanation
    if not results["explanation"]:
        results["explanation"] = f"Detected {category or 'unknown'} error in {lang or 'unknown'} project."
        results["manual_steps"].append("Check the error log above for details")
        results["manual_steps"].append("Search online for the error message")

    return results


def apply_code_patch(project_path: str, patch: str, target_file: str | None = None) -> bool:
    """Apply a suggested code patch to the project."""
    if not patch:
        return False
    print(f"  \U0001f4dd Suggested fix: {patch}")
    from runit.cli import confirm
    if confirm("Apply this fix?"):
        if target_file:
            file_path = Path(project_path) / target_file
            if file_path.exists():
                try:
                    original = file_path.read_text()
                    new_content = original + f"\n# Auto-fix by Runit Debugger\n{patch}\n"
                    file_path.write_text(new_content)
                    print(f"  \u2705 Patch applied to {target_file}")
                    return True
                except Exception as e:
                    print(f"  \u274c Failed to patch: {e}")
                    return False
        print("  \u2705 Patch instruction recorded (apply manually if needed)")
        return True
    return False


def print_debug_report(results: dict):
    """Display structured debug results to the user."""
    console = _console()

    lines = []
    if results.get("root_cause"):
        lines.append(f"  \U0001f50d  Root cause: {results['root_cause']}")
    if results.get("language"):
        lines.append(f"  \U0001f4bb  Language: {results['language']}")
    if results.get("category"):
        cat_labels = {
            "missing_api_key": "Missing API Key / Auth",
            "port_conflict": "Port Conflict",
            "disk_space": "Disk Space",
            "memory": "Memory",
            "network": "Network",
            "version_mismatch": "Version Mismatch",
            "dependency_conflict": "Dependency Conflict",
            "permission": "Permission",
            "config_error": "Configuration Error",
        }
        label = cat_labels.get(results["category"], results["category"])
        lines.append(f"  \U0001f9e0  Category: {label}")
    if results.get("confidence", 0) > 0:
        pct = int(results["confidence"] * 100)
        lines.append(f"  \U0001f4ca  Confidence: {pct}%")
    if results.get("explanation"):
        lines.append(f"  \U0001f4a1  Diagnosis: {results['explanation']}")
    if results.get("code_patch"):
        lines.append(f"  \U0001f4dd  Suggestion: {results['code_patch']}")
    if results.get("manual_steps"):
        lines.append(f"  \U0001f527  Steps:")
        for i, step in enumerate(results["manual_steps"], 1):
            lines.append(f"    {i}. {step}")

    if console:
        from rich.panel import Panel
        from rich.text import Text
        text = Text("\n".join(lines))
        console.print(Panel(text, title="\U0001f9e0 Debug Report", border_style="yellow"))
    else:
        print("\n  \U0001f9e0 Debug Report:")
        for line in lines:
            print(line)
