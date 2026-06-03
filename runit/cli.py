import sys
import os

AUTO_YES = False
FORCE_PLAIN = False

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
    from rich.prompt import Prompt, Confirm as RichConfirm
    from rich.text import Text
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.align import Align
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def _console():
    if HAS_RICH and not FORCE_PLAIN:
        return Console()
    if HAS_RICH:
        return Console(force_terminal=False, no_color=True)
    return None


CREDIT = "Made with ❤️ by Jay Paun"


def print_banner():
    if HAS_RICH:
        c = _console()
        banner_text = Text()
        banner_text.append("╔══════════════════════════════════════╗\n", style="cyan")
        banner_text.append("║", style="cyan")
        banner_text.append("     ⚡ Runit v2.1.2               ", style="bold cyan")
        banner_text.append("║\n", style="cyan")
        banner_text.append("║", style="cyan")
        banner_text.append("  Zero-Config Project Runner            ", style="dim white")
        banner_text.append("║\n", style="cyan")
        banner_text.append("║", style="cyan")
        banner_text.append('  "Make any project runnable"         ', style="italic yellow")
        banner_text.append("║\n", style="cyan")
        banner_text.append("╚══════════════════════════════════════╝", style="cyan")
        c.print()
        c.print(Align.center(banner_text))
        c.print(Align.center(Text(CREDIT, style="dim italic")))
        c.print()
    else:
        print("")
        print("  ╔══════════════════════════════════════╗")
        print("  ║     ⚡ Runit v2.1.2               ║")
        print("  ║  AI-Powered Repo Execution Agent     ║")
        print("  ║  \"Make any project runnable\"         ║")
        print("  ╚══════════════════════════════════════╝")
        print(f"  {CREDIT}")
        print("")


def print_env_banner(env_type: str):
    env_labels = {
        "kaggle": "[bold yellow]📊 Running on Kaggle[/]",
        "colab": "[bold blue]📝 Running on Google Colab[/]",
        "local": "[bold green]💻 Running locally[/]",
    }
    label = env_labels.get(env_type, "")
    if HAS_RICH and label:
        c = _console()
        c.print(Align.center(Panel(label, box=box.SQUARE, border_style="dim")))
    elif label:
        print(f"  {label}")


def print_step(step: int, total: int, label: str, status: str = "running"):
    icons = {1: "\U0001f4e6", 2: "\U0001f50d", 3: "\U0001f4e5", 4: "\U000025b6", 5: "\U0001f4a1", 6: "\U0001f9e0"}
    icon = icons.get(step, "\U0001f536")
    if HAS_RICH:
        c = _console()
        color = "green" if status == "done" else "yellow" if status == "warning" else "red" if status == "error" else "cyan"
        text = Text()
        text.append(f"  ", style="dim")
        text.append(f"[{step}/{total}]", style=color)
        text.append(f" {icon} ", style=color)
        text.append(label, style="bold")
        c.print(text)
    else:
        marker = "\u2713" if status == "done" else "\u26a0" if status == "warning" else "\u2717" if status == "error" else "\u25b6"
        print(f"  [{step}/{total}] {marker} {label}")


def print_agent_badge(name: str, description: str):
    if HAS_RICH:
        c = _console()
        c.print(Panel(
            f"[bold green]\U0001f9e0 {name}[/]\n[dim]{description}[/]",
            box=box.SQUARE, border_style="green", padding=(0, 2), width=60
        ))
    else:
        print(f"  \U0001f9e0 {name}: {description}")


def print_web_research(results: list[dict]):
    if not results:
        return
    if HAS_RICH:
        c = _console()
        c.print(f"\n  [bold yellow]\U0001f50d Web Research Results:[/]")
        for r in results[:3]:
            c.print(f"    \U0001f517 [link={r['url']}]{r['title']}[/]")
    else:
        print(f"\n  \U0001f50d Web Research Results:")
        for r in results[:3]:
            print(f"    \U0001f517 {r['title']}")


def print_success(cmd: str, logs: str, project_name: str, project_path: str):
    if HAS_RICH:
        c = _console()
        c.print()
        c.print(Panel.fit(
            f"[bold green]\u2705  SUCCESS[/]\n\n"
            f"[bold]Project:[/]  [cyan]{project_name}[/]\n"
            f"[bold]Command:[/]  [cyan]{cmd}[/]\n"
            f"[bold]Location:[/] {project_path}",
            box=box.ROUNDED,
            border_style="green",
            padding=(1, 4)
        ))
        if logs:
            c.print("\n[bold]📋 Output:[/]")
            c.print(Syntax(logs[:2000], "bash", theme="monokai", word_wrap=True))
        c.print(f"\n[dim]To run manually:[/]")
        c.print(f"  [cyan]$ {cmd}[/]")
        c.print(f"\n[dim italic]{CREDIT}[/]")
    else:
        print(f"\n\u2705 SUCCESS")
        print(f"  Project: {project_name}")
        print(f"  Command: {cmd}")
        print(f"  Location: {project_path}")
        if logs:
            print(f"\n  Output:\n{logs[:1000]}")
        print(f"\n  To run manually: $ {cmd}")
        print(f"\n  {CREDIT}")


def print_failure(error_log: str, plan: dict, manual_steps: list[str] | None = None):
    if HAS_RICH:
        c = _console()
        c.print()
        c.print(Panel.fit(
            "[bold red]\u274c  FAILURE[/]\n\n"
            "Runit exhausted all strategies.\n"
            "The project could not be started automatically.",
            box=box.ROUNDED,
            border_style="red",
            padding=(1, 4)
        ))
        c.print("\n[bold red]Error Trace:[/]")
        c.print(Syntax(error_log[-1500:], "bash", theme="monokai", word_wrap=True))
        if manual_steps:
            c.print("\n[bold yellow]Suggested Manual Steps:[/]")
            for i, step in enumerate(manual_steps, 1):
                c.print(f"  {i}. {step}")
        c.print(f"\n[dim italic]{CREDIT}[/]")
    else:
        print(f"\n\u274c FAILURE")
        print("  Runit exhausted all strategies.")
        print(f"\n  Error Trace:\n{error_log[-1000:]}")
        if manual_steps:
            print("\n  Suggested Manual Steps:")
            for i, step in enumerate(manual_steps, 1):
                print(f"    {i}. {step}")
        print(f"\n  {CREDIT}")


def print_plan(plan: dict):
    required_env = plan.get("required_env", [])
    has_dotenv = plan.get("has_dotenv", False)

    if HAS_RICH:
        c = _console()
        table = Table(box=box.HEAVY_EDGE, border_style="blue", header_style="bold cyan")
        table.add_column("Property", style="bold yellow")
        table.add_column("Value", style="cyan")
        table.add_row("Type", plan.get("type", "?"))
        table.add_row("Entry", plan.get("entry", "?"))
        table.add_row("Fallbacks", ", ".join(plan.get("fallbacks", [])))
        table.add_row("Dependencies", ", ".join(plan.get("dependencies", [])))
        table.add_row("Command", plan.get("run_command", "?"))
        table.add_row("Description", plan.get("description", "")[:60])
        if required_env:
            table.add_row("Required Env", ", ".join(required_env[:8]))
            if len(required_env) > 8:
                table.add_row("", f"... and {len(required_env)-8} more")
        if has_dotenv:
            table.add_row("Dotenv", "\U0001f4c4 .env.example found")
        c.print("\n[bold]📋 Execution Plan:[/]")
        c.print(table)
        if required_env:
            c.print(f"\n  \U0001f511 [yellow]{len(required_env)} env var(s) detected[/]")
    else:
        print("\n  Execution Plan:")
        print(f"    Type:         {plan.get('type', '?')}")
        print(f"    Entry:        {plan.get('entry', '?')}")
        print(f"    Fallbacks:    {', '.join(plan.get('fallbacks', []))}")
        print(f"    Dependencies: {', '.join(plan.get('dependencies', []))}")
        print(f"    Command:      {plan.get('run_command', '?')}")
        print(f"    Description:  {plan.get('description', '')[:60]}")
        if required_env:
            print(f"    Required Env: {', '.join(required_env)}")
        if has_dotenv:
            print("    Dotenv:       .env.example found")


def print_skill(skill: dict | None):
    if not skill:
        return
    if HAS_RICH:
        c = _console()
        c.print(Panel(
            f"[bold green]\U0001f9e0 {skill['name']}[/]\n[dim]{skill['description']}[/]",
            box=box.SIMPLE,
            border_style="green",
            width=60
        ))
    else:
        print(f"  \U0001f9e0 {skill['name']}: {skill['description']}")


def confirm(msg: str, default: bool = True) -> bool:
    if AUTO_YES:
        return True
    is_notebook = False
    try:
        from runit.environment import is_notebook_env
        is_notebook = is_notebook_env()
    except Exception:
        pass
    if HAS_RICH and not is_notebook:
        return RichConfirm.ask(f"[bold]{msg}[/]", default=default)
    suffix = " [Y/n]" if default else " [y/N]"
    print(f"  {msg}{suffix}")
    try:
        val = input("  > ").strip().lower()
        if not val:
            return default
        return val in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return default


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def prompt_input(msg: str, secret: bool = False, default: str = "") -> str:
    if AUTO_YES:
        return default
    is_notebook = False
    try:
        from runit.environment import is_notebook_env
        is_notebook = is_notebook_env()
    except Exception:
        pass
    if HAS_RICH and _is_tty() and not is_notebook:
        from rich.prompt import Prompt
        if secret:
            return Prompt.ask(f"[bold]{msg}[/]", password=True, default=default)
        return Prompt.ask(f"[bold]{msg}[/]", default=default)
    prompt_text = f"  {msg}"
    if default:
        prompt_text += f" [{default}]"
    prompt_text += ": "
    if secret:
        try:
            if _is_tty() and not is_notebook:
                import getpass
                try:
                    return getpass.getpass(prompt_text) or default
                except Exception:
                    pass
            val = input(prompt_text)
            return val.strip() or default
        except (EOFError, KeyboardInterrupt):
            return default
    try:
        val = input(prompt_text)
        return val.strip() or default
    except (EOFError, KeyboardInterrupt):
        return default


def print_key_request(var_name: str, project_name: str):
    if HAS_RICH:
        c = _console()
        c.print()
        c.print(Panel.fit(
            f"[bold yellow]\U0001f511  API Key / Token Required[/]\n\n"
            f"[bold]{project_name}[/] needs: [cyan]{var_name}[/]\n\n"
            "Stored locally in ~/.runit/keys.json.\n"
            "Never shared or uploaded.",
            box=box.ROUNDED,
            border_style="yellow",
            padding=(1, 3)
        ))
    else:
        print(f"\n  \U0001f511 API Key / Token Required")
        print(f"  Project needs: {var_name}")
        print(f"  Stored locally in ~/.runit/keys.json")


def print_keystore():
    from runit.config import list_keys
    keys = list_keys()
    if HAS_RICH:
        c = _console()
        if not keys:
            c.print("[dim]No stored keys.[/]")
            return
        table = Table(box=box.SIMPLE, border_style="yellow", title="\U0001f511 Stored Keys")
        table.add_column("Name", style="bold")
        table.add_column("Value", style="dim")
        for name, value in keys.items():
            masked = value[:6] + "..." + value[-4:] if len(value) > 12 else "***"
            table.add_row(name, masked)
        c.print(table)
    else:
        if not keys:
            print("  No stored keys.")
            return
        print("  Stored Keys:")
        for name, value in keys.items():
            masked = value[:6] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"    {name}: {masked}")


def print_github_readme(readme_text: str):
    if not readme_text:
        return
    if HAS_RICH:
        c = _console()
        from rich.markdown import Markdown
        try:
            md = Markdown(readme_text[:2000])
            c.print(Panel(md, title="\U0001f4d6 README", border_style="dim", width=70))
        except Exception:
            c.print(f"[dim]{readme_text[:500]}[/]")
    else:
        print(f"\n  README:\n  {readme_text[:500]}")


def print_docker_prompt(has_docker_setup: bool, has_dev_scripts: bool):
    if HAS_RICH:
        c = _console()
        text = Text()
        text.append("\n  \U0001f433  ", style="bold cyan")
        text.append("This project supports multiple run modes\n", style="bold")
        options = []
        if has_docker_setup:
            options.append("    [cyan]1[/]  \U0001f4e6  Docker — production mode (pull & run container)")
        if has_dev_scripts:
            options.append("    [cyan]2[/]  \U0001f4bb  Development — run source code directly")
        text.append("\n".join(options))
        text.append("\n    [dim]Enter 1 or 2[/]")
        c.print(Panel(text, box=box.SQUARE, border_style="cyan", padding=(1, 2)))
    else:
        print("\n  \U0001f433  This project supports multiple run modes:")
        if has_docker_setup:
            print("    1 \U0001f4e6 Docker — production mode (pull & run container)")
        if has_dev_scripts:
            print("    2 \U0001f4bb Development — run source code directly")
