"""Lecture/écriture JSON et dates. Toutes les dates sont stockées en UTC (ISO 8601)."""
import datetime
import json
from pathlib import Path


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def ecrire_json(obj, chemin):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return chemin


def lire_json(chemin, defaut=None):
    chemin = Path(chemin)
    if not chemin.exists():
        return defaut
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)
