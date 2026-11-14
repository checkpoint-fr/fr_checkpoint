"""Planificateur : lancé toutes les 10 minutes, il fait ce que l'heure demande (config.yaml → planning).

Pour chaque créneau de la journée (heure de Paris) :
- à l'heure de recherche : veille → tri du créneau → rédaction → images → envoi sur Telegram ;
- à l'heure de publication : publie le mieux classé des carrousels que tu as validés (rappel si aucun) ;
- après la tolérance : abandonne ce qui n'a pas été validé et le signale sur Telegram.
À chaque passage, tes clics Telegram sont appliqués. L'état de la journée est dans data/planning.json.
"""
import datetime
import os
import shutil
import subprocess
import time

from agents import publication, redacteur, reel, tri, validation, veille, visuel
from agents.validation import api as telegram
from common.config import DATA, env, load_config
from common.io import ecrire_json, lire_json, maintenant

from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
ETAT = DATA / "planning.json"
VERROU = DATA / ".verrou"


def a_l_heure(jour, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime.combine(jour, datetime.time(h, m), tzinfo=PARIS)


def prevenir(texte):
    try:
        telegram("sendMessage", json={"chat_id": env("TELEGRAM_CHAT_ID").strip(), "text": texte})
    except Exception as ex:
        print(f"[planning] Telegram injoignable : {ex}")


def cloturer(nom, jour):
    """Fin de créneau : les carrousels restés sans décision ou non publiés sont abandonnés."""
    fichiers = validation.tous_les_brouillons()
    chat = env("TELEGRAM_CHAT_ID").strip()
    for bs in fichiers.values():
        for b in bs:
            if b.get("creneau") == nom and publication.du_jour(b, jour) and b["statut"] in ("a_valider", "valide"):
                b["statut"] = "expire"
                if b.get("telegram"):
                    try:
                        telegram("editMessageReplyMarkup", json={"chat_id": chat, "message_id": b["telegram"]["message_id"],
                                                                  "reply_markup": {"inline_keyboard": []}})
                    except Exception:
                        pass
    validation.enregistrer(fichiers)


def menage(jour):
    """Garde le dépôt léger : images effacées 3 jours après rédaction, historiques après 30 jours."""
    limite_images = (jour - datetime.timedelta(days=3)).isoformat()
    limite = (jour - datetime.timedelta(days=30)).isoformat()
    fichiers = validation.tous_les_brouillons()
    for bs in fichiers.values():
        for b in bs:
            if b.get("images") and b["redige_le"][:10] < limite_images and b["statut"] not in ("a_valider", "valide"):
                shutil.rmtree(DATA / "visuels" / b["sujet_id"], ignore_errors=True)
                b["images"] = []
            if b.get("video") and b["redige_le"][:10] < limite_images and b["statut"] not in ("a_valider", "valide"):
                (DATA / "videos" / f"{b['sujet_id']}.mp4").unlink(missing_ok=True)
                b["video"] = ""
    validation.enregistrer(fichiers)
    for dossier in ("redaction", "tri"):
        for f in (DATA / dossier).glob("2*.json"):
            if f.stem < limite:
                f.unlink()


def rechercher(nom, conf):
    print(f"[planning] recherche « {conf['libelle']} »")
    veille.collecter()
    sujets = tri.trier(nom)
    if not sujets:
        return False
    redacteur.rediger()
    if load_config().get("format") == "reel":
        reel.produire()
    else:
        visuel.produire()
    validation.valider()
    return True


def passage(maintenant_paris=None):
    plan = load_config()["planning"]
    ici = maintenant_paris or datetime.datetime.now(PARIS)
    jour = ici.date()
    validation.valider()                                   # tes clics + envoi de ce qui attend
    if jour.isoformat() < plan["debut"]:
        publication.publier()                              # avant le planning : publication au fil de l'eau
        return

    etats = lire_json(ETAT, {})
    etats = {j: e for j, e in etats.items() if j >= (jour - datetime.timedelta(days=7)).isoformat()}
    du_jour = etats.setdefault(jour.isoformat(), {})
    tolerance = datetime.timedelta(minutes=plan["tolerance_minutes"])

    for nom, conf in plan["creneaux"].items():
        e = du_jour.setdefault(nom, {})
        recherche, pub = a_l_heure(jour, conf["recherche"]), a_l_heure(jour, conf["publication"])
        fin = pub + tolerance
        heure = conf["publication"].replace(":", " h ")

        if recherche <= ici < fin and not e.get("recherche"):
            trouve = rechercher(nom, conf)
            e["recherche"] = maintenant().isoformat()
            if not trouve:
                e["publication"] = e["cloture"] = "aucun sujet"
                prevenir(f"ℹ️ Pas de nouvelle info « {conf['libelle']} » aujourd'hui : pas de post à {heure}.")
            ecrire_json(etats, ETAT)

        if pub <= ici < fin and e.get("recherche") and not e.get("publication"):
            if publication.publier_creneau(nom):
                e["publication"] = maintenant().isoformat()
            elif not e.get("rappel"):
                e["rappel"] = maintenant().isoformat()
                prevenir(f"⏰ Le post « {conf['libelle']} » de {heure} attend ta validation "
                         f"(encore {plan['tolerance_minutes'] // 60} h {plan['tolerance_minutes'] % 60:02d} max).")
            ecrire_json(etats, ETAT)

        if ici >= fin and e.get("recherche") and not e.get("cloture"):
            cloturer(nom, jour)
            e["cloture"] = maintenant().isoformat()
            if not e.get("publication"):
                e["publication"] = "aucun"
                prevenir(f"⌛ Pas de post « {conf['libelle']} » aujourd'hui : rien n'a été validé à temps.")
            ecrire_json(etats, ETAT)

    ecrire_json(etats, ETAT)
    menage(jour)


def lancer():
    """Évite deux passages en même temps (une rédaction peut durer plus de 10 minutes)."""
    if VERROU.exists() and time.time() - VERROU.stat().st_mtime < 45 * 60:
        print("[planning] passage précédent encore en cours : on saute ce tour")
        return
    VERROU.write_text(str(os.getpid()))
    try:
        passage()
    finally:
        VERROU.unlink(missing_ok=True)


def fin_de_surveillance(ici):
    """Fenêtre de surveillance d'un créneau : de 45 min avant la recherche à la fin de la tolérance."""
    plan = load_config()["planning"]
    tolerance = datetime.timedelta(minutes=plan["tolerance_minutes"] + 5)
    for conf in plan["creneaux"].values():
        debut = a_l_heure(ici.date(), conf["recherche"]) - datetime.timedelta(minutes=45)
        fin = a_l_heure(ici.date(), conf["publication"]) + tolerance
        if debut <= ici < fin:
            return fin
    return None


def sauvegarder():
    """Sur GitHub Actions : enregistre l'état (data/) dans le dépôt au fil de la surveillance."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True)
    git("add", "data")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("-c", "user.name=checkpoint-bot", "-c", "user.email=checkpoint-bot@users.noreply.github.com",
        "commit", "-q", "-m", f"état {maintenant().strftime('%Y-%m-%dT%H:%MZ')}")
    git("pull", "-q", "--rebase", "-X", "theirs", "origin", "main")   # conflit : l'état de ce passage l'emporte
    envoi = git("push", "-q", "origin", "HEAD:main")
    if envoi.returncode:
        print(f"[planning] état non enregistré sur GitHub : {envoi.stderr.strip()[:200]}")


def surveiller():
    """Pendant une fenêtre : reste allumé, applique chaque clic Telegram en quelques secondes et
    publie à l'heure pile. En dehors : un seul passage. Point d'entrée de GitHub Actions."""
    fin = fin_de_surveillance(datetime.datetime.now(PARIS))
    if not fin:
        lancer()
        return
    print(f"[planning] surveillance jusqu'à {fin.strftime('%H:%M')} (heure de Paris)")
    chat = env("TELEGRAM_CHAT_ID").strip()
    dernier = 0.0
    while datetime.datetime.now(PARIS) < fin:
        try:
            fichiers = validation.tous_les_brouillons()
            clics = validation.lire_reponses(fichiers, chat, attente=25)
            if clics:
                validation.enregistrer(fichiers)
            if clics or time.time() - dernier > 60:
                passage()
                dernier = time.time()
                sauvegarder()
        except Exception as ex:                               # un souci réseau ne doit pas arrêter la surveillance
            print(f"[planning] incident : {ex}")
            time.sleep(30)
    passage()
    sauvegarder()


if __name__ == "__main__":
    lancer()
