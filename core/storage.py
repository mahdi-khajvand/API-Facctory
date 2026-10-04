import json
from pathlib import Path
from typing import Any

from . import config


def _read_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_status() -> dict:
    return _read_json(config.STATUS_FILE, {})


def save_status(data: dict):
    _write_json(config.STATUS_FILE, data)


def load_db_configs() -> dict:
    return _read_json(config.DB_CONFIGS_FILE, {})


def save_db_configs(data: dict):
    _write_json(config.DB_CONFIGS_FILE, data)


def load_keys() -> dict:
    return _read_json(config.KEYS_FILE, {})


def save_keys(data: dict):
    _write_json(config.KEYS_FILE, data)


def load_dashboards() -> dict:
    return _read_json(config.BI_DASHBOARDS_FILE, {})


def save_dashboards(data: dict):
    _write_json(config.BI_DASHBOARDS_FILE, data)
