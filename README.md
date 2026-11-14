# @fr_checkpoint — veille jeux vidéo sur Instagram

Des agents IA lisent chaque jour l'actualité du jeu vidéo, écrivent des synthèses originales
(avec leurs sources), fabriquent les carrousels et les publient sur Instagram après ta validation
en un clic. Tout est gratuit : GitHub Actions + IA en version gratuite.

Voir [FEUILLE_DE_ROUTE.md](FEUILLE_DE_ROUTE.md) pour les étapes.

## Planning

2 posts par jour (heure de Paris) réglés dans `config.yaml` → `planning` : actu jeu vidéo (recherche 10 h 30, publication 12 h 30) et GTA 6 (recherche 18 h, publication 19 h 30). `run_all.py` tourne sur GitHub Actions : pendant les fenêtres de validation, il surveille Telegram en continu (clics appliqués en quelques secondes) ; sinon, un passage par demi-heure.

## Lancer les agents

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_all.py
```

| Agent | Lancer seul | Résultat |
|---|---|---|
| 1 Veille | `.venv/bin/python -m agents.veille` | `data/veille/<date>.json` (tous les articles récents) |
| 2 Tri | `.venv/bin/python -m agents.tri` | `data/tri/<date>.json` (les sujets retenus et leurs articles) |
| 3 Rédacteur | `.venv/bin/python -m agents.redacteur` | `data/redaction/<date>.json` (brouillons à valider) |
| 4 Visuel | `.venv/bin/python -m agents.visuel` | `data/visuels/<sujet_id>/01.jpg…` (carrousel) |
| 5 Validation | `.venv/bin/python -m agents.validation` | carrousels envoyés sur Telegram, tes clics appliqués aux brouillons |
| 6 Publication | `.venv/bin/python -m agents.publication` (`--essai` : sans rien envoyer) | posts Instagram, lien envoyé sur Telegram |

Le rédacteur a besoin de `GEMINI_API_KEY` dans `.env` (clé gratuite : https://aistudio.google.com/apikey).
Sa consigne d'écriture est dans `agents/prompts/redacteur.md`.

Tout se règle dans `config.yaml` : sources, nombre de sujets, poids du classement, exclusions.
`data/tri/proposes.json` mémorise les sujets déjà proposés : le supprimer pour tout reproposer.
