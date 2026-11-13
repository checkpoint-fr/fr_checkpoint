"""Agent 1 – Veille : lit les flux RSS de config.yaml et garde les articles récents jamais vus.

Sortie : data/veille/<AAAA-MM-JJ>.json (fusionné à chaque passage de la journée).
On ne stocke que titre, lien, chapô tronqué et date : jamais l'article ni les images.
"""
import calendar
import datetime
import hashlib
import html
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

from common.config import DATA, load_config
from common.io import ecrire_json, lire_json, maintenant

DOSSIER = DATA / "veille"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
PARAMS_PISTAGE = re.compile(r"^(utm_|fbclid|gclid|xtor|at_)", re.I)


def lien_canonique(url):
    """Retire les paramètres de pistage et la barre finale pour repérer les doublons."""
    p = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not PARAMS_PISTAGE.match(k)])
    hote = re.sub(r"^www\.", "", p.netloc.lower())
    return urlunsplit(("https", hote, p.path.rstrip("/"), query, ""))


def identifiant(url):
    return hashlib.sha1(lien_canonique(url).encode()).hexdigest()[:16]


def texte_brut(fragment, maxi):
    t = html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*submitted by /u/\S+.*$", "", t)      # signature ajoutée par Reddit
    return t if len(t) <= maxi else t[:maxi].rsplit(" ", 1)[0] + "…"


def date_publication(entree):
    st = entree.get("published_parsed") or entree.get("updated_parsed")
    if not st:
        return None
    return datetime.datetime.fromtimestamp(calendar.timegm(st), datetime.timezone.utc)


def lire_flux(session, source):
    r = session.get(source["url"], headers=UA, timeout=20)
    if r.status_code == 429:              # Reddit limite les rafales : une seule nouvelle tentative
        time.sleep(10)
        r = session.get(source["url"], headers=UA, timeout=20)
    r.raise_for_status()
    flux = feedparser.parse(r.content)
    if flux.bozo and not flux.entries:
        raise ValueError(f"flux illisible ({flux.bozo_exception})")
    return flux.entries


def deja_vus():
    """Identifiants déjà collectés sur la période de conservation."""
    vus = set()
    for f in DOSSIER.glob("*.json"):
        vus.update(a["id"] for a in lire_json(f, []))
    return vus


def purger(conservation_jours):
    limite = (maintenant() - datetime.timedelta(days=conservation_jours)).date().isoformat()
    for f in DOSSIER.glob("*.json"):
        if f.stem < limite:
            f.unlink()


def collecter():
    cfg = load_config()["veille"]
    debut = maintenant()
    seuil = debut - datetime.timedelta(hours=cfg["fenetre_heures"])
    DOSSIER.mkdir(parents=True, exist_ok=True)
    purger(cfg["conservation_jours"])
    vus = deja_vus()

    nouveaux, erreurs = [], []
    session = requests.Session()
    for source in cfg["sources"]:
        try:
            entrees = lire_flux(session, source)
        except Exception as ex:
            erreurs.append(source["nom"])
            print(f"[veille] ✗ {source['nom']} : {ex}")
            continue
        gardes = 0
        for e in entrees:
            lien, titre = e.get("link", ""), texte_brut(e.get("title", ""), 300)
            if not lien or not titre:
                continue
            publie = date_publication(e)
            if publie and publie < seuil:
                continue
            ident = identifiant(lien)
            if ident in vus:
                continue
            vus.add(ident)
            gardes += 1
            nouveaux.append({
                "id": ident,
                "source": source["nom"],
                "type": source["type"],
                "langue": source["langue"],
                "titre": titre,
                "lien": lien,
                "resume": texte_brut(e.get("summary", ""), cfg["resume_max"]),
                "publie_le": (publie or debut).isoformat(),
                "collecte_le": debut.isoformat(),
            })
        print(f"[veille] ✓ {source['nom']} : {gardes} nouveaux / {len(entrees)} lus")

    fichier = DOSSIER / f"{debut.date().isoformat()}.json"
    du_jour = lire_json(fichier, []) + nouveaux
    du_jour.sort(key=lambda a: a["publie_le"], reverse=True)
    ecrire_json(du_jour, fichier)
    print(f"[veille] {len(nouveaux)} nouveaux articles ({len(du_jour)} aujourd'hui) -> {fichier.relative_to(DATA.parent)}"
          + (f" · sources en échec : {', '.join(erreurs)}" if erreurs else ""))
    return nouveaux


if __name__ == "__main__":
    collecter()
