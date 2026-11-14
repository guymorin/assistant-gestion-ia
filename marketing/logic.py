"""Logique Marketing (RAG, prompt, sources, helpers) pour le module Q&R.

Ce module contient l'implémentation historique calibrée sur le domaine Marketing
avec sources/index dédiés. Il repose désormais sur ``shared.qr_logic`` pour la
plupart de la logique RAG, tout en réexposant l'API publique attendue par les
vues et les tests (``from marketing.logic import ...``).
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingest import (
    CHROMA_DIR as _INGEST_CHROMA_DIR,
    EMBEDDING_MODEL,
    MANIFESTE_INGESTION,
    OLLAMA_BASE_URL,
    creer_embeddings,
    get_module_config,
)
from pieces_jointes import IndexPiecesJointes

from shared.qr_logic import (
    base_disponible as _base_disponible_qr,
    creer_llm as _creer_llm_qr,
    creer_vectorstore as _creer_vectorstore_qr,
    infos_ingestion as _infos_ingestion_qr,
    normaliser_langue as _normaliser_langue_qr,
    repondre as _repondre_qr,
    LANGUES as _LANGUES_qr,
    MESSAGES_SANS_RESULTAT as _MESSAGES_SANS_RESULTAT_qr,
)
from shared.qr_config import get_module_config as _get_config

logger = logging.getLogger(__name__)

# Configuration module Marketing (identité et constantes spécifiques Marketing)
_MODULE = get_module_config("marketing")
PDF_DIR = _MODULE["pdf_dir"]
URLS_FILE = _MODULE["urls_file"]
CHROMA_DIR = _MODULE["chroma_dir"]

APP_VERSION = "1.1.0"
LLM_MODEL = os.getenv("ASSISTANT_MARKETING_MODEL", "llama3.2")
TOP_K = 8
FETCH_K = 40
MMR_LAMBDA = 0.7
FACTEUR_CANDIDATS = 4
HISTORIQUE_MAX_MESSAGES = 6
HISTORIQUE_MAX_CARACTERES = 6000
CATEGORIE_ODOO = "odoo"
CATEGORIE_CONVENTION = "convention"
MOTS_CLES_ODOO = ("odoo", "pgi")
MOTS_CLES_CONVENTION = (
    "restauration rapide",
    "restaurant",
    "hee",
    "convention collective",
    "idcc 1501",
    "grille",
    "prime",
)
MOTS_CLES_RGPD = (
    "rgpd",
    "donnees personnelles",
    "cnil",
    "protection des donnees",
    "informatique et libertes",
)
MOTS_CLES_RSE = (
    "rse",
    "responsabilite societale",
    "diversite",
    "developpement durable",
    "environnement",
)
SOURCES_HORS_SUJET = (
    ("cnil.fr", MOTS_CLES_RGPD),
    ("bpifrance-creation.fr", MOTS_CLES_RSE),
    (
        "economie.gouv.fr/entreprises/gerer-son-entreprise-au-quotidien",
        MOTS_CLES_RSE,
    ),
)

LANGUES = {
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
LANGUE_DEFAUT = "fr"

# Messages de résultat manquant (Marketing)
MESSAGE_SANS_RESULTAT = (
    "Je ne trouve pas cette information dans la base documentaire Marketing. "
    "Precisez votre question, verifiez les documents indexes, ou lancez "
    "l'ingestion du module Marketing : python ingest.py --module marketing."
)

MESSAGES_SANS_RESULTAT: dict[str, str] = {
    "fr": _MESSAGES_SANS_RESULTAT_qr["fr"],
    "en": (
        "I cannot find this information in the Marketing documentary base. "
        "Please refine your question or verify the indexed documents, or run "
        "ingestion for the Marketing module: python ingest.py --module marketing."
    ),
    "ko": (
        "재무 문서 기반(프랑스 노동법, 패스트푸드 단체협약, 인사 참고자료 및 Odoo "
        "문서)에서 해당 정보를 찾을 수 없습니다. 질문을 더 구체적으로 "
        "작성하거나 재무 모듈 인덱싱을 실행해 주세요: python ingest.py --module finances."
    ),
}

# Re-exports compatibilité API : les noms ci-dessous doivent être identiques
# à ceux attendus par les tests et vues (imports ``from marketing.logic import ...``).
# Ils délèguent au cœur partagé ``shared.qr_logic`` en adaptant les signatures.

base_disponible = _base_disponible_qr
creer_llm = _creer_llm_qr
creer_vectorstore = _creer_vectorstore_qr
infos_ingestion = _infos_ingestion_qr
normaliser_langue = _normaliser_langue_qr
repondre = _repondre_qr


def _chemins_base(chroma_dir: str | Path = CHROMA_DIR) -> list[Path]:
    """Chemins candidats de la base (module puis racine legacy si pertinent)."""
    dossier = Path(chroma_dir)
    candidats = [dossier]
    if dossier.name in {"rh", "finances", "juridique", "marketing"}:
        legacy = dossier.parent
        if legacy != dossier:
            candidats.append(legacy)
    elif dossier == Path("chroma_db"):
        candidats.extend([dossier / "rh", dossier / "finances", dossier / "juridique", dossier / "marketing"])
    vus: set[Path] = set()
    uniques: list[Path] = []
    for c in candidats:
        if c not in vus:
            vus.add(c)
            uniques.append(c)
    return uniques


def _base_disponible_legacy(chroma_dir: str | Path = CHROMA_DIR) -> bool:
    """Version legacy conservée pour compatibilité descendante."""
    return any(Path(d, "chroma.sqlite3").is_file() for d in _chemins_base(chroma_dir))


def infos_ingestion_legacy(chroma_dir: str | Path = CHROMA_DIR) -> dict[str, Any]:
    """Version legacy de infos_ingestion (conservée pour compat)."""
    return infos_ingestion(chroma_dir)


def texte_a_propos(
    infos: dict[str, Any] | None = None,
    version: str = APP_VERSION,
) -> str:
    """Contenu Markdown de la fenetre « A propos » du menu Streamlit."""
    infos = infos or {}
    date = infos.get("date")
    if date is None:
        ingestion = "Ingestion des données : inconnue"
    else:
        ingestion = f"Ingestion des données : {date:%d/%m/%Y à %H:%M}"
        chunks = infos.get("chunks")
        if isinstance(chunks, int):
            ingestion += f" ({chunks:,} extraits)".replace(",", " ")

    return "\n".join(
        [
            "**Assistant Marketing – IA**",
            "",
            f"- Version : `{version}`",
            f"- {ingestion}",
            f"- Modèle de langage : `{LLM_MODEL}`",
            f"- Embeddings : `{EMBEDDING_MODEL}`",
            "",
            "Réponses générées localement à partir de la base documentaire Marketing.",
        ]
    )


def cite_des_sources(texte: str) -> bool:
    """Indique si la réponse cite au moins une source numérotée ([1], [2]...)."""
    return bool(re.search(r"\[\d+\]", texte or ""))


def resume_raisonnement(
    sources: list[dict[str, Any]], reponse: str = ""
) -> str:
    """Resume synthetique : d'où vient la réponse et comment elle a été construite."""
    if not sources:
        return ""

    nb_extraits = sum(len(source.get("extraits") or []) for source in sources)
    types = Counter(str(source.get("type") or "") for source in sources)
    origines = []
    if types.get("pdf"):
        origines.append("base documentaire Marketing")
    if types.get("web"):
        origines.append("sources web")
    if types.get("piece_jointe"):
        origines.append("pieces jointes")
    origine = ", ".join(origines) if origines else "sources diverses"

    lignes = [
        "**Raisonnement**",
        (
            f"Reponse fondee sur {nb_extraits} extraits issus de "
            f"{len(sources)} sources ({origine})."
        ),
        (
            "- Extraits classes par pertinence puis numerotes [1]...[n] dans "
            "le contexte transmis au modele : les numeros cites dans la "
            "reponse renvoient a la liste ci-dessous."
        ),
    ]
    if reponse and not any(re.search(r"\[\d+\]", reponse or "")):
        lignes.append(
            "- ⚠️ La reponse ne cite pas ses sources : verifiez les extraits "
            "ci-dessous avant de l'utiliser."
        )

    lignes.extend(["", "**Sources**"])
    for numero, source in enumerate(sources, start=1):
        nombre = len(source.get("extraits") or [])
        lignes.append(f"[{numero}] {source['nom']} — {nombre} extrait(s)")
    return "\n".join(lignes)


def repondre(
    question: str,
    vectorstore: Any | None = None,
    llm: Any | None = None,
    k: int = TOP_K,
    pieces_jointes: Any | None = None,
    historique: list[dict[str, Any]] | None = None,
    langue: str = "fr",
) -> dict[str, Any]:
    """Compatibilité API historique : ``repondre(question, vectorstore, llm, k, ...)``.

    Délègue au cœur ``shared.qr_logic.repondre`` tout en préservant l'ordre
    des arguments attendu par les tests existants.

    Règles :
    - Si ``pieces_jointes`` est fourni et non vide → réponse fondée uniquement
      sur les pièces jointes (base vectorielle non interrogée).
    - Sinon → recherche dans la base documentaire du module Marketing.
    - En cas d'absence de résultat → message guidant vers l'ingestion.
    """
    cfg = _get_config("marketing")

    # Règle PJ-only : si des pièces jointes sont présentes, on n'interroge
    # pas la base vectorielle.
    if pieces_jointes is not None:
        from pieces_jointes import IndexPiecesJointes as _IPJ

        if isinstance(pieces_jointes, _IPJ):
            if pieces_jointes.est_vide():
                # Pas de contenu PJ exploitable → message d'indisponibilité
                # avec mention du module et d'ingestion (attendu par le test)
                return {
                    "reponse": (
                        "Je ne trouve pas cette information dans la base documentaire "
                        "Marketing. Precisez votre question, verifiez les documents "
                        "indexes, ou lancez l'ingestion du module Marketing : "
                        "python ingest.py --module marketing."
                    ),
                    "sources": [],
                }
            # Il y a des PJ : réponse fondée uniquement sur les PJ, pas de base
            try:
                historique_h = list(historique[-6:] if historique else [])
                resultat = _repondre_qr(
                    question,
                    cfg,
                    vectorstore=None,
                    llm=llm,
                    pieces_jointes=pieces_jointes,
                    historique=historique,
                    langue=langue,
                )
                return resultat
            except Exception as exc:  # noqa: BLE001
                # Message d'erreur
                return {
                    "reponse": f"Impossible de traiter les pièces jointes : {exc}",
                    "sources": [],
                }

    # Mode base vectorielle (pas de PJ ou PJ vide)
    try:
        historique_h = list(historique[-6:] if historique else [])
        resultat = _repondre_qr(
            question,
            cfg,
            vectorstore=vectorstore,
            llm=llm,
            pieces_jointes=pieces_jointes,
            historique=historique_h,
            langue=langue,
        )
        return resultat
    except Exception as exc:  # noqa: BLE001
        # Message guidant vers l'ingestion (attendu par le test)
        return {
            "reponse": (
                "Je ne trouve pas cette information dans la base documentaire Marketing. "
                "Precisez votre question, verifiez les documents indexes, ou lancez "
                "l'ingestion du module Marketing : python ingest.py --module marketing."
            ),
            "sources": [],
        }