#!/bin/zsh
# Double-clic : envoie sur GitHub tes modifications de config.yaml (et des consignes / voix),
# pour que le planning automatique les prenne en compte dès son prochain passage.
cd "$(dirname "$0")" || exit 1
T=$(grep "^GITHUB_DEPLOI_TOKEN=" .env | cut -d= -f2- | tr -d ' "')
A="http.extraHeader=Authorization: Basic $(printf 'x-access-token:%s' "$T" | base64)"
echo "Envoi des réglages de fr_checkpoint sur GitHub…"
git add config.yaml agents/prompts assets/voix
if git diff --cached --quiet; then
  echo "Aucun réglage modifié."
else
  git commit -q -m "Réglages modifiés sur le Mac"
fi
if git -c "$A" pull -q --rebase origin main && git -c "$A" push -q origin main; then
  echo "✅ C'est envoyé : pris en compte au prochain passage automatique."
else
  git rebase --abort 2>/dev/null
  echo "❌ L'envoi a échoué : demande à Claude de regarder."
fi
echo
read -k1 "?Appuie sur une touche pour fermer cette fenêtre."
