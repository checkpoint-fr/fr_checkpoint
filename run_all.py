"""Point d'entrée de GitHub Actions : pendant une fenêtre de validation, surveille Telegram en continu ;
sinon, un seul passage. Voir config.yaml → planning et agents/planificateur.py. Ne pas lancer sur le Mac."""
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

from agents import planificateur  # noqa: E402

if __name__ == "__main__":
    planificateur.surveiller()
