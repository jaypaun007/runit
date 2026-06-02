import os
import json
import sys
from pathlib import Path

try:
    import readline
except ImportError:
    pass


def prompt(text: str, default: str = "") -> str:
    if default:
        val = input(f"  {text} [{default}]: ").strip()
        return val or default
    return input(f"  {text}: ").strip()


def secret_prompt(text: str) -> str:
    if sys.platform == "win32":
        import msvcrt
        print(f"  {text}: ", end="", flush=True)
        val = []
        while True:
            ch = msvcrt.getch()
            if ch in (b"\r", b"\n"):
                print()
                break
            if ch == b"\x08":
                if val:
                    val.pop()
            else:
                val.append(ch.decode("utf-8", errors="replace"))
        return "".join(val)
    else:
        import getpass
        return getpass.getpass(f"  {text}: ")


SUPPORTED_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4",
        "default_base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku", "claude-3-5-sonnet"],
        "default_model": "claude-3-5-sonnet",
        "default_base_url": "https://api.anthropic.com/v1",
    },
    "custom": {
        "name": "Custom Endpoint",
        "models": ["custom"],
        "default_model": "custom",
        "default_base_url": "",
    }
}


def setup_byok_interactive():
    from rich.console import Console
    from rich.panel import Panel
    from rich import box

    console = Console()
    console.print(Panel.fit(
        "[bold yellow]🔑 Bring Your Own Key (BYOK) Setup[/]\n"
        "Configure your AI provider to power Runit's analysis engine.",
        box=box.ROUNDED
    ))

    print("\n  Supported providers:")
    for key, info in SUPPORTED_PROVIDERS.items():
        print(f"    {key:12s} - {info['name']}")
    print()

    provider = prompt("Provider", "openai").strip().lower()
    while provider not in SUPPORTED_PROVIDERS:
        print(f"  Invalid provider. Choose from: {', '.join(SUPPORTED_PROVIDERS.keys())}")
        provider = prompt("Provider", "openai").strip().lower()

    info = SUPPORTED_PROVIDERS[provider]

    api_key = secret_prompt("API key")

    if provider == "custom":
        base_url = prompt("Custom API endpoint URL (e.g. https://api.myendpoint.com/v1)")
        model = prompt("Model name", "gpt-4")
    else:
        base_url = prompt("Base URL (leave blank for default)", info["default_base_url"])
        model = prompt("Model", info["default_model"])

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }
