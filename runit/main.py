import sys
import os
import json
from pathlib import Path

from runit.config import load_config, save_config, save_key, get_key, list_keys, delete_key
from runit.cli import (
    print_banner, print_step, confirm, prompt_input,
    print_keystore, _console, AUTO_YES, FORCE_PLAIN,
)
from runit.project_loader import load_project, get_project_name, cleanup, is_github_url
from runit.orchestrator import Orchestrator
from runit.process_monitor import ProcessMonitor
from runit.environment import detect_env, is_notebook_env
from runit.skills import SKILLS_REGISTRY
from runit import __version__


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Runit v2.0 — AI-Powered Repo Execution Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", nargs="?", help="GitHub URL or local path")
    parser.add_argument("--retries", type=int, default=None, help="Max retry attempts (default: 10)")
    parser.add_argument("--token", "-t", help="GitHub personal access token")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all prompts")
    parser.add_argument("--plain", action="store_true", help="Disable rich/ANSI output")
    parser.add_argument("--max-steps", type=int, default=50, help="Max agent steps (default: 50)")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--setup", action="store_true", help="Interactive API key/provider setup")
    parser.add_argument("--status", action="store_true", help="Show configuration status")
    parser.add_argument("--skills", action="store_true", help="List all supported skills")
    parser.add_argument("--key-list", action="store_true", help="List stored API keys")
    parser.add_argument("--key-add", metavar="NAME", help="Store an API key")
    parser.add_argument("--key-delete", metavar="NAME", help="Delete a stored key")

    args = parser.parse_args()

    if args.version:
        print(f"Runit v{__version__}")
        return 0

    if args.plain:
        import runit.cli as cli_mod
        cli_mod.FORCE_PLAIN = True

    if args.yes:
        import runit.cli as cli_mod
        cli_mod.AUTO_YES = True

    if args.setup:
        return _setup()
    if args.status:
        return _status()
    if args.skills:
        return _list_skills()
    if args.key_list:
        return _key_list()
    if args.key_add:
        return _key_add(args.key_add)
    if args.key_delete:
        return _key_delete(args.key_delete)

    if not args.target:
        parser.print_help()
        return 1

    return cmd_run(
        args.target,
        token=args.token,
        max_retries=args.retries or 10,
        max_steps=args.max_steps,
    )


def cmd_run(target: str, token: str | None = None,
            max_retries: int = 10, max_steps: int = 50) -> int:
    c = _console()

    env_type = detect_env()
    if env_type in ("kaggle", "colab"):
        import runit.cli as cli_mod
        cli_mod.FORCE_PLAIN = True

    print_banner()
    print()

    if is_github_url(target):
        print(f"  \u26a0\ufe0f  This tool runs code from third-party repositories.")
        print(f"  \u26a0\ufe0f  Only proceed if you trust the source.")
        if not AUTO_YES:
            ok = confirm("Continue?", default=True)
            if not ok:
                print("  \u2716 Aborted")
                return 1
        else:
            print("  \u2716 Disclaimer accepted (--yes)")
        print()

    from runit.project_loader import load_project, get_project_name
    project_path = load_project(target, token=token)

    if not project_path:
        print(f"  \u274c Failed to load project: {target}")
        return 1

    project_name = get_project_name(project_path) or Path(project_path).name
    print(f"  \U0001f4c1  Project: {project_name}")
    print(f"  \U0001f4cd  Path: {project_path}")
    print()

    print_step(1, 3, "Agent setting up project...")

    orch = Orchestrator(
        project_path=project_path,
        env_type=env_type,
        auto_yes=AUTO_YES,
        max_retries=max_retries,
        max_steps=max_steps,
    )
    result = orch.run()

    if result.get("status") == "success":
        return 0
    else:
        print(f"\n  \u274c  Setup failed. Try running with --max-steps 100 for deeper analysis.")
        return 1


def _setup() -> int:
    from runit.byok import setup_byok_interactive
    setup_byok_interactive()
    return 0


def _status() -> int:
    cfg = load_config()
    c = _console()
    print(f"  Runit v{__version__}")
    print(f"  API Key: {'\u2705 Set' if cfg.get('api_key') else '\u274c Not set'}")
    print(f"  Provider: {cfg.get('provider', 'openai')}")
    print(f"  Model: {cfg.get('model', 'gpt-4o')}")
    print(f"  Base URL: {cfg.get('base_url', 'https://api.openai.com/v1')}")
    print(f"  Max Retries: {cfg.get('max_retries', 10)}")
    keys = list_keys()
    print(f"  Stored keys: {len(keys)}")
    return 0


def _list_skills() -> int:
    print(f"\n  \U0001f4a1  Supported Skills ({len(SKILLS_REGISTRY)}):")
    for skill in SKILLS_REGISTRY:
        print(f"    \u2022 {skill['name']} ({skill['key']})")
    return 0


def _key_list() -> int:
    print_keystore()
    return 0


def _key_add(name: str) -> int:
    val = prompt_input(f"Enter value for {name}", secret=True)
    if val:
        save_key(name, val)
        print(f"  \u2705 Saved {name}")
    return 0


def _key_delete(name: str) -> int:
    from runit.config import delete_key as del_key
    val = get_key(name)
    if not val:
        print(f"  \u274c No key '{name}' found")
        return 1
    if not AUTO_YES:
        ok = confirm(f"Delete '{name}'?", default=False)
        if not ok:
            print("  \u2716 Cancelled")
            return 1
    del_key(name)
    print(f"  \u2705 Deleted {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
