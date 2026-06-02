import subprocess
import sys
import os
import re
import shutil
from pathlib import Path


def _run(cmd: list[str], cwd: str, env: dict | None = None,
         timeout: int = 180, capture: bool = True) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    kwargs = {"cwd": cwd, "env": merged_env}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    else:
        kwargs["stdout"] = None
        kwargs["stderr"] = None
    try:
        return subprocess.run(cmd, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=cmd, returncode=124,
            stdout=getattr(e, 'stdout', '') or "",
            stderr=(getattr(e, 'stderr', '') or "") + "\n[ERROR] Command timed out"
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=cmd, returncode=127,
            stdout="", stderr=f"[ERROR] Command not found: {cmd[0]}"
        )


def _find_entry(project_path: str, entry: str) -> str | None:
    candidates = [entry, f"src/{entry}", f"bin/{entry}", f"app/{entry}"]
    for c in candidates:
        if (Path(project_path) / c).exists():
            return c
    return None


def run_python(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry)
    if not found:
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
        )
    return _run([sys.executable, str(Path(project_path) / found)], project_path, env)


def run_node(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry)
    if not found:
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
        )
    return _run(["node", str(Path(project_path) / found)], project_path, env)


def run_rust(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return _run(["cargo", "run"], project_path, env)


def run_go(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return _run(["go", "run", "."], project_path, env)


def run_ruby(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry)
    if not found:
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
        )
    return _run(["ruby", str(Path(project_path) / found)], project_path, env)


def run_deno(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry)
    if not found:
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
        )
    return _run(["deno", "run", str(Path(project_path) / found)], project_path, env)


def _detect_docker_ports(project_path: str) -> list[str]:
    """Auto-detect exposed ports from Dockerfile or docker-compose.yml."""
    ports = []
    dockerfile = Path(project_path) / "Dockerfile"
    compose = Path(project_path) / "docker-compose.yml"

    if dockerfile.exists():
        try:
            for line in dockerfile.read_text(errors="replace").splitlines():
                m = re.search(r"EXPOSE\s+(\d+)", line)
                if m:
                    ports.append(f"{m.group(1)}:{m.group(1)}")
        except Exception:
            pass

    if compose.exists():
        try:
            import yaml
            with open(compose) as f:
                data = yaml.safe_load(f)
            for service in (data.get("services", {}) or {}).values():
                svc_ports = service.get("ports", []) or []
                for p in svc_ports:
                    if isinstance(p, str) and ":" in p:
                        ports.append(p)
                    elif isinstance(p, int):
                        ports.append(f"{p}:{p}")
        except Exception:
            pass

    return ports


def run_docker(image: str, env_vars: dict | None = None,
               ports: list[str] | None = None, extra_args: list[str] | None = None,
               project_path: str | None = None) -> subprocess.CompletedProcess:
    """Run a project via Docker in foreground (with timeout)."""
    if not shutil.which("docker"):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="[ERROR] docker not found. Install Docker first."
        )
    if not ports and project_path:
        ports = _detect_docker_ports(project_path)

    cmd = ["docker", "run", "--rm"]
    if ports:
        for p in ports:
            cmd.extend(["-p", p])
    if env_vars:
        for k, v in env_vars.items():
            if v:
                cmd.extend(["-e", f"{k}={v}"])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(image)
    result = _run(cmd, cwd="/", capture=True, timeout=300)
    return result


def run_dev_script(project_path: str, script: str = "dev",
                   pm: str = "npm", env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a dev script (e.g. pnpm dev, npm start)."""
    runners = {"pnpm": "pnpm", "yarn": "yarn", "npm": "npm"}
    runner = runners.get(pm, "npm")
    cmd = [runner, "run", script] if script != runner else [runner]
    return _run(cmd, project_path, env=env, timeout=300, capture=True)


def run_c_cpp(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "Makefile").exists():
        return _run(["make"], project_path, env, timeout=300)
    if (root / "CMakeLists.txt").exists():
        build = root / "build"
        build.mkdir(exist_ok=True)
        r1 = _run(["cmake", ".."], str(build), env, timeout=120)
        if r1.returncode != 0:
            return r1
        return _run(["make"], str(build), env, timeout=300)
    found = _find_entry(project_path, entry)
    if found:
        ext = Path(found).suffix
        if ext in (".c",):
            compiler = shutil.which("gcc") or "cc"
            return _run([compiler, "-o", "/tmp/runit_out", str(Path(project_path) / found), "-lm"],
                        project_path, env, timeout=120)
        if ext in (".cpp", ".cc", ".cxx"):
            compiler = shutil.which("g++") or "c++"
            return _run([compiler, "-o", "/tmp/runit_out", str(Path(project_path) / found)],
                        project_path, env, timeout=120)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
    )


def run_csharp(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    csproj_files = list(root.glob("*.csproj"))
    if csproj_files:
        return _run(["dotnet", "run", "--project", str(csproj_files[0])], project_path, env, timeout=300)
    found = _find_entry(project_path, entry)
    if found:
        return _run(["dotnet", "run", str(Path(project_path) / found)], project_path, env, timeout=300)
    return _run(["dotnet", "run"], project_path, env, timeout=300)


def run_php(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "artisan").exists():
        return _run(["php", "artisan", "serve"], project_path, env, timeout=300)
    found = _find_entry(project_path, entry) or "index.php"
    return _run(["php", "-S", "localhost:8000", "-t", str(root), str(root / found) if (root / found).exists() else found],
                project_path, env, timeout=300)


def run_kotlin(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "gradlew").exists():
        return _run(["./gradlew", "run"], project_path, env, timeout=300)
    if (root / "build.gradle.kts").exists() and shutil.which("gradle"):
        return _run(["gradle", "run"], project_path, env, timeout=300)
    found = _find_entry(project_path, entry) or "Main.kt"
    if shutil.which("kotlinc"):
        jar = "/tmp/runit_kt.jar"
        r = _run(["kotlinc", str(Path(project_path) / found), "-include-runtime", "-d", jar],
                 project_path, env, timeout=120)
        if r.returncode != 0:
            return r
        return _run(["java", "-jar", jar], project_path, env, timeout=120)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="kotlinc not found. Install Kotlin or use gradlew."
    )


def run_dart(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "pubspec.yaml").exists():
        if shutil.which("flutter"):
            return _run(["flutter", "run"], project_path, env, timeout=300)
        if shutil.which("dart"):
            found = _find_entry(project_path, entry) or "lib/main.dart"
            if found:
                return _run(["dart", "run", str(Path(project_path) / found)], project_path, env, timeout=300)
            return _run(["dart", "run"], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Dart/Flutter SDK not found."
    )


def run_r_lang(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry) or "main.R"
    if Path(project_path / found).exists():
        return _run(["Rscript", str(Path(project_path) / found)], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
    )


def run_julia(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry) or "main.jl"
    if Path(project_path / found).exists():
        return _run(["julia", str(Path(project_path) / found)], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
    )


def run_lua(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    found = _find_entry(project_path, entry) or "main.lua"
    if Path(project_path / found).exists():
        runner = shutil.which("luajit") or shutil.which("lua") or "lua"
        return _run([runner, str(Path(project_path) / found)], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=f"Entry not found: {entry}"
    )


def run_scala(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "build.sbt").exists():
        return _run(["sbt", "run"], project_path, env, timeout=300)
    found = _find_entry(project_path, entry) or "Main.scala"
    if (root / found).exists() and shutil.which("scala"):
        return _run(["scala", str(Path(project_path) / found)], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="sbt or scala not found."
    )


def run_elixir(entry: str, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    root = Path(project_path)
    if (root / "mix.exs").exists():
        return _run(["mix", "run"], project_path, env, timeout=300)
    found = _find_entry(project_path, entry) or "lib/main.ex"
    if (root / found).exists() and shutil.which("elixir"):
        return _run(["elixir", str(Path(project_path) / found)], project_path, env, timeout=300)
    return subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Elixir not found."
    )


def ensure_runtime(project_type: str) -> bool:
    from runit.skills import SKILLS_REGISTRY
    skill = SKILLS_REGISTRY.get(project_type)
    if not skill:
        return True
    checks = skill.get("runtime_check", [])
    for check in checks:
        if shutil.which(check):
            return True
    install_cmds = skill.get("runtime_install", [])
    if not install_cmds:
        return False
    for cmd in install_cmds:
        try:
            subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        except Exception:
            pass
    for check in checks:
        if shutil.which(check):
            return True
    return False


RUNNERS = {
    "python": run_python,
    "node": run_node,
    "rust": run_rust,
    "go": run_go,
    "ruby": run_ruby,
    "deno": run_deno,
    "c_cpp": run_c_cpp,
    "csharp": run_csharp,
    "php": run_php,
    "kotlin": run_kotlin,
    "dart": run_dart,
    "r_lang": run_r_lang,
    "julia": run_julia,
    "lua": run_lua,
    "scala": run_scala,
    "elixir": run_elixir,
}


def execute(plan: dict, project_path: str, env: dict | None = None) -> subprocess.CompletedProcess:
    mode = plan.get("_run_mode", "direct")
    if mode == "docker":
        return run_docker(
            image=plan.get("_docker_image", ""),
            env_vars=env or plan.get("_docker_env", {}),
            ports=plan.get("_docker_ports", []),
            project_path=project_path,
        )
    if mode == "dev_script":
        return run_dev_script(
            project_path,
            script=plan.get("_dev_script", "dev"),
            pm=plan.get("_package_manager", "npm"),
            env=env,
        )

    ptype = plan.get("type", "python")
    entry = plan.get("entry", "")
    fallbacks = plan.get("fallbacks", [])

    if not ensure_runtime(ptype):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr=f"[ERROR] Runtime for {ptype} not available and could not be installed."
        )

    runner = RUNNERS.get(ptype)
    if not runner:
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr=f"Unsupported project type: {ptype}"
        )

    all_entries = [entry] + fallbacks if entry else fallbacks
    last_result = None
    for i, e in enumerate(all_entries):
        if not e:
            continue
        result = runner(e, project_path, env)
        if result.returncode == 0:
            return result
        last_result = result

    return last_result
