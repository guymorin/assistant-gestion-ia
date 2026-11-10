"""Tests TDD du pipeline d'ingestion RH (ingest.py).

Phase RED : ces tests decrivent le comportement attendu avant toute
implementation. Ils doivent echouer tant que ingest.py n'expose pas l'API
publique definie dans plan.json.

Les tests unitaires n'appellent ni le reseau, ni Ollama, ni un vrai
ChromaDB : les chargeurs, le splitter et le vectorstore sont injectes.
Les tests d'integration sont marques et exclus par defaut (voir pytest.ini).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

import ingest


@dataclass
class FakeDocument:
    """Document minimal, suffisant pour tester l'orchestration."""

    page_content: str
    metadata: dict = field(default_factory=dict)


class FakeLoader:
    def __init__(self, documents=None, error=None):
        self.documents = documents or []
        self.error = error
        self.load_calls = 0

    def load(self):
        self.load_calls += 1
        if self.error is not None:
            raise self.error
        return list(self.documents)


class FakeSplitter:
    def __init__(self, chunks):
        self.chunks = chunks
        self.received = None

    def split_documents(self, documents):
        self.received = list(documents)
        return list(self.chunks)


class FakeStoreFactory:
    """Capture les arguments transmis a la fabrique de vectorstore."""

    def __init__(self, store="vectorstore"):
        self.store = store
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.store


class TestLireUrls:
    def test_ignore_commentaires_et_lignes_vides(self, tmp_path):
        fichier = tmp_path / "urls.txt"
        fichier.write_text(
            "# documentation RH\n"
            "https://exemple.fr/rse\n"
            "\n"
            "   https://exemple.fr/cnil   \n"
            "#https://exemple.fr/ignoree\n",
            encoding="utf-8",
        )

        assert ingest.lire_urls(fichier) == [
            "https://exemple.fr/rse",
            "https://exemple.fr/cnil",
        ]

    def test_leve_une_erreur_explicite_si_le_fichier_est_absent(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="absent.txt"):
            ingest.lire_urls(tmp_path / "absent.txt")

    def test_le_fichier_d_urls_est_dans_le_dossier_documentaire(self):
        assert ingest.URLS_FILE == "./DRH/DRH-web.txt"
        assert Path(ingest.URLS_FILE).parent == Path(ingest.PDF_DIR)


class TestChargerPdf:
    def test_le_dossier_par_defaut_est_celui_du_plan(self):
        assert ingest.PDF_DIR == "./DRH"

    def test_transmet_le_dossier_au_loader_et_retourne_ses_documents(self):
        documents = [FakeDocument("page 1"), FakeDocument("page 2")]
        dossiers_vus = []

        def loader_factory(dossier):
            dossiers_vus.append(dossier)
            return FakeLoader(documents)

        resultat = ingest.charger_pdf("./DRH", loader_factory=loader_factory)

        assert dossiers_vus == ["./DRH"]
        assert resultat == documents


class TestChargerWeb:
    def test_charge_chaque_url_avec_son_propre_loader(self):
        documents_par_url = {
            "https://a.fr": [FakeDocument("a")],
            "https://b.fr": [FakeDocument("b")],
        }
        urls_vues = []

        def loader_factory(url):
            urls_vues.append(url)
            return FakeLoader(documents_par_url[url])

        resultat = ingest.charger_web(
            ["https://a.fr", "https://b.fr"], loader_factory=loader_factory
        )

        assert urls_vues == ["https://a.fr", "https://b.fr"]
        assert resultat == documents_par_url["https://a.fr"] + documents_par_url["https://b.fr"]

    def test_continue_apres_une_url_en_echec(self, caplog):
        caplog.set_level(logging.WARNING)

        def loader_factory(url):
            if url == "https://cassee.fr":
                return FakeLoader(error=RuntimeError("timeout"))
            return FakeLoader([FakeDocument("contenu")])

        resultat = ingest.charger_web(
            ["https://cassee.fr", "https://ok.fr"], loader_factory=loader_factory
        )

        assert [document.page_content for document in resultat] == ["contenu"]
        assert "https://cassee.fr" in caplog.text

    def test_replie_sur_le_chargement_complet_si_le_contenu_principal_est_vide(
        self, monkeypatch
    ):
        modes = []

        def faux_loader(url, contenu_principal=True):
            modes.append(contenu_principal)
            if contenu_principal:
                return FakeLoader([FakeDocument("   ")])
            return FakeLoader([FakeDocument("contenu complet")])

        monkeypatch.setattr(ingest, "_loader_web_par_defaut", faux_loader)

        documents = ingest._charger_une_url("https://exemple.fr")

        assert [document.page_content for document in documents] == ["contenu complet"]
        assert modes == [True, False]


class TestDecoupage:
    def test_delegue_au_splitter_injecte(self):
        documents = [FakeDocument("texte")]
        morceaux = [FakeDocument("morceau 1"), FakeDocument("morceau 2")]
        splitter = FakeSplitter(morceaux)

        resultat = ingest.decouper_documents(documents, splitter=splitter)

        assert splitter.received == documents
        assert resultat == morceaux

    def test_construire_splitter_respecte_la_taille_maximale(self):
        texte = "Article 1 : la duree legale du travail est de 35 heures.\n\n" * 100

        chunks = ingest.construire_splitter().split_text(texte)

        assert len(chunks) > 1
        assert all(len(chunk) <= 1000 for chunk in chunks)

    def test_construire_splitter_privilegie_les_articles(self):
        splitter = ingest.construire_splitter()

        assert any("Article" in separateur for separateur in splitter._separators)


class TestCategoriserSource:
    def test_classe_la_documentation_odoo(self):
        assert ingest.categoriser_source(
            "https://www.odoo.com/documentation/20.0/applications/hr.html"
        ) == "odoo"

    def test_classe_la_convention_collective(self):
        assert ingest.categoriser_source(
            "DRH/Convention_collective-2026-04-25.pdf"
        ) == "convention"

    def test_classe_les_reponses_officielles_de_la_convention(self):
        assert ingest.categoriser_source(
            "https://code.travail.gouv.fr/contribution/1501-quelles-sont-les-primes-prevues-par-la-convention-collective"
        ) == "convention"

    def test_classe_le_code_du_travail(self):
        assert ingest.categoriser_source(
            "DRH/Code_du_travail-2026-10-08.pdf"
        ) == "code_travail"

    def test_classe_les_referentiels_et_anact(self):
        assert ingest.categoriser_source(
            "DRH/referentiel_gestion_des_ressources_humaines.pdf"
        ) == "referentiel"
        assert ingest.categoriser_source("DRH/ANACT-fiche.pdf") == "referentiel"

    def test_classe_les_autres_sources_web_et_internes(self):
        assert ingest.categoriser_source("https://www.cnil.fr/fr/rh") == "web_rh"
        assert ingest.categoriser_source("note-interne.pdf") == "interne"

    def test_categoriser_documents_ajoute_la_metadonnee(self):
        documents = [
            FakeDocument("a", {"source": "DRH/Convention_collective.pdf"}),
            FakeDocument("b", {"source": "https://www.odoo.com/documentation/20.0/"}),
        ]

        ingest.categoriser_documents(documents)

        assert [document.metadata["categorie"] for document in documents] == [
            "convention",
            "odoo",
        ]


class TestEmbeddingsEtVectorstore:
    def test_creer_embeddings_utilise_nomic_embed_text_sur_ollama_local(self):
        embeddings = ingest.creer_embeddings()

        assert embeddings.model == "nomic-embed-text"
        assert "11434" in str(embeddings.base_url)

    def test_creer_vectorstore_transmet_documents_embeddings_et_persistance(self):
        chunks = [FakeDocument("a"), FakeDocument("b")]
        embeddings = object()
        store_factory = FakeStoreFactory()

        resultat = ingest.creer_vectorstore(
            chunks,
            embeddings,
            persist_directory="./chroma_db",
            store_factory=store_factory,
        )

        assert resultat == "vectorstore"
        assert store_factory.calls == [
            {
                "documents": chunks,
                "embedding": embeddings,
                "persist_directory": "./chroma_db",
            }
        ]

    def test_supprime_la_collection_existante_avant_de_reindexer(self, monkeypatch):
        import sys
        import types

        suppressions = []

        class FakeChroma:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def delete_collection(self):
                suppressions.append(self.kwargs["persist_directory"])

            @classmethod
            def from_documents(cls, **kwargs):
                return "vectorstore"

        module = types.ModuleType("langchain_chroma")
        module.Chroma = FakeChroma
        monkeypatch.setitem(sys.modules, "langchain_chroma", module)

        resultat = ingest.creer_vectorstore(
            [FakeDocument("a")], object(), persist_directory="./chroma_db"
        )

        assert suppressions == ["./chroma_db"]
        assert resultat == "vectorstore"


class TestIngerer:
    @staticmethod
    def _ecrire_urls(tmp_path, contenu):
        fichier = tmp_path / "urls.txt"
        fichier.write_text(contenu, encoding="utf-8")
        return fichier

    def test_fusionne_pdf_et_web_avant_de_vectoriser(self, tmp_path):
        urls = self._ecrire_urls(tmp_path, "https://rh.fr\n")
        documents_pdf = [FakeDocument("pdf")]
        documents_web = [FakeDocument("web")]
        morceaux = [FakeDocument("chunk 1"), FakeDocument("chunk 2")]
        splitter = FakeSplitter(morceaux)
        store_factory = FakeStoreFactory()
        embeddings = object()

        total = ingest.ingerer(
            pdf_dir="./DRH",
            urls_file=urls,
            chroma_dir=tmp_path / "chroma",
            pdf_loader_factory=lambda dossier: FakeLoader(documents_pdf),
            web_loader_factory=lambda url: FakeLoader(documents_web),
            splitter=splitter,
            embeddings=embeddings,
            store_factory=store_factory,
        )

        assert splitter.received == documents_pdf + documents_web
        assert total == 2
        assert store_factory.calls[0]["documents"] == morceaux
        assert store_factory.calls[0]["persist_directory"] == tmp_path / "chroma"
        assert store_factory.calls[0]["embedding"] is embeddings

    def test_arrete_si_aucun_document(self, tmp_path):
        urls = self._ecrire_urls(tmp_path, "# aucune url exploitable\n")
        store_factory = FakeStoreFactory()

        total = ingest.ingerer(
            pdf_dir=tmp_path / "vide",
            urls_file=urls,
            chroma_dir=tmp_path / "chroma",
            pdf_loader_factory=lambda dossier: FakeLoader([]),
            web_loader_factory=lambda url: FakeLoader([]),
            splitter=FakeSplitter([]),
            embeddings=object(),
            store_factory=store_factory,
        )

        assert total == 0
        assert store_factory.calls == []


class TestManifesteIngestion:
    def test_ecrit_la_date_et_le_nombre_de_morceaux(self, tmp_path):
        chemin = ingest.enregistrer_manifeste_ingestion(
            tmp_path / "chroma",
            42,
            date=datetime(2026, 11, 10, 9, 9),
        )

        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        assert contenu["date_ingestion"] == "2026-11-10T09:09:00"
        assert contenu["chunks"] == 42

    def test_l_ingestion_ecrit_le_manifeste(self, tmp_path):
        urls = tmp_path / "urls.txt"
        urls.write_text("https://rh.fr\n", encoding="utf-8")
        chroma_dir = tmp_path / "chroma"

        ingest.ingerer(
            pdf_dir=tmp_path / "vide",
            urls_file=urls,
            chroma_dir=chroma_dir,
            pdf_loader_factory=lambda dossier: FakeLoader([]),
            web_loader_factory=lambda url: FakeLoader([FakeDocument("web")]),
            splitter=FakeSplitter([FakeDocument("chunk")]),
            embeddings=object(),
            store_factory=FakeStoreFactory(),
        )

        contenu = json.loads(
            (chroma_dir / "ingestion.json").read_text(encoding="utf-8")
        )
        assert contenu["chunks"] == 1
        assert "date_ingestion" in contenu


class TestCachePdf:
    @staticmethod
    def _dossier_pdf(tmp_path, noms=("a.pdf",)):
        dossier = tmp_path / "pdf"
        dossier.mkdir()
        for nom in noms:
            (dossier / nom).write_bytes(b"%PDF-1.4 faux contenu")
        return dossier

    @staticmethod
    def _loader_compteur(documents):
        appels = []

        def factory(dossier):
            appels.append(dossier)
            return FakeLoader(documents)

        return appels, factory

    def test_l_empreinte_depend_du_nom_du_dossier(self, tmp_path):
        ancien = tmp_path / "DRH-pdf"
        nouveau = tmp_path / "DRH"
        for dossier in (ancien, nouveau):
            dossier.mkdir()
            pdf = dossier / "a.pdf"
            pdf.write_bytes(b"%PDF-1.4 contenu identique")
            os.utime(pdf, (1_000_000, 1_000_000))

        assert ingest.empreinte_dossier_pdf(ancien) != ingest.empreinte_dossier_pdf(nouveau)

    def test_sans_cache_le_loader_est_appele_a_chaque_fois(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path)
        appels, factory = self._loader_compteur([FakeDocument("page")])

        ingest.charger_pdf(dossier, loader_factory=factory)
        ingest.charger_pdf(dossier, loader_factory=factory)

        assert len(appels) == 2

    def test_ecrit_un_cache_apres_la_premiere_extraction(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path)
        cache = tmp_path / "cache"
        _, factory = self._loader_compteur([FakeDocument("page", {"page": 0})])

        ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)

        empreinte = ingest.empreinte_dossier_pdf(dossier)
        assert (cache / f"pdf-{empreinte}.json").is_file()

    def test_reutilise_le_cache_sans_relancer_le_loader(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path)
        cache = tmp_path / "cache"
        appels, factory = self._loader_compteur(
            [FakeDocument("page 1", {"page": 0}), FakeDocument("page 2", {"page": 1})]
        )

        premier = ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)
        second = ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)

        assert len(appels) == 1
        assert [document.page_content for document in second] == [
            document.page_content for document in premier
        ]
        assert second[0].metadata == {"page": 0}
        assert second[1].metadata == {"page": 1}

    def test_invalide_le_cache_si_un_pdf_change(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path)
        cache = tmp_path / "cache"
        appels, factory = self._loader_compteur([FakeDocument("page")])

        ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)
        (dossier / "a.pdf").write_bytes(b"%PDF-1.4 contenu modifie")
        ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)

        assert len(appels) == 2

    def test_invalide_le_cache_si_un_pdf_est_ajoute(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path, noms=("a.pdf",))
        cache = tmp_path / "cache"
        appels, factory = self._loader_compteur([FakeDocument("page")])

        ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)
        (dossier / "b.pdf").write_bytes(b"%PDF-1.4 autre contenu")
        ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)

        assert len(appels) == 2

    def test_regenere_un_cache_illisible(self, tmp_path):
        dossier = self._dossier_pdf(tmp_path)
        cache = tmp_path / "cache"
        cache.mkdir()
        chemin = cache / f"pdf-{ingest.empreinte_dossier_pdf(dossier)}.json"
        chemin.write_text("{ceci n'est pas du json", encoding="utf-8")
        appels, factory = self._loader_compteur([FakeDocument("page")])

        documents = ingest.charger_pdf(dossier, loader_factory=factory, cache_dir=cache)

        assert len(appels) == 1
        assert [document.page_content for document in documents] == ["page"]
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        assert contenu["documents"][0]["page_content"] == "page"


class TestMain:
    @pytest.mark.parametrize(("total", "code"), [(3, 0), (0, 1)])
    def test_traduit_le_nombre_de_morceaux_en_code_de_sortie(self, monkeypatch, total, code):
        monkeypatch.setattr(ingest, "ingerer", lambda **_kwargs: total)

        assert ingest.main() == code

    def test_retourne_1_si_l_ingestion_echoue(self, monkeypatch):
        def ingestion_en_echec(**_kwargs):
            raise RuntimeError("Ollama indisponible")

        monkeypatch.setattr(ingest, "ingerer", ingestion_en_echec)

        assert ingest.main() == 1

    def test_active_le_cache_pdf_par_defaut(self, monkeypatch):
        recus = {}

        def faux_ingerer(**kwargs):
            recus.update(kwargs)
            return 1

        monkeypatch.setattr(ingest, "ingerer", faux_ingerer)

        ingest.main()

        assert recus["cache_dir"] == ingest.PDF_CACHE_DIR


@pytest.mark.integration
class TestIntegration:
    def test_les_pdf_reels_sont_charges(self):
        assert Path(ingest.PDF_DIR).is_dir()
        assert Path(ingest.URLS_FILE).is_file()
        assert Path(ingest.URLS_FILE).parent == Path(ingest.PDF_DIR)

        documents = ingest.charger_pdf()

        assert documents
        assert all(
            str(document.metadata.get("source", "")).endswith(".pdf")
            for document in documents
        )
        assert all(
            str(document.metadata.get("source", "")).replace("\\", "/").startswith("DRH/")
            for document in documents
        )

    def test_ollama_produit_un_vecteur(self):
        embeddings = ingest.creer_embeddings()
        try:
            vecteur = embeddings.embed_query("la duree legale du travail")
        except Exception as exc:  # noqa: BLE001 - message clair si Ollama est arrete
            pytest.skip(f"Ollama indisponible : {exc}")

        assert vecteur
        assert all(isinstance(valeur, float) for valeur in vecteur)

    def test_chroma_persiste_et_retrouve_un_document(self, tmp_path):
        from langchain_chroma import Chroma
        from langchain_core.documents import Document

        embeddings = ingest.creer_embeddings()
        try:
            embeddings.embed_query("test")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Ollama indisponible : {exc}")

        store = Chroma.from_documents(
            documents=[
                Document(page_content="Le conge maternite est de 16 semaines.")
            ],
            embedding=embeddings,
            persist_directory=str(tmp_path / "chroma"),
        )

        resultats = store.similarity_search("duree du conge maternite", k=1)

        assert resultats
        assert "maternite" in resultats[0].page_content
