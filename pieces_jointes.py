"""Pieces jointes de session pour l'assistant RH.

Extrait le texte des fichiers PDF/TXT/Markdown fournis par l'utilisateur,
le decoupe avec le splitter juridique de ingest.py, puis recherche les
passages les plus proches de la question. Les fichiers courts (comme un
bulletin de paie) peuvent etre renvoyes entiers via ``documents_complets``,
sans passer par la recherche par similarite.

Tout reste en memoire de session : rien n'est persiste dans ChromaDB. Les
embeddings sont calcules une seule fois a l'ajout du fichier, ce qui evite
de les recalculer a chaque question.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from ingest import construire_splitter

logger = logging.getLogger(__name__)

# Configuration
EXTENSIONS_ACCEPTEES = (".pdf", ".txt", ".md")
MAX_CHUNKS_PAR_FICHIER = 300
# En dessous de cette taille, une piece jointe est envoyee entiere au LLM
# plutot que reduite aux k extraits les plus proches.
MAX_CARACTERES_CONTEXTE_COMPLET = 8000


class ErreurPieceJointe(ValueError):
    """Fichier joint illisible, vide ou de format non supporte."""


class Embeddings(Protocol):
    def embed_documents(self, textes: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, texte: str) -> list[float]: ...


def _nom_lisible(nom: str) -> str:
    return Path(nom).name or "piece jointe"


def _extraire_texte(nom: str, contenu: bytes) -> str:
    return contenu.decode("utf-8-sig", errors="replace")


def _extraire_texte_page(page: Any) -> str:
    """Extrait le texte d'une page en preservant la disposition.

    Le mode par defaut de pypdf peut inserer un espace entre chaque
    caractere de certains PDF (bulletins de paie generes par EBP, par
    exemple) : les montants deviennent alors illisibles pour le LLM. Le
    mode ``layout`` respecte la position des glyphes et restitue les
    colonnes. On retombe sur le mode par defaut si ``layout`` n'est pas
    disponible (ancien pypdf, doublure de test) ou ne produit rien.
    """
    try:
        texte = page.extract_text(extraction_mode="layout")
    except TypeError:
        # Signature sans ``extraction_mode`` : lecteur de test ou pypdf ancien.
        return page.extract_text() or ""
    except Exception:  # noqa: BLE001 - on retombe sur le mode par defaut
        logger.debug(
            "Extraction en mode layout impossible, mode par defaut", exc_info=True
        )
        texte = None

    if texte and texte.strip():
        return texte
    return page.extract_text() or ""


def _extraire_pdf(
    nom: str,
    contenu: bytes,
    reader_factory: Callable[[Any], Any],
) -> list[Any]:
    from langchain_core.documents import Document

    try:
        lecteur = reader_factory(io.BytesIO(contenu))
        pages = list(lecteur.pages)
    except Exception as exc:  # noqa: BLE001 - tout echec de lecture devient un message clair
        raise ErreurPieceJointe(f"PDF illisible : {_nom_lisible(nom)}") from exc

    documents = []
    for numero, page in enumerate(pages):
        try:
            texte = _extraire_texte_page(page)
        except Exception:  # noqa: BLE001 - une page en echec ne doit pas bloquer les autres
            logger.warning("Page %d illisible dans %s", numero + 1, nom)
            continue
        if not texte.strip():
            continue
        documents.append(
            Document(
                page_content=texte,
                metadata={
                    "source": _nom_lisible(nom),
                    "page": numero,
                    "page_label": str(numero + 1),
                    "origine": "piece_jointe",
                },
            )
        )

    if not documents:
        raise ErreurPieceJointe(
            f"Aucun texte exploitable dans le PDF : {_nom_lisible(nom)}"
        )
    return documents


def extraire_documents(
    nom: str,
    contenu: bytes,
    *,
    pdf_reader_factory: Callable[[Any], Any] | None = None,
) -> list[Any]:
    """Retourne les documents (pages PDF ou fichier texte) d'une piece jointe."""
    nom = _nom_lisible(nom)
    extension = Path(nom).suffix.lower()
    if extension not in EXTENSIONS_ACCEPTEES:
        raise ErreurPieceJointe(
            f"Format non supporte ({extension or 'sans extension'}) : {nom}. "
            f"Formats acceptes : {', '.join(EXTENSIONS_ACCEPTEES)}."
        )

    if extension == ".pdf":
        if pdf_reader_factory is None:
            from pypdf import PdfReader

            pdf_reader_factory = PdfReader
        return _extraire_pdf(nom, contenu, pdf_reader_factory)

    from langchain_core.documents import Document

    texte = _extraire_texte(nom, contenu)
    if not texte.strip():
        raise ErreurPieceJointe(f"Fichier vide : {nom}")

    return [
        Document(
            page_content=texte,
            metadata={"source": nom, "origine": "piece_jointe"},
        )
    ]


def decouper_piece_jointe(
    documents: list[Any],
    splitter: Any | None = None,
    max_chunks: int = MAX_CHUNKS_PAR_FICHIER,
) -> list[Any]:
    """Decoupe les documents en morceaux, avec un plafond par fichier."""
    if splitter is None:
        splitter = construire_splitter()
    morceaux = list(splitter.split_documents(documents))
    return morceaux[:max_chunks]


def _cosinus(vecteur_a: Sequence[float], vecteur_b: Sequence[float]) -> float:
    produit = sum(a * b for a, b in zip(vecteur_a, vecteur_b))
    norme_a = math.sqrt(sum(a * a for a in vecteur_a))
    norme_b = math.sqrt(sum(b * b for b in vecteur_b))
    if norme_a == 0 or norme_b == 0:
        return 0.0
    return produit / (norme_a * norme_b)


class IndexPiecesJointes:
    """Index en memoire des morceaux de pieces jointes et de leurs vecteurs."""

    def __init__(self, embeddings: Embeddings):
        self._embeddings = embeddings
        self._entrees: dict[str, list[tuple[Any, list[float]]]] = {}
        self._documents: dict[str, list[Any]] = {}

    def ajouter(self, nom: str, contenu: bytes) -> int:
        """Extrait, decoupe et vectorise un fichier ; retourne le nombre de morceaux."""
        nom = _nom_lisible(nom)
        documents = extraire_documents(nom, contenu)
        morceaux = decouper_piece_jointe(documents)

        # Guardrail : vérification que les embeddings ne sont pas vides
        textes = [morceau.page_content for morceau in morceaux]
        if not textes:
            logger.warning("Aucun texte à encoder pour le fichier %s", nom)
            return 0
        vecteurs = self._embeddings.embed_documents(textes)

        # Vérifier que les vecteurs sont valides (non vides)
        if not vecteurs or all(not v for v in vecteurs):
            logger.error("Embeddings vides pour le fichier %s", nom)
            return 0

        self._documents[nom] = documents
        self._entrees[nom] = list(zip(morceaux, vecteurs))
        return len(morceaux)

    def retirer(self, nom: str) -> None:
        nom = _nom_lisible(nom)
        self._entrees.pop(nom, None)
        self._documents.pop(nom, None)

    def noms(self) -> list[str]:
        return list(self._entrees)

    def nombre_chunks(self) -> int:
        return sum(len(entrees) for entrees in self._entrees.values())

    def est_vide(self) -> bool:
        return not self._entrees

    def documents_complets(
        self, max_caracteres: int = MAX_CARACTERES_CONTEXTE_COMPLET
    ) -> list[Any] | None:
        """Retourne les documents entiers s'ils tiennent sous la limite.

        Les documents renvoyes sont ceux extraits avant decoupage : ils ne
        contiennent donc pas les chevauchements des morceaux. Retourne
        ``None`` si le total depasse ``max_caracteres`` ; l'appelant doit
        alors utiliser la recherche par similarite.
        """
        documents = [
            document
            for nom in self._entrees
            for document in self._documents.get(nom, [])
        ]
        total = sum(len(document.page_content) for document in documents)
        if total > max_caracteres:
            return None
        return documents

    def rechercher(self, question: str, k: int = 4) -> list[Any]:
        """Retourne les k morceaux les plus proches de la question."""
        if self.est_vide() or k <= 0:
            return []

        vecteur_question = self._embeddings.embed_query(question)

        # Guardrail : vérification que l'embedding question n'est pas vide
        if not vecteur_question:
            logger.warning("Embedding vide pour la question : %s", question[:50])
            return []

        resultats = [
            (_cosinus(vecteur_question, vecteur), document)
            for entrees in self._entrees.values()
            for document, vecteur in entrees
        ]
        resultats.sort(key=lambda resultat: resultat[0], reverse=True)
        return [document for _, document in resultats[:k]]
