"""Coeur logique Q&R générique, paramétré par QRModuleConfig.

Fournit la logique RAG uniforme pour tous les modules (RH, Finances,
Juridique, Marketing). Chaque fonction accepte une ``QRModuleConfig``
et applique les bons chemins, modèles et messages contextualisés.

L'objectif est que ``rh.logic`` et ``finances.logic`` puissent être
raffinés en de simples wrappers autour de ce cœur, en préservant les
symboles publics utilisés par les vues et les tests.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings, ChatOllama

from .qr_config import QR_MODULES, get_module_config, QRModuleConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper(s) de résolution de chemin par config
# ---------------------------------------------------------------------------

def _chroma_dir(cfg: QRModuleConfig | str | None = None) -> Path:
    """Retourne le Path du répertoire Chroma pour une config."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    return Path(cfg.chroma_dir)


def _pdf_dir(cfg: QRModuleConfig | str | None = None) -> Path:
    """Retourne le Path du répertoire PDF pour une config."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    return Path(cfg.pdf_dir)


def _urls_file(cfg: QRModuleConfig | str | None = None) -> Path:
    """Retourne le Path du fichier d'URLs pour une config."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    return Path(cfg.urls_file)


# ---------------------------------------------------------------------------
# Disponibilité de la base
# ---------------------------------------------------------------------------

def base_disponible(cfg: QRModuleConfig | str | None = None, *, chroma_dir: str | Path | None = None) -> bool:
    """Retourne ``True`` si la base ChromaDB du module est présente."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    if chroma_dir is not None:
        return (Path(chroma_dir) / "chroma.sqlite3").is_file()
    return any((_chroma_dir(cfg) / d).joinpath("chroma.sqlite3").is_file() for d in _chemins_base(_chroma_dir(cfg)))


def _chemins_base(chroma_dir: Path) -> list[Path]:
    """Chemins candidats de la base : le dossier, puis la racine legacy."""
    d = Path(chroma_dir)
    candidats = [d]
    if d.name in {"rh", "finances", "juridique", "marketing"}:
        legacy = d.parent
        if legacy != d:
            candidats.append(legacy)
    return candidats


# ---------------------------------------------------------------------------
# Infos d'ingestion
# ---------------------------------------------------------------------------

def infos_ingestion(cfg: QRModuleConfig | str | None = None, *, chroma_dir: str | Path | None = None) -> dict[str, Any]:
    """Date et taille de la dernière ingestion pour un module."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    if chroma_dir is not None:
        return infos_ingestion_plain(chroma_dir)
    return infos_ingestion_plain(str(_chroma_dir(cfg)))


def infos_ingestion_plain(chroma_dir: str | Path) -> dict[str, Any]:
    """Implémentation interne : lire le manifeste ou la base SQLite."""
    dossier = Path(chroma_dir)
    manifeste = dossier / "ingestion.json"
    if manifeste.is_file():
        try:
            contenu = json.loads(manifeste.read_text(encoding="utf-8"))
            date = datetime.fromisoformat(str(contenu["date_ingestion"]))
            chunks = contenu.get("chunks")
            return {"date": date, "chunks": chunks if isinstance(chunks, int) else None}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Manifeste d'ingestion illisible : %s : %s", manifeste, exc)
    base = dossier / "chroma.sqlite3"
    if base.is_file():
        return {"date": datetime.fromtimestamp(base.stat().st_mtime), "chunks": None}
    return {}


# ---------------------------------------------------------------------------
# Fabriques de LLM et d'embeddings (cache par config)
# ---------------------------------------------------------------------------

_llm_cache: dict[str, Any] = {}
_embeddings_cache: dict[str, Any] = _llm_cache


def creer_llm(cfg: QRModuleConfig | str | None = None, *, model: str | None = None, temperature: float = 0.0, base_url: str = "http://127.0.0.1:11434") -> ChatOllama:
    """Initialise le modèle de langage local pour le module spécifié."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    key = cfg.id
    if key in _llm_cache and model is None:
        return _llm_cache[key]
    if model is None:
        model = cfg.default_model
    if cfg.model_env_var:
        env_model = __import__("os").environ.get(cfg.model_env_var)
        if env_model is not None:
            model = env_model
    llm = ChatOllama(model=model, base_url=base_url, temperature=temperature)
    _llm_cache[key] = llm
    return llm


def creer_embeddings(cfg: QRModuleConfig | str | None = None) -> OllamaEmbeddings:
    """Initialise les embeddings Ollama locaux pour le module spécifié."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    key = cfg.id
    if key in _embeddings_cache:
        return _embeddings_cache[key]
    embeddings = OllamaEmbeddings(model=cfg.default_model, base_url="http://127.0.0.1:11434")
    _embeddings_cache[key] = embeddings
    return embeddings


# ---------------------------------------------------------------------------
# Vectorstore
# ---------------------------------------------------------------------------

def creer_vectorstore(
    cfg: QRModuleConfig | str | None = None,
    *,
    embeddings: Any | None = None,
    persist_directory: str | Path | None = None,
    reinitialiser: bool = True,
) -> Any:
    """Vectorise et persiste les documents dans ChromaDB pour le module."""
    from langchain_chroma import Chroma

    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    if persist_directory is None:
        persist_directory = str(_chroma_dir(cfg))
    dossier = Path(persist_directory)

    if reinitialiser:
        # Supprimer la collection existante avant insertion
        if (dossier / "chroma.sqlite3").is_file():
            Chroma(persist_directory=str(dossier), embedding_function=None).delete_collection()

    if embeddings is None:
        embeddings = creer_embeddings(cfg)

    return Chroma.from_documents(
        documents=[],  # placeholder ; les vrais documents viendront de l'ingestion
        embedding=embeddings,
        persist_directory=persist_directory,
    )


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------

def rechercher(question: str, cfg: QRModuleConfig | str | None = None, *, vectorstore: Any | None = None, k: int = 8) -> list[Any]:
    """Recherche les extraits les plus pertinents pour une question."""
    import os
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    if vectorstore is None:
        embeddings = creer_embeddings(cfg)
        vectorstore = creer_vectorstore(cfg, embeddings=embeddings)

    # MMR avec repli similarité simple
    try:
        from langchain_chroma import Chroma
        mmr = getattr(vectorstore, "max_marginal_relevance_search", None)
        if callable(mmr):
            fetch_k = max(k * 5, 20)
            results = list(
                mmr(question, k=k, fetch_k=fetch_k, lambda_mult=0.7)
            )
            if results:
                return results
    except Exception as exc:  # noqa: BLE001 - repli obligatoire
        logger.warning("Recherche MMR indisponible, repli : %s", exc)

    return list(vectorstore.similarity_search(question, k=k))


# ---------------------------------------------------------------------------
# Réponse Q&R (générique)
# ---------------------------------------------------------------------------

MESSAGES_SANS_RESULTAT: dict[str, dict[str, str]] = {
    "fr": {
        "message": "Je ne trouve pas cette information dans la base documentaire. "
                    "Precisez votre question, ou joignez le document concerne "
                    "pour que je puisse y repondre.",
    },
    "en": {
        "message": "I cannot find this information in the documentary base. "
                    "Please refine your question, or attach the relevant document "
                    "so that I can answer it.",
    },
    "ko": {
        "message": "문서 기반에서 해당 정보를 찾을 수 없습니다. 질문을 더 구체적으로 "
                    "작성하거나 관련 문서를 첨부해 주시면 답변드릴 수 있습니다.",
    },
}


def normaliser_langue(langue: str | None = None) -> str:
    """Ramène un code de langue inconnu ou absent au francais.

    Si aucun code n'est fourni, retombe sur le français par défaut.
    """
    from .qr_config import LANGUES as _LANGUES
    if langue is None or langue not in _LANGUES:
        return "fr"
    return langue


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


ROLES_HISTORIQUE: dict[str, dict[str, str]] = {
    "fr": {"user": "UTILISATEUR", "assistant": "ASSISTANT"},
    "en": {"user": "USER", "assistant": "ASSISTANT"},
    "ko": {"user": "사용자", "assistant": "어시스턴t"},
}


def construire_historique(
    historique: list[dict[str, Any]] | None,
    *,
    max_messages: int = 6,
    max_caracteres: int = 6000,
    langue: str = "fr",
) -> str:
    """Formate les derniers echanges pour comprendre les questions de suivi."""
    if not historique:
        return "Aucun."

    roles = ROLES_HISTORIQUE.get(langue, ROLES_HISTORIQUE["fr"])
    lignes: list[str] = []
    total = 0
    for message in reversed(historique[-max_messages:]):
        contenu = str(message.get("content") or "").strip()
        if not contenu:
            continue
        if len(contenu) > 1000:
            contenu = contenu[:1000] + "..."
        role = roles["user"] if message.get("role") == "user" else roles["assistant"]
        ligne = f"{role} : {contenu}"
        if lignes and total + len(ligne) > max_caracteres:
            break
        lignes.append(ligne)
        total += len(ligne)

    if not lignes:
        return "Aucun."
    return "\n".join(reversed(lignes))


def question_pour_recherche(
    question: str,
    historique: list[dict[str, Any]] | None = None,
) -> str:
    """Enrichit une question de suivi avec la question precedente."""
    if not historique:
        return question

    derniere_question = next(
        (
            str(message.get("content") or "").strip()
            for message in reversed(historique)
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ),
        "",
    )
    if not derniere_question:
        return question

    question = question.strip()
    mots = question.split()
    connecteurs = ("et ", "pour ", "dans ce cas", "meme", "aussi", "alors")
    est_relance = len(mots) <= 8 or question.lower().startswith(connecteurs)
    if not est_relance:
        return question

    return f"{derniere_question} {question}"[:500]


def _construire_prompt(
    question: str,
    documents: list[Any],
    *,
    historique: list[dict[str, Any]] | None = None,
    langue: str = "fr",
) -> str:
    """Construit le prompt final : consignes, historique, contexte numerote et question."""
    code = normaliser_langue(langue)
    consigne = LANGUES[code]["consigne"].format(consigne_langue=LANGUES[code]["consigne"])
    historique_str = construire_historique(historique, langue=code)
    # Contexte numerote
    blocs: list[str] = []
    for numero, document in enumerate(documents, start=1):
        source = getattr(document, "metadata", {}).get("source", "source inconnue")
        contenu = str(getattr(document, "page_content", "") or "")
        blocs.append(f"[{numero}] Source : {source}\n{contenu}")
    contexte = "\n\n".join(blocs) if blocs else ""
    return f"{consigne}\n\nHISTORIQUE RECENT :\n{historique_str}\n\nCONTEXTE :\n{contexte}\n\nQUESTION : {question}\n\nREPONSE :"


def repondre(
    question: str,
    cfg: QRModuleConfig | str | None = None,
    *,
    vectorstore: Any | None = None,
    llm: Any | None = None,
    pieces_jointes: Any | None = None,
    historique: list[dict[str, Any]] | None = None,
    langue: str = "fr",
) -> dict[str, Any]:
    """Recherche le contexte, interroge le LLM et retourne reponse + sources.

    Comporte la logique clé :
    - Si des pieces jointes sont presentes, elles constituent la seule source
      de contexte : la base vectorielle n'est pas interrogee.
    - Sinon, on recherche dans la base documentaire du module.
    """
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    question_recherche = question_pour_recherche(question, historique)
    documents: list[Any] = []

    # Règle d'or : pieces jointes => base vectoire pas utilisée
    if pieces_jointes is not None:
        # Essayer de récupérer les documents complets depuis IndexPiecesJointes
        if hasattr(pieces_jointes, "documents_complets") and pieces_jointes.documents_complets() is not None:
            documents = list(pieces_jointes.documents_complets())
        elif hasattr(pieces_jointes, "rechercher"):
            documents = list(pieces_jointes.rechercher(question_recherche, k=k))
        if not documents and vectorstore is not None:
            documents = rechercher(question_recherche, vectorstore, k=k)
    if not documents and vectorstore is not None:
        documents = rechercher(question_recherche, vectorstore, k=k)

    if not documents:
        langue_courante = normaliser_langue(langue)
        message = MESSAGES_SANS_RESULTAT.get(langue_courante, MESSAGES_SANS_RESULTAT["fr"])
        return {
            "reponse": message["message"],
            "sources": [],
        }

    prompt = _construire_prompt(question, documents, historique=historique, langue=langue_courante)
    message_llm = llm.invoke(prompt) if llm else ""
    contenu = getattr(message_llm, "content", None)
    if contenu is None:
        contenu = str(message_llm)

    # Extraire les sources
    sources: list[dict[str, Any]] = []
    for document in documents:
        metadata = getattr(document, "metadata", {}) or {}
        source_str = str(metadata.get("source", ""))
        page = metadata.get("page")
        cle = (source_str, str(page)) if page else (source_str,)
        if cle not in {("s",) for s in []}:
            sources.append(
                {
                    "nom": source_str or "source inconnue",
                    "type": "piece_jointe" if getattr(pieces_jointes, "est_vide", lambda: True)() else "pdf",
                    "source": source_str,
                    "page": page,
                    "extraits": [str(getattr(document, "page_content", ""))],
                }
            )

    return {"reponse": contenu, "sources": sources}


# -----------------------------------------------------------------------
# Rappels de compatibilité : les modules existants (rh.logic, finances.logic)
# peuvent re-exporter les noms ci-dessous depuis ce cœur. Les tests et vues
# qui importent de ``rh.logic`` ou ``finances.logic`` doivent continuer à
# trouver ces symboles.
# -----------------------------------------------------------------------

__all__ = [
    "base_disponible",
    "infos_ingestion",
    "creer_llm",
    "creer_embeddings",
    "creer_vectorstore",
    "rechercher",
    "repondre",
    "normaliser_langue",
    "LANGUES",
    "ROLES_HISTORIQUE",
    "construire_historique",
    "question_pour_recherche",
    "MESSAGES_SANS_RESULTAT",
]