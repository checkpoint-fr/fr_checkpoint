"""Agent 4 – Visuel : dessine le carrousel Instagram de chaque brouillon à valider.

Entrée : data/redaction/*.json (brouillons « a_valider » sans images).
Sortie : data/visuels/<sujet_id>/01.jpg … (couverture, un visuel par point, conclusion + sources),
chemins ajoutés au brouillon dans le champ « images ». Aucune image d'autrui : tout est dessiné ici.
"""
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from common.config import DATA, ROOT, load_config
from common.io import ecrire_json, lire_json

DOSSIER = DATA / "visuels"
M = 90                                   # marge extérieure


def cfg():
    return load_config()["visuel"]


@lru_cache(maxsize=None)
def police(nature, taille, graisse=400):
    """nature : « titre » (Archivo Black) ou « texte » (Archivo variable, graisse 100 à 900)."""
    f = ImageFont.truetype(str(ROOT / cfg()["polices"][nature]), taille)
    if nature == "texte":
        f.set_variation_by_axes([graisse, 100])          # axes : graisse, chasse
    return f


def couleur(nom):
    return cfg()["couleurs"][nom]


# ---------- texte ----------

def typo(texte):
    """Typographie française : apostrophe courbe, espaces insécables (ponctuation, « », initiales, unités)."""
    t = " ".join(texte.split()).replace("'", "’")
    t = re.sub(r" ([:;!?»])", "\u00a0\\1", t)
    t = re.sub(r"\b([A-Z])\. (?=[A-Z])", "\\1.\u00a0", t)            # initiale + nom : « Jordan A. Mun »
    t = re.sub(r"(\d) (?=[%€$]|(Go|Mo|To|Ko|h|min|s|ans?|jours?|mois|heures?|fps|Hz|millions?|milliards?|euros?|dollars?)\b)",
               "\\1\u00a0", t)                                        # nombre + unité : « 210 Go »
    return re.sub(r"« ", "«\u00a0", t)


def couper(texte, f, largeur):
    """Coupe en lignes sans dépasser `largeur`, et sans laisser un mot seul sur la dernière ligne.
    Les espaces insécables (typo) ne sont jamais des points de coupe."""
    lignes, courante = [], ""
    for mot in typo(texte).split(" "):
        essai = f"{courante} {mot}".strip()
        if courante and f.getlength(essai) > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    if courante:
        lignes.append(courante)
    if len(lignes) > 1 and " " not in lignes[-1]:
        avant = lignes[-2].rsplit(" ", 1)
        if len(avant) == 2 and f.getlength(f"{avant[1]} {lignes[-1]}") <= largeur:
            lignes[-2], lignes[-1] = avant[0], f"{avant[1]} {lignes[-1]}"
    return lignes


def ajuster(texte, nature, tailles, largeur, hauteur, interligne, graisse=400, max_lignes=99):
    """Plus grande taille de `tailles` pour laquelle le texte tient dans le cadre."""
    for t in tailles:
        f = police(nature, t, graisse)
        lignes = couper(texte, f, largeur)
        tient = all(f.getlength(ligne) <= largeur for ligne in lignes)    # un mot très long déborderait
        if tient and len(lignes) <= max_lignes and len(lignes) * t * interligne <= hauteur:
            return f, lignes, round(t * interligne)
    return f, lignes, round(t * interligne)


def ecrire(d, x, y, lignes, f, pas, teinte):
    for i, ligne in enumerate(lignes):
        d.text((x, y + i * pas), ligne, font=f, fill=teinte)
    return y + len(lignes) * pas


def espace(d, x, y, texte, f, teinte, ecart):
    """Texte en capitales espacées (Pillow n'a pas d'interlettrage)."""
    for c in texte:
        d.text((x, y), c, font=f, fill=teinte)
        x += f.getlength(c) + ecart
    return x - ecart


def largeur_espacee(texte, f, ecart):
    return sum(f.getlength(c) for c in texte) + ecart * (len(texte) - 1)


# ---------- éléments communs ----------

def progression(d, n, total):
    c = cfg()
    y, l = c["hauteur"] - 96, c["largeur"] - 2 * M
    d.rounded_rectangle([M, y, M + l, y + 6], 3, fill=couleur("carte"))
    d.rounded_rectangle([M, y, M + l * n / total, y + 6], 3, fill=couleur("accent"))


def pastille(d, x, y, texte, plein):
    f = police("texte", 28, 800)
    ecart, h, pad = 3, 58, 28
    l = largeur_espacee(texte, f, ecart) + 2 * pad
    if plein:
        d.rounded_rectangle([x, y, x + l, y + h], h // 2, fill=couleur("accent"))
    else:
        d.rounded_rectangle([x, y, x + l, y + h], h // 2, outline=couleur("accent"), width=3)
    haut, bas = f.getbbox("OFFICIELRUMÉ")[1], f.getbbox("OFFICIEL")[3]   # centrage sur l'encre
    espace(d, x + pad, y + (h - (bas - haut)) / 2 - haut, texte,
           f, couleur("fond") if plein else couleur("accent"), ecart)


def drapeau(d, x, y, h):
    """Logo : mât + fanion, le « checkpoint »."""
    d.rectangle([x, y, x + h * 0.12, y + h], fill=couleur("accent"))
    d.polygon([(x + h * 0.12, y), (x + h * 0.75, y + h * 0.27), (x + h * 0.12, y + h * 0.55)], fill=couleur("accent"))


def icone(d, nom, x, y, s):
    """Pictogrammes dessinés (aucune police d'emoji) : j'aime, commentaire, partage, enregistrement."""
    a = couleur("accent")
    if nom == "coeur":
        r = s * 0.27
        d.ellipse([x + s * 0.27 - r, y + s * 0.32 - r, x + s * 0.27 + r, y + s * 0.32 + r], fill=a)
        d.ellipse([x + s * 0.73 - r, y + s * 0.32 - r, x + s * 0.73 + r, y + s * 0.32 + r], fill=a)
        d.polygon([(x + s * 0.02, y + s * 0.42), (x + s * 0.98, y + s * 0.42), (x + s * 0.5, y + s * 0.95)], fill=a)
    elif nom == "bulle":
        d.ellipse([x, y + s * 0.05, x + s, y + s * 0.8], fill=a)
        d.polygon([(x + s * 0.18, y + s * 0.62), (x + s * 0.08, y + s), (x + s * 0.48, y + s * 0.76)], fill=a)
    elif nom == "partage":
        d.polygon([(x, y + s * 0.42), (x + s, y + s * 0.02), (x + s * 0.58, y + s), (x + s * 0.44, y + s * 0.58)], fill=a)
    elif nom == "signet":
        d.polygon([(x + s * 0.15, y), (x + s * 0.85, y), (x + s * 0.85, y + s),
                   (x + s * 0.5, y + s * 0.72), (x + s * 0.15, y + s)], fill=a)


# ---------- images ----------

def toile():
    c = cfg()
    img = Image.new("RGB", (c["largeur"], c["hauteur"]), couleur("fond"))
    return img, ImageDraw.Draw(img)


def couverture(b, total):
    c = cfg()
    img, d = toile()
    statut = b.get("statut_info", "rumeur")
    pastille(d, M, 170, c["statuts"].get(statut, statut.upper()), plein=statut == "officiel")
    largeur = c["largeur"] - 2 * M
    f, lignes, pas = ajuster(b["accroche"], "titre", range(112, 60, -4), largeur, 560, 1.1, max_lignes=5)
    y = ecrire(d, M, 280, lignes, f, pas, couleur("texte"))
    d.rectangle([M, y + 30, M + 140, y + 40], fill=couleur("accent"))
    f2, lignes2, pas2 = ajuster(b["sous_titre"], "texte", range(44, 30, -2), largeur, 240, 1.35, 400)
    ecrire(d, M, y + 80, lignes2, f2, pas2, couleur("secondaire"))
    progression(d, 1, total)
    return img


def point(p, n, total):
    c = cfg()
    img, d = toile()
    largeur = c["largeur"] - 2 * M
    d.text((M - 6, 170), f"{n - 1:02d}", font=police("titre", 190), fill=couleur("accent"))
    f, lignes, pas = ajuster(p["titre"], "titre", range(84, 44, -4), largeur, 290, 1.12, max_lignes=3)
    y = ecrire(d, M, 440, lignes, f, pas, couleur("texte"))
    f2, lignes2, pas2 = ajuster(p["texte"], "texte", range(60, 32, -2), largeur,
                                c["hauteur"] - 200 - (y + 50), 1.42, 400)
    ecrire(d, M, y + 50, lignes2, f2, pas2, "#D5DBE6")
    progression(d, n, total)
    return img


def conclusion(b, total):
    c = cfg()
    img, d = toile()
    largeur = c["largeur"] - 2 * M
    espace(d, M, 150, "À RETENIR", police("texte", 30, 800), couleur("accent"), 4)
    f, lignes, pas = ajuster(b["a_retenir"], "texte", range(84, 44, -2), largeur, 820, 1.24, 700)
    ecrire(d, M, 220, lignes, f, pas, couleur("texte"))
    progression(d, total - 1, total)
    return img


def appel(total):
    """Dernière image : inviter à aimer, commenter, partager, enregistrer et s'abonner."""
    c, a = cfg(), cfg()["appel"]
    img, d = toile()
    largeur = c["largeur"] - 2 * M
    drapeau(d, M, 150, 100)
    f, lignes, pas = ajuster(a["titre"], "titre", range(96, 56, -4), largeur, 260, 1.1, max_lignes=2)
    y = ecrire(d, M, 300, lignes, f, pas, couleur("texte")) + 70
    ft = police("texte", 42, 600)
    for nom, texte in zip(("coeur", "bulle", "partage", "signet"), a["actions"]):
        icone(d, nom, M, y, 56)
        d.text((M + 96, y + 28), typo(texte), font=ft, fill=couleur("texte"), anchor="lm")
        y += 108
    fs = police("titre", 58)
    yb = c["hauteur"] - 280
    suivre = a["suivre"] + " "
    d.text((M, yb), suivre, font=fs, fill=couleur("texte"))
    d.text((M + fs.getlength(suivre), yb), load_config()["compte"]["nom"], font=fs, fill=couleur("accent"))
    d.text((M, yb + 84), typo(a["sous_titre"]), font=police("texte", 36, 400), fill=couleur("secondaire"))
    progression(d, total, total)
    return img


def dessiner(b):
    total = len(b["points"]) + 3
    images = [couverture(b, total)] + [point(p, i + 2, total) for i, p in enumerate(b["points"])] \
        + [conclusion(b, total), appel(total)]
    dossier = DOSSIER / b["sujet_id"]
    dossier.mkdir(parents=True, exist_ok=True)
    chemins = []
    for i, img in enumerate(images, 1):
        chemin = dossier / f"{i:02d}.jpg"
        img.save(chemin, "JPEG", quality=cfg()["qualite_jpeg"], optimize=True)
        chemins.append(str(chemin.relative_to(ROOT)))
    return chemins


def produire():
    faits = 0
    for fichier in sorted((DATA / "redaction").glob("*.json")):
        brouillons = lire_json(fichier, [])
        a_faire = [b for b in brouillons if b["statut"] == "a_valider"
                   and not all((ROOT / p).exists() for p in b.get("images") or ["?"])]
        for b in a_faire:
            b["images"] = dessiner(b)
            faits += 1
            print(f"[visuel] ✓ {len(b['images'])} images · {b['accroche'][:70]}")
        if a_faire:
            ecrire_json(brouillons, fichier)
    print(f"[visuel] {faits} carrousels dessinés -> data/visuels/")
    return faits


if __name__ == "__main__":
    produire()
