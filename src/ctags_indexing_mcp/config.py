from __future__ import annotations

import json
import time
from pathlib import Path

CONFIG_FILENAME = "config.json"


def config_path(output_dir: Path) -> Path:
    return output_dir / CONFIG_FILENAME


def save_config(output_dir: Path, languages: list[str], excludes: list[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_path(output_dir)
    existing = load_config(output_dir) or {}
    payload = {
        "languages": languages,
        "excludes": excludes,
        "created_at": existing.get("created_at", time.time()),
        "updated_at": time.time(),
    }
    cfg_path.write_text(json.dumps(payload, indent=2))
    return cfg_path


def load_config(output_dir: Path) -> dict | None:
    cfg_path = config_path(output_dir)
    if not cfg_path.is_file():
        return None
    try:
        return json.loads(cfg_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
