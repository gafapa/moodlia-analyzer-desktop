"""Persist local AI settings in ~/.moodle_analyzer/ai_settings.json."""
import json
import os
from typing import Dict


SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".moodle_analyzer")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "ai_settings.json")

DEFAULT_SETTINGS = {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "",
}


def _ensure_dir():
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    try:
        os.chmod(SETTINGS_DIR, 0o700)
    except OSError:
        pass


def load_ai_settings() -> Dict:
    _ensure_dir()
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        settings = dict(DEFAULT_SETTINGS)
        settings.update(data if isinstance(data, dict) else {})
        return settings
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_ai_settings(settings: Dict):
    _ensure_dir()
    payload = dict(DEFAULT_SETTINGS)
    payload.update(settings or {})
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass
