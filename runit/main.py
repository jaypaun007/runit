import sys
import os
import json

from runit.config import load_config, save_config, DEFAULT_MAX_RETRIES, save_key, get_key, list_keys, delete_key
from runit.byok import setup_byok_interactive
from runit.cli import (
    print_banner, print_step, print_success, print_failure,
    print_plan, print_skill, confirm, prompt_input,
    print_key_request, print_keystore, print_agent_badge,
    print_env_banner, print_docker_prompt, _console, print_web_research,
)
from runit.project_loader import load_project, get_project_name, cleanup, is_github_url
from runit.analyzer import analyze_project
from runit.skills import get_skill, SKILLS_REGISTRY, detect_package_manager, has_pnpm, get_build_instructions
from runit.deps import install
from runit.executor import execute
from runit.error_handler import fix_error, apply_fix, research_error_online
from runit.debugger import deep_debug, print_debug_report, apply_code_patch
from runit.notify import notify_done
from runit.environment import detect_env, env_info, has_docker, is_notebook_env
from runit.web_tools import web_search, fetch_github_readme


def _prompt_for_missing_env(plan: dict, project_name: str) -> dict:
    """Ask user for missing environment variables and return them as a dict."""
    required = plan.get("required_env", [])
    if not required:
        return {}

    already_have = set(os.environ.keys())
    env_vars = {}

    for var in required:
        if var in already_have:
            continue
        stored = get_key(var)
        if stored:
            env_vars[var] = stored
            continue

        print_key_request(var, project_name)
        val = prompt_input(f"Enter value for {var}", secret=True)
        if val:
            env_vars[var] = val
            if confirm(f"Save {var} for future use?", default=True):
                save_key(var, val)
            print(f"  \u2713 {var} set")

    return env_vars


def _escalation_strategies(plan: dict, project_path: str) -> list[callable]:
    """Return list of escalation strategies to try in order."""
    strategies = []

    required = plan.get("required_env", [])
    if required:
        def ask_env(p, pp, env_vars_ref):
            if any(v not in os.environ for v in required):
                print("\n  \U0001f50d Project needs environment variables to run.")
                new_env = _prompt_for_missing_env(p, get_project_name(pp))
                env_vars_ref.update(new_env)
                return bool(new_env)
            return False
        strategies.append(ask_env)

    from pathlib import Path
    if (Path(project_path) / ".env.example").exists() and not (Path(project_path) / ".env").exists():
        def create_dotenv(p, pp, env_vars_ref):
            print("  \U0001f4c4 .env.example found but no .env file exists.")
            if confirm("Copy .env.example to .env and let you edit it?"):
                import shutil
                shutil.copy(Path(pp) / ".env.example", Path(pp) / ".env")
                print("  \u2705 Created .env — edit it, press Enter when ready")
                prompt_input("Press Enter when ready")
                return True
            return False
        strategies.append(create_dotenv)

    def ask_user(p, pp, env_vars_ref):
        print("  \U0001f4ac Runit needs your help:")
        print("    \U0001f511 ENV_VAR=value  — set environment variable")
        print("    \U0001f4c4  path/to/file  — try different entry file")
        print("    \U0001f50d  web:search    — search web for solution")
        print("    \u23f3  (Enter)       — skip")
        hint = prompt_input("Your input").strip()
        if hint.lower().startswith("web:"):
            query = hint[4:].strip()
            results = web_search(query)
            print_web_research(results)
            if results:
                print("  \u2713 Search complete. Retrying...")
                return True
            return False
        if "=" in hint:
            parts = hint.split("=", 1)
            env_vars_ref[parts[0].strip()] = parts[1].strip()
            print(f"  \u2713 Set {parts[0].strip()}")
            return True
        if hint:
            p["entry"] = hint
            print(f"  \u2713 Will try entry: {hint}")
            return True
        return False
    strategies.append(ask_user)

    return strategies


def _choose_run_mode(plan: dict, project_path: str) -> bool:
    """Ask user for Docker vs dev mode. Returns True if mode was resolved."""
    docker_available = plan.get("has_docker", False)
    docker_installed = docker_available and has_docker()
    has_dev_scripts = bool(plan.get("dev_scripts"))
    pm = detect_package_manager(project_path)

    if not docker_available and not has_dev_scripts:
        return False

    print_docker_prompt(docker_available, has_dev_scripts)
    if docker_available and not docker_installed:
        print("  \u26a0\ufe0f  Docker not found on this system. Install Docker for mode 1.")

    while True:
        choice = prompt_input("Run mode").strip()
        if not choice:
            if has_dev_scripts:
                choice = "2"
            else:
                choice = "1"

        if choice == "1" and docker_available:
            if not docker_installed:
                print("  \u274c  Docker is not installed. Install Docker first, or choose mode 2.")
                continue
            image = plan.get("docker_image", "")
            if not image:
                print("  \u26a0\ufe0f No Docker image auto-detected.")
                image = prompt_input("Docker image (e.g. ghcr.io/org/repo:latest)")
                if not image:
                    print("  \u274c Cannot use Docker mode without an image.")
                    return False
            plan["_run_mode"] = "docker"
            plan["_docker_image"] = image
            print(f"  \u2705 Will run via Docker: {image}")
            return True

        if choice == "2" and has_dev_scripts:
            script = plan.get("dev_scripts", ["dev"])[0]
            if len(plan.get("dev_scripts", [])) > 1:
                script_list = ", ".join(plan["dev_scripts"])
                s = prompt_input(f"Which script?", default=script)
                if s in plan["dev_scripts"]:
                    script = s
            plan["_run_mode"] = "dev_script"
            plan["_dev_script"] = script
            plan["_package_manager"] = pm
            print(f"  \u2705 Will run via {pm} run {script}")
            return True

        print(f"  \u26a0\ufe0f  Invalid choice. Enter 1 or 2.")


def cmd_run(target: str, token: str | None = None, max_retries: int | None = None,
            force_docker: bool = False, force_dev: bool = False, yes: bool = False,
            plain: bool = False):
    cfg = load_config()
    max_retries = max_retries or cfg.get("max_retries", DEFAULT_MAX_RETRIES)

    import runit.cli as cli_mod
    if yes:
        cli_mod.AUTO_YES = True
    if plain:
        cli_mod.FORCE_PLAIN = True

    no_api_key = not cfg.get("api_key")
    if no_api_key:
        c = cli_mod._console()
        if c:
            c.print("  \u26a0\ufe0f  No AI API key configured. Running in limited fallback mode.")
            c.print("  Run [cyan]runit --setup[/] to configure your AI provider for smarter analysis.\n")
        else:
            print("  \u26a0\ufe0f  No AI API key configured. Running in limited fallback mode.")
            print("  Run runit --setup to configure your AI provider for smarter analysis.\n")

    print_banner()

    if is_github_url(target):
        print("")
        print("  \u26a0\ufe0f  [bold yellow]Disclaimer:[/] This tool runs code from third-party repositories.")
        print("  \u26a0\ufe0f  [yellow]Only proceed if you trust the source. Use isolated environments for untrusted code.[/]")
        print("  \u26a0\ufe0f  [yellow]You assume all risk. See README for full disclaimer.[/]")
        from runit.cli import confirm
        if not confirm("Continue?", default=False):
            print("  \u274c Aborted by user.")
            return 1

    env_type = detect_env()
    print_env_banner(env_type)
    is_remote = env_type in ("kaggle", "colab")
    if not plain and not cli_mod.FORCE_PLAIN and is_remote:
        cli_mod.FORCE_PLAIN = True
    if is_remote:
        print("  \U0001f30d  Detected cloud environment — optimizing execution strategy")

    print_step(1, 6, "Loading project...")
    repo_url = target if is_github_url(target) else None
    project_path = load_project(target, token)
    project_name = get_project_name(project_path)
    print(f"  \U0001f4c1 Loaded: {project_name} ({project_path})")

    print_step(2, 6, "Analyzing project structure...")
    plan = analyze_project(project_path, repo_url=repo_url)
    print_plan(plan)

    skill = get_skill(plan.get("type", ""))
    if skill:
        print_step(2, 6, f"Agent skill loaded: {skill['name']}", "done")
        print_skill(skill)
        build_steps = get_build_instructions(plan.get("type", ""))
        if build_steps:
            print(f"  \U0001f527  Typical setup: {'  |  '.join(build_steps)}")

    # Ask user for custom run instructions
    print_step(2, 6, "Optional: Add custom instructions", "running")
    print("  \U0001f4ac  Any special instructions for how to run this project?")
    print("    (e.g. 'use python3 instead of python', 'set --port 9000', 'cd backend first')")
    print("    \u23f3  Press Enter to skip")
    user_instructions = prompt_input("Instructions").strip()
    if user_instructions:
        plan["_user_instructions"] = user_instructions
        print(f"  \u2713 Noted: {user_instructions}")

    # Prompt user for any required keys upfront
    required_env = plan.get("required_env", [])
    if required_env:
        missing = [v for v in required_env if v not in os.environ and not get_key(v)]
        if missing:
            print(f"\n  \U0001f511  This project requires {len(missing)} environment variable(s)")
            for var in missing:
                print(f"    \U0001f511  {var}")
            if confirm("Set these now?", default=True):
                env_overrides = _prompt_for_missing_env(plan, project_name)
                plan["_env_overrides"] = env_overrides
            else:
                print("  \u2716 Will prompt when needed during execution")

    if is_remote:
        plan["_cloud_mode"] = True

    # Ask Docker vs Dev mode if applicable
    docker_available = plan.get("has_docker", False)
    has_dev_scripts = bool(plan.get("dev_scripts"))
    mode_chosen = False

    if force_docker and docker_available:
        image = plan.get("docker_image", "") or prompt_input("Docker image")
        if image:
            plan["_run_mode"] = "docker"
            plan["_docker_image"] = image
            mode_chosen = True
            print(f"  \U0001f4e6  Docker mode: {image}")
    elif force_dev and has_dev_scripts:
        pm = detect_package_manager(project_path)
        script = plan.get("dev_scripts", ["dev"])[0]
        plan["_run_mode"] = "dev_script"
        plan["_dev_script"] = script
        plan["_package_manager"] = pm
        mode_chosen = True
        print(f"  \U0001f4bb  Dev mode: {pm} run {script}")

    if not mode_chosen and (docker_available or has_dev_scripts):
        print_step(3, 6, "Choosing run mode...")
        mode_chosen = _choose_run_mode(plan, project_path)

    if not mode_chosen:
        step_label = "Installing dependencies..."
        step_num = 3
    else:
        step_label = "Preparing runtime..."
        step_num = 3

    if plan.get("_run_mode") != "docker":
        print_step(step_num, 6, step_label)
        install(plan, project_path)
        print(f"  \u2705 Dependencies ready")

    last_error = ""
    manual_steps = []
    env_overrides = {}
    attempt = 0
    strategies = _escalation_strategies(plan, project_path)
    strategy_index = 0
    user_cancelled = False
    web_researched = False

    while True:
        attempt += 1
        label = f"Running project (attempt {attempt})"
        if attempt <= max_retries:
            print_step(4, 6, label)
        else:
            print(f"  \U0001f504  Attempt {attempt} (persistent mode)...")

        result = execute(plan, project_path, env=env_overrides if env_overrides else None)

        if result.returncode == 0:
            notify_done(True, project_name)
            print_success(
                plan.get("run_command", ""),
                result.stdout,
                project_name,
                project_path
            )
            if token:
                cfg = load_config()
                if not cfg.get("github_token"):
                    if confirm("Save this GitHub token for future clones?", default=True):
                        save_config({"github_token": token})
                        print("  \u2705 Token saved to ~/.runit/config.json")
            cleanup(project_path)
            return 0

        last_error = result.stderr or result.stdout
        print(f"  \u274c Attempt {attempt} failed")

        print_step(5, 6, "Analyzing error...")
        # Run deep debugger for advanced analysis
        debug_result = deep_debug(last_error, plan, project_path)
        print_debug_report(debug_result)

        fix = fix_error(last_error, plan, project_path)
        fix_result = apply_fix(fix, plan, project_path)

        if fix_result.get("ask_user"):
            print_key_request(fix.get("target", "API_KEY"), project_name)
            val = prompt_input(f"Enter value for {fix['target']}", secret=True)
            if val:
                env_overrides[fix["target"]] = val
                save_key(fix["target"], val)
                print(f"  \u2713 {fix['target']} saved and applied")
                continue
        elif fix_result.get("applied"):
            manual_steps.append(fix.get("explanation", ""))
            continue
        else:
            if strategy_index < len(strategies):
                strategy = strategies[strategy_index]
                print(f"  \U0001f9f0  Escalation strategy {strategy_index + 1}/{len(strategies)}...")
                if strategy(plan, project_path, env_overrides):
                    strategy_index += 1
                    continue
                strategy_index += 1
            else:
                if not web_researched:
                    print("  \U0001f50d  Searching web for solutions...")
                    research_error_online(last_error, plan)
                    web_researched = True
                    continue

                print("  \U0001f4ac  All strategies exhausted. Can you help?")
                print("    \U0001f511 ENV=val    — set env var")
                print("    \U0001f4c4  file.py   — try entry file")
                print("    \U0001f50d  web:query  — search web")
                print("    \u23f3  Enter     — give up")
                hint = prompt_input("Your input").strip()
                if hint.lower().startswith("web:"):
                    query = hint[4:].strip()
                    for r in web_search(query):
                        print(f"    \U0001f517 {r['title']}: {r['url']}")
                    continue
                if not hint or hint.lower() in ("skip", "quit", "exit"):
                    if confirm("Give up on this project?", default=False):
                        user_cancelled = True
                        break
                    continue
                if "=" in hint:
                    parts = hint.split("=", 1)
                    env_overrides[parts[0].strip()] = parts[1].strip()
                    print(f"  \u2713 Set {parts[0].strip()}")
                else:
                    plan["entry"] = hint
                    plan.setdefault("fallbacks", []).insert(0, hint)
                    print(f"  \u2713 Will try entry: {hint}")

        if attempt > 50:
            print("  \u26a0\ufe0f  Over 50 attempts. Stopping to avoid infinite loop.")
            break

    notify_done(False, project_name)
    print_failure(last_error, plan, manual_steps if manual_steps else None)
    cleanup(project_path)
    return 1


def cmd_setup():
    print_banner()
    cfg = setup_byok_interactive()

    print("\n  \U0001f510  Also configure a GitHub token? (for private repos)")
    if confirm("Configure GitHub token?", default=False):
        from runit.byok import secret_prompt
        token = secret_prompt("GitHub personal access token")
        cfg["github_token"] = token
        print("  \u2705 GitHub token saved")

    save_config(cfg)

    console = _console()
    if console:
        from rich.panel import Panel
        console.print(Panel.fit(
            "[bold green]\u2705  Configured successfully![/]\n\n"
            f"Provider: {cfg['provider']}\n"
            f"Model:    {cfg['model']}\n"
            f"Endpoint: {cfg.get('base_url') or 'default'}\n"
            f"GitHub:   {'\u2713 token set' if cfg.get('github_token') else '\u274c none'}",
            border_style="green"
        ))
    else:
        print("\n\u2705 Configured successfully!")
        print(f"  Provider: {cfg['provider']}")
        print(f"  Model:    {cfg['model']}")


def cmd_status():
    cfg = load_config()
    stored_keys = list_keys()
    env = env_info()
    console = _console()

    if console:
        from rich.panel import Panel
        from rich.table import Table
        from rich import box

        table = Table(box=box.SIMPLE, border_style="blue")
        table.add_column("Setting", style="bold yellow")
        table.add_column("Value", style="cyan")
        table.add_row("AI Provider", cfg.get("provider", "not set"))
        table.add_row("AI Model", cfg.get("model", "not set"))
        table.add_row("AI API Key", "\u2713 configured" if cfg.get("api_key") else "\u274c not set")
        table.add_row("AI Base URL", cfg.get("base_url") or "default")
        table.add_row("GitHub Token", "\u2713 set" if cfg.get("github_token") else "\u274c not set")
        table.add_row("Max Retries", str(cfg.get("max_retries", 3)))
        table.add_row("Notifications", str(cfg.get("notifications", True)))
        table.add_row("Stored Keys", str(len(stored_keys)))
        table.add_row("Platform", env.get("platform", "?"))
        table.add_row("Environment", detect_env())

        console.print(Panel.fit(
            "[bold cyan]\U0001f50d  Runit Status[/]",
            border_style="cyan"
        ))
        console.print(table)
        if stored_keys:
            console.print("\n[bold]Stored Project Keys:[/]")
            print_keystore()
    else:
        print("Runit Status:")
        print(f"  AI Provider:    {cfg.get('provider', 'not set')}")
        print(f"  AI Model:       {cfg.get('model', 'not set')}")
        print(f"  AI API Key:     {'configured' if cfg.get('api_key') else 'not set'}")
        print(f"  AI Base URL:    {cfg.get('base_url') or 'default'}")
        print(f"  GitHub Token:   {'set' if cfg.get('github_token') else 'not set'}")
        print(f"  Max Retries:    {cfg.get('max_retries', 3)}")
        print(f"  Notifications:  {cfg.get('notifications', True)}")
        print(f"  Stored Keys:    {len(stored_keys)}")
        print(f"  Platform:       {env.get('platform', '?')}")
        print(f"  Environment:    {detect_env()}")
        if stored_keys:
            print_keystore()


def cmd_skills():
    console = _console()

    if console:
        from rich.table import Table
        from rich import box
        from rich.panel import Panel

        table = Table(box=box.SIMPLE, border_style="green", header_style="bold green")
        table.add_column("Skill", style="yellow")
        table.add_column("Description")
        table.add_column("Detects")

        for key, skill in SKILLS_REGISTRY.items():
            table.add_row(
                f"\U0001f9e0 {skill['name']}",
                skill['description'],
                ", ".join(skill['detect_files'])
            )

        console.print(Panel.fit(
            "[bold green]\U0001f9e0  Runit Agent Skills[/]",
            border_style="green"
        ))
        console.print(table)
    else:
        print("Runit Agent Skills:")
        for key, skill in SKILLS_REGISTRY.items():
            print(f"  \U0001f9e0 {skill['name']}")
            print(f"     {skill['description']}")
            print(f"     Detects: {', '.join(skill['detect_files'])}")


def cmd_keys(args):
    if args.get("list"):
        keys = list_keys()
        if not keys:
            print("  No stored keys.")
            return 0
        console = _console()
        if console:
            from rich.table import Table
            from rich import box
            table = Table(box=box.SIMPLE, border_style="yellow", title="\U0001f511 Stored Keys")
            table.add_column("Name", style="bold")
            table.add_column("Value")
            for name, value in keys.items():
                masked = value[:6] + "..." + value[-4:] if len(value) > 12 else "***"
                table.add_row(name, masked)
            console.print(table)
        else:
            print("Stored Keys:")
            for name, value in keys.items():
                masked = value[:6] + "..." + value[-4:] if len(value) > 12 else "***"
                print(f"  {name}: {masked}")
        return 0

    if args.get("add"):
        name = args["add"]
        val = prompt_input(f"Enter value for {name}", secret=True)
        save_key(name, val)
        print(f"  \u2705 Key '{name}' saved.")
        return 0

    if args.get("delete"):
        name = args["delete"]
        if delete_key(name):
            print(f"  \u2705 Key '{name}' deleted.")
        else:
            print(f"  \u274c Key '{name}' not found.")
        return 0

    print("key usage: runit key --list | --add <name> | --delete <name>")
    return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="runit",
        description="AI-powered agent that makes any project runnable automatically",
        epilog="Examples:\n  runit https://github.com/user/repo\n  runit .\n  runit /path/to/project"
    )

    parser.add_argument("target", nargs="?", help="GitHub repo URL or local folder path")
    parser.add_argument("--retries", type=int, default=None,
                        help="Max retry attempts (default: config value or 3)")
    parser.add_argument("--token", "-t", type=str, default=None,
                        help="GitHub personal access token for private repos")
    parser.add_argument("--docker", action="store_true",
                        help="Use Docker mode (skip prompt)")
    parser.add_argument("--dev", action="store_true",
                        help="Use development mode (skip prompt)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Auto-confirm all prompts (for non-interactive environments)")
    parser.add_argument("--plain", action="store_true",
                        help="Disable rich/colored output (auto-enabled in notebooks)")
    parser.add_argument("--version", action="store_true", help="Show version")

    subcommands = parser.add_argument_group("commands")
    subcommands.add_argument("--setup", action="store_true", help="Configure API key and provider")
    subcommands.add_argument("--status", action="store_true", help="Show current configuration")
    subcommands.add_argument("--skills", action="store_true", help="List available agent skills")

    key_commands = parser.add_argument_group("key management")
    key_commands.add_argument("--key-list", action="store_true", help="List stored project keys")
    key_commands.add_argument("--key-add", type=str, default=None, metavar="NAME",
                              help="Store a project key/token")
    key_commands.add_argument("--key-delete", type=str, default=None, metavar="NAME",
                              help="Delete a stored key")

    args = parser.parse_args()

    if args.version:
        from runit import __version__
        print(f"Runit v{__version__} — Made with ❤️ by Jay Paun")
        return 0

    if args.setup:
        cmd_setup()
        return 0

    if args.status:
        cmd_status()
        return 0

    if args.skills:
        cmd_skills()
        return 0

    if args.key_list or args.key_add or args.key_delete:
        return cmd_keys({"list": args.key_list, "add": args.key_add, "delete": args.key_delete})

    if args.target:
        return cmd_run(args.target, token=args.token, max_retries=args.retries,
                       force_docker=args.docker, force_dev=args.dev,
                       yes=args.yes, plain=args.plain)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
