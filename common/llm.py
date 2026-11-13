"""Appel LLM avec bascule automatique Gemini -> Gemini léger -> Groq. Sortie JSON garantie ou None."""
import json
import re
import time

import requests

from common.config import env, load_config


def _gemini(system, user, temperature, model=None):
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY absent")
    model = model or load_config()["llm"]["modele_gemini"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(system, user, temperature):
    key = env("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY absent")
    model = load_config()["llm"]["modele_groq"]
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini_leger(system, user, temperature):
    return _gemini(system, user, temperature, load_config()["llm"]["modele_gemini_leger"])


FOURNISSEURS = {"gemini": _gemini, "gemini_leger": _gemini_leger, "groq": _groq}


def _parse_json(texte):
    texte = texte.strip()
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte)
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texte, re.S)
        return json.loads(m.group(0)) if m else None


def disponible():
    return bool(env("GEMINI_API_KEY") or env("GROQ_API_KEY"))


def llm_json(system, user, temperature=0.2, essais=2):
    """Essaie chaque fournisseur de config.yaml → llm.fournisseurs, dans l'ordre."""
    cfg = load_config()["llm"]
    ordre = cfg["fournisseurs"]
    for nom in ordre:
        fn = FOURNISSEURS[nom]
        for i in range(essais):
            try:
                texte = fn(system, user, temperature)
                data = _parse_json(texte)
                if data is not None:
                    print(f"  [llm] réponse via {nom}")
                    return data
                print(f"  [llm] {nom} : JSON invalide, nouvel essai")
            except Exception as e:  # noqa: BLE001
                print(f"  [llm] {nom} indisponible ({e.__class__.__name__}: {str(e)[:120]})")
                if "absent" in str(e):
                    break
                time.sleep(10 * (i + 1))      # 503 / quota : Google se libère vite
    print("  [llm] aucun fournisseur : mode dégradé sans IA")
    return None
