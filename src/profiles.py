"""Persist connection profiles in ~/.moodle_analyzer/profiles.json."""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


PROFILES_DIR = os.path.join(os.path.expanduser("~"), ".moodle_analyzer")
PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")


def _ensure_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)
    try:
        os.chmod(PROFILES_DIR, 0o700)
    except OSError:
        pass


def load_profiles() -> List[Dict]:
    """Load saved profiles."""
    _ensure_dir()
    if not os.path.exists(PROFILES_FILE):
        return []
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("profiles", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_profiles(profiles: List[Dict]):
    """Save the complete profile list."""
    _ensure_dir()
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump({"profiles": profiles}, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(PROFILES_FILE, 0o600)
    except OSError:
        pass


def upsert_profile(name: str, url: str, token: str, username: str = "") -> List[Dict]:
    """Create or update a named profile and return the updated list."""
    profiles = load_profiles()
    existing = next((p for p in profiles if p["name"] == name), None)
    if existing:
        existing["url"] = url
        existing["token"] = token
        if username:
            existing["username"] = username
        else:
            existing.pop("username", None)
        existing["last_used"] = datetime.now().isoformat()
    else:
        profile = {
            "name": name,
            "url": url,
            "token": token,
            "last_used": datetime.now().isoformat(),
        }
        if username:
            profile["username"] = username
        profiles.append(profile)
    save_profiles(profiles)
    return profiles


def delete_profile(name: str) -> List[Dict]:
    """Delete a named profile and return the updated list."""
    profiles = [p for p in load_profiles() if p["name"] != name]
    save_profiles(profiles)
    return profiles


def touch_last_used(name: str):
    """Update a profile's last-used timestamp."""
    profiles = load_profiles()
    for p in profiles:
        if p["name"] == name:
            p["last_used"] = datetime.now().isoformat()
            break
    save_profiles(profiles)


def get_profile(name: str) -> Optional[Dict]:
    return next((p for p in load_profiles() if p["name"] == name), None)
