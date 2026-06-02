import subprocess
import sys
import shutil
from pathlib import Path
from runit.notify import notify_install
from runit.skills import detect_package_manager, has_pnpm, has_pnpm_cli


def _pip_install(packages: list[str]) -> bool:
    success = True
    for pkg in packages:
        notify_install(pkg, "python")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg, "--user"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                print(f"  \u26a0\ufe0f Could not install {pkg} (try: pip install {pkg})")
                success = False
    return success


def install_python_deps(project_path: str, extra_modules: list[str] | None = None):
    root = Path(project_path)
    req_file = root / "requirements.txt"
    if req_file.exists():
        notify_install("requirements.txt", "python")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--user"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                print(f"  \u26a0\ufe0f pip install failed. Try: pip install -r {req_file}")

    setup_file = root / "setup.py"
    if setup_file.exists():
        notify_install("setup.py (dev)", "python")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            pass

    if extra_modules:
        _pip_install(extra_modules)


def install_node_deps(project_path: str):
    root = Path(project_path)
    if not (root / "package.json").exists():
        return

    pm = detect_package_manager(project_path)
    notify_install(f"{pm} packages", "node")

    if pm == "pnpm":
        cmd = ["pnpm", "install"]
        if not has_pnpm_cli():
            print("  \u26a0\ufe0f pnpm not installed. Try: npm install -g pnpm")
            print("  \U0001f504 Falling back to npm install...")
            cmd = ["npm", "install", "--no-audit", "--no-fund"]
    elif pm == "yarn":
        cmd = ["yarn", "install"]
    else:
        cmd = ["npm", "install", "--no-audit", "--no-fund"]

    try:
        subprocess.check_call(cmd, cwd=project_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"  \u26a0\ufe0f {pm} install failed (in {project_path})")


def install_rust_deps(project_path: str):
    notify_install("cargo dependencies", "rust")
    try:
        subprocess.check_call(
            ["cargo", "build"],
            cwd=project_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        print(f"  \u26a0\ufe0f cargo build failed. Try: cargo build (in {project_path})")


def install_go_deps(project_path: str):
    notify_install("go modules", "go")
    try:
        subprocess.check_call(
            ["go", "mod", "download"],
            cwd=project_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        print(f"  \u26a0\ufe0f go mod download failed. Try: go mod download (in {project_path})")


def install_ruby_deps(project_path: str):
    notify_install("bundler gems", "ruby")
    try:
        subprocess.check_call(
            ["bundle", "install"],
            cwd=project_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        print(f"  \u26a0\ufe0f bundle install failed. Try: bundle install (in {project_path})")


def install_c_cpp_deps(project_path: str):
    root = Path(project_path)
    if (root / "CMakeLists.txt").exists():
        notify_install("cmake dependencies", "c_cpp")
        build = root / "build"
        build.mkdir(exist_ok=True)
        try:
            subprocess.check_call(["cmake", ".."], cwd=str(build),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f cmake configuration failed")


def install_csharp_deps(project_path: str):
    root = Path(project_path)
    csproj = list(root.glob("*.csproj"))
    if csproj:
        notify_install(".NET dependencies", "csharp")
        try:
            subprocess.check_call(["dotnet", "restore"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f dotnet restore failed")


def install_php_deps(project_path: str):
    root = Path(project_path)
    if (root / "composer.json").exists():
        notify_install("composer packages", "php")
        try:
            subprocess.check_call(["composer", "install"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f composer install failed")


def install_kotlin_deps(project_path: str):
    root = Path(project_path)
    if (root / "gradlew").exists():
        notify_install("gradle dependencies", "kotlin")
        try:
            subprocess.check_call(["./gradlew", "build", "-x", "test"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f gradle build failed")


def install_dart_deps(project_path: str):
    root = Path(project_path)
    if (root / "pubspec.yaml").exists():
        notify_install("dart packages", "dart")
        try:
            cmd = ["flutter", "pub", "get"] if shutil.which("flutter") else ["dart", "pub", "get"]
            subprocess.check_call(cmd, cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f pub get failed")


def install_r_lang_deps(project_path: str):
    root = Path(project_path)
    if (root / "renv.lock").exists():
        notify_install("R packages", "r_lang")
        try:
            subprocess.check_call(["Rscript", "-e", "renv::restore()"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f renv restore failed")


def install_julia_deps(project_path: str):
    root = Path(project_path)
    if (root / "Project.toml").exists():
        notify_install("Julia packages", "julia")
        try:
            subprocess.check_call(
                ["julia", "-e", "using Pkg; Pkg.instantiate()"], cwd=project_path,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f Pkg.instantiate() failed")


def install_lua_deps(project_path: str):
    root = Path(project_path)
    rockspecs = list(root.glob("*.rockspec"))
    if rockspecs:
        notify_install("Lua rocks", "lua")
        try:
            subprocess.check_call(["luarocks", "install", str(rockspecs[0])], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f luarocks install failed")


def install_scala_deps(project_path: str):
    root = Path(project_path)
    if (root / "build.sbt").exists():
        notify_install("sbt dependencies", "scala")
        try:
            subprocess.check_call(["sbt", "update"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f sbt update failed")


def install_elixir_deps(project_path: str):
    root = Path(project_path)
    if (root / "mix.exs").exists():
        notify_install("mix dependencies", "elixir")
        try:
            subprocess.check_call(["mix", "deps.get"], cwd=project_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("  \u26a0\ufe0f mix deps.get failed")


INSTALLERS = {
    "python": install_python_deps,
    "node": install_node_deps,
    "rust": install_rust_deps,
    "go": install_go_deps,
    "ruby": install_ruby_deps,
    "deno": lambda p: None,
    "java": lambda p: None,
    "c_cpp": install_c_cpp_deps,
    "csharp": install_csharp_deps,
    "php": install_php_deps,
    "kotlin": install_kotlin_deps,
    "dart": install_dart_deps,
    "r_lang": install_r_lang_deps,
    "julia": install_julia_deps,
    "lua": install_lua_deps,
    "scala": install_scala_deps,
    "elixir": install_elixir_deps,
    "mixed": lambda p: (install_python_deps(p), install_node_deps(p)),
}


def install(plan: dict, project_path: str, extra_modules: list[str] | None = None):
    ptype = plan.get("type", "python")
    installer = INSTALLERS.get(ptype)
    if installer:
        if ptype == "python":
            installer(project_path, extra_modules)
        else:
            installer(project_path)
