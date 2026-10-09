from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_DIMENSION_KEYS = ("nether_locked", "end_locked")


def normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    return default


def default_state_from_config(config: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "nether_locked": normalize_bool(config.get("nether_locked", False), False),
        "end_locked": normalize_bool(config.get("end_locked", False), False),
    }


def merge_state(config: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, bool]:
    merged = default_state_from_config(config)
    for key in DEFAULT_DIMENSION_KEYS:
        if key in overrides:
            merged[key] = normalize_bool(overrides[key], merged[key])
    return merged


def load_saved_state(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, bool] = {}
    for key in DEFAULT_DIMENSION_KEYS:
        value = raw.get(key)
        if isinstance(value, bool):
            cleaned[key] = value
    return cleaned


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump({key: bool(state.get(key, False)) for key in DEFAULT_DIMENSION_KEYS}, handle, separators=(",", ":"))
    temp_path.replace(path)


def clear_state(path: Path) -> None:
    if path.exists():
        path.unlink()
