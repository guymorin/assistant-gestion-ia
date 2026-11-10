"""Recherche lexicale BM25 pour completer la recherche vectorielle.

La recherche semantique retrouve bien les passages proches du sens de la
question, mais elle peut manquer un article precis contenant les mots cles
attends (« 30 jours ouvrables », « IDCC 1501 », un nom de module Odoo).
Ce module construit un index BM25 en memoire a partir des documents de
ChromaDB, puis renvoie les passages qui partagent le plus de termes avec la
question. Les deux classements sont ensuite fusionnes dans app.py.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

# Mots vides francais : ils n'apportent pas de signal pour le classement.
STOPWORDS = frozenset(
    """
    a au aux avec ce cet cette ces c d de des du dans en et elle elles est etre
    eu fait faire faut il ils j je l la le les leur leurs lui m ma mais me meme
    mes moins mon ne ni n nos notre nous on ou par pas pendant plus pour pourquoi
    qu quand que quel quelle quels quelles qui quoi s sa sans se ses si son sont
    sous sur t ta te tes toi ton tous tout toute toutes tres tu un une vos votre
    vous y afin ainsi alors apres aussi avant bien car chez comment depuis donc
    entre jusqu lors or pourtant puisque selon vers via
    """.split()
)


def normaliser(texte: str) -> str:
    """Minuscules sans accents, pour rapprocher « congés » et « conges »."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(
        caractere
        for caractere in texte
        if unicodedata.category(caractere) != "Mn"
    )


def tokeniser(texte: str) -> list[str]:
    """Decoupe un texte en termes utiles (minuscules, sans accents ni mots vides)."""
    termes = re.findall(r"[a-z0-9]+", normaliser(texte))
    return [
        terme
        for terme in termes
        if len(terme) >= 2 and terme not in STOPWORDS
    ]


class IndexLexical:
    """Index BM25 en memoire, construit une seule fois par vectorstore."""

    def __init__(self, documents: list[Any]):
        self.documents = documents
        self._frequences: list[Counter[str]] = []
        self._longueurs: list[int] = []
        self._frequence_document: Counter[str] = Counter()
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)

        for numero, document in enumerate(documents):
            termes = tokeniser(getattr(document, "page_content", "") or "")
            frequences = Counter(termes)
            self._frequences.append(frequences)
            self._longueurs.append(len(termes))
            self._frequence_document.update(frequences.keys())
            for terme, nombre in frequences.items():
                self._postings[terme].append((numero, nombre))

        self._nombre_documents = len(documents)
        self._longueur_moyenne = (
            sum(self._longueurs) / self._nombre_documents
            if self._nombre_documents
            else 1.0
        )

    def rechercher(
        self,
        question: str,
        k: int = 8,
        categorie: str | None = None,
    ) -> list[Any]:
        """Retourne les k documents les mieux classes par BM25."""
        if not self.documents or k <= 0:
            return []

        termes_question = set(tokeniser(question))
        if not termes_question:
            return []

        scores: dict[int, float] = defaultdict(float)
        k1, b = 1.5, 0.75
        for terme in termes_question:
            postings = self._postings.get(terme)
            if not postings:
                continue
            nombre_postings = len(postings)
            idf = math.log(
                1
                + (self._nombre_documents - nombre_postings + 0.5)
                / (nombre_postings + 0.5)
            )
            for numero, frequence in postings:
                if categorie is not None:
                    metadata = getattr(self.documents[numero], "metadata", None) or {}
                    if metadata.get("categorie") != categorie:
                        continue
                longueur = self._longueurs[numero]
                denominateur = frequence + k1 * (
                    1 - b + b * longueur / self._longueur_moyenne
                )
                scores[numero] += idf * frequence * (k1 + 1) / denominateur

        classement = sorted(scores.items(), key=lambda element: element[1], reverse=True)
        return [self.documents[numero] for numero, _ in classement[:k]]


def construire_index(vectorstore: Any) -> IndexLexical | None:
    """Charge tous les documents du vectorstore et construit l'index BM25."""
    get = getattr(vectorstore, "get", None)
    if not callable(get):
        return None

    try:
        donnees = get(include=["documents", "metadatas"])
    except Exception:  # noqa: BLE001 - l'absence d'index lexical ne doit pas bloquer
        return None

    documents_texte = donnees.get("documents") or []
    metadonnees = donnees.get("metadatas") or []
    if not documents_texte:
        return None

    from langchain_core.documents import Document

    documents = [
        Document(page_content=texte or "", metadata=metadata or {})
        for texte, metadata in zip(documents_texte, metadonnees)
    ]
    return IndexLexical(documents)
