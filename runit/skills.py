import shutil
from pathlib import Path


SKILLS_REGISTRY = {
    "python": {
        "name": "Python Expert",
        "description": "Handles Python projects: venv, pip, import fixes",
        "install_cmd": ["{python}", "-m", "pip", "install"],
        "detect_files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
        "entry_candidates": ["main.py", "app.py", "cli.py", "run.py", "index.py", "server.py", "bot.py"],
        "lock_files": ["requirements.txt", "Pipfile.lock", "poetry.lock"],
        "setup_steps": ["pip install -r requirements.txt", "pip install -e ."],
    },
    "node": {
        "name": "Node.js Expert",
        "description": "Handles Node.js projects: npm/pnpm/yarn, package.json, npx",
        "install_cmd": ["npm", "install"],
        "detect_files": ["package.json", "yarn.lock", "pnpm-lock.yaml", "pnpm-workspace.yaml"],
        "entry_candidates": ["index.js", "server.js", "app.js", "main.js", "cli.js", "bin/www"],
        "lock_files": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "setup_steps": ["npm install", "npm run build"],
    },
    "rust": {
        "name": "Rust Expert",
        "description": "Handles Rust projects: cargo build, run",
        "install_cmd": ["cargo", "build"],
        "detect_files": ["Cargo.toml"],
        "entry_candidates": ["src/main.rs", "src/lib.rs"],
        "lock_files": ["Cargo.lock"],
        "setup_steps": ["cargo build"],
    },
    "go": {
        "name": "Go Expert",
        "description": "Handles Go projects: go mod, go run",
        "install_cmd": ["go", "mod", "download"],
        "detect_files": ["go.mod", "go.sum"],
        "entry_candidates": ["main.go", "cmd/main.go"],
        "lock_files": ["go.sum"],
        "setup_steps": ["go mod download"],
    },
    "ruby": {
        "name": "Ruby Expert",
        "description": "Handles Ruby projects: bundler, gem install",
        "install_cmd": ["bundle", "install"],
        "detect_files": ["Gemfile", "Gemfile.lock"],
        "entry_candidates": ["main.rb", "app.rb", "server.rb", "bin/setup"],
        "lock_files": ["Gemfile.lock"],
        "setup_steps": ["bundle install"],
    },
    "deno": {
        "name": "Deno Expert",
        "description": "Handles Deno projects: deno run",
        "install_cmd": [],
        "detect_files": ["deno.json", "deno.jsonc", "import_map.json"],
        "entry_candidates": ["main.ts", "main.js", "mod.ts", "cli.ts"],
        "lock_files": [],
        "setup_steps": [],
    },
    "java": {
        "name": "Java Expert",
        "description": "Handles Java projects: mvn, gradle",
        "install_cmd": [],
        "detect_files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "entry_candidates": [],
        "lock_files": [],
        "setup_steps": ["mvn compile", "gradle build"],
    },
    "c_cpp": {
        "name": "C/C++ Expert",
        "description": "Handles C and C++ projects: cmake, make, gcc/clang",
        "install_cmd": ["make"],
        "detect_files": ["CMakeLists.txt", "Makefile", "configure", "configure.ac", "meson.build"],
        "entry_candidates": ["main.c", "main.cpp", "src/main.c", "src/main.cpp"],
        "lock_files": [],
        "setup_steps": ["cmake . && make", "./configure && make", "make"],
    },
    "csharp": {
        "name": "C# / .NET Expert",
        "description": "Handles C# and .NET projects: dotnet build/run",
        "install_cmd": ["dotnet", "restore"],
        "detect_files": ["*.csproj", "*.sln", "global.json"],
        "entry_candidates": ["Program.cs", "Main.cs", "src/Program.cs"],
        "lock_files": [],
        "setup_steps": ["dotnet restore", "dotnet build"],
    },
    "php": {
        "name": "PHP Expert",
        "description": "Handles PHP projects: composer, artisan",
        "install_cmd": ["composer", "install"],
        "detect_files": ["composer.json", "composer.lock", "artisan"],
        "entry_candidates": ["index.php", "public/index.php", "artisan", "bin/console"],
        "lock_files": ["composer.lock"],
        "setup_steps": ["composer install"],
    },
    "kotlin": {
        "name": "Kotlin Expert",
        "description": "Handles Kotlin projects: gradle, kotlinc",
        "install_cmd": [],
        "detect_files": ["*.kt", "build.gradle.kts", "settings.gradle.kts"],
        "entry_candidates": ["Main.kt", "src/Main.kt", "src/main/kotlin/Main.kt"],
        "lock_files": [],
        "setup_steps": ["gradle build", "kotlinc Main.kt -include-runtime -d main.jar"],
    },
    "dart": {
        "name": "Dart/Flutter Expert",
        "description": "Handles Dart and Flutter projects: pub get, dart/flutter run",
        "install_cmd": ["pub", "get"],
        "detect_files": ["pubspec.yaml", "pubspec.lock"],
        "entry_candidates": ["lib/main.dart", "bin/main.dart", "main.dart"],
        "lock_files": ["pubspec.lock"],
        "setup_steps": ["dart pub get", "flutter pub get"],
    },
    "r_lang": {
        "name": "R Expert",
        "description": "Handles R projects: Rscript, renv, install.packages",
        "install_cmd": ["Rscript", "-e", "install.packages"],
        "detect_files": ["DESCRIPTION", "NAMESPACE", "*.Rproj"],
        "entry_candidates": ["main.R", "app.R", "run.R", "server.R"],
        "lock_files": ["renv.lock"],
        "setup_steps": ["Rscript -e 'renv::restore()'", "R CMD INSTALL ."],
    },
    "julia": {
        "name": "Julia Expert",
        "description": "Handles Julia projects: julia run, Pkg",
        "install_cmd": ["julia", "-e", "using Pkg; Pkg.instantiate()"],
        "detect_files": ["Project.toml", "Manifest.toml"],
        "entry_candidates": ["main.jl", "src/main.jl", "app.jl", "run.jl"],
        "lock_files": ["Manifest.toml"],
        "setup_steps": ["julia -e 'using Pkg; Pkg.instantiate()'"],
    },
    "lua": {
        "name": "Lua Expert",
        "description": "Handles Lua projects: lua/luajit, luarocks",
        "install_cmd": ["luarocks", "install"],
        "detect_files": ["*.rockspec", ".luarocks", "conf.lua"],
        "entry_candidates": ["main.lua", "init.lua", "src/main.lua", "app.lua"],
        "lock_files": [],
        "setup_steps": ["luarocks install"],
    },
    "scala": {
        "name": "Scala Expert",
        "description": "Handles Scala projects: sbt, scalac",
        "install_cmd": ["sbt", "update"],
        "detect_files": ["build.sbt", "*.scala", "build.sc"],
        "entry_candidates": ["Main.scala", "src/main/scala/Main.scala", "App.scala"],
        "lock_files": [],
        "setup_steps": ["sbt compile"],
    },
    "elixir": {
        "name": "Elixir Expert",
        "description": "Handles Elixir projects: mix deps.get, mix run",
        "install_cmd": ["mix", "deps.get"],
        "detect_files": ["mix.exs", "mix.lock"],
        "entry_candidates": ["lib/main.ex", "mix.exs"],
        "lock_files": ["mix.lock"],
        "setup_steps": ["mix deps.get", "mix compile"],
    },
}


def match_skills(project_path: str) -> list[dict]:
    root = Path(project_path)
    matched = []
    for key, skill in SKILLS_REGISTRY.items():
        for fname in skill["detect_files"]:
            if fname.startswith("*"):
                pattern = fname[1:]
                if list(root.glob(f"*{pattern}")) or list(root.glob(f"**/{pattern}")):
                    matched.append({**skill, "id": key})
                    break
            elif (root / fname).exists():
                matched.append({**skill, "id": key})
                break
    return matched


def get_skill(project_type: str) -> dict | None:
    if project_type in SKILLS_REGISTRY:
        return {**SKILLS_REGISTRY[project_type], "id": project_type}
    return None


def has_pnpm(project_path: str) -> bool:
    root = Path(project_path)
    return (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists()


def has_pnpm_cli() -> bool:
    return shutil.which("pnpm") is not None


def detect_package_manager(project_path: str) -> str:
    root = Path(project_path)
    if (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists() or (root / "package.json").exists():
        return "npm"
    return "npm"


def get_build_instructions(project_type: str) -> list[str]:
    skill = SKILLS_REGISTRY.get(project_type)
    if skill:
        return skill.get("setup_steps", [])
    return []
