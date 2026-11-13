# Feuille de route

| # | Agent | Rôle | État |
|---|---|---|---|
| 1 | Veille | Lit 15 flux RSS (presse FR/EN, PlayStation, Xbox, Reddit), garde les articles récents jamais vus | ✅ fait |
| 2 | Tri | Écarte guides et promos, regroupe les articles d'une même info (FR + EN), classe par importance (nb de sources, officiel, Reddit, fraîcheur), propose 5 sujets jamais proposés depuis 3 jours | ✅ fait |
| 3 | Rédacteur | Lit 3 articles par sujet, écrit le carrousel (accroche, 3-4 points, conclusion) et la légende en français, au conditionnel si rumeur ; écarte doublons et hors-sujet ; sources et mention IA ajoutées par le code (Gemini gratuit) | ✅ fait, testé : 5 brouillons le 12 nov. |
| 4 | Visuel | Carrousel 1080×1350 en JPEG : couverture (statut officiel/confirmé/rumeur), une image par point, conclusion + sources, image finale « like, commente, partage, enregistre, suis @fr_checkpoint » ; sans en-tête, barre de progression en bas. Police Archivo (libre), bleu électrique #4D8DFF, typographie française | ✅ fait |
| 5 | Validation | @checkpointfr_validation_bot : album + légende + liens des sources + boutons ✅ Publier / ❌ Rejeter ; seuls tes clics comptent ; sans réponse en 24 h, le brouillon expire | ✅ fait |
| 6 | Publication | Carrousels validés publiés via l'API Instagram (connexion Instagram, sans page Facebook) ; images déposées quelques minutes sur un dépôt GitHub public puis supprimées ; 1 post par passage, 8 h–23 h, 1 h 30 d'écart ; lien du post envoyé sur Telegram | ✅ fait : 1er post publié le 13 nov. 2026 (https://www.instagram.com/p/DfrdXJRCFsK/) |
| — | Planning | 2 posts/jour depuis le 14 nov. : actu (recherche 10 h 30, post 12 h 30, 3 propositions) et GTA 6 (recherche 18 h, post 19 h 30, 2 propositions) ; rappel Telegram si rien n'est validé, abandon 2 h 30 après l'heure prévue (agents/planificateur.py, lancé toutes les 10 min par run_all.py) | ✅ fait, testé sur une journée simulée |
| 7 | Lien en bio | Page GitHub Pages avec les liens d'affiliation | à faire |
| — | Automatisation | GitHub Actions toutes les quelques heures | à faire |

## Comptes à créer (par toi)

- Compte Instagram **professionnel** `@fr_checkpoint` (pas besoin de page Facebook) : voir GUIDE_PUBLICATION.md
- ~~Application développeur Meta~~ faite (connexion unifiée, jeton utilisateur système sans expiration) · ~~dépôt GitHub `checkpoint-fr/checkpoint-medias`~~ fait, testé
- ~~Bot Telegram via @BotFather~~ fait
- ~~Clé Gemini~~ et ~~clé Groq~~ faites
- Compte GitHub (dépôt privé)
- Identité visuelle du compte Instagram et une certaine mise en page cohérente pour les postes et réels

## Points d'attention

- Reddit limite les requêtes et bloque souvent les serveurs GitHub : la source peut échouer sans gêner le reste.
- Ne jamais republier un article ni une image : seulement des synthèses originales avec le lien de la source.
- Gemini gratuit sature souvent (erreurs 503) : un sujet non rédigé est repris au passage suivant. Une clé Groq gratuite dans `.env` sert de secours.
- Chaque brouillon garde ce que l'IA a lu dans `data/redaction/entrees/<sujet_id>.json` pour vérifier un fait avant de valider.
- Jeton `MEDIAS_TOKEN` expire vers le **12 novembre 2027** (créé le 12 nov. 2026, 1 an) : le recréer sur GitHub (compte checkpoint-fr) et remplacer la valeur dans `.env`.
- macOS interdit aux tâches planifiées du Mac (launchd) de lire le Bureau : l'automatisation passe par GitHub Actions (ou un dossier hors du Bureau).
