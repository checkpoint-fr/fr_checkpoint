"""Agent 2 – Tri : regroupe les articles qui parlent de la même info et classe les sujets.

Entrée : data/veille/*.json (articles des dernières `fenetre_heures`).
Sortie : data/tri/<AAAA-MM-JJ>.json, cumul des `nb_sujets` meilleurs sujets jamais proposés
à chaque passage.
Sans IA ni clé : regroupement par mots rares partagés (noms de jeux, studios, chiffres).
"""
import datetime
import math
import re
import unicodedata
from collections import Counter

from common.config import DATA, load_config
from common.io import ecrire_json, lire_json, maintenant

DOSSIER = DATA / "tri"
HISTORIQUE = DOSSIER / "proposes.json"

MOTS_VIDES = set("""
a au aux avec ce ces cet cette dans de des du elle en est et etre il ils je la le les leur lui ma mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sont sur ta te tes toi ton tu un une
vos votre vous y ete fait faire plus moins tout tous toute toutes tres bien encore deja enfin alors comme quand
si sans sous apres avant depuis entre vers chez voici voila cela ca c d l j m n s t qu jusqu aussi peut
the of and to in on for with at by from is are was were be been has have had it its this that these those as an
or but not no so if than then into over after before about up out new now just will can could would should
his her their they them he she we you your our my me us what when where who why how all more most some any
one two first last get got gets make makes still yet also only even like here there via vs
jeu jeux game games gaming joueurs joueur players player video nouveau nouvelle nouvelles annonce annonces
trailer bande mise jour update sortie release date officiel officially official review test avis
ps5 ps4 xbox series pc switch playstation nintendo steam console consoles 2026
janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
january february march april june july august september october november december
today tomorrow aujourd hui demain week semaine
""".split())


def normaliser(texte, alias):
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'`´]", " ", t)
    t = " " + re.sub(r"[^a-z0-9]+", " ", t) + " "
    for long, court in alias.items():
        t = t.replace(f" {long} ", f" {court} ")
    return t


def mots(article, alias):
    texte = normaliser(article["titre"] + " " + article["resume"][:160], alias)
    return {m for m in texte.split() if m not in MOTS_VIDES and (len(m) > 2 or m.isdigit())}


def poids_idf(ensembles):
    n = len(ensembles)
    freq = Counter(m for e in ensembles for m in e)
    return {m: math.log((n + 1) / (f + 0.5)) for m, f in freq.items()}


def similarite(a, b, idf):
    defaut = max(idf.values(), default=1.0)      # mot absent du corpus du jour = mot rare
    union = sum(idf.get(m, defaut) for m in a | b)
    return sum(idf.get(m, defaut) for m in a & b) / union if union else 0.0


def regrouper(articles, ensembles, idf, seuil):
    """Liaison moyenne : un article rejoint le groupe dont il est en moyenne le plus proche."""
    groupes = []                      # listes d'indices
    for i in sorted(range(len(articles)), key=lambda k: articles[k]["publie_le"]):
        meilleur, score_max = None, seuil
        for g in groupes:
            s = sum(similarite(ensembles[i], ensembles[j], idf) for j in g) / len(g)
            if s >= score_max:
                meilleur, score_max = g, s
        if meilleur is None:
            groupes.append([i])
        else:
            meilleur.append(i)
    return groupes


def exclu(article, motifs):
    titre = normaliser(article["titre"], {})
    return any(re.search(m, titre) for m in motifs)


def titre_representatif(arts):
    """Titre français de préférence (on publie en français), sinon officiel, sinon le plus repris."""
    for cond in (lambda a: a["langue"] == "fr", lambda a: a["type"] == "officiel"):
        choix = [a for a in arts if cond(a)]
        if choix:
            return choix[0]["titre"]
    return arts[0]["titre"]


def noter(arts, cfg, maintenant_):
    p = cfg["poids"]
    sources = {a["source"] for a in arts}
    types = {a["type"] for a in arts}
    langues = {a["langue"] for a in arts}
    dernier = max(datetime.datetime.fromisoformat(a["publie_le"]) for a in arts)
    age_h = max((maintenant_ - dernier).total_seconds() / 3600, 0)
    brut = (p["par_source"] * len(sources)
            + p["officiel"] * ("officiel" in types)
            + p["communaute"] * ("communaute" in types)
            + p["fr_et_en"] * (len(langues) > 1))
    return round(brut * 0.5 ** (age_h / cfg["demi_vie_heures"]), 2), dernier


def deja_propose(signature, historique, idf, seuil):
    return any(similarite(signature, set(h["mots"]), idf) >= seuil for h in historique)


def du_theme(article, motifs):
    texte = normaliser(article["titre"] + " " + article["resume"], {})
    return any(re.search(m, texte) for m in motifs)


def trier(creneau=None):
    """Sans créneau : tous les sujets. Avec un créneau de config.yaml → planning, seulement ses
    articles (`inclure`), sans ceux d'un autre thème (`exclure`), et `nb_sujets` candidats."""
    cfg = load_config()["tri"]
    plan = load_config()["planning"]["creneaux"][creneau] if creneau else {}
    debut = maintenant()
    seuil_date = debut - datetime.timedelta(hours=cfg["fenetre_heures"])

    articles = []
    for f in sorted((DATA / "veille").glob("*.json")):
        articles += [a for a in lire_json(f, [])
                     if datetime.datetime.fromisoformat(a["publie_le"]) >= seuil_date]
    exclus = [a for a in articles if exclu(a, cfg["exclusions"])]
    articles = [a for a in articles if not exclu(a, cfg["exclusions"])]
    if plan.get("inclure"):
        articles = [a for a in articles if du_theme(a, plan["inclure"])]
    if plan.get("exclure"):
        articles = [a for a in articles if not du_theme(a, plan["exclure"])]
    if not articles:
        print(f"[tri] aucun article récent{' pour ' + creneau if creneau else ''}")
        return []

    alias = {normaliser(k, {}).strip(): normaliser(v, {}).strip() for k, v in cfg["alias"].items()}
    ensembles = [mots(a, alias) for a in articles]
    idf = poids_idf(ensembles)
    groupes = regrouper(articles, ensembles, idf, cfg["seuil_regroupement"])

    limite_histo = (debut - datetime.timedelta(days=cfg["memoire_jours"])).isoformat()
    historique = [h for h in lire_json(HISTORIQUE, []) if h["date"] >= limite_histo]

    sujets = []
    for g in groupes:
        arts = sorted((articles[i] for i in g), key=lambda a: a["publie_le"], reverse=True)
        score, dernier = noter(arts, cfg, debut)
        nb_sources = len({a["source"] for a in arts})
        if nb_sources < plan.get("min_sources", cfg["min_sources"]) and "communaute" not in {a["type"] for a in arts}:
            continue
        compte = Counter(m for i in g for m in ensembles[i])
        signature = {m for m, n in compte.items() if n >= max(2, len(g) / 2)} or set(compte)
        if deja_propose(signature, historique, idf, cfg["seuil_regroupement"]):
            continue
        sujets.append({
            "signature": sorted(signature),
            "titre": titre_representatif(arts),
            "score": score,
            "nb_sources": nb_sources,
            "sources": sorted({a["source"] for a in arts}),
            "langues": sorted({a["langue"] for a in arts}),
            "dernier_article": dernier.isoformat(),
            "mots_cles": sorted(signature, key=lambda m: -idf.get(m, 0))[:8],
            "articles": [{k: a[k] for k in ("source", "type", "langue", "titre", "lien", "resume", "publie_le")}
                         for a in arts],
        })

    sujets.sort(key=lambda s: s["score"], reverse=True)
    retenus = sujets[:plan.get("nb_sujets", cfg["nb_sujets"])]

    for s in retenus:
        s["propose_le"] = debut.isoformat()
        s["creneau"] = creneau
    fichier = DOSSIER / f"{debut.date().isoformat()}.json"
    ecrire_json(lire_json(fichier, []) + retenus, fichier)      # cumul des passages de la journée
    historique += [{"date": debut.isoformat(), "titre": s["titre"], "mots": s["signature"]} for s in retenus]
    ecrire_json(historique, HISTORIQUE)

    print(f"[tri] {len(articles)} articles ({len(exclus)} exclus) -> {len(groupes)} groupes, "
          f"{len(sujets)} sujets valables, {len(retenus)} retenus -> {fichier.relative_to(DATA.parent)}")
    for s in retenus:
        print(f"  {s['score']:5.2f} · {s['nb_sources']} sources · {s['titre'][:90]}")
    return retenus


if __name__ == "__main__":
    import sys
    trier(sys.argv[1] if len(sys.argv) > 1 else None)
