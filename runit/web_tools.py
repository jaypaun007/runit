import json
import re
import urllib.request
import urllib.parse
import urllib.error

USER_AGENT = "Runit/1.0 (AI Execution Agent)"


def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using a public search API (DuckDuckGo lite)."""
    results = []
    try:
        url = f"https://lite.duckduckgo.com/lite?q={urllib.parse.quote(query)}"
        html = _fetch(url)
        links = re.findall(r'<a[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html)
        seen = set()
        for href, text in links:
            if href not in seen and len(results) < max_results:
                seen.add(href)
                results.append({"title": text.strip(), "url": href})
    except Exception:
        pass
    return results


def fetch_github_readme(repo_url: str) -> str:
    """Fetch README from a GitHub repo without cloning."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", repo_url)
    if not m:
        return ""
    owner, repo = m.group(1), m.group(2).rstrip("/").replace(".git", "")

    branches = ["main", "master"]
    for branch in branches:
        for name in ["README.md", "README.rst", "README.txt", "README"]:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
            try:
                text = _fetch(url, timeout=8)
                if text:
                    return text[:5000]
            except Exception:
                continue
    return ""


def fetch_github_file_list(repo_url: str) -> list[dict]:
    """Fetch file tree from GitHub API."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", repo_url)
    if not m:
        return []
    owner, repo = m.group(1), m.group(2).rstrip("/").replace(".git", "")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    try:
        data = json.loads(_fetch(url))
        files = []
        for item in data[:50]:
            files.append({"name": item["name"], "type": item["type"], "path": item["path"]})
        return files
    except Exception:
        return []


def search_error_online(error_msg: str) -> list[dict]:
    """Search the web for an error message to find solutions."""
    query = urllib.parse.quote(error_msg[:200])
    return web_search(f"fix error: {query}", max_results=3)
