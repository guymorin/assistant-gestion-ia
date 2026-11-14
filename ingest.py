"""Pipeline d'ingestion RAG pour l'application RH locale.

Charge les PDF du dossier ./DRH et les pages web listees dans
./DRH/DRH-web.txt, decoupe les documents avec un splitter adapte aux textes
juridiques, calcule les embeddings via Ollama (nomic-embed-text) et
persiste le tout dans ChromaDB (./chroma_db).

Les imports des integrations (LangChain, Chroma, Ollama) sont paresseux :
le module reste importable et testable sans service externe. Les
fabriques de chargeurs, de splitter et de vectorstore sont injectables
pour les tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Configuration
PDF_CACHE_DIR = "./.cache/pdf"
MANIFESTE_INGESTION = "ingestion.json"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

MODULES = {
    "rh": {
        "pdf_dir": "./Ingestion/RH",
        "urls_file": "./Ingestion/RH/RH-web.txt",
        "chroma_dir": "./chroma_db/rh",
    },
    "finances": {
        "pdf_dir": "./Ingestion/Finances",
        "urls_file": "./Ingestion/Finances/Finances-web.txt",
        "chroma_dir": "./chroma_db/finances",
    },
    "juridique": {
        "pdf_dir": "./Ingestion/Juridique",
        "urls_file": "./Ingestion/Juridique/Juridique-web.txt",
        "chroma_dir": "./chroma_db/juridique",
    },
    "marketing": {
        "pdf_dir": "./Ingestion/Marketing",
        "urls_file": "./Ingestion/Marketing/Marketing-web.txt",
        "chroma_dir": "./chroma_db/marketing",
    },
}

DEFAULT_MODULE = "rh"


def get_module_config(module: str) -> dict[str, str]:
    """Retourne la configuration d'ingestion/indexation pour un module."""
    if module not in MODULES:
        raise ValueError(f"Module inconnu : {module}")
    return dict(MODULES[module])


# Compatibilité / défauts alignés sur le module RH
PDF_DIR = MODULES[DEFAULT_MODULE]["pdf_dir"]
URLS_FILE = MODULES[DEFAULT_MODULE]["urls_file"]
CHROMA_DIR = MODULES[DEFAULT_MODULE]["chroma_dir"]

# Decoupage adapte aux textes juridiques
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
LEGAL_SEPARATORS = [
    "\n\nArticle ",
    "\n\nARTICLE ",
    "\n\nChapitre ",
    "\n\nTitre ",
    "\n\nSection ",
    "\n\n",
    "\n",
    ". ",
    " ",
    "",
]


def lire_urls(chemin: str | Path = URLS_FILE) -> list[str]:
    """Retourne les URLs du fichier, en ignorant vides et commentaires."""
    chemin = Path(chemin)
    if not chemin.is_file():
        raise FileNotFoundError(f"Fichier d'URLs introuvable : {chemin}")

    urls = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        url = ligne.strip()
        if not url or url.startswith("#"):
            continue
        urls.append(url)
    return urls


def empreinte_dossier_pdf(dossier: str | Path) -> str:
    """Empreinte SHA-256 du dossier et des PDF (nom, taille, date de modification).

    Le chemin resolu du dossier fait partie de l'empreinte : renommer le
    dossier invalide donc le cache, dont les metadonnees ``source``
    contiendraient sinon l'ancien chemin.
    """
    dossier = Path(dossier)
    digest = hashlib.sha256()
    digest.update(str(dossier.resolve()).encode("utf-8"))
    digest.update(b"\0")
    for pdf in sorted(dossier.rglob("*.pdf")):
        stat = pdf.stat()
        for valeur in (str(pdf.relative_to(dossier)), stat.st_size, stat.st_mtime_ns):
            digest.update(str(valeur).encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _lire_cache(chemin: Path) -> list[Any] | None:
    """Retourne les documents du cache, ou None si absent ou illisible."""
    if not chemin.is_file():
        return None
    try:
        from langchain_core.documents import Document

        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        return [
            Document(
                page_content=element["page_content"],
                metadata=element.get("metadata") or {},
            )
            for element in contenu["documents"]
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Cache PDF illisible, regeneration (%s) : %s", chemin, exc)
        return None


def _ecrire_cache(chemin: Path, documents: list[Any]) -> None:
    """Ecrit le cache de facon atomique ; une erreur d'ecriture reste non bloquante."""
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        contenu = {
            "documents": [
                {
                    "page_content": document.page_content,
                    "metadata": getattr(document, "metadata", {}) or {},
                }
                for document in documents
            ]
        }
        temporaire = chemin.with_suffix(".tmp")
        temporaire.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
        temporaire.replace(chemin)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Impossible d'ecrire le cache PDF %s : %s", chemin, exc)


def charger_pdf(
    dossier: str | Path = PDF_DIR,
    loader_factory: Callable[[str], Any] | None = None,
    cache_dir: str | Path | None = None,
) -> list[Any]:
    """Charge toutes les pages des PDF du dossier, avec cache optionnel."""
    if loader_factory is None:
        from langchain_community.document_loaders import PyPDFDirectoryLoader

        loader_factory = PyPDFDirectoryLoader

    chemin_cache = None
    if cache_dir is not None:
        chemin_cache = Path(cache_dir) / f"pdf-{empreinte_dossier_pdf(dossier)}.json"
        documents = _lire_cache(chemin_cache)
        if documents is not None:
            logger.info(
                "%d page(s) PDF lue(s) depuis le cache %s", len(documents), chemin_cache
            )
            return documents

    documents = list(loader_factory(str(dossier)).load())
    logger.info("%d page(s) PDF chargee(s) depuis %s", len(documents), dossier)
    if chemin_cache is not None:
        _ecrire_cache(chemin_cache, documents)
    return documents


USER_AGENT = "Assistant-DRH-IA/1.0 (RAG RH local)"


def _loader_web_par_defaut(url: str, contenu_principal: bool = True) -> Any:
    """Construit le chargeur web, limite au contenu principal si possible."""
    from langchain_community.document_loaders import WebBaseLoader

    kwargs: dict[str, Any] = {
        "header_template": {"User-Agent": USER_AGENT},
    }
    if contenu_principal:
        from bs4.element import SoupStrainer

        kwargs["bs_kwargs"] = {"parse_only": SoupStrainer("main")}
    return WebBaseLoader(url, **kwargs)


def _charger_une_url(url: str) -> list[Any]:
    """Charge une URL en privilegiant le contenu principal.

    Certaines pages n'ont pas de balise ``main`` : dans ce cas le chargement
    produit un texte vide et on relance sans filtre pour ne rien perdre.
    """
    documents = list(_loader_web_par_defaut(url).load())
    if not any(document.page_content.strip() for document in documents):
        logger.info("Pas de contenu principal pour %s, chargement complet", url)
        documents = list(_loader_web_par_defaut(url, contenu_principal=False).load())
    return documents


def charger_web(
    urls: list[str],
    loader_factory: Callable[[str], Any] | None = None,
) -> list[Any]:
    """Charge le contenu de chaque URL, sans interrompre les autres en cas d'echec."""
    documents = []
    for url in urls:
        try:
            if loader_factory is None:
                documents.extend(_charger_une_url(url))
            else:
                documents.extend(loader_factory(url).load())
            logger.info("Contenu web charge : %s", url)
        except Exception as exc:  # noqa: BLE001 - une URL en echec ne doit pas tout bloquer
            logger.warning("Echec du chargement de %s : %s", url, exc)
    return documents


def construire_splitter():
    """Construit le splitter configure pour les textes juridiques."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=list(LEGAL_SEPARATORS),
    )


def decouper_documents(documents: list[Any], splitter: Any | None = None) -> list[Any]:
    """Decoupe les documents en morceaux avec le splitter fourni ou par defaut."""
    if splitter is None:
        splitter = construire_splitter()
    return list(splitter.split_documents(documents))


def categoriser_source(source: str) -> str:
    """Classe une source pour permettre un routage de recherche par famille.

    Les categories sont volontairement larges : elles servent a garantir
    qu'une question Odoo trouve la documentation Odoo, ou qu'une question
    « restauration rapide » trouve la convention collective, sans dependre
    du seul classement semantique.
    """
    source_minuscule = source.lower()
    if "odoo.com" in source_minuscule:
        return "odoo"
    if "convention_collective" in source_minuscule:
        return "convention"
    if "code.travail.gouv.fr/contribution/" in source_minuscule and "1501" in source_minuscule:
        return "convention"
    if "code_du_travail" in source_minuscule or "legifrance" in source_minuscule:
        return "code_travail"
    if "referentiel" in source_minuscule or "anact" in source_minuscule:
        return "referentiel"
    if source_minuscule.startswith("http://") or source_minuscule.startswith("https://"):
        return "web_rh"
    return "interne"


def categoriser_documents(documents: list[Any]) -> list[Any]:
    """Ajoute la categorie de chaque document a ses metadonnees."""
    for document in documents:
        metadata = getattr(document, "metadata", None)
        if metadata is None:
            continue
        metadata["categorie"] = categoriser_source(str(metadata.get("source") or ""))
    return documents


def creer_embeddings():
    """Initialise les embeddings Ollama locaux."""
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


def creer_vectorstore(
    chunks: list[Any],
    embeddings: Any,
    persist_directory: str | Path = CHROMA_DIR,
    store_factory: Callable[..., Any] | None = None,
    reinitialiser: bool = True,
) -> Any:
    """Vectorise les morceaux et les persiste dans ChromaDB.

    Par defaut la collection existante est supprimee avant l'insertion :
    relancer l'ingestion reconstruit l'index au lieu d'y ajouter des
    doublons.
    """
    if store_factory is None:
        from langchain_chroma import Chroma

        if reinitialiser:
            Chroma(
                persist_directory=str(persist_directory),
                embedding_function=embeddings,
            ).delete_collection()
        store_factory = Chroma.from_documents

    # Filtrer les chunks vides pour éviter l'erreur d'upsert avec des embeddings vides
    chunks_non_vides = [c for c in chunks if getattr(c, "page_content", None) and str(c.page_content).strip()]

    return store_factory(
        documents=chunks_non_vides,
        embedding=embeddings,
        persist_directory=persist_directory,
    )


def enregistrer_manifeste_ingestion(
    chroma_dir: str | Path = CHROMA_DIR,
    chunks: int = 0,
    *,
    date: datetime | None = None,
) -> Path:
    """Consigne la date et le nombre de morceaux de la derniere ingestion.

    Le manifeste est ecrit dans le dossier ChromaDB afin que l'interface
    puisse afficher la fraicheur de la base documentaire.
    """
    dossier = Path(chroma_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = (date or datetime.now()).replace(microsecond=0)
    chemin = dossier / MANIFESTE_INGESTION
    chemin.write_text(
        json.dumps(
            {
                "date_ingestion": horodatage.isoformat(),
                "chunks": chunks,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return chemin


def _ingerer_chemins(
    *,
    pdf_dir: str | Path,
    urls_file: str | Path,
    chroma_dir: str | Path,
    pdf_loader_factory: Callable[[str], Any] | None = None,
    web_loader_factory: Callable[[str], Any] | None = None,
    splitter: Any | None = None,
    embeddings: Any | None = None,
    store_factory: Callable[..., Any] | None = None,
    cache_dir: str | Path | None = None,
) -> int:
    """Execute le pipeline complet pour des chemins explicites."""
    documents_pdf = charger_pdf(
        pdf_dir, loader_factory=pdf_loader_factory, cache_dir=cache_dir
    )
    urls = lire_urls(urls_file)
    documents_web = charger_web(urls, loader_factory=web_loader_factory)
    documents = documents_pdf + documents_web

    if not documents:
        logger.warning("Aucun document a indexer, arret du pipeline.")
        return 0

    if splitter is None:
        splitter = construire_splitter()
    chunks = categoriser_documents(decouper_documents(documents, splitter=splitter))

    if not chunks:
        logger.warning("Aucun morceau genere, arret du pipeline.")
        return 0

    if embeddings is None:
        embeddings = creer_embeddings()

    creer_vectorstore(
        chunks,
        embeddings,
        persist_directory=chroma_dir,
        store_factory=store_factory,
    )
    enregistrer_manifeste_ingestion(chroma_dir, len(chunks))
    logger.info("%d morceau(x) indexe(s) dans %s", len(chunks), chroma_dir)
    return len(chunks)


def ingerer(
    pdf_dir: str | Path = PDF_DIR,
    urls_file: str | Path = URLS_FILE,
    chroma_dir: str | Path = CHROMA_DIR,
    *,
    module: str | None = None,
    pdf_loader_factory: Callable[[str], Any] | None = None,
    web_loader_factory: Callable[[str], Any] | None = None,
    splitter: Any | None = None,
    embeddings: Any | None = None,
    store_factory: Callable[..., Any] | None = None,
    cache_dir: str | Path | None = None,
) -> int:
    """Execute le pipeline complet et retourne le nombre de morceaux indexes.

    Si ``module`` est fourni, ses chemins sont utilisés (les arguments
    explicites de chemins les remplacent si différents des valeurs par défaut).
    """
    if module is not None:
        cfg = get_module_config(module)
        if str(pdf_dir) == str(PDF_DIR):
            pdf_dir = cfg["pdf_dir"]
        if str(urls_file) == str(URLS_FILE):
            urls_file = cfg["urls_file"]
        if str(chroma_dir) == str(CHROMA_DIR):
            chroma_dir = cfg["chroma_dir"]
    return _ingerer_chemins(
        pdf_dir=pdf_dir,
        urls_file=urls_file,
        chroma_dir=chroma_dir,
        pdf_loader_factory=pdf_loader_factory,
        web_loader_factory=web_loader_factory,
        splitter=splitter,
        embeddings=embeddings,
        store_factory=store_factory,
        cache_dir=cache_dir,
    )


def ingerer_module(module: str, **kwargs) -> int:
    """Ingère un module cible en utilisant sa configuration."""
    cfg = get_module_config(module)
    return _ingerer_chemins(
        pdf_dir=cfg["pdf_dir"],
        urls_file=cfg["urls_file"],
        chroma_dir=cfg["chroma_dir"],
        **kwargs,
    )


def main(argv: list[str] | None = None) -> int:
    """Point d'entree CLI : code de sortie 0 si l'ingestion a produit des morceaux."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--module",
        choices=["rh", "finances", "juridique", "marketing", "all"],
        default="all",
        help="Module à ingérer (rh, finances, juridique ou marketing). Défaut: all.",
    )
    args, _ = parser.parse_known_args(argv)
    modules = (
        ["rh", "finances", "juridique", "marketing"]
        if args.module == "all"
        else [args.module]
    )
    try:
        totals = [ingerer(module=m, cache_dir=PDF_CACHE_DIR) for m in modules]
    except Exception:  # noqa: BLE001 - le CLI doit toujours renvoyer un code de sortie
        logger.exception("Echec de l'ingestion")
        return 1
    return 0 if any(totals) else 1


if __name__ == "__main__":
    raise SystemExit(main())



