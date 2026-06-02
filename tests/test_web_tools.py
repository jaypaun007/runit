from runit.web_tools import web_search, fetch_github_readme, search_error_online


def test_web_search_returns_list():
    results = web_search("python hello world")
    assert isinstance(results, list)


def test_search_error_online_returns_list():
    results = search_error_online("ModuleNotFoundError: No module named flask")
    assert isinstance(results, list)


def test_fetch_github_readme_invalid_url():
    result = fetch_github_readme("https://example.com/repo")
    assert result == ""
