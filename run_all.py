"""Point d'entrée lancé toutes les 10 minutes (Mac ou GitHub Actions) : le planificateur fait
ce que l'heure demande. Voir config.yaml → planning et agents/planificateur.py."""
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

from agents import planificateur  # noqa: E402

if __name__ == "__main__":
    planificateur.lancer()
