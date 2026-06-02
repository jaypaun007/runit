import json
import re
from runit.config import load_config
from runit.llm import llm_call
from runit.cli import _console


class AgentCore:
    def __init__(self, project_path: str, console=None, auto_yes: bool = False,
                 max_steps: int = 50, system_prompt: str = ""):
        self.project_path = project_path
        self.c = console or _console()
        self.auto_yes = auto_yes
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.steps_taken = 0
        self.last_result = None
        self.error_history = []
        self.context = {}
        self.action_history = []

    def cprint(self, msg):
        if self.c:
            self.c.print(msg)

    def _is_repeating(self, tool: str, args: dict) -> bool:
        sig = (tool, str(sorted(args.items())))
        recent = self.action_history[-5:]
        count = sum(1 for a in recent if a == sig)
        if count >= 2:
            self.error_history.append(f"Repeated action: {tool}")
            return True
        return False

    def _force_new_tool(self):
        tools_used = set(a[0] for a in self.action_history[-10:])
        suggestions = []
        if "research_project" in tools_used and "read_file" not in tools_used:
            suggestions.append("read_file")
        if "read_file" in tools_used and "run_command" not in tools_used:
            suggestions.append("run_command")
        if "list_dir" not in tools_used:
            suggestions.append("list_dir")
        if suggestions:
            return f"You've been repeating tools. Try something different like: {', '.join(suggestions)}"
        return ""

    def run(self, task: str, tools: dict) -> dict:
        cfg = load_config()
        if not cfg.get("api_key"):
            return {"status": "no_api", "result": "AI agent requires an API key"}

        context = f"""Task: {task}
Project: {self.project_path}

Work through this step by step. Use tools to explore, understand, and execute.
IMPORTANT: 
- You can ask the user for API keys, passwords, or choices using ask_user.
- If research_project returns empty data, read files directly with read_file and list_dir.
- NEVER call the same tool more than twice in a row. Try different approaches."""

        while self.steps_taken < self.max_steps:
            self.steps_taken += 1

            extra_hint = self._force_new_tool()
            warning = ""
            if extra_hint:
                warning = f"\n\n⚠️  {extra_hint}"

            prompt = f"""{context}

Previous result: {self.last_result if self.last_result else 'Starting...'}
Errors so far: {'; '.join(self.error_history[-3:]) if self.error_history else 'None'}
{warning}

Step {self.steps_taken}/{self.max_steps}. What should I do next?
Respond with JSON: {{"thought": "...", "action": "tool_name or done", "args": {{}}, "done": bool}}"""

            try:
                raw = llm_call(prompt, system=self.system_prompt)
                response = self._parse_response(raw)
                if response is None:
                    continue

                if response.get("done"):
                    result = response.get("result", "")
                    if isinstance(result, str):
                        try:
                            result = json.loads(result)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    return {
                        "status": "success",
                        "result": result,
                        "steps": self.steps_taken,
                    }

                tool = response.get("action")
                args = response.get("args", {})
                thought = response.get("thought", "")

                if self._is_repeating(tool, args):
                    if self.c:
                        self.cprint(f"  [yellow]Breaking repeat cycle: {tool} called too many times[/]")
                    self.last_result = "That tool was already called recently. Try a different approach."
                    continue

                self.action_history.append((tool, str(sorted(args.items()))))

                if self.c:
                    self.cprint(f"  [dim]> {thought}[/]")

                if tool == "ask_user":
                    if self.auto_yes:
                        self.last_result = "User skipped (auto_yes mode)"
                    else:
                        user_input = self._ask_user(
                            args.get("question", ""),
                            args.get("secret", False)
                        )
                        self.last_result = f"User responded: {user_input[:200]}"
                    continue

                if tool in tools:
                    try:
                        result = tools[tool](self.project_path, args)
                        self.last_result = result.get("_text", str(result)[:2000])
                    except Exception as e:
                        self.last_result = f"Tool error: {e}"
                        self.error_history.append(f"{tool}: {e}")
                else:
                    self.last_result = f"Unknown tool: {tool}"
                    self.error_history.append(f"Unknown tool: {tool}")

            except Exception as e:
                if self.c:
                    self.cprint(f"  [yellow]Agent error: {e}[/]")
                self.error_history.append(str(e))
                continue

        return {
            "status": "max_steps",
            "result": f"Reached max steps ({self.max_steps})",
            "steps": self.steps_taken,
        }

    def _parse_response(self, raw: str) -> dict | None:
        response = raw.strip()
        if not response:
            self.cprint(f"  [yellow]Agent: empty response[/]")
            return None

        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response[3:]
            end = response.rfind("```")
            if end >= 0:
                response = response[:end]

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{.*"thought".*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\{.*"action".*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        self.cprint(f"  [yellow]Agent: could not parse JSON, retrying...[/]")
        return None

    def _ask_user(self, question: str, secret: bool = False) -> str:
        try:
            val = input(f"  \U0001f4ac Agent asks: {question}: ")
            return val.strip()
        except (EOFError, KeyboardInterrupt):
            return ""
