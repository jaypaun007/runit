import json
import re
from pathlib import Path
from runit.llm import llm_call
from runit.project_loader import get_file_tree
from runit.web_tools import web_search, fetch_github_readme, fetch_github_file_list
from runit.cli import print_web_research, print_github_readme
from runit.skills import detect_package_manager, has_pnpm
from runit.environment import has_docker

ANALYSIS_SYSTEM_PROMPT = """You are Runit, an AI project analysis agent. Your job is to analyze codebases and determine how to run them.

Rules:
- Identify the project type (python, node, rust, go, ruby, deno, java, or mixed)
- Find the main entry file
- List fallback entry files
- Identify dependency files
- Provide the exact run command
- Check for required environment variables / API keys
- Detect Docker/dev mode options
- Return ONLY valid JSON

Output schema:
{
  "type": "python|node|rust|go|ruby|deno|java|mixed",
  "entry": "main.py",
  "fallbacks": ["app.py", "index.py"],
  "dependencies": ["requirements.txt"],
  "run_command": "python main.py",
  "description": "Brief project description",
  "required_env": ["API_KEY", "DATABASE_URL"],
  "has_dotenv": true|false,
  "has_docker": true|false,
  "docker_image": "ghcr.io/org/repo:tag",
  "dev_scripts": ["dev", "start", "setup"],
  "package_manager": "npm|pnpm|yarn"
}"""


ENV_VAR_PATTERNS = [
    r'os\.getenv\(["\']([A-Z_]+)["\']',
    r'os\.environ\.get\(["\']([A-Z_]+)["\']',
    r'os\.environ\[["\']([A-Z_]+)["\']',
    r'process\.env\.([A-Z_]+)',
    r'process\.env\[["\']([A-Z_]+)["\']',
    r'env\(["\']([A-Z_]+)["\']',
    r'deno\.env\.toObject\(\)\.([A-Z_]+)',
    r'\$\(["\']([A-Z_]+)["\']\)',
    r'config\(["\']([A-Z_]+)["\']',
]


def _scan_env_vars(project_path: str) -> list[str]:
    root = Path(project_path)
    found = set()
    excluded = {"PATH", "HOME", "USER", "SHELL", "PWD", "LANG", "TERM", "PYTHONPATH", "NODE_PATH"}

    src_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go", ".rs", ".sh", ".env.example", ".env.sample"}

    for f in root.rglob("*"):
        if f.suffix not in src_exts and f.name not in (".env.example", ".env.sample"):
            continue
        if any(part.startswith(".") for part in f.parts) and f.name not in (".env.example", ".env.sample"):
            continue
        if f.name in ("node_modules", "__pycache__", ".git", "venv", ".venv"):
            continue
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        for pattern in ENV_VAR_PATTERNS:
            for m in re.finditer(pattern, text):
                var = m.group(1)
                if var not in excluded:
                    found.add(var)

    env_example = root / ".env.example"
    if env_example.exists():
        try:
            for line in env_example.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    found.add(line.split("=")[0].strip())
        except Exception:
            pass

    env_sample = root / ".env.sample"
    if env_sample.exists():
        try:
            for line in env_sample.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    found.add(line.split("=")[0].strip())
        except Exception:
            pass

    return sorted(found)


def _read_key_files(project_path: str) -> str:
    root = Path(project_path)
    candidates = [
        "main.py", "app.py", "index.py", "cli.py", "run.py", "server.py", "bot.py",
        "package.json", "requirements.txt", "Makefile", "README.md",
        "setup.py", "pyproject.toml", "Cargo.toml", "go.mod",
        "index.js", "server.js", "app.js", "main.js",
        "Gemfile", "Pipfile", "deno.json", "deno.jsonc",
        "pom.xml", "build.gradle", "Dockerfile", "docker-compose.yml",
        ".env.example", ".env.sample",
    ]
    parts = []
    for name in candidates:
        fp = root / name
        if fp.exists() and fp.is_file():
            try:
                text = fp.read_text(errors="replace")[:1500]
                parts.append(f"--- {name} ---\n{text}")
            except Exception:
                parts.append(f"--- {name} ---\n<unreadable>")
    return "\n\n".join(parts)


def _detect_docker_options(project_path: str) -> dict:
    """Detect Docker support and dev scripts in the project."""
    root = Path(project_path)
    result = {"has_docker": False, "docker_image": "", "dev_scripts": [], "has_docker_compose": False}

    has_df = (root / "Dockerfile").exists()
    has_dc = (root / "docker-compose.yml").exists()
    result["has_docker"] = has_df or has_dc
    result["has_docker_compose"] = has_dc

    # Try to find docker image from README or scripts
    readme = root / "README.md"
    if readme.exists():
        text = readme.read_text(errors="replace")
        images = re.findall(r'(?:ghcr\.io|docker\.io)/[\w/-]+:[\w.]+', text)
        if images:
            result["docker_image"] = images[0]

    # Check for dev scripts in package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            import json as j
            pkg = j.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            for preferred in ["dev", "start", "setup", "develop", "serve"]:
                if preferred in scripts:
                    result["dev_scripts"].append(preferred)
            if not result["dev_scripts"]:
                result["dev_scripts"] = list(scripts.keys())[:3]
        except Exception:
            pass

    return result


def analyze_project(project_path: str, repo_url: str | None = None) -> dict:
    tree = get_file_tree(project_path, max_depth=2)
    key_files = _read_key_files(project_path)
    scanned_env = _scan_env_vars(project_path)
    docker_opts = _detect_docker_options(project_path)
    pm = detect_package_manager(project_path)

    context_parts = [
        "Analyze this project and tell me how to run it.\n\n",
        f"File structure:\n{json.dumps(tree, indent=2)}\n\n",
        f"Key file contents:\n{key_files}\n\n",
    ]

    if repo_url:
        readme = fetch_github_readme(repo_url)
        if readme:
            context_parts.append(f"GitHub README:\n{readme[:2000]}\n\n")
            print_github_readme(readme)

    prompt = "".join(context_parts) + (
        "Pay special attention to:\n"
        "- Entry point files\n"
        "- Required environment variables or API keys\n"
        "- Docker / docker-compose setup\n"
        "- Development scripts (dev, start, setup)"
    )

    try:
        response = llm_call(prompt, system=ANALYSIS_SYSTEM_PROMPT)
        plan = json.loads(response)
    except (json.JSONDecodeError, Exception):
        plan = _guess_plan(project_path)

    plan.setdefault("type", "python")
    plan.setdefault("entry", "main.py")
    plan.setdefault("fallbacks", ["app.py", "index.py", "run.py", "server.py", "cli.py"])
    plan.setdefault("dependencies", [])
    plan.setdefault("run_command", "")
    plan.setdefault("description", "")
    plan.setdefault("required_env", [])
    plan.setdefault("has_dotenv", False)

    # Merge Docker options
    plan["has_docker"] = docker_opts["has_docker"]
    plan["has_docker_compose"] = docker_opts["has_docker_compose"]
    plan["docker_image"] = docker_opts["docker_image"]
    plan["dev_scripts"] = docker_opts["dev_scripts"]
    plan["package_manager"] = pm

    if scanned_env:
        existing = set(plan.get("required_env", []))
        for var in scanned_env:
            if var not in existing:
                plan.setdefault("required_env", []).append(var)

    if (Path(project_path) / ".env.example").exists() or (Path(project_path) / ".env.sample").exists():
        plan["has_dotenv"] = True

    if plan.get("type") in ("python", "unknown") and not scanned_env:
        research_results = web_search(f"how to run {plan.get('description', 'this project')} github")
        if research_results:
            print_web_research(research_results)
            plan["_web_research"] = research_results

    return plan


def _guess_plan(project_path: str) -> dict:
    root = Path(project_path)
    files = {f.name for f in root.iterdir() if f.is_file() and not f.name.startswith(".")}
    dirs = {d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")}

    if files & {"Cargo.toml"}:
        return {"type": "rust", "entry": "src/main.rs", "fallbacks": ["src/lib.rs"],
                "dependencies": ["Cargo.toml"], "run_command": "cargo run", "description": "Rust project"}
    if files & {"go.mod"}:
        return {"type": "go", "entry": "main.go", "fallbacks": ["cmd/main.go"],
                "dependencies": ["go.mod"], "run_command": "go run .", "description": "Go project"}
    if files & {"pnpm-lock.yaml"} or files & {"pnpm-workspace.yaml"}:
        return {"type": "node", "entry": "", "fallbacks": [],
                "dependencies": ["pnpm-lock.yaml"], "run_command": "pnpm dev",
                "description": "Node.js pnpm monorepo project"}
    if files & {"package.json"}:
        return {"type": "node", "entry": "index.js", "fallbacks": ["server.js", "app.js", "main.js", "cli.js"],
                "dependencies": ["package.json"], "run_command": "node index.js", "description": "Node.js project"}
    if files & {"Gemfile"}:
        return {"type": "ruby", "entry": "main.rb", "fallbacks": ["app.rb", "server.rb"],
                "dependencies": ["Gemfile"], "run_command": "ruby main.rb", "description": "Ruby project"}
    if files & {"deno.json", "deno.jsonc"}:
        return {"type": "deno", "entry": "main.ts", "fallbacks": ["main.js", "mod.ts", "cli.ts"],
                "dependencies": ["deno.json"], "run_command": "deno run main.ts", "description": "Deno project"}
    if files & {"requirements.txt", "setup.py", "pyproject.toml"}:
        return {"type": "python", "entry": "main.py", "fallbacks": ["app.py", "index.py", "run.py", "server.py", "cli.py"],
                "dependencies": ["requirements.txt"], "run_command": "python main.py", "description": "Python project"}
    if files & {"pom.xml", "build.gradle"}:
        return {"type": "java", "entry": "", "fallbacks": [],
                "dependencies": ["pom.xml"], "run_command": "mvn compile exec:java", "description": "Java project"}

    # New project type detections
    if files & {"CMakeLists.txt", "Makefile", "configure", "configure.ac"}:
        cmd = "make" if "Makefile" in files else "cmake . && make"
        return {"type": "c_cpp", "entry": "main.c", "fallbacks": ["main.cpp", "src/main.c", "src/main.cpp"],
                "dependencies": ["CMakeLists.txt", "Makefile"], "run_command": cmd,
                "description": "C/C++ project"}
    csproj_files = list(root.glob("*.csproj"))
    if csproj_files or files & {"*.sln", "global.json"}:
        return {"type": "csharp", "entry": "Program.cs", "fallbacks": ["Main.cs", "src/Program.cs"],
                "dependencies": [csproj_files[0].name if csproj_files else "*.csproj"],
                "run_command": "dotnet run", "description": "C# / .NET project"}
    if files & {"composer.json", "composer.lock", "artisan"}:
        return {"type": "php", "entry": "index.php", "fallbacks": ["public/index.php", "artisan", "bin/console"],
                "dependencies": ["composer.json"], "run_command": "php -S localhost:8000",
                "description": "PHP project"}
    if files & {"pubspec.yaml", "pubspec.lock"}:
        return {"type": "dart", "entry": "lib/main.dart", "fallbacks": ["bin/main.dart", "main.dart"],
                "dependencies": ["pubspec.yaml"], "run_command": "dart run lib/main.dart",
                "description": "Dart/Flutter project"}
    if files & {"mix.exs", "mix.lock"}:
        return {"type": "elixir", "entry": "lib/main.ex", "fallbacks": ["mix.exs"],
                "dependencies": ["mix.exs"], "run_command": "mix run",
                "description": "Elixir project"}
    if files & {"build.sbt", "build.sc"}:
        return {"type": "scala", "entry": "Main.scala", "fallbacks": ["src/main/scala/Main.scala", "App.scala"],
                "dependencies": ["build.sbt"], "run_command": "sbt run",
                "description": "Scala project"}
    if files & {"Project.toml", "Manifest.toml"}:
        return {"type": "julia", "entry": "main.jl", "fallbacks": ["src/main.jl", "app.jl", "run.jl"],
                "dependencies": ["Project.toml"], "run_command": "julia main.jl",
                "description": "Julia project"}
    if files & {"DESCRIPTION", "NAMESPACE"} or list(root.glob("*.Rproj")):
        return {"type": "r_lang", "entry": "main.R", "fallbacks": ["app.R", "run.R", "server.R"],
                "dependencies": ["DESCRIPTION"], "run_command": "Rscript main.R",
                "description": "R project"}
    if list(root.glob("*.kt")) or files & {"build.gradle.kts", "settings.gradle.kts"}:
        return {"type": "kotlin", "entry": "Main.kt", "fallbacks": ["src/Main.kt", "src/main/kotlin/Main.kt"],
                "dependencies": ["build.gradle.kts"], "run_command": "kotlinc Main.kt -include-runtime -d main.jar && java -jar main.jar",
                "description": "Kotlin project"}
    if list(root.glob("*.rockspec")) or list(root.glob("*.lua")):
        return {"type": "lua", "entry": "main.lua", "fallbacks": ["init.lua", "src/main.lua", "app.lua"],
                "dependencies": [], "run_command": "lua main.lua",
                "description": "Lua project"}

    return {"type": "python", "entry": "main.py", "fallbacks": ["app.py", "index.py", "run.py", "server.py", "cli.py"],
            "dependencies": [], "run_command": "python main.py", "description": "Unknown project type (guessed Python)"}
