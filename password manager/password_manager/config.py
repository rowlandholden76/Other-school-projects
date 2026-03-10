import json
import os
from typing import Any


DEFAULT_CONFIG_PATH = "config.json"


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write(data: dict, path: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def get_config_value(key: str, default: Any = None, path: str = DEFAULT_CONFIG_PATH) -> Any:
    cfg = _load(path)
    return cfg.get(key, default)


def set_config_value(key: str, value: Any, path: str = DEFAULT_CONFIG_PATH) -> None:
    cfg = _load(path)
    cfg[key] = value
    _write(cfg, path)
