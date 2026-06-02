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
        "frameworks": ["django", "flask", "fastapi", "streamlit", "gradio", "dash"],
        "runtime_check": ["python3", "python"],
        "runtime_install": ["apt-get install -y python3 python3-pip"],
    },
    "node": {
        "name": "Node.js Expert",
        "description": "Handles Node.js projects: npm/pnpm/yarn, npx, Next.js, Express",
        "install_cmd": ["npm", "install"],
        "detect_files": ["package.json", "yarn.lock", "pnpm-lock.yaml", "pnpm-workspace.yaml"],
        "entry_candidates": ["index.js", "server.js", "app.js", "main.js", "cli.js", "bin/www", "next.config.js", "next.config.mjs"],
        "lock_files": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "setup_steps": ["npm install", "npm run build"],
        "frameworks": ["next.js", "express", "react", "vue", "svelte", "nuxt", "gatsby", "remix"],
        "runtime_check": ["node", "nodejs"],
        "runtime_install": ["apt-get install -y nodejs npm"],
    },
    "rust": {
        "name": "Rust Expert",
        "description": "Handles Rust projects: cargo build, run",
        "install_cmd": ["cargo", "build"],
        "detect_files": ["Cargo.toml"],
        "entry_candidates": ["src/main.rs", "src/lib.rs"],
        "lock_files": ["Cargo.lock"],
        "setup_steps": ["cargo build"],
        "frameworks": ["actix", "rocket", "axum", "warp", "tokio"],
        "runtime_check": ["cargo", "rustc"],
        "runtime_install": ["curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
    },
    "go": {
        "name": "Go Expert",
        "description": "Handles Go projects: go mod, go run",
        "install_cmd": ["go", "mod", "download"],
        "detect_files": ["go.mod", "go.sum"],
        "entry_candidates": ["main.go", "cmd/main.go"],
        "lock_files": ["go.sum"],
        "setup_steps": ["go mod download"],
        "frameworks": ["gin", "echo", "fiber", "chi", "beego"],
        "runtime_check": ["go"],
        "runtime_install": ["apt-get install -y golang-go", "wget https://go.dev/dl/go1.22.linux-amd64.tar.gz"],
    },
    "ruby": {
        "name": "Ruby Expert",
        "description": "Handles Ruby projects: bundler, gem install, Rails",
        "install_cmd": ["bundle", "install"],
        "detect_files": ["Gemfile", "Gemfile.lock"],
        "entry_candidates": ["main.rb", "app.rb", "server.rb", "bin/setup", "bin/rails"],
        "lock_files": ["Gemfile.lock"],
        "setup_steps": ["bundle install"],
        "frameworks": ["rails", "sinatra", "jekyll", "hanami"],
        "runtime_check": ["ruby"],
        "runtime_install": ["apt-get install -y ruby ruby-dev"],
    },
    "deno": {
        "name": "Deno Expert",
        "description": "Handles Deno projects: deno run",
        "install_cmd": [],
        "detect_files": ["deno.json", "deno.jsonc", "import_map.json"],
        "entry_candidates": ["main.ts", "main.js", "mod.ts", "cli.ts"],
        "lock_files": [],
        "setup_steps": [],
        "frameworks": ["oak", "hono", "fresh"],
        "runtime_check": ["deno"],
        "runtime_install": ["curl -fsSL https://deno.land/install.sh | sh"],
    },
    "java": {
        "name": "Java Expert",
        "description": "Handles Java projects: mvn, gradle, Spring Boot",
        "install_cmd": [],
        "detect_files": ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
        "entry_candidates": [],
        "lock_files": [],
        "setup_steps": ["mvn compile", "gradle build"],
        "frameworks": ["spring", "spring boot", "quarkus", "micronaut", "hibernate"],
        "runtime_check": ["java", "javac"],
        "runtime_install": ["apt-get install -y default-jdk"],
    },
    "c_cpp": {
        "name": "C/C++ Expert",
        "description": "Handles C and C++ projects: cmake, make, gcc/clang",
        "install_cmd": ["make"],
        "detect_files": ["CMakeLists.txt", "Makefile", "configure", "configure.ac", "meson.build"],
        "entry_candidates": ["main.c", "main.cpp", "src/main.c", "src/main.cpp"],
        "lock_files": [],
        "setup_steps": ["cmake . && make", "./configure && make", "make"],
        "frameworks": [],
        "runtime_check": ["gcc", "clang", "g++"],
        "runtime_install": ["apt-get install -y build-essential cmake"],
    },
    "csharp": {
        "name": "C# / .NET Expert",
        "description": "Handles C# and .NET projects: dotnet build/run, ASP.NET, Blazor",
        "install_cmd": ["dotnet", "restore"],
        "detect_files": ["*.csproj", "*.sln", "global.json"],
        "entry_candidates": ["Program.cs", "Main.cs", "src/Program.cs"],
        "lock_files": [],
        "setup_steps": ["dotnet restore", "dotnet build"],
        "frameworks": ["asp.net", "blazor", "wpf", "winforms", "entity framework"],
        "runtime_check": ["dotnet"],
        "runtime_install": ["wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh && bash dotnet-install.sh"],
    },
    "php": {
        "name": "PHP Expert",
        "description": "Handles PHP projects: composer, artisan, Laravel, Symfony",
        "install_cmd": ["composer", "install"],
        "detect_files": ["composer.json", "composer.lock", "artisan"],
        "entry_candidates": ["index.php", "public/index.php", "artisan", "bin/console"],
        "lock_files": ["composer.lock"],
        "setup_steps": ["composer install"],
        "frameworks": ["laravel", "symfony", "wordpress", "drupal", "codeigniter"],
        "runtime_check": ["php"],
        "runtime_install": ["apt-get install -y php php-cli php-mbstring composer"],
    },
    "kotlin": {
        "name": "Kotlin Expert",
        "description": "Handles Kotlin projects: gradle, kotlinc, Ktor",
        "install_cmd": [],
        "detect_files": ["*.kt", "build.gradle.kts", "settings.gradle.kts"],
        "entry_candidates": ["Main.kt", "src/Main.kt", "src/main/kotlin/Main.kt"],
        "lock_files": [],
        "setup_steps": ["gradle build", "kotlinc Main.kt -include-runtime -d main.jar"],
        "frameworks": ["ktor", "spring", "kotlinx"],
        "runtime_check": ["kotlin", "kotlinc"],
        "runtime_install": ["apt-get install -y kotlin"],
    },
    "dart": {
        "name": "Dart/Flutter Expert",
        "description": "Handles Dart and Flutter projects: pub get, dart/flutter run",
        "install_cmd": ["pub", "get"],
        "detect_files": ["pubspec.yaml", "pubspec.lock"],
        "entry_candidates": ["lib/main.dart", "bin/main.dart", "main.dart"],
        "lock_files": ["pubspec.lock"],
        "setup_steps": ["dart pub get", "flutter pub get"],
        "frameworks": ["flutter", "angular dart"],
        "runtime_check": ["dart", "flutter"],
        "runtime_install": ["apt-get install -y dart"],
    },
    "r_lang": {
        "name": "R Expert",
        "description": "Handles R projects: Rscript, renv, install.packages",
        "install_cmd": ["Rscript", "-e", "install.packages"],
        "detect_files": ["DESCRIPTION", "NAMESPACE", "*.Rproj"],
        "entry_candidates": ["main.R", "app.R", "run.R", "server.R"],
        "lock_files": ["renv.lock"],
        "setup_steps": ["Rscript -e 'renv::restore()'", "R CMD INSTALL ."],
        "frameworks": ["shiny", "plumber", "tidyverse"],
        "runtime_check": ["R", "Rscript"],
        "runtime_install": ["apt-get install -y r-base"],
    },
    "julia": {
        "name": "Julia Expert",
        "description": "Handles Julia projects: julia run, Pkg",
        "install_cmd": ["julia", "-e", "using Pkg; Pkg.instantiate()"],
        "detect_files": ["Project.toml", "Manifest.toml"],
        "entry_candidates": ["main.jl", "src/main.jl", "app.jl", "run.jl"],
        "lock_files": ["Manifest.toml"],
        "setup_steps": ["julia -e 'using Pkg; Pkg.instantiate()'"],
        "frameworks": ["flux", "genie"],
        "runtime_check": ["julia"],
        "runtime_install": ["apt-get install -y julia"],
    },
    "lua": {
        "name": "Lua Expert",
        "description": "Handles Lua projects: lua/luajit, luarocks, LÖVE",
        "install_cmd": ["luarocks", "install"],
        "detect_files": ["*.rockspec", ".luarocks", "conf.lua"],
        "entry_candidates": ["main.lua", "init.lua", "src/main.lua", "app.lua"],
        "lock_files": [],
        "setup_steps": ["luarocks install"],
        "frameworks": ["love", "lapis"],
        "runtime_check": ["lua", "luajit"],
        "runtime_install": ["apt-get install -y lua5.4 luarocks"],
    },
    "scala": {
        "name": "Scala Expert",
        "description": "Handles Scala projects: sbt, scalac, Akka, Play",
        "install_cmd": ["sbt", "update"],
        "detect_files": ["build.sbt", "*.scala", "build.sc"],
        "entry_candidates": ["Main.scala", "src/main/scala/Main.scala", "App.scala"],
        "lock_files": [],
        "setup_steps": ["sbt compile"],
        "frameworks": ["akka", "play", "http4s", "cats"],
        "runtime_check": ["scala", "scalac", "sbt"],
        "runtime_install": ["apt-get install -y scala"],
    },
    "elixir": {
        "name": "Elixir Expert",
        "description": "Handles Elixir projects: mix deps.get, mix run, Phoenix",
        "install_cmd": ["mix", "deps.get"],
        "detect_files": ["mix.exs", "mix.lock"],
        "entry_candidates": ["lib/main.ex", "mix.exs"],
        "lock_files": ["mix.lock"],
        "setup_steps": ["mix deps.get", "mix compile"],
        "frameworks": ["phoenix", "phoenix liveview", "nerves", "absinthe"],
        "runtime_check": ["elixir", "mix"],
        "runtime_install": ["apt-get install -y elixir"],
    },
    "docker_compose": {
        "name": "Docker Compose Expert",
        "description": "Handles Docker Compose projects: docker-compose up with service orchestration",
        "install_cmd": [],
        "detect_files": ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"],
        "entry_candidates": [],
        "lock_files": [],
        "setup_steps": ["docker compose up -d", "docker compose up"],
        "frameworks": [],
        "runtime_check": ["docker", "docker-compose"],
        "runtime_install": ["apt-get install -y docker.io docker-compose-v2"],
    },
    "dockerfile": {
        "name": "Docker Expert",
        "description": "Handles Docker projects: docker build and run",
        "install_cmd": [],
        "detect_files": ["Dockerfile", "Dockerfile.dev", "Containerfile"],
        "entry_candidates": [],
        "lock_files": [],
        "setup_steps": ["docker build -t project .", "docker run project"],
        "frameworks": [],
        "runtime_check": ["docker"],
        "runtime_install": ["apt-get install -y docker.io"],
    },
    "nextjs": {
        "name": "Next.js Expert",
        "description": "Handles Next.js projects: full-stack React framework",
        "install_cmd": ["npm", "install"],
        "detect_files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "entry_candidates": ["pages/index.js", "app/page.js", "src/app/page.js"],
        "lock_files": ["package-lock.json", "yarn.lock"],
        "setup_steps": ["npm install", "npm run build"],
        "frameworks": ["next.js", "react"],
        "runtime_check": ["node"],
        "runtime_install": ["apt-get install -y nodejs npm"],
    },
    "fastapi": {
        "name": "FastAPI Expert",
        "description": "Handles FastAPI Python projects with uvicorn",
        "install_cmd": ["{python}", "-m", "pip", "install"],
        "detect_files": ["main.py"],
        "entry_candidates": ["main.py", "app.py", "api.py"],
        "lock_files": ["requirements.txt"],
        "setup_steps": ["pip install -r requirements.txt", "pip install uvicorn fastapi"],
        "frameworks": ["fastapi"],
        "runtime_check": ["python3", "python"],
        "runtime_install": ["apt-get install -y python3 python3-pip"],
    },
}

FRAMEWORK_ALIASES = {
    "next": "nextjs",
    "next.js": "nextjs",
    "fastapi": "fastapi",
    "flask": "python",
    "django": "python",
    "express": "node",
    "react": "node",
    "vue": "node",
    "svelte": "node",
    "angular": "node",
    "rails": "ruby",
    "spring": "java",
    "laravel": "php",
    "phoenix": "elixir",
    "shiny": "r_lang",
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
    resolved = FRAMEWORK_ALIASES.get(project_type)
    if resolved and resolved in SKILLS_REGISTRY:
        return {**SKILLS_REGISTRY[resolved], "id": resolved}
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
    if not skill:
        resolved = FRAMEWORK_ALIASES.get(project_type)
        if resolved:
            skill = SKILLS_REGISTRY.get(resolved)
    if skill:
        return skill.get("setup_steps", [])
    return []


def detect_framework(project_path: str) -> str | None:
    root = Path(project_path)
    for key, skill in SKILLS_REGISTRY.items():
        frameworks = skill.get("frameworks", [])
        for fw in frameworks:
            fw_files = list(root.glob(f"*{fw}*")) + list(root.glob(f"**/*{fw}*"))
            if fw_files:
                return fw
    return None


def get_runtime_install_cmd(project_type: str) -> list[str]:
    skill = SKILLS_REGISTRY.get(project_type)
    if skill:
        return skill.get("runtime_install", [])
    return []
