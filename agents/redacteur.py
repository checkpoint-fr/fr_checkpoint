"""Agent 3 – Rédacteur : transforme chaque sujet retenu en brouillon de carrousel Instagram.

Entrée : data/tri/*.json (sujets pas encore rédigés).
Sortie : data/redaction/<AAAA-MM-JJ>.json, brouillons au statut « a_valider » (ou « ecarte »).
L'IA ne reçoit que les faits des articles ; les sources et la mention IA sont ajoutées par le code.
"""
import datetime
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

from agents.veille import UA
from common.config import DATA, load_config
from common.io import ecrire_json, lire_json, maintenant
from common.llm import disponible, llm_json

DOSSIER = DATA / "redaction"
ENTREES = DOSSIER / "entrees"          # ce que l'IA a reçu, pour vérifier un fait avant de valider
PROMPT = Path(__file__).parent / "prompts" / "redacteur.md"
BLABLA = re.compile(r"newsletter|sign (you )?up|subscribe|your email|cookies|inscri(vez|ption)|abonne", re.I)


class _Paragraphes(HTMLParser):
    """Récupère le texte des balises <p> d'une page (hors menus, scripts, pieds de page)."""
    IGNORES = {"script", "style", "nav", "footer", "aside", "form"}

    def __init__(self):
        super().__init__()
        self.paragraphes, self._courant, self._dans_p, self._ignore = [], [], False, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self._ignore += 1
        elif tag == "p":
            self._dans_p, self._courant = True, []

    def handle_endtag(self, tag):
        if tag in self.IGNORES:
            self._ignore = max(self._ignore - 1, 0)
        elif tag == "p" and self._dans_p:
            texte = " ".join("".join(self._courant).split())
            if len(texte) > 60 and not BLABLA.search(texte):
                self.paragraphes.append(texte)
            self._dans_p = False

    def handle_data(self, data):
        if self._dans_p and not self._ignore:
            self._courant.append(data)


def extrait(lien, maxi):
    """Début du texte de l'article, pour donner des faits à l'IA. Vide si la page résiste."""
    try:
        r = requests.get(lien, headers=UA, timeout=20)
        r.raise_for_status()
        lecteur = _Paragraphes()
        lecteur.feed(r.text)
        return " ".join(lecteur.paragraphes)[:maxi]
    except Exception:
        return ""


def identifiant(sujet):
    return hashlib.sha1((sujet["propose_le"] + sujet["titre"]).encode()).hexdigest()[:12]


def a_lire(articles, nombre):
    """Un article par média, presse et officiel d'abord (Reddit ne renvoie qu'à une discussion)."""
    choisis, vus = [], set()
    for a in sorted(articles, key=lambda a: (a["type"] == "communaute", a["langue"] != "fr")):
        if a["source"] not in vus and a["type"] != "communaute":
            choisis.append(a)
            vus.add(a["source"])
    return choisis[:nombre]


def sources_uniques(articles):
    vus, sources = set(), []
    for a in articles:
        if a["source"] not in vus:
            vus.add(a["source"])
            sources.append({"nom": a["source"], "lien": a["lien"]})
    return sources


def nettoyer_points(points):
    """Garde les points complets ; tolère une clé mal orthographiée par l'IA (« titq »…)."""
    propres = []
    for p in points if isinstance(points, list) else []:
        if not isinstance(p, dict) or not p.get("texte"):
            continue
        titre = p.get("titre") or next((v for k, v in p.items() if k != "texte" and isinstance(v, str)), "")
        propres.append({"titre": titre.strip(), "texte": p["texte"].strip()})
    return propres[:4]


def depassements(b, limites):
    """Champs plus longs que la place prévue sur les images : signalés, jamais coupés."""
    alertes = [f"{champ} : {len(b[champ])}/{maxi} car." for champ, maxi in limites.items()
               if champ in b and len(b[champ]) > maxi]
    for i, pt in enumerate(b["points"], 1):
        for champ in ("titre", "texte"):
            maxi = limites[f"point_{champ}"]
            if len(pt[champ]) > maxi:
                alertes.append(f"point {i} {champ} : {len(pt[champ])}/{maxi} car.")
    return alertes


def uniformiser(valeur, regles):
    """Même nom partout (texte, voix, légende) : « Grand Theft Auto VI » → « GTA 6 », etc."""
    if isinstance(valeur, str):
        for motif, remplacement in regles:
            valeur = re.sub(motif, remplacement, valeur, flags=re.IGNORECASE)
        return valeur
    if isinstance(valeur, list):
        return [uniformiser(v, regles) for v in valeur]
    if isinstance(valeur, dict):
        return {k: uniformiser(v, regles) for k, v in valeur.items()}
    return valeur


def construire_legende(texte, sources, hashtags, cfg):
    noms = ", ".join(s["nom"] for s in sources)
    tags = list(dict.fromkeys(cfg["hashtags_fixes"] + ["#" + h.lstrip("#").replace(" ", "") for h in hashtags]))
    return f"{texte.strip()}\n\nSources : {noms}\n\n{' '.join(tags[:15])}"


def rediger():
    cfg = load_config()["redaction"]
    temperature = load_config()["llm"]["temperature_redaction"]
    if not disponible():
        print("[rédacteur] aucune clé IA dans .env (GEMINI_API_KEY) : étape ignorée")
        return []

    debut = maintenant()
    fichier = DOSSIER / f"{debut.date().isoformat()}.json"
    du_jour = lire_json(fichier, [])
    faits = {b["sujet_id"] for f in DOSSIER.glob("*.json") for b in lire_json(f, [])}
    hier = (debut - datetime.timedelta(hours=24)).isoformat()      # au-delà, l'info est périmée
    sujets = [s for f in sorted((DATA / "tri").glob("2*.json")) for s in lire_json(f, [])
              if identifiant(s) not in faits and s["propose_le"] >= hier]
    if not sujets:
        print("[rédacteur] aucun nouveau sujet : lancer d'abord agents.tri")
        return []

    systeme = PROMPT.read_text(encoding="utf-8")
    nouveaux = []
    for sujet in sorted(sujets, key=lambda s: s["score"], reverse=True):
        print(f"[rédacteur] {sujet['titre'][:80]}")
        lus = {a["lien"] for a in a_lire(sujet["articles"], cfg["articles_lus"])}
        entree = {
            "articles": [{"source": a["source"], "langue": a["langue"], "titre": a["titre"],
                          "chapo": a["resume"], "date": a["publie_le"][:10],
                          "extrait": extrait(a["lien"], cfg["extrait_max"]) if a["lien"] in lus else ""}
                         for a in sujet["articles"]],
            "deja_rediges": [{"numero": i, "accroche": b["accroche"]}
                             for i, b in enumerate(du_jour + nouveaux) if b["statut"] == "a_valider"],
        }
        ecrire_json(entree["articles"], ENTREES / f"{identifiant(sujet)}.json")
        rep = llm_json(systeme, json.dumps(entree, ensure_ascii=False), temperature, essais=3)
        if not rep:
            print("  ✗ pas de réponse de l'IA, sujet repris au prochain passage")
            continue

        hashtags = rep.pop("hashtags", [])                    # les hashtags gardent leur forme
        rep = uniformiser(rep, cfg.get("uniformiser", []))
        rep["hashtags"] = hashtags
        sources = sources_uniques(sujet["articles"])
        brouillon = {
            "sujet_id": identifiant(sujet),
            "statut": "a_valider",
            "motif": "",
            "statut_info": rep.get("statut_info", "rumeur"),
            "accroche": rep.get("accroche", ""),
            "sous_titre": rep.get("sous_titre", ""),
            "points": nettoyer_points(rep.get("points")),
            "a_retenir": rep.get("a_retenir", ""),
            "voix": rep.get("voix") or {},
            "prononciation": rep.get("prononciation") or {},
            "legende": construire_legende(rep.get("legende", ""), sources, rep.get("hashtags", []), cfg),
            "sources": sources,
            "score_tri": sujet["score"],
            "creneau": sujet.get("creneau"),
            "redige_le": debut.isoformat(),
        }
        brouillon["alertes"] = depassements(brouillon, cfg["limites"])
        doublon = next((d for d in entree["deja_rediges"] if d["numero"] == rep.get("doublon_de")), None)
        if rep.get("hors_sujet"):
            brouillon.update(statut="ecarte", motif="hors sujet (pas du jeu vidéo)")
        elif doublon:
            brouillon.update(statut="ecarte", motif=f"doublon de « {doublon['accroche']} »")
        elif not brouillon["accroche"] or len(brouillon["points"]) < 2:
            brouillon.update(statut="ecarte", motif="réponse de l'IA incomplète")
        nouveaux.append(brouillon)
        ecrire_json(du_jour + nouveaux, fichier)          # enregistré au fil de l'eau
        if brouillon["statut"] == "a_valider":
            print(f"  ✓ {brouillon['accroche']}" + (f"  ⚠ {', '.join(brouillon['alertes'])}" if brouillon["alertes"] else ""))
        else:
            print(f"  – écarté : {brouillon['motif']}")

    prets = sum(b["statut"] == "a_valider" for b in nouveaux)
    print(f"[rédacteur] {prets} brouillons à valider, {len(nouveaux) - prets} écartés -> {fichier.relative_to(DATA.parent)}")
    return nouveaux


if __name__ == "__main__":
    rediger()
