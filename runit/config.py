import os
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".runit"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYS_FILE = CONFIG_DIR / "keys.json"
DEFAULT_MAX_RETRIES = 3
DEFAULT_TEMP_DIR = "/tmp/runit" if os.name != "nt" else os.environ.get("TEMP", "C:\\Temp") + "\\runit"


def load_config() -> dict:
    cfg = {
        "provider": "openai",
        "model": "gpt-4",
        "api_key": "",
        "base_url": "",
        "github_token": "",
        "max_retries": DEFAULT_MAX_RETRIES,
        "temp_dir": DEFAULT_TEMP_DIR,
        "notifications": True,
    }
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text())
            cfg.update(user)
        except Exception:
            pass
    cfg["api_key"] = cfg.get("api_key") or os.environ.get("RUNIT_API_KEY", "")
    cfg["base_url"] = cfg.get("base_url") or os.environ.get("RUNIT_BASE_URL", "")
    cfg["model"] = os.environ.get("RUNIT_MODEL", cfg["model"])
    cfg["provider"] = os.environ.get("RUNIT_PROVIDER", cfg["provider"])
    cfg["github_token"] = cfg.get("github_token") or os.environ.get("GITHUB_TOKEN", "")
    return cfg


def save_config(updates: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg.update(updates)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def load_keys() -> dict[str, str]:
    if KEYS_FILE.exists():
        try:
            return json.loads(KEYS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_key(name: str, value: str):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    keys = load_keys()
    keys[name] = value
    KEYS_FILE.write_text(json.dumps(keys, indent=2))


def get_key(name: str) -> str | None:
    return load_keys().get(name)


def list_keys() -> dict[str, str]:
    return load_keys()


def delete_key(name: str) -> bool:
    keys = load_keys()
    if name in keys:
        del keys[name]
        KEYS_FILE.write_text(json.dumps(keys, indent=2))
        return True
    return False
