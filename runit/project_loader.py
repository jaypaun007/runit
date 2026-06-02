import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from runit.config import load_config


def is_github_url(path: str) -> bool:
    parsed = urlparse(path)
    return "github.com" in parsed.netloc


def clone_repo(url: str, token: str | None = None, dest_dir: str | None = None) -> str:
    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    dest = os.path.abspath(os.path.join(dest_dir or os.getcwd(), repo_name))

    if os.path.isdir(dest) and os.path.isdir(os.path.join(dest, ".git")):
        print(f"  \U0001f504 Updating existing repo: {dest}")
        try:
            subprocess.check_call(
                ["git", "-C", dest, "pull", "--ff-only"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return dest
        except subprocess.CalledProcessError:
            print(f"  \u26a0\ufe0f  Could not update, using existing: {dest}")
            return dest

    if token:
        parsed = urlparse(url)
        authed_url = f"https://{token}@{parsed.netloc}{parsed.path}"
    else:
        authed_url = url

    print(f"  \U0001f500 Cloning {url} ...")
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", authed_url, dest],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        if not token:
            raise PermissionError(
                "Repository requires authentication. Provide a GitHub token with --token or set GITHUB_TOKEN env var."
            ) from e
        raise
    return dest


def resolve_local(path: str) -> str:
    resolved = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(resolved):
        raise NotADirectoryError(f"Not a directory: {resolved}")
    return resolved


def _get_github_token(input_token: str | None) -> str | None:
    token = input_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    cfg = load_config()
    return cfg.get("github_token") or None


def load_project(input_path: str, token: str | None = None) -> str:
    if is_github_url(input_path):
        gh_token = _get_github_token(token)
        return clone_repo(input_path, gh_token)
    return resolve_local(input_path)


def get_file_tree(project_path: str, max_depth: int = 2) -> dict:
    root = Path(project_path)
    tree = {"path": str(root.resolve()), "name": root.name, "children": []}

    try:
        entries = sorted(root.iterdir())
    except PermissionError:
        return tree

    for entry in entries:
        if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules", ".git", "venv", ".venv"):
            continue
        node = {"name": entry.name}
        if entry.is_dir():
            node["type"] = "dir"
            if max_depth > 0:
                try:
                    sub = sorted(entry.iterdir())[:20]
                    node["children"] = [
                        {"name": e.name, "type": "dir" if e.is_dir() else "file"}
                        for e in sub
                        if not e.name.startswith(".")
                    ]
                except PermissionError:
                    node["children"] = []
        else:
            node["type"] = "file"
        tree["children"].append(node)
    return tree


def get_project_name(project_path: str) -> str:
    return Path(project_path).name


def cleanup(path: str):
    pass
