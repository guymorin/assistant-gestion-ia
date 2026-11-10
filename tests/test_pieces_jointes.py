"""Tests TDD des pieces jointes de session (pieces_jointes.py).

Les tests n'appellent ni Streamlit, ni Ollama, ni le reseau : les
embeddings et le lecteur PDF sont injectes.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

import pieces_jointes as pj


class FakePage:
    def __init__(self, texte):
        self.texte = texte

    def extract_text(self):
        return self.texte


class FakeReader:
    def __init__(self, flux):
        self.flux = flux
        self.pages = [FakePage("Page une"), FakePage("Page deux")]


class FakeSplitter:
    def __init__(self, nombre):
        self.nombre = nombre

    def split_documents(self, documents):
        metadonnees = dict(documents[0].metadata)
        return [
            Document(page_content=f"morceau {numero}", metadata=dict(metadonnees))
            for numero in range(self.nombre)
        ]


class FakeEmbeddings:
    """Vecteurs deterministes : [1, 0] pour le conge, [0, 1] sinon."""

    def __init__(self):
        self.documents_appeles = []
        self.requetes = []

    def embed_documents(self, textes):
        textes = list(textes)
        self.documents_appeles.append(textes)
        return [self._vecteur(texte) for texte in textes]

    def embed_query(self, texte):
        self.requetes.append(texte)
        return self._vecteur(texte)

    @staticmethod
    def _vecteur(texte):
        return [1.0, 0.0] if "conge" in texte.lower() else [0.0, 1.0]


class TestExtraireDocuments:
    def test_extrait_un_fichier_texte(self):
        documents = pj.extraire_documents(
            "note.txt", "Le conge maternite est de 16 semaines.".encode("utf-8")
        )

        assert len(documents) == 1
        assert documents[0].page_content == "Le conge maternite est de 16 semaines."
        assert documents[0].metadata == {
            "source": "note.txt",
            "origine": "piece_jointe",
        }

    def test_accepte_le_markdown(self):
        documents = pj.extraire_documents("note.md", b"# Titre\n\nContenu")

        assert documents[0].page_content == "# Titre\n\nContenu"
        assert documents[0].metadata["source"] == "note.md"

    def test_ignore_un_eventuel_bom_utf8(self):
        documents = pj.extraire_documents("note.txt", b"\xef\xbb\xbfContenu")

        assert documents[0].page_content == "Contenu"

    def test_decode_un_texte_invalide_sans_planter(self):
        documents = pj.extraire_documents("latin.txt", b"caf\xe9")

        assert documents[0].page_content.startswith("caf")

    def test_refuse_une_extension_non_supportee(self):
        with pytest.raises(pj.ErreurPieceJointe, match="docx"):
            pj.extraire_documents("cv.docx", b"contenu")

    def test_refuse_un_fichier_vide(self):
        with pytest.raises(pj.ErreurPieceJointe):
            pj.extraire_documents("vide.txt", b"   \n")

    def test_extrait_un_pdf_page_par_page(self):
        documents = pj.extraire_documents(
            "note.pdf", b"%PDF", pdf_reader_factory=FakeReader
        )

        assert [document.page_content for document in documents] == [
            "Page une",
            "Page deux",
        ]
        assert [document.metadata["page"] for document in documents] == [0, 1]
        assert [document.metadata["page_label"] for document in documents] == [
            "1",
            "2",
        ]
        assert all(
            document.metadata["origine"] == "piece_jointe" for document in documents
        )

    def test_prefere_le_mode_layout_pour_les_bulletins_de_paie(self):
        """Un bulletin genere peut etre extrait avec un espace entre chaque caractere."""

        class PageEspaced:
            def extract_text(self, extraction_mode="plain"):
                if extraction_mode == "layout":
                    return "Net a payer 2 143,97"
                return "N e t a p a y e r 2 1 4 3 , 9 7"

        class ReaderLayout:
            def __init__(self, flux):
                self.pages = [PageEspaced()]

        documents = pj.extraire_documents(
            "bulletin.pdf", b"%PDF", pdf_reader_factory=ReaderLayout
        )

        assert documents[0].page_content == "Net a payer 2 143,97"

    def test_retombe_sur_le_mode_par_defaut_si_layout_echoue(self):
        class PageSansLayout:
            def extract_text(self, extraction_mode="plain"):
                if extraction_mode == "layout":
                    raise ValueError("mode non supporte")
                return "Texte par defaut"

        class ReaderSansLayout:
            def __init__(self, flux):
                self.pages = [PageSansLayout()]

        documents = pj.extraire_documents(
            "note.pdf", b"%PDF", pdf_reader_factory=ReaderSansLayout
        )

        assert documents[0].page_content == "Texte par defaut"

    def test_retombe_sur_le_mode_par_defaut_si_layout_est_vide(self):
        class PageLayoutVide:
            def extract_text(self, extraction_mode="plain"):
                if extraction_mode == "layout":
                    return "   \n"
                return "Texte par defaut"

        class ReaderLayoutVide:
            def __init__(self, flux):
                self.pages = [PageLayoutVide()]

        documents = pj.extraire_documents(
            "note.pdf", b"%PDF", pdf_reader_factory=ReaderLayoutVide
        )

        assert documents[0].page_content == "Texte par defaut"

    def test_ignore_les_pages_pdf_sans_texte(self):
        class ReaderAvecPageVide:
            def __init__(self, flux):
                self.pages = [FakePage(""), FakePage(None), FakePage("Page trois")]

        documents = pj.extraire_documents(
            "note.pdf", b"%PDF", pdf_reader_factory=ReaderAvecPageVide
        )

        assert [document.page_content for document in documents] == ["Page trois"]
        assert documents[0].metadata["page"] == 2

    def test_signale_un_pdf_illisible(self):
        def lecteur_en_echec(flux):  # noqa: ARG001 - signature imposee
            raise ValueError("fichier corrompu")

        with pytest.raises(pj.ErreurPieceJointe, match="note.pdf"):
            pj.extraire_documents(
                "note.pdf", b"%PDF", pdf_reader_factory=lecteur_en_echec
            )

    def test_signale_un_pdf_sans_texte_exploitable(self):
        class ReaderSansTexte:
            def __init__(self, flux):
                self.pages = [FakePage(""), FakePage(None)]

        with pytest.raises(pj.ErreurPieceJointe):
            pj.extraire_documents(
                "note.pdf", b"%PDF", pdf_reader_factory=ReaderSansTexte
            )


class TestDecouperPieceJointe:
    def test_decoupe_et_conserve_les_metadonnees(self):
        documents = [
            Document(
                "phrase. " * 400,
                metadata={"source": "note.txt", "origine": "piece_jointe"},
            )
        ]

        morceaux = pj.decouper_piece_jointe(documents)

        assert len(morceaux) > 1
        assert all(
            morceau.metadata["source"] == "note.txt" for morceau in morceaux
        )
        assert all(
            morceau.metadata["origine"] == "piece_jointe" for morceau in morceaux
        )

    def test_plafonne_le_nombre_de_morceaux(self):
        documents = [Document("contenu", metadata={"source": "note.txt"})]

        morceaux = pj.decouper_piece_jointe(
            documents, splitter=FakeSplitter(5), max_chunks=2
        )

        assert len(morceaux) == 2


class TestIndexPiecesJointes:
    def _index(self):
        embeddings = FakeEmbeddings()
        index = pj.IndexPiecesJointes(embeddings)
        index.ajouter("conge.txt", b"Le conge maternite est de 16 semaines.")
        index.ajouter("teletravail.txt", b"Le teletravail est encadre.")
        return index, embeddings

    def test_recherche_le_passage_le_plus_proche(self):
        index, _ = self._index()

        resultats = index.rechercher("conge", k=1)

        assert [document.page_content for document in resultats] == [
            "Le conge maternite est de 16 semaines."
        ]

    def test_ne_recalcule_pas_les_vecteurs_des_documents(self):
        index, embeddings = self._index()

        index.rechercher("conge")
        index.rechercher("teletravail")

        assert len(embeddings.documents_appeles) == 2
        assert embeddings.requetes == ["conge", "teletravail"]

    def test_retourne_au_plus_k_resultats(self):
        index, _ = self._index()

        assert len(index.rechercher("formation", k=1)) == 1
        assert len(index.rechercher("formation", k=10)) == 2

    def test_retire_un_fichier(self):
        index, _ = self._index()

        index.retirer("conge.txt")

        assert index.noms() == ["teletravail.txt"]
        assert index.nombre_chunks() == 1
        assert all(
            "teletravail" in document.page_content
            for document in index.rechercher("conge", k=2)
        )

    def test_remplace_un_fichier_du_meme_nom(self):
        index, _ = self._index()

        index.ajouter("conge.txt", b"Le conge paternite est de 28 jours.")

        assert index.noms() == ["conge.txt", "teletravail.txt"]
        assert index.nombre_chunks() == 2
        assert index.rechercher("conge", k=1)[0].page_content == (
            "Le conge paternite est de 28 jours."
        )

    def test_index_vide_ne_calcule_aucun_vecteur(self):
        embeddings = FakeEmbeddings()
        index = pj.IndexPiecesJointes(embeddings)

        assert index.est_vide() is True
        assert index.rechercher("conge") == []
        assert embeddings.requetes == []

    def test_un_fichier_illisible_ne_modifie_pas_l_index(self):
        index, _ = self._index()

        with pytest.raises(pj.ErreurPieceJointe):
            index.ajouter("vide.txt", b"")

        assert index.noms() == ["conge.txt", "teletravail.txt"]


class TestDocumentsComplets:
    def test_retourne_tous_les_documents_quand_le_total_est_court(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())
        index.ajouter("a.txt", b"Premier document.")
        index.ajouter("b.txt", b"Second document.")

        documents = index.documents_complets(max_caracteres=100)

        assert [document.page_content for document in documents] == [
            "Premier document.",
            "Second document.",
        ]
        assert [document.metadata["source"] for document in documents] == [
            "a.txt",
            "b.txt",
        ]

    def test_retourne_none_quand_le_total_depasse_la_limite(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())
        index.ajouter("long.txt", b"x" * 50)

        assert index.documents_complets(max_caracteres=10) is None

    def test_retourne_une_liste_vide_sans_fichier(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())

        assert index.documents_complets() == []

    def test_utilise_la_limite_par_defaut(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())
        index.ajouter("court.txt", b"court")

        assert index.documents_complets() is not None

    def test_oublie_les_documents_retires(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())
        index.ajouter("a.txt", b"Premier.")
        index.ajouter("b.txt", b"Second.")
        index.retirer("a.txt")

        documents = index.documents_complets()

        assert [document.page_content for document in documents] == ["Second."]

    def test_retourne_le_texte_original_sans_chevauchement(self):
        index = pj.IndexPiecesJointes(FakeEmbeddings())
        texte = "phrase. " * 400
        index.ajouter("long.txt", texte.encode("utf-8"))

        documents = index.documents_complets()

        assert len(documents) == 1
        assert documents[0].page_content == texte
        assert index.nombre_chunks() > 1
