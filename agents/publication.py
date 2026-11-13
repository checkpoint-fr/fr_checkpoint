"""Agent 6 – Publication : publie sur Instagram les carrousels que tu as validés sur Telegram.

Pour chaque brouillon « valide » (dans la limite de `max_par_passage` et des heures de publication) :
1. dépose les images sur le dépôt GitHub public de médias (Instagram exige une adresse publique) ;
2. crée les conteneurs Instagram (un par image, puis le carrousel avec la légende) et publie ;
3. supprime les images du dépôt, note le lien du post et te prévient sur Telegram.
`python -m agents.publication --essai` montre ce qui serait publié, sans rien envoyer.
"""
import base64
import datetime
import sys
import time

import requests

from agents.validation import api as telegram, enregistrer, tous_les_brouillons
from common.config import ROOT, env, load_config
from common.io import maintenant

from zoneinfo import ZoneInfo


def cfg():
    return load_config()["publication"]


# ---------- GitHub : hébergement temporaire des images ----------

def github(methode, chemin, **kwargs):
    url = f"https://api.github.com/repos/{env('MEDIAS_DEPOT').strip()}/contents/{chemin}"
    r = requests.request(methode, url, timeout=60, headers={
        "Authorization": f"Bearer {env('MEDIAS_TOKEN').strip()}",
        "Accept": "application/vnd.github+json"}, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub {methode} {chemin} : {r.status_code} {r.text[:200]}")
    return r.json()


def deposer(b):
    """Envoie les images, renvoie [(chemin_dans_le_depot, sha, url_publique)]."""
    depot = env("MEDIAS_DEPOT").strip()
    deposes = []
    for local in b["images"]:
        chemin = f"medias/{b['sujet_id']}/{local.rsplit('/', 1)[-1]}"
        contenu = base64.b64encode((ROOT / local).read_bytes()).decode()
        rep = github("PUT", chemin, json={"message": f"média {b['sujet_id']}", "content": contenu})
        # adresse figée sur le commit : Meta refuse parfois l'adresse « main » (cache pas encore à jour)
        deposes.append((chemin, rep["content"]["sha"],
                        f"https://raw.githubusercontent.com/{depot}/{rep['commit']['sha']}/{chemin}"))
    return deposes


def retirer(deposes):
    for chemin, sha, _ in deposes:
        try:
            github("DELETE", chemin, json={"message": "média publié", "sha": sha})
        except RuntimeError as ex:
            print(f"  (image laissée sur GitHub : {ex})")


def attendre_url(url):
    """raw.githubusercontent.com met parfois quelques secondes à servir un nouveau fichier."""
    for _ in range(12):
        if requests.head(url, timeout=20).status_code == 200:
            return
        time.sleep(5)
    raise RuntimeError(f"image introuvable en ligne : {url}")


# ---------- Instagram ----------

def instagram(methode, chemin, **params):
    url = f"https://{cfg()['hote_api']}/{cfg()['version_api']}/{chemin}"
    params["access_token"] = env("INSTAGRAM_ACCESS_TOKEN").strip()
    r = requests.request(methode, url, params=params, timeout=60).json()
    if "error" in r:
        e = r["error"]
        raise RuntimeError(f"Instagram {chemin} : {e.get('message')} (code {e.get('code')})")
    return r


def compte_instagram():
    """Jeton « utilisateur système » (connexion unifiée) : le compte est celui affecté à ce jeton."""
    if env("INSTAGRAM_USER_ID").strip():
        return env("INSTAGRAM_USER_ID").strip()
    comptes = instagram("GET", "me/assigned_instagram_accounts")["data"]
    if not comptes:
        raise RuntimeError("aucun compte Instagram affecté à ce jeton")
    return comptes[0]["id"]


def attendre_conteneur(ident):
    for _ in range(20):                              # 5 minutes au plus, comme le recommande Meta
        statut = instagram("GET", ident, fields="status_code")["status_code"]
        if statut == "FINISHED":
            return
        if statut in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"conteneur {ident} : {statut}")
        time.sleep(15)
    raise RuntimeError(f"conteneur {ident} toujours en traitement après 5 min")


def publier_carrousel(ig, urls, legende):
    enfants = []
    for url in urls:
        for essai in range(3):                     # Meta n'arrive pas toujours à lire l'image du premier coup
            try:
                enfants.append(instagram("POST", f"{ig}/media", image_url=url, is_carousel_item="true")["id"])
                break
            except RuntimeError as ex:
                if "9004" not in str(ex) or essai == 2:
                    raise
                time.sleep(15)
    for enfant in enfants:
        attendre_conteneur(enfant)
    carrousel = instagram("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(enfants),
                          caption=legende)["id"]
    attendre_conteneur(carrousel)
    media = instagram("POST", f"{ig}/media_publish", creation_id=carrousel)["id"]
    lien = instagram("GET", media, fields="permalink").get("permalink", "")
    return media, lien


# ---------- choix des brouillons ----------

def creneau_ouvert():
    heure = datetime.datetime.now(ZoneInfo("Europe/Paris")).hour
    debut, fin = cfg()["heures_publication"]
    return debut <= heure < fin


def derniere_publication(fichiers):
    dates = [b["instagram"]["publie_le"] for bs in fichiers.values() for b in bs if b.get("instagram")]
    return max(dates) if dates else ""


def a_publier(fichiers):
    """Brouillons validés hors planning (sans créneau), publiés au fil de l'eau."""
    limite = (maintenant() - datetime.timedelta(hours=cfg()["fraicheur_heures"])).isoformat()
    candidats, perimes = [], []
    for bs in fichiers.values():
        for b in bs:
            if b["statut"] != "valide" or b.get("creneau"):
                continue
            (candidats if b["decide_le"] >= limite else perimes).append(b)
    candidats.sort(key=lambda b: b["score_tri"], reverse=True)
    return candidats, perimes


def cles_manquantes():
    return [k for k in ("INSTAGRAM_ACCESS_TOKEN", "MEDIAS_TOKEN", "MEDIAS_DEPOT") if not env(k)]


def publier_brouillon(b, ig, fichiers):
    """Dépose les images, publie le carrousel, prévient sur Telegram ; compte les échecs."""
    chat = env("TELEGRAM_CHAT_ID").strip()
    print(f"[publication] {b['accroche'][:70]}")
    deposes = []
    try:
        deposes = deposer(b)
        for _, _, url in deposes:
            attendre_url(url)
        media, lien = publier_carrousel(ig, [u for _, _, u in deposes], b["legende"][:2200])
        b["statut"] = "publie"
        b["instagram"] = {"media_id": media, "lien": lien, "publie_le": maintenant().isoformat()}
        print(f"  ✓ publié : {lien}")
        telegram("sendMessage", json={"chat_id": chat, "text": f"📣 Publié sur Instagram : {b['accroche']}\n{lien}"})
        return True
    except Exception as ex:
        b["echecs"] = b.get("echecs", 0) + 1
        b["erreur"] = str(ex)[:300]
        if b["echecs"] >= cfg()["essais_max"]:
            b["statut"] = "echec"
        print(f"  ✗ {ex}")
        telegram("sendMessage", json={"chat_id": chat, "text":
                 f"⚠️ Publication ratée ({b['echecs']}/{cfg()['essais_max']}) : {b['accroche']}\n{str(ex)[:300]}"})
        return False
    finally:
        retirer(deposes)
        enregistrer(fichiers)


def publier(essai=False):
    """Hors planning : un brouillon validé par passage, de 8 h à 23 h, 1 h 30 d'écart."""
    if cles_manquantes() and not essai:
        print(f"[publication] {', '.join(cles_manquantes())} absents dans .env : étape ignorée")
        return
    fichiers = tous_les_brouillons()
    candidats, perimes = a_publier(fichiers)
    for b in perimes:
        b["statut"] = "expire"
        print(f"[publication] ⌛ trop ancien, abandonné : {b['accroche'][:70]}")

    ecart = datetime.timedelta(minutes=cfg()["ecart_minutes"])
    derniere = derniere_publication(fichiers)
    if not creneau_ouvert():
        print(f"[publication] hors des heures de publication {cfg()['heures_publication']} (heure de Paris)")
        candidats = []
    elif derniere and maintenant() - datetime.datetime.fromisoformat(derniere) < ecart:
        print(f"[publication] dernier post il y a moins de {cfg()['ecart_minutes']} min : on attend")
        candidats = []
    candidats = candidats[:cfg()["max_par_passage"]]

    if essai:
        for b in candidats:
            print(f"[publication] (essai) publierait : {b['accroche']} · {len(b['images'])} images · "
                  f"légende {len(b['legende'])} car.")
        print(f"[publication] (essai) {len(candidats)} à publier, rien n'a été envoyé")
        return

    ig = compte_instagram() if candidats else None
    for b in candidats:
        publier_brouillon(b, ig, fichiers)
    enregistrer(fichiers)


def du_jour(b, jour):
    return datetime.datetime.fromisoformat(b["redige_le"]).astimezone(ZoneInfo("Europe/Paris")).date() == jour


def publier_creneau(nom, essai=False):
    """Planning : publie le mieux classé des brouillons validés aujourd'hui pour ce créneau.
    Renvoie True quand le créneau est traité (publié, ou rien à publier faute de brouillon)."""
    if cles_manquantes() and not essai:
        print(f"[publication] {', '.join(cles_manquantes())} absents dans .env : étape ignorée")
        return False
    jour = datetime.datetime.now(ZoneInfo("Europe/Paris")).date()
    fichiers = tous_les_brouillons()
    du_creneau = [b for bs in fichiers.values() for b in bs if b.get("creneau") == nom and du_jour(b, jour)]
    if any(b["statut"] == "publie" for b in du_creneau):
        return True
    valides = sorted((b for b in du_creneau if b["statut"] == "valide"), key=lambda b: b["score_tri"], reverse=True)
    if not valides:
        print(f"[publication] {nom} : aucun carrousel validé pour l'instant")
        return False
    if essai:
        print(f"[publication] (essai) {nom} publierait : {valides[0]['accroche']}")
        return True
    if publier_brouillon(valides[0], compte_instagram(), fichiers):
        for b in valides[1:]:
            b["statut"] = "non_retenu"
            print(f"[publication] non retenu (un seul post par créneau) : {b['accroche'][:60]}")
        enregistrer(fichiers)
        return True
    return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        publier_creneau(sys.argv[1], essai="--essai" in sys.argv)
    else:
        publier(essai="--essai" in sys.argv)
