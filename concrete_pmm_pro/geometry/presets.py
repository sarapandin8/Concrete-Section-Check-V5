"""Load metadata-driven section presets from JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
DEFAULT_PRESET_PATH = REPO_ROOT / "data" / "section_presets.json"


def load_section_presets(path: Path | str = DEFAULT_PRESET_PATH) -> list[dict[str, Any]]:
    preset_path = Path(path)
    with preset_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    presets = raw.get("presets", raw)
    if not isinstance(presets, list):
        raise ValueError("section_presets.json must contain a 'presets' list")
    return presets


def load_section_categories(path: Path | str = DEFAULT_PRESET_PATH) -> list[str]:
    preset_path = Path(path)
    with preset_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    configured = raw.get("categories", [])
    presets = raw.get("presets", raw)
    preset_categories = [preset["category"] for preset in presets if "category" in preset]
    categories = list(dict.fromkeys([*configured, *preset_categories]))
    return categories


def preset_by_key(key: str, path: Path | str = DEFAULT_PRESET_PATH) -> dict[str, Any]:
    for preset in load_section_presets(path):
        if preset["key"] == key:
            return preset
    raise KeyError(f"Preset not found: {key}")
