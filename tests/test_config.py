import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from runit.config import load_config, save_config, save_key, get_key, list_keys, delete_key


def test_load_config_defaults():
    with patch("runit.config.CONFIG_FILE", Path(tempfile.mktemp())):
        cfg = load_config()
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4"
        assert cfg["max_retries"] == 3
        assert cfg["notifications"] is True


def test_save_and_load_config():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_file = Path(tmp) / "config.json"
        with patch("runit.config.CONFIG_FILE", cfg_file):
            save_config({"model": "gpt-4o", "max_retries": 5})
            cfg = load_config()
            assert cfg["model"] == "gpt-4o"
            assert cfg["max_retries"] == 5
            assert cfg["provider"] == "openai"


def test_save_and_get_key():
    with tempfile.TemporaryDirectory() as tmp:
        keys_file = Path(tmp) / "keys.json"
        with patch("runit.config.KEYS_FILE", keys_file):
            save_key("TEST_KEY", "test-value-123")
            assert get_key("TEST_KEY") == "test-value-123"


def test_list_keys():
    with tempfile.TemporaryDirectory() as tmp:
        keys_file = Path(tmp) / "keys.json"
        with patch("runit.config.KEYS_FILE", keys_file):
            save_key("KEY_A", "val-a")
            save_key("KEY_B", "val-b")
            keys = list_keys()
            assert keys == {"KEY_A": "val-a", "KEY_B": "val-b"}


def test_delete_key():
    with tempfile.TemporaryDirectory() as tmp:
        keys_file = Path(tmp) / "keys.json"
        with patch("runit.config.KEYS_FILE", keys_file):
            save_key("TO_DELETE", "value")
            assert delete_key("TO_DELETE") is True
            assert get_key("TO_DELETE") is None
            assert delete_key("NONEXISTENT") is False
