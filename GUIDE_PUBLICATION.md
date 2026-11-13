# Brancher Instagram (à faire une seule fois)

Trois choses à créer, environ 30 minutes. Aucune page Facebook n'est nécessaire.

**Adresse e-mail du projet, à utiliser partout :** `fr.checkpoint.fr@gmail.com`
Les clés vont dans le fichier `.env` (jamais dans le chat).

## 1. Le compte Instagram @fr_checkpoint

1. Dans l’appli Instagram : compte **@fr_checkpoint** (renommé depuis @checkpoint.fr le 13 nov. 2026) (photo de profil : le drapeau bleu).
2. Profil → menu ☰ → **Paramètres et activité** → **Type de compte et outils** →
   **Passer à un compte professionnel** → choisir **Créateur** → catégorie « Média/Actualités » ou « Jeux vidéo ».
3. Vérifier que le compte est **public**.

## 2. L'application Meta (autorisation de publier)

1. Aller sur https://developers.facebook.com/apps (se connecter avec Facebook, puis accepter
   de devenir développeur si c'est demandé).
2. Créer le **portefeuille business** (obligatoire) sur https://business.facebook.com/overview →
   **Créer un compte** → nom de l'entreprise `checkpoint.fr`, ton prénom et nom,
   e-mail `fr.checkpoint.fr@gmail.com` → confirmer le mail reçu.
   (Un compte Facebook tout neuf doit parfois attendre avant de pouvoir le faire.)
3. **Créer une app** → nom `checkpoint publication`, e-mail `fr.checkpoint.fr@gmail.com` →
   cas d'usage **Gérer les messages et le contenu sur Instagram** → portefeuille `checkpoint.fr`.
4. Ouvrir le cas d'usage (**Personnaliser**) → **Configuration de l'API avec connexion Instagram** →
   vérifier `instagram_business_basic` et `instagram_business_content_publish` → **Générer des jetons d'accès** →
   **Ajouter un compte** → se connecter avec @fr_checkpoint → accepter les autorisations.
5. Cliquer **Générer le jeton** à côté du compte → copier le jeton.
6. Dans `.env` : `INSTAGRAM_ACCESS_TOKEN=` suivi du jeton.

Le jeton dure 60 jours ; l'agent le renouvellera (prévu lors de l'automatisation).
Si Meta demande une « vérification d'entreprise » ou un « examen de l'app », me le dire avant d'aller plus loin.

## 3. Le dépôt GitHub qui héberge les images

Instagram ne prend que des images en ligne : l'agent les dépose quelques minutes sur GitHub,
publie, puis les supprime.

1. Créer un compte sur https://github.com avec `fr.checkpoint.fr@gmail.com`.
2. **New repository** → nom `checkpoint-medias` → **Public** → cocher **Add a README** → Create.
3. Photo de profil → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token** :
   - nom : `checkpoint-medias`, expiration : 1 an ;
   - **Repository access** : *Only select repositories* → `checkpoint-medias` ;
   - **Permissions** → *Repository permissions* → **Contents : Read and write**.
4. Copier le jeton, puis dans `.env` :
   - `MEDIAS_TOKEN=` suivi du jeton ;
   - `MEDIAS_DEPOT=` ton pseudo GitHub + `/checkpoint-medias` (ex. `monpseudo/checkpoint-medias`).

## 4. Prévenir Claude

Je lance alors la première vraie publication d'un carrousel validé et je vérifie le post.
