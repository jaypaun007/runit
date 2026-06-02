import json
import time
import requests
from runit.config import load_config


def _openai_chat(prompt: str, system: str = "") -> str:
    cfg = load_config()
    model = cfg["model"].strip()
    url = (cfg["base_url"] or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _anthropic_chat(prompt: str, system: str = "") -> str:
    cfg = load_config()
    model = cfg["model"].strip()
    url = (cfg["base_url"] or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
    headers = {
        "x-api-key": cfg["api_key"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def llm_call(prompt: str, system: str = "", max_retries: int = 5) -> str:
    cfg = load_config()
    if not cfg.get("api_key"):
        return _fallback_response(prompt)

    last_error = ""
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            if cfg["provider"] == "anthropic":
                return _anthropic_chat(prompt, system)
            return _openai_chat(prompt, system)
        except requests.RequestException as e:
            last_error = str(e)
            status = 0
            if hasattr(e, 'response') and e.response is not None:
                status = e.response.status_code
            if status in (429, 500, 502, 503, 504):
                continue
            if status == 400:
                return json.dumps({
                    "error": f"API 400 error - check model name, base URL, and API key: {last_error}",
                    "hint": "Make sure RUNIT_MODEL has no trailing spaces and RUNIT_BASE_URL is correct"
                })
            if attempt == max_retries - 1:
                print(f"  \u26a0\ufe0f API call failed after {max_retries} retries: {last_error}")
                return _fallback_response(prompt)
        except Exception as e:
            last_error = str(e)
            if attempt == max_retries - 1:
                print(f"  \u26a0\ufe0f API call failed: {last_error}")
                return _fallback_response(prompt)

    print(f"  \u26a0\ufe0f API call failed after {max_retries} retries: {last_error}")
    return _fallback_response(prompt)


_MOCK_PLAN = {
    "type": "python",
    "entry": "main.py",
    "fallbacks": ["app.py", "index.py", "server.py", "cli.py", "run.py"],
    "dependencies": ["requirements.txt"],
    "run_command": "python main.py",
    "description": "Python project (limited analysis without API key)"
}


def _fallback_response(prompt: str) -> str:
    if "analyze" in prompt.lower() or "project" in prompt.lower():
        return json.dumps(_MOCK_PLAN)
    return json.dumps({
        "fix": "No automatic fix available without AI API key.",
        "manual_steps": [
            "Install project dependencies manually",
            "Check the project README for setup instructions",
            "Run the project entry file directly"
        ]
    })
