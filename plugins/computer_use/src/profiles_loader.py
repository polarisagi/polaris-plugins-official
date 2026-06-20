from typing import Optional
import json
import glob
import os
import utils

_PROFILES_DIR = os.path.join(os.path.dirname(__file__), "profiles")


def _load_profiles() -> dict:
    profiles: dict = {}
    for path in sorted(glob.glob(os.path.join(_PROFILES_DIR, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            continue
        keys = set()
        for field in ("app_name", "open_name"):
            v = p.get(field, "")
            if v:
                keys.add(v.lower())
        for alias in p.get("aliases", []):
            if alias:
                keys.add(alias.lower())
        for k in keys:
            profiles[k] = p
    return profiles


APP_PROFILES: dict = _load_profiles()

SYSTEM_LOCALE: str = utils.detect_locale()


def resolve(value, loc: Optional[str] = None):
    """Resolve a profile field that may be a locale map {"zh": …, "en": …}."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        locale_key = loc or SYSTEM_LOCALE
        return (
            value.get(locale_key) or value.get("en") or next(iter(value.values()), None)
        )
    return str(value)
