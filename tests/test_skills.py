from pathlib import Path
import tempfile

from runit.skills import (
    SKILLS_REGISTRY, match_skills, get_skill,
    detect_package_manager, has_pnpm, has_pnpm_cli,
    get_build_instructions,
)


def test_skills_registry_has_all_types():
    expected = {"python", "node", "rust", "go", "ruby", "deno", "java"}
    assert expected.issubset(SKILLS_REGISTRY.keys())


def test_skills_registry_has_new_types():
    new = {"c_cpp", "csharp", "php", "kotlin", "dart", "r_lang", "julia", "lua", "scala", "elixir"}
    assert new.issubset(SKILLS_REGISTRY.keys())
    assert len(SKILLS_REGISTRY) >= 17


def test_get_skill_returns_none_for_unknown():
    assert get_skill("unknown") is None


def test_get_skill_returns_known_skill():
    skill = get_skill("python")
    assert skill is not None
    assert skill["name"] == "Python Expert"
    assert "requirements.txt" in skill["detect_files"]


def test_match_skills_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        matched = match_skills(tmp)
        assert matched == []


def test_match_skills_python():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "requirements.txt").write_text("flask\n")
        matched = match_skills(tmp)
        assert len(matched) == 1
        assert matched[0]["id"] == "python"


def test_match_skills_node():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text('{"name": "test"}')
        (Path(tmp) / "pnpm-lock.yaml").write_text("")
        matched = match_skills(tmp)
        ids = {m["id"] for m in matched}
        assert "node" in ids


def test_detect_package_manager():
    with tempfile.TemporaryDirectory() as tmp:
        assert detect_package_manager(tmp) == "npm"
        (Path(tmp) / "yarn.lock").write_text("")
        assert detect_package_manager(tmp) == "yarn"
        (Path(tmp) / "pnpm-lock.yaml").write_text("")
        assert detect_package_manager(tmp) == "pnpm"


def test_has_pnpm():
    with tempfile.TemporaryDirectory() as tmp:
        assert has_pnpm(tmp) is False
        (Path(tmp) / "pnpm-lock.yaml").write_text("")
        assert has_pnpm(tmp) is True


def test_has_pnpm_cli():
    result = has_pnpm_cli()
    assert isinstance(result, bool)


def test_match_skills_c_cpp():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.0)")
        matched = match_skills(tmp)
        ids = {m["id"] for m in matched}
        assert "c_cpp" in ids


def test_match_skills_php():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "composer.json").write_text('{"name": "test/app"}')
        matched = match_skills(tmp)
        ids = {m["id"] for m in matched}
        assert "php" in ids


def test_match_skills_dart():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "pubspec.yaml").write_text("name: test_app")
        matched = match_skills(tmp)
        ids = {m["id"] for m in matched}
        assert "dart" in ids


def test_get_build_instructions_python():
    steps = get_build_instructions("python")
    assert len(steps) >= 1


def test_get_build_instructions_unknown():
    steps = get_build_instructions("nonexistent")
    assert steps == []


def test_get_build_instructions_c_cpp():
    steps = get_build_instructions("c_cpp")
    assert len(steps) >= 1
    assert any("cmake" in s or "make" in s for s in steps)
