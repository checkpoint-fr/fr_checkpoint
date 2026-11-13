"""Agent 5 – Validation : envoie chaque carrousel sur Telegram avec ✅ / ❌ et applique tes réponses.

1. Lit les clics reçus depuis le dernier passage : brouillon « valide » ou « rejete ».
2. Envoie les nouveaux brouillons « a_valider » qui ont leurs images (album + légende + boutons).
3. Passe en « expire » ceux restés sans réponse plus de `expiration_heures`.
Seule la conversation TELEGRAM_CHAT_ID est écoutée : les clics de quelqu'un d'autre sont ignorés.
"""
import datetime
import json

import requests

from common.config import DATA, ROOT, env, load_config
from common.io import ecrire_json, lire_json, maintenant

DOSSIER = DATA / "redaction"
CURSEUR = DATA / "telegram_curseur.json"      # dernier message Telegram déjà traité


def api(methode, **kwargs):
    url = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN').strip()}/{methode}"
    r = requests.post(url, timeout=60, **kwargs).json()
    if not r.get("ok"):
        raise RuntimeError(f"Telegram {methode} : {r.get('description')}")
    return r["result"]


def tous_les_brouillons():
    """{fichier: [brouillons]} pour relire et réécrire au même endroit."""
    return {f: lire_json(f, []) for f in sorted(DOSSIER.glob("*.json"))}


def enregistrer(fichiers):
    for f, brouillons in fichiers.items():
        ecrire_json(brouillons, f)


def texte_validation(b):
    liens = "\n".join(f"• {s['nom']} : {s['lien']}" for s in b["sources"])
    alertes = f"\n⚠️ {', '.join(b['alertes'])}" if b.get("alertes") else ""
    creneau = ""
    if b.get("creneau"):
        c = load_config()["planning"]["creneaux"][b["creneau"]]
        creneau = (f"\n🕒 Post « {c['libelle']} » de {c['publication'].replace(':', ' h ')} : "
                   "un seul sera publié, le mieux classé parmi ceux que tu valides")
    return (f"{b['legende']}\n\n━━━━━━━━━━\nStatut : {b['statut_info']} · score {b['score_tri']}{alertes}"
            f"{creneau}\nÀ vérifier si besoin :\n{liens}")[:4096]


def boutons(sujet_id):
    return {"inline_keyboard": [[{"text": "✅ Publier", "callback_data": f"ok:{sujet_id}"},
                                 {"text": "❌ Rejeter", "callback_data": f"non:{sujet_id}"}]]}


def decision(chat, message_id, texte_actuel, verdict):
    """Retire les boutons et note la décision sous le message."""
    try:
        api("editMessageText", json={"chat_id": chat, "message_id": message_id,
                                     "text": f"{texte_actuel}\n\n{verdict}"[:4096]})
    except RuntimeError as ex:
        print(f"  (message non modifié : {ex})")


def lire_reponses(fichiers, chat):
    curseur = lire_json(CURSEUR, {"offset": 0})
    mises_a_jour = api("getUpdates", json={"offset": curseur["offset"], "timeout": 0,
                                           "allowed_updates": ["callback_query"]})
    par_id = {b["sujet_id"]: b for brouillons in fichiers.values() for b in brouillons}
    traites = 0
    for maj in mises_a_jour:
        curseur["offset"] = maj["update_id"] + 1
        clic = maj.get("callback_query")
        if not clic:
            continue
        if str(clic["from"]["id"]) != chat:                   # quelqu'un d'autre : ignoré
            api("answerCallbackQuery", json={"callback_query_id": clic["id"], "text": "Non autorisé"})
            continue
        action, _, sujet_id = clic.get("data", "").partition(":")
        b = par_id.get(sujet_id)
        if not b or b["statut"] != "a_valider":
            api("answerCallbackQuery", json={"callback_query_id": clic["id"], "text": "Déjà traité"})
            continue
        b["statut"] = "valide" if action == "ok" else "rejete"
        b["decide_le"] = maintenant().isoformat()
        verdict = ("✅ Validé : publication au prochain passage" if action == "ok" else "❌ Rejeté")
        try:
            api("answerCallbackQuery", json={"callback_query_id": clic["id"], "text": verdict})
        except RuntimeError:
            pass                                               # clic trop ancien : Telegram refuse la réponse
        decision(chat, clic["message"]["message_id"], clic["message"].get("text", ""), verdict)
        traites += 1
        print(f"[validation] {verdict[:2]} {b['accroche'][:70]}")
    ecrire_json(curseur, CURSEUR)
    return traites


def envoyer(fichiers, chat):
    envoyes = 0
    for brouillons in fichiers.values():
        for b in brouillons:
            if b["statut"] != "a_valider" or b.get("telegram") or not b.get("images"):
                continue
            fichiers_photos = {f"p{i}": open(ROOT / chemin, "rb") for i, chemin in enumerate(b["images"])}
            try:
                album = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(b["images"]))]
                album[0]["caption"] = b["accroche"]
                api("sendMediaGroup", data={"chat_id": chat, "media": json.dumps(album)}, files=fichiers_photos)
            finally:
                for f in fichiers_photos.values():
                    f.close()
            message = api("sendMessage", json={"chat_id": chat, "text": texte_validation(b),
                                               "disable_web_page_preview": True,
                                               "reply_markup": boutons(b["sujet_id"])})
            b["telegram"] = {"message_id": message["message_id"], "envoye_le": maintenant().isoformat()}
            envoyes += 1
            print(f"[validation] → envoyé : {b['accroche'][:70]}")
    return envoyes


def expirer(fichiers, chat, heures):
    limite = (maintenant() - datetime.timedelta(hours=heures)).isoformat()
    for brouillons in fichiers.values():
        for b in brouillons:
            t = b.get("telegram")
            if b["statut"] == "a_valider" and t and t["envoye_le"] < limite:
                b["statut"] = "expire"
                try:
                    api("editMessageReplyMarkup", json={"chat_id": chat, "message_id": t["message_id"],
                                                        "reply_markup": {"inline_keyboard": []}})
                except RuntimeError:
                    pass
                print(f"[validation] ⌛ expiré : {b['accroche'][:70]}")


def valider():
    chat = env("TELEGRAM_CHAT_ID").strip()
    if not env("TELEGRAM_BOT_TOKEN") or not chat:
        print("[validation] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID absents dans .env : étape ignorée")
        return
    fichiers = tous_les_brouillons()
    traites = lire_reponses(fichiers, chat)
    enregistrer(fichiers)                                      # décisions sauvées avant tout envoi
    expirer(fichiers, chat, load_config()["validation"]["expiration_heures"])
    try:
        envoyes = envoyer(fichiers, chat)
    finally:
        enregistrer(fichiers)
    print(f"[validation] {traites} décisions appliquées, {envoyes} carrousels envoyés sur Telegram")


if __name__ == "__main__":
    valider()
