"""Chargement de la configuration (config.yaml) et des secrets (.env)."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")

_CONFIG = None


def load_config():
    global _CONFIG
    if _CONFIG is None:
        with open(ROOT / "config.yaml", encoding="utf-8") as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def env(name, default=""):
    return os.getenv(name, default) or default


def format_du_jour():
    """« reel » ou « carrousel » : `format` de config.yaml, sauf les jours listés dans `carrousel_les`."""
    import datetime
    from zoneinfo import ZoneInfo
    cfg = load_config()
    jour = datetime.datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    return "carrousel" if jour in (cfg.get("carrousel_les") or []) else cfg.get("format", "carrousel")
