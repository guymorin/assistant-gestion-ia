"""Tests de l'index lexical BM25 (recherche_lexicale.py)."""

from __future__ import annotations

from langchain_core.documents import Document

from recherche_lexicale import IndexLexical, construire_index, tokeniser


def document(texte: str, **metadata) -> Document:
    return Document(page_content=texte, metadata=metadata)


class TestTokeniser:
    def test_normalise_accents_majuscules_et_punctuation(self):
        assert tokeniser("Congés PAYÉS, arrêt maladie !") == [
            "conges",
            "payes",
            "arret",
            "maladie",
        ]

    def test_retire_les_mots_vides(self):
        assert "le" not in tokeniser("le contrat de travail")
        assert "contrat" in tokeniser("le contrat de travail")


class TestIndexLexical:
    def test_retrouve_un_passage_par_ses_mots_cles(self):
        documents = [
            document(
                "Le salarie a droit a 30 jours ouvrables de conges payes par an.",
                source="a.pdf",
            ),
            document("Le teletravail est encadre par accord.", source="b.pdf"),
        ]
        index = IndexLexical(documents)

        resultat = index.rechercher("combien de jours de conges payes", k=1)

        assert resultat[0].metadata["source"] == "a.pdf"

    def test_filtre_par_categorie(self):
        documents = [
            document("30 jours ouvrables", source="a.pdf", categorie="code_travail"),
            document("30 jours ouvrables", source="b.pdf", categorie="convention"),
        ]
        index = IndexLexical(documents)

        resultat = index.rechercher(
            "30 jours ouvrables", k=5, categorie="convention"
        )

        assert [document.metadata["source"] for document in resultat] == ["b.pdf"]

    def test_retourne_une_liste_vide_sans_terme_utile(self):
        index = IndexLexical([document("Le contrat de travail", source="a.pdf")])

        assert index.rechercher("le la les", k=4) == []


class TestConstruireIndex:
    def test_retourne_none_sans_methode_get(self):
        assert construire_index(object()) is None

    def test_construit_l_index_depuis_le_vectorstore(self):
        class VectorStoreFactice:
            def get(self, include=None):  # noqa: ARG002 - signature imposee
                return {
                    "documents": ["Le salarie a droit a 30 jours ouvrables."],
                    "metadatas": [{"source": "a.pdf"}],
                }

        index = construire_index(VectorStoreFactice())

        assert index is not None
        assert index.rechercher("jours ouvrables")[0].metadata["source"] == "a.pdf"
