"""Agent 4 bis – Reel : transforme chaque brouillon à valider en vidéo verticale Instagram.

Écrans 1080×1920 (accroche, un écran par point, « À retenir », appel à s'abonner), voix off française
(Gemini, gratuit) lue par le rédacteur, sous-titres incrustés, musique libre de droits en fond
(assets/musique/*.mp3, facultatif). Sortie : data/videos/<sujet_id>.mp4, chemin noté dans « video ».
Si la voix est indisponible, la vidéo est faite sans voix (texte affiché plus longtemps).
"""
import base64
import difflib
import random
import re
import subprocess
import tempfile
import unicodedata
import wave
from pathlib import Path

import imageio_ffmpeg
import requests
from PIL import Image, ImageDraw

from agents.visuel import ajuster, couleur, couper, drapeau, ecrire, espace, icone, pastille, police, typo
from common.config import DATA, ROOT, env, load_config
from common.io import ecrire_json, lire_json

DOSSIER = DATA / "videos"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
M = 90


def cfg():
    return load_config()["reel"]


# ---------- voix ----------

def voix_off(texte, sortie):
    """Lit le texte avec la voix Gemini (modèle principal puis léger). Le texte est envoyé seul : toute
    consigne ajoutée serait lue à voix haute. Renvoie True si le fichier existe."""
    c = cfg()["voix"]
    corps = {"contents": [{"parts": [{"text": texte}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": c["nom"]}}}}}
    for modele in c["modeles"]:
        for essai in range(2):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent",
                                  headers={"x-goog-api-key": env("GEMINI_API_KEY").strip()}, json=corps, timeout=180)
                r.raise_for_status()
                partie = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                donnees = base64.b64decode(partie["data"])
                if not donnees.startswith(b"RIFF"):          # PCM brut 24 kHz mono 16 bits
                    with wave.open(str(sortie), "wb") as w:
                        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000), w.writeframes(donnees)
                else:
                    Path(sortie).write_bytes(donnees)
                return True
            except Exception as ex:
                print(f"  [voix] {modele} indisponible ({str(ex)[:100]})")
    return False


def duree_wav(chemin):
    with wave.open(str(chemin)) as w:
        return w.getnframes() / w.getframerate()


def transcrire(chemin):
    """Ce que la voix a vraiment dit, mot par mot avec l'heure exacte (Whisper chez Groq, gratuit)."""
    try:
        with open(chemin, "rb") as f:
            r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", timeout=120,
                              headers={"Authorization": f"Bearer {env('GROQ_API_KEY').strip()}"},
                              files={"file": f}, data={"model": cfg()["transcription"], "language": "fr",
                                                       "response_format": "verbose_json",
                                                       "timestamp_granularities[]": "word"})
        r.raise_for_status()
        return [(w["word"], w["start"], w["end"]) for w in r.json().get("words", [])]
    except Exception as ex:
        print(f"  [voix] transcription indisponible ({str(ex)[:100]}) : synchro approximative")
        return []


def normal(mot):
    m = unicodedata.normalize("NFKD", mot.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in m if not unicodedata.combining(c)))


def chronologie(textes, mots_dits, total):
    """Heure de début de chaque mot du script, en le calant sur la transcription (les mots non
    reconnus, comme un nombre lu en toutes lettres, sont placés entre leurs voisins)."""
    script = [(normal(m), m, i) for i, t in enumerate(textes) for m in t.split()]
    heures = [None] * len(script)
    if mots_dits:
        appariement = difflib.SequenceMatcher(None, [s[0] for s in script], [normal(m[0]) for m in mots_dits],
                                              autojunk=False)
        for a, b, taille in appariement.get_matching_blocks():
            for k in range(taille):
                heures[a + k] = mots_dits[b + k][1]
    connus = [i for i, h in enumerate(heures) if h is not None]
    if len(connus) < max(3, len(script) // 4):                # transcription absente ou inutilisable
        poids = [len(s[1]) + 1 for s in script]
        cumul = 0
        for i, p in enumerate(poids):
            heures[i] = total * cumul / sum(poids)
            cumul += p
        return script, heures
    for i in range(len(script)):                             # interpolation des trous
        if heures[i] is None:
            avant = max((k for k in connus if k < i), default=None)
            apres = min((k for k in connus if k > i), default=None)
            if avant is None:
                heures[i] = max(0.0, heures[apres] - 0.3 * (apres - i))
            elif apres is None:
                heures[i] = min(total, heures[avant] + 0.3 * (i - avant))
            else:
                heures[i] = heures[avant] + (heures[apres] - heures[avant]) * (i - avant) / (apres - avant)
    return script, heures


def decouper_sous_titres(script, heures, segment, fin_segment):
    """Morceaux de 2 lignes au plus pour un écran, chacun affiché de son premier mot au suivant."""
    indices = [k for k, s in enumerate(script) if s[2] == segment]
    morceaux, courant = [], []
    for k in indices:
        courant.append(k)
        texte = " ".join(script[j][1] for j in courant)
        if len(texte) > 34 or script[k][1][-1:] in ".!?":
            morceaux.append(courant)
            courant = []
    if courant:
        morceaux.append(courant)
    sortie = []
    for n, morceau in enumerate(morceaux):
        debut = heures[morceau[0]]
        fin = heures[morceaux[n + 1][0]] if n + 1 < len(morceaux) else fin_segment
        sortie.append((" ".join(script[j][1] for j in morceau), debut, max(fin, debut + 0.2)))
    return sortie


# ---------- écrans ----------

def toile():
    c = cfg()
    img = Image.new("RGB", (c["largeur"], c["hauteur"]), couleur("fond"))
    return img, ImageDraw.Draw(img)


def progression(d, n, total):
    largeur = cfg()["largeur"] - 2 * M
    d.rounded_rectangle([M, 240, M + largeur, 246], 3, fill=couleur("carte"))
    d.rounded_rectangle([M, 240, M + largeur * n / total, 246], 3, fill=couleur("accent"))


def ecran_couverture(b):
    img, d = toile()
    statut = b.get("statut_info", "rumeur")
    pastille(d, M, 330, load_config()["visuel"]["statuts"].get(statut, statut.upper()), plein=statut == "officiel")
    f, lignes, pas = ajuster(b["accroche"], "titre", range(124, 64, -4), cfg()["largeur"] - 2 * M, 700, 1.08, max_lignes=6)
    y = ecrire(d, M, 440, lignes, f, pas, couleur("texte"))
    d.rectangle([M, y + 34, M + 160, y + 46], fill=couleur("accent"))
    return img


def ecran_point(p, numero):
    img, d = toile()
    d.text((M - 8, 310), f"{numero:02d}", font=police("titre", 230), fill=couleur("accent"))
    f, lignes, pas = ajuster(p["titre"], "titre", range(96, 52, -4), cfg()["largeur"] - 2 * M, 520, 1.1, max_lignes=4)
    ecrire(d, M, 610, lignes, f, pas, couleur("texte"))
    return img


def ecran_retenir(b):
    img, d = toile()
    espace(d, M, 340, "À RETENIR", police("texte", 34, 800), couleur("accent"), 4)
    f, lignes, pas = ajuster(b["a_retenir"], "texte", range(88, 48, -2), cfg()["largeur"] - 2 * M, 760, 1.22, 700)
    ecrire(d, M, 420, lignes, f, pas, couleur("texte"))
    return img


def ecran_appel():
    a = load_config()["visuel"]["appel"]
    img, d = toile()
    drapeau(d, M, 330, 110)
    f, lignes, pas = ajuster(a["titre"], "titre", range(104, 60, -4), cfg()["largeur"] - 2 * M, 280, 1.1, max_lignes=2)
    y = ecrire(d, M, 500, lignes, f, pas, couleur("texte")) + 80
    ft = police("texte", 46, 600)
    for nom, texte in zip(("coeur", "bulle", "partage", "signet"), a["actions"]):
        icone(d, nom, M, y, 60)
        d.text((M + 104, y + 30), typo(texte), font=ft, fill=couleur("texte"), anchor="lm")
        y += 122
    fs = police("titre", 64)
    suivre = a["suivre"] + " "
    d.text((M, y + 70), suivre, font=fs, fill=couleur("texte"))
    d.text((M + fs.getlength(suivre), y + 70), load_config()["compte"]["nom"], font=fs, fill=couleur("accent"))
    return img


def incruster(base, texte):
    img = base.copy()
    d = ImageDraw.Draw(img)
    largeur = cfg()["largeur"] - 2 * M - 80             # marge à droite : icônes d'Instagram
    f = police("texte", 56, 800)
    lignes = couper(texte, f, largeur - 60)[:2]
    haut = len(lignes) * 72 + 44
    y0 = 1290
    d.rounded_rectangle([M, y0, M + largeur, y0 + haut], 26, fill=couleur("carte"))
    d.rectangle([M, y0 + 18, M + 8, y0 + haut - 18], fill=couleur("accent"))
    for i, ligne in enumerate(lignes):
        d.text((M + 40, y0 + 22 + i * 72), ligne, font=f, fill=couleur("texte"))
    return img


# ---------- montage ----------

def fabriquer(b):
    """Crée la vidéo d'un brouillon. Renvoie le chemin relatif du MP4."""
    c = cfg()
    voix = b.get("voix") or {}
    points = b["points"]
    textes = [voix.get("couverture") or b["accroche"]]
    textes += [(voix.get("points") or [])[i] if i < len(voix.get("points") or []) else p["texte"]
               for i, p in enumerate(points)]
    textes += [voix.get("retenir") or b["a_retenir"], c["voix"]["appel"]]
    textes = [t.strip() + ("" if t.strip()[-1:] in ".!?" else ".") for t in textes]
    ecrans = [ecran_couverture(b)] + [ecran_point(p, i + 1) for i, p in enumerate(points)] \
        + [ecran_retenir(b), ecran_appel()]
    total = len(ecrans)

    DOSSIER.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        voix_wav, decalage = tmp / "voix.wav", 0.0
        mots_dits = []
        a_lire = " ".join(textes)
        # sigles et nombres exclus des réécritures de l'IA : la voix les lit très bien à la française
        propres = {n: v for n, v in (b.get("prononciation") or {}).items()
                   if not re.search(r"\b[A-Z]{2,}\b|\d", n)}
        for nom, phonetique in {**propres, **c.get("prononciation", {})}.items():
            a_lire = re.sub(rf"(?<!\w){re.escape(nom)}(?!\w)", phonetique, a_lire)
        if voix_off(a_lire, voix_wav):
            duree_voix = duree_wav(voix_wav)
            mots_dits = transcrire(voix_wav)
            script, heures = chronologie(textes, mots_dits, duree_voix)
            if heures[0] > 1.2:                                 # la voix a dit autre chose avant le texte
                decalage = heures[0] - 0.15
                heures = [h - decalage for h in heures]
            duree_totale = duree_voix - decalage + c["fin_secondes"]   # dernier écran tenu après la voix
        else:
            voix_wav = None
            duree_totale = sum(max(3.0, len(t) / 15) for t in textes)   # temps de lecture sans voix
            script, heures = chronologie(textes, [], duree_totale)
        premiers = [min(k for k, x in enumerate(script) if x[2] == i) for i in range(total)]
        debuts = [0.0] + [heures[k] for k in premiers[1:]]
        fins = debuts[1:] + [duree_totale]

        liste, n = [], 0

        def ajouter(image, temps):
            nonlocal n
            chemin = tmp / f"{n:03d}.png"
            image.save(chemin)
            liste.append(f"file '{chemin}'\nduration {max(temps, 0.04):.3f}")
            n += 1

        for i, ecran in enumerate(ecrans):
            progression(ImageDraw.Draw(ecran), i + 1, total)
            if i == total - 1:                                  # écran d'appel : pas de sous-titres
                ajouter(ecran, fins[i] - debuts[i])
                continue
            morceaux = decouper_sous_titres(script, heures, i, fins[i])
            if morceaux and morceaux[0][1] > debuts[i] + 0.04:
                ajouter(ecran, morceaux[0][1] - debuts[i])
            for texte, debut, fin in morceaux:
                ajouter(incruster(ecran, typo(texte)), min(fin, fins[i]) - debut)
        liste.append(f"file '{tmp / f'{n - 1:03d}.png'}'")
        (tmp / "images.txt").write_text("\n".join(liste))

        musiques = sorted((ROOT / c["musique"]["dossier"]).glob("*.mp3"))
        entrees, filtres = [], []
        if voix_wav:
            entrees += ["-i", str(voix_wav)]
        if musiques:
            entrees += ["-stream_loop", "-1", "-i", str(random.choice(musiques))]
        if voix_wav and musiques:
            filtres = ["-filter_complex",
                       f"[0:a]atrim=start={decalage:.2f},asetpts=PTS-STARTPTS,apad,atrim=0:{duree_totale:.2f}[v];[1:a]volume={c['musique']['volume']},"
                       f"atrim=0:{duree_totale:.2f},afade=t=out:st={duree_totale - 2:.2f}:d=2[m];"
                       "[v][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "2:v", "-map", "[a]"]
        elif voix_wav or musiques:
            filtres = ["-filter_complex", f"[0:a]atrim=start={decalage if voix_wav else 0:.2f},asetpts=PTS-STARTPTS,apad,atrim=0:{duree_totale:.2f},afade=t=out:st={duree_totale - 1:.2f}:d=1[a]",
                       "-map", "1:v", "-map", "[a]"]
        else:
            entrees += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            filtres = ["-map", "1:v", "-map", "0:a", "-shortest"]
        sortie = DOSSIER / f"{b['sujet_id']}.mp4"
        commande = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *entrees,
                    "-f", "concat", "-safe", "0", "-i", str(tmp / "images.txt"), *filtres,
                    "-r", str(c["fps"]), "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-t", f"{duree_totale:.2f}",
                    "-movflags", "+faststart", str(sortie)]
        r = subprocess.run(commande, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"ffmpeg : {r.stderr[-300:]}")
    b["duree"] = round(duree_totale, 1)
    b["voix_off"] = bool(voix_wav)
    return str(sortie.relative_to(ROOT))


def produire():
    faits = 0
    for fichier in sorted((DATA / "redaction").glob("*.json")):
        brouillons = lire_json(fichier, [])
        a_faire = [b for b in brouillons if b["statut"] == "a_valider" and not b.get("telegram")
                   and not (b.get("video") and (ROOT / b["video"]).exists())]
        for b in a_faire:
            try:
                b["video"] = fabriquer(b)
                faits += 1
                print(f"[reel] ✓ {b['duree']} s{' (sans voix)' if not b['voix_off'] else ''} · {b['accroche'][:60]}")
            except Exception as ex:
                print(f"[reel] ✗ {b['accroche'][:60]} : {ex}")
            ecrire_json(brouillons, fichier)
    print(f"[reel] {faits} vidéos montées -> data/videos/")
    return faits


if __name__ == "__main__":
    produire()
