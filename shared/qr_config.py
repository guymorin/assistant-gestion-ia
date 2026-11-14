"""Configuration Q&R par module.

Definit `QRModuleConfig` (dataclass figée) et le registre `QR_MODULES`
source de vérité pour tous les modules Q&R (RH, Finances, Juridique, Marketing).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .info import InfoItem

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class QRModuleConfig:
    """Configuration figée d'un module Q&R.

    Chaque module déclare son identité, ses chemins d'ingestion/Chroma,
    son modèle par défaut et les clés de session namespacées.
    """

    id: str
    """Identifiant court du module (clé dans QR_MODULES)."""

    label: str
    """Label affiché dans l'interface (ex. "RH", "Finances", "Juridique", "Marketing")."""

    chroma_dir: str
    """Chemin relatif ou absolu vers la base ChromaDB dédiée."""

    pdf_dir: str
    """Chemin relatif vers les PDFs du module (pour ingestion)."""

    urls_file: str
    """Chemin relatif vers le fichier d'URLs web du module."""

    model_env_var: str | None = None
    """Variable d'environnement optionnelle pour surcharger le modèle LLM."""

    default_model: str = "llama3.2"
    """Modèle LLM par défaut si la variable d'environnement n'est pas définie."""

    state_prefix: str = "qr"
    """Préfixe pour les clés d'état session (messages, pièces jointes)."""


def _env(name: str, default: str | None = None) -> str | None:
    """Lit une variable d'environnement; renvoie la valeur ou ``default``."""
    val = os.environ.get(name)
    return val if val else default


# ---------------------------------------------------------------------------
# Registre des configurations Q&R par identifiant de module
# ---------------------------------------------------------------------------

QR_MODULES: Dict[str, QRModuleConfig] = {
    "rh": QRModuleConfig(
        id="rh",
        label="RH",
        chroma_dir="./chroma_db/rh",
        pdf_dir="./Ingestion/RH",
        urls_file="./Ingestion/RH/RH-web.txt",
        model_env_var="ASSISTANT_DRH_MODEL",
        default_model="llama3.2",
        state_prefix="rh",
    ),
    "finances": QRModuleConfig(
        id="finances",
        label="Finances",
        chroma_dir="./chroma_db/finances",
        pdf_dir="./Ingestion/Finances",
        urls_file="./Ingestion/Finances/Finances-web.txt",
        model_env_var="ASSISTANT_FINANCES_MODEL",
        default_model="llama3.2",
        state_prefix="fin",
    ),
    "juridique": QRModuleConfig(
        id="juridique",
        label="Juridique",
        chroma_dir="./chroma_db/juridique",
        pdf_dir="./Ingestion/Juridique",
        urls_file="./Ingestion/Juridique/Juridique-web.txt",
        model_env_var="ASSISTANT_JURIDIQUE_MODEL",
        default_model="llama3.2",
        state_prefix="jur",
    ),
    "marketing": QRModuleConfig(
        id="marketing",
        label="Marketing",
        chroma_dir="./chroma_db/marketing",
        pdf_dir="./Ingestion/Marketing",
        urls_file="./Ingestion/Marketing/Marketing-web.txt",
        model_env_var="ASSISTANT_MARKETING_MODEL",
        default_model="llama3.2",
        state_prefix="mar",
    ),
}


def get_module_config(module: str) -> QRModuleConfig:
    """Retourne la configuration figée pour un module donné."""
    if module not in QR_MODULES:
        raise ValueError(f"Module Q&R inconnu : {module}")
    return QR_MODULES[module]


def get_all_configs() -> Dict[str, QRModuleConfig]:
    """Retourne toutes les configurations de modules."""
    return dict(QR_MODULES)


def list_modules() -> list[str]:
    """Retourne la liste des identifiants de modules enregistrés."""
    return list(QR_MODULES.keys())


# Module-level constants (importables depuis shared.qr_config)
LANGUES: dict[str, dict[str, str]] = {
    "fr": {
        "nom": "Français",
        "consigne": (
            "Reponds en francais, de facon claire, concise et structuree. "
            "Redige toute la reponse dans cette langue, y compris les titres."
        ),
    },
    "en": {
        "nom": "English",
        "consigne": (
            "Answer in English, clearly, concisely and in a structured way. "
            "Write the whole answer in that language, headings included."
        ),
    },
    "ko": {
        "nom": "한국어",
        "consigne": (
            "한국어로 명확하고 간결하게, 체계적으로 답하세요. "
            "제목을 포함한 답변 전체를 한국어로 작성하세요."
        ),
    },
}

# ---------------------------------------------------------------------------
# Helpers de compatibilité : exposer les anciens noms importés par les modules
# existants (rh.logic, finances.logic) via le cœur partagé.
# ---------------------------------------------------------------------------

def rh_config() -> QRModuleConfig:
    """Retourne la config RH pour compatibilité avec le code existant."""
    return QR_MODULES["rh"]


def finances_config() -> QRModuleConfig:
    """Retourne la config Finances pour compatibilité avec le code existant."""
    return QR_MODULES["finances"]


def juridique_config() -> QRModuleConfig:
    """Retourne la config Juridique pour compatibilité avec le code existant."""
    return QR_MODULES["juridique"]


def marketing_config() -> QRModuleConfig:
    """Retourne la config Marketing pour compatibilité avec le code existant."""
    return QR_MODULES["marketing"]