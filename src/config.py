"""Carga y acceso a automation_config.yaml."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "automation_config.yaml"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "mode": "recomendacion",
    "schedule": {"cron": "0 * * * *", "managed_by": "usuario", "ia_can_pause": True,
                 # Ciclo en-app: corre solo mientras el dashboard está abierto (sin tarea de SO)
                 "app_auto": False, "app_every_min": 60},
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "risk": {
        "max_per_trade_pct": 1.0,
        "max_daily_loss_pct": 3.0,
        "max_open_positions": 3,
        "require_stop_loss": True,
    },
    "forecast": {"horizon": "4h", "min_confidence": 0.60},
    "notifications": {"channel": "chat", "notify_on": ["recomendacion", "ejecucion", "error", "kill_switch"]},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    data = {}
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULTS, data)


def save_config(cfg: dict, path: str | os.PathLike | None = None) -> None:
    p = Path(path) if path else CONFIG_PATH
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
