"""Tests TDD de l'application Streamlit RH (app_rh.py).

Phase RED : ces tests decrivent le comportement attendu de l'interface et
de la logique RAG avant toute implementation. Ils doivent echouer tant que
app_rh.py n'existe pas.

Les tests unitaires n'appellent ni le reseau, ni Ollama, ni un vrai
ChromaDB : le vectorstore et le LLM sont injectes. Les tests d'integration
sont marques et exclus par defaut (voir pytest.ini).
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

import app_rh


class FakeVectorStore:
    """Vectorstore minimal qui enregistre les appels recus."""

    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.calls = []
        self.mmr_calls = []

    def similarity_search(self, question, k=None, filter=None):
        appel = {"question": question, "k": k}
        if filter is not None:
            appel["filter"] = filter
        self.calls.append(appel)
        return list(self.documents)

    def max_marginal_relevance_search(
        self, question, k=None, fetch_k=None, lambda_mult=None
    ):
        self.mmr_calls.append(
            {
                "question": question,
                "k": k,
                "fetch_k": fetch_k,
                "lambda_mult": lambda_mult,
            }
        )
        return list(self.documents[:k])


class FakeLLM:
    """LLM minimal qui enregistre les prompts et retourne une reponse fixe."""

    def __init__(self, contenu="Reponse generee"):
        self.contenu = contenu
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return AIMessage(content=self.contenu)


class FakePiecesJointes:
    """Index de pieces jointes minimal qui enregistre les recherches."""

    def __init__(self, documents=None, documents_complets=None):
        self.documents = list(documents or [])
        self._documents_complets = documents_complets
        self.calls = []

    def rechercher(self, question, k=None):
        self.calls.append({"question": question, "k": k})
        return list(self.documents)

    def documents_complets(self):
        return self._documents_complets


class LLMInterdit:
    """Echoue si l'application appelle le LLM alors qu'aucun document n'a ete trouve."""

    def invoke(self, prompt):  # noqa: ARG002 - signature imposee par l'interface
        raise AssertionError("Le LLM ne doit pas etre appele sans document.")


def document(texte: str, **metadata) -> Document:
    return Document(page_content=texte, metadata=metadata)


class TestNommerSource:
    def test_formate_un_pdf_avec_sa_page(self):
        metadata = {
            "source": "DRH/referentiel_gestion_des_ressources_humaines.pdf",
            "page": "2",
            "page_label": "3",
        }

        assert (
            app_rh.nommer_source(metadata)
            == "referentiel_gestion_des_ressources_humaines.pdf (p. 3)"
        )

    def test_utilise_page_plus_un_si_page_label_est_absent(self):
        metadata = {"source": "DRH/code_du_travail.pdf", "page": 0}

        assert app_rh.nommer_source(metadata) == "code_du_travail.pdf (p. 1)"

    def test_retourne_le_nom_du_pdf_sans_page_si_absente(self):
        metadata = {"source": "DRH/convention_collective.pdf"}

        assert app_rh.nommer_source(metadata) == "convention_collective.pdf"

    def test_retourne_l_url_pour_une_source_web(self):
        metadata = {
            "source": "https://www.cnil.fr/fr/la-gestion-des-ressources-humaines"
        }

        assert (
            app_rh.nommer_source(metadata)
            == "https://www.cnil.fr/fr/la-gestion-des-ressources-humaines"
        )

    def test_retourne_un_libelle_explicite_sans_source(self):
        assert app_rh.nommer_source({}) == "source inconnue"

    def test_prefixe_une_piece_jointe_avec_sa_page(self):
        metadata = {
            "source": "note.pdf",
            "page": "0",
            "page_label": "1",
            "origine": "piece_jointe",
        }

        assert app_rh.nommer_source(metadata) == "Piece jointe : note.pdf (p. 1)"


class TestExtraireSources:
    def test_deduplique_par_document_et_page_en_conservant_l_ordre(self):
        documents = [
            document("extrait a1", source="DRH/a.pdf", page="1", page_label="2"),
            document("extrait b1", source="https://exemple.fr/rh"),
            document("extrait a2", source="DRH/a.pdf", page="1", page_label="2"),
        ]

        sources = app_rh.extraire_sources(documents)

        assert [source["nom"] for source in sources] == [
            "a.pdf (p. 2)",
            "https://exemple.fr/rh",
        ]
        assert sources[0]["extraits"] == ["extrait a1", "extrait a2"]
        assert sources[1]["extraits"] == ["extrait b1"]

    def test_distingue_les_sources_pdf_et_web(self):
        documents = [
            document("texte", source="DRH/a.pdf", page="0"),
            document("texte", source="https://exemple.fr/rh"),
        ]

        sources = app_rh.extraire_sources(documents)

        assert [source["type"] for source in sources] == ["pdf", "web"]

    def test_retourne_une_liste_vide_sans_document(self):
        assert app_rh.extraire_sources([]) == []

    def test_marque_une_source_comme_piece_jointe(self):
        documents = [
            document("texte", source="note.txt", origine="piece_jointe"),
        ]

        sources = app_rh.extraire_sources(documents)

        assert sources[0]["type"] == "piece_jointe"


class TestConstruireContexte:
    def test_numerote_les_extraits_avec_leur_source(self):
        documents = [
            document(
                "Le conge maternite est de 16 semaines.",
                source="DRH/a.pdf",
                page="2",
                page_label="3",
            ),
            document("Le teletravail est encadre.", source="https://exemple.fr/rh"),
        ]

        attendu = (
            "[1] Source : a.pdf (p. 3)\n"
            "Le conge maternite est de 16 semaines.\n\n"
            "[2] Source : https://exemple.fr/rh\n"
            "Le teletravail est encadre."
        )

        assert app_rh.construire_contexte(documents) == attendu

    def test_retourne_une_chaine_vide_sans_document(self):
        assert app_rh.construire_contexte([]) == ""


class TestConstruirePrompt:
    def test_contient_la_question_le_contexte_et_la_consigne_anti_hallucination(self):
        documents = [
            document(
                "Le conge maternite est de 16 semaines.",
                source="DRH/a.pdf",
                page="0",
                page_label="1",
            )
        ]

        prompt = app_rh.construire_prompt("Quelle est la duree du conge maternite ?", documents)

        assert "Quelle est la duree du conge maternite ?" in prompt
        assert "Le conge maternite est de 16 semaines." in prompt
        assert "Utilise uniquement le CONTEXTE" in prompt
        assert "N'invente aucune information" in prompt
        assert "[1] Source : a.pdf (p. 1)" in prompt

    def test_decrit_la_couverture_rh_et_la_convention_restauration_rapide(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt("Comment recruter ?", documents)

        assert "Odoo" in prompt
        assert "IDCC 1501" in prompt
        assert "point par point" in prompt
        assert "HISTORIQUE RECENT" in prompt
        assert "Chaque affirmation factuelle" in prompt
        assert "non precise dans les sources" in prompt
        assert "metropole / Mayotte" in prompt
        assert "Termine la reponse par une ligne" not in prompt

    def test_demande_une_reponse_en_francais_par_defaut(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt("Quelle est la duree du conge ?", documents)

        assert app_rh.LANGUES["fr"]["consigne"] in prompt

    @pytest.mark.parametrize(
        "langue",
        ["fr", "en", "ko"],
    )
    def test_transmet_la_langue_demandee_au_llm(self, langue):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt(
            "Quelle est la duree du conge ?", documents, langue=langue
        )

        assert app_rh.LANGUES[langue]["consigne"] in prompt

    def test_redige_le_prompt_anglais_en_anglais(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt(
            "What is the notice period?", documents, langue="en"
        )

        assert "Rules:" in prompt
        assert "RECENT HISTORY:" in prompt
        assert "ANSWER (in English only):" in prompt
        assert "Regles :" not in prompt

    def test_redige_le_prompt_coreen_en_coreen(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt(
            "휴가 기간은 얼마입니까?", documents, langue="ko"
        )

        assert "규칙:" in prompt
        assert "최근 대화 기록:" in prompt
        assert "답변(한국어로만):" in prompt
        assert "Regles :" not in prompt

    def test_rep_une_langue_inconnue_par_le_francais(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]

        prompt = app_rh.construire_prompt(
            "Quelle est la duree du conge ?", documents, langue="xx"
        )

        assert app_rh.LANGUES["fr"]["consigne"] in prompt

    def test_transmet_l_historique_recent_au_llm(self):
        documents = [document("texte", source="DRH/a.pdf", page="0")]
        historique = [
            {"role": "user", "content": "Quelle est la duree du conge maternite ?"},
            {"role": "assistant", "content": "Le conge maternite dure 16 semaines."},
        ]

        prompt = app_rh.construire_prompt("Et pour un CDD ?", documents, historique=historique)

        assert "UTILISATEUR : Quelle est la duree du conge maternite ?" in prompt
        assert "ASSISTANT : Le conge maternite dure 16 semaines." in prompt
        assert "QUESTION : Et pour un CDD ?" in prompt


class TestConstruireHistorique:
    def test_retourne_aucun_sans_historique(self):
        assert app_rh.construire_historique(None) == "Aucun."
        assert app_rh.construire_historique([]) == "Aucun."

    def test_formate_les_echanges_dans_l_ordre_chronologique(self):
        historique = [
            {"role": "user", "content": "Quelle est la duree du conge ?"},
            {"role": "assistant", "content": "16 semaines."},
        ]

        assert app_rh.construire_historique(historique) == (
            "UTILISATEUR : Quelle est la duree du conge ?\n"
            "ASSISTANT : 16 semaines."
        )

    def test_garde_les_messages_les_plus_recents(self):
        historique = [
            {"role": "user", "content": f"question {numero}"} for numero in range(10)
        ]

        texte = app_rh.construire_historique(historique, max_messages=2)

        assert "question 8" in texte
        assert "question 9" in texte
        assert "question 7" not in texte


class TestQuestionPourRecherche:
    def test_sans_historique_conserve_la_question(self):
        assert app_rh.question_pour_recherche("Quelle est la duree du conge ?") == (
            "Quelle est la duree du conge ?"
        )

    def test_rattache_une_relance_courte_a_la_question_precedente(self):
        historique = [
            {"role": "user", "content": "Quelle est la duree du conge maternite ?"},
            {"role": "assistant", "content": "16 semaines."},
        ]

        assert app_rh.question_pour_recherche("et pour un CDD ?", historique) == (
            "Quelle est la duree du conge maternite ? et pour un CDD ?"
        )

    def test_ne_modifie_pas_une_question_autonome(self):
        historique = [
            {"role": "user", "content": "Quelle est la duree du conge maternite ?"}
        ]
        question = (
            "Comment calculer l'indemnite de licenciement pour un salarie de la "
            "restauration rapide ?"
        )

        assert app_rh.question_pour_recherche(question, historique) == question


class TestRechercher:
    def test_utilise_mmr_avec_le_k_par_defaut(self):
        documents = [document("a", source="DRH/a.pdf")]
        vectorstore = FakeVectorStore(documents)

        resultat = app_rh.rechercher("question rh", vectorstore)

        assert resultat == documents
        assert vectorstore.calls == []
        assert vectorstore.mmr_calls == [
            {
                "question": "question rh",
                "k": app_rh.TOP_K * app_rh.FACTEUR_CANDIDATS,
                "fetch_k": max(
                    app_rh.FETCH_K,
                    app_rh.TOP_K * app_rh.FACTEUR_CANDIDATS * 4,
                ),
                "lambda_mult": app_rh.MMR_LAMBDA,
            }
        ]

    def test_respecte_un_k_personnalise(self):
        vectorstore = FakeVectorStore([])

        app_rh.rechercher("question rh", vectorstore, k=7)

        assert vectorstore.mmr_calls[0]["k"] == 7 * app_rh.FACTEUR_CANDIDATS

    def test_replie_sur_la_similarite_si_mmr_est_indisponible(self):
        class VectorStoreSansMmr:
            def __init__(self):
                self.calls = []

            def similarity_search(self, question, k=None):
                self.calls.append({"question": question, "k": k})
                return ["document"]

        vectorstore = VectorStoreSansMmr()

        assert app_rh.rechercher("question rh", vectorstore) == ["document"]
        assert vectorstore.calls == [
            {
                "question": "question rh",
                "k": app_rh.TOP_K * app_rh.FACTEUR_CANDIDATS,
            }
        ]


class TestCategorieQuestion:
    def test_detecte_une_question_odoo(self):
        assert app_rh.categorie_question("Comment paramétrer les congés dans Odoo ?") == (
            app_rh.CATEGORIE_ODOO
        )

    def test_detecte_une_question_restauration_rapide(self):
        assert app_rh.categorie_question(
            "Quelle prime pour la restauration rapide ?"
        ) == app_rh.CATEGORIE_CONVENTION

    def test_retourne_none_pour_une_question_generale(self):
        assert app_rh.categorie_question("Quelle est la duree du travail ?") is None


class TestModuleOdoo:
    def test_detecte_le_module_conges(self):
        assert app_rh.module_odoo("Comment poser un conge dans Odoo ?") == "time_off"

    def test_detecte_le_module_paie(self):
        assert app_rh.module_odoo("Ou se trouve la paie dans Odoo ?") == "payroll"

    def test_retourne_none_sans_module_reconnu(self):
        assert app_rh.module_odoo("Comment creer une societe dans Odoo ?") is None


class TestRoutageRecherche:
    def test_question_odoo_filtre_la_documentation_odoo(self):
        documents = [document("odoo", source="https://www.odoo.com/doc")]
        vectorstore = FakeVectorStore(documents)

        resultat = app_rh.rechercher("Comment gerer les conges dans Odoo ?", vectorstore)

        assert resultat == documents
        assert vectorstore.calls[0]["filter"] == {
            "source": app_rh.SOURCES_ODOO["time_off"]
        }
        assert vectorstore.calls[-1]["filter"] == {
            "categorie": app_rh.CATEGORIE_ODOO
        }
        assert vectorstore.mmr_calls == []

    def test_question_odoo_interroge_directement_la_source_du_module(self):
        document_time_off = document(
            "conges", source=app_rh.SOURCES_ODOO["time_off"]
        )
        vectorstore = FakeVectorStore([document_time_off])

        resultat = app_rh.rechercher("Comment gerer les conges dans Odoo ?", vectorstore)

        assert resultat == [document_time_off]
        assert vectorstore.calls[0]["filter"] == {
            "source": app_rh.SOURCES_ODOO["time_off"]
        }

    def test_question_odoo_priorise_le_module_attendu(self):
        documents = [
            document("paie", source="https://www.odoo.com/documentation/20.0/applications/hr/payroll.html"),
            document("conges", source="https://www.odoo.com/documentation/20.0/applications/hr/time_off.html"),
        ]
        vectorstore = FakeVectorStore(documents)

        resultat = app_rh.rechercher("Comment gerer les conges dans Odoo ?", vectorstore)

        assert resultat[0].metadata["source"].endswith("time_off.html")

    def test_question_restauration_ajoute_la_convention_collective(self):
        documents = [document("convention", source="DRH/Convention_collective.pdf")]
        vectorstore = FakeVectorStore(documents)

        app_rh.rechercher("Quelle prime pour la restauration rapide ?", vectorstore)

        assert vectorstore.calls[0]["filter"] == {
            "categorie": app_rh.CATEGORIE_CONVENTION
        }
        assert vectorstore.mmr_calls


class TestRetraitHorsSujet:
    def test_retire_la_cnil_sur_une_question_non_rgpd(self):
        documents = [
            document("cnil", source="https://www.cnil.fr/fr/reglement"),
            document("maladie", source="https://www.service-public.fr/F303"),
        ]
        vectorstore = FakeVectorStore(documents)

        resultat = app_rh.rechercher(
            "Quels sont les droits en cas d'arret maladie ?", vectorstore
        )

        assert [source["source"] for source in app_rh.extraire_sources(resultat)] == [
            "https://www.service-public.fr/F303"
        ]

    def test_garde_la_cnil_pour_une_question_rgpd(self):
        documents = [
            document("cnil", source="https://www.cnil.fr/fr/reglement"),
            document("maladie", source="https://www.service-public.fr/F303"),
        ]
        vectorstore = FakeVectorStore(documents)

        resultat = app_rh.rechercher(
            "Quelles sont les regles RGPD pour les donnees RH ?", vectorstore
        )

        assert [source["source"] for source in app_rh.extraire_sources(resultat)] == [
            "https://www.cnil.fr/fr/reglement",
            "https://www.service-public.fr/F303",
        ]


class TestParatexteConvention:
    def test_detecte_une_page_de_garde(self):
        document_garde = document(
            "Convention Collective IDCC 1501 Texte integral",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="0",
        )

        assert app_rh._est_paratexte_convention(document_garde) is True

    def test_detecte_un_sommaire(self):
        sommaire = document(
            "Sommaire Avenant n 53 .... 135",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="4",
        )

        assert app_rh._est_paratexte_convention(sommaire) is True

    def test_detecte_un_arrete_d_extension_en_fin_de_document(self):
        arrete = document(
            "Article 1 Sont rendues obligatoires...",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="239",
        )

        assert app_rh._est_paratexte_convention(arrete) is True

    def test_conserve_un_article_de_la_convention(self):
        article = document(
            "Article 12 - Prime d'anciennete. Les salaries beneficient...",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="80",
        )

        assert app_rh._est_paratexte_convention(article) is False

    def test_conserve_les_documents_hors_convention(self):
        autre = document(
            "Le SMIC horaire est de 12,31 euros.",
            source="DRH/Code_du_travail-2026-10-08.pdf",
            page="0",
        )

        assert app_rh._est_paratexte_convention(autre) is False

    def test_la_recherche_hybride_ecarte_le_paratexte(self):
        paratexte = document(
            "Sommaire de la convention",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="4",
            categorie="convention",
        )
        article = document(
            "Article 12 - Prime d'anciennete",
            source="DRH/Convention_collective-2026-04-25.pdf",
            page="80",
            categorie="convention",
        )
        vectorstore = FakeVectorStore([paratexte, article])

        resultat = app_rh.rechercher("prime anciennete restauration rapide", vectorstore)

        assert article in resultat
        assert paratexte not in resultat


class TestCiteDesSources:
    def test_detecte_une_citation_numerotee(self):
        assert app_rh.cite_des_sources("La prime est de 215 euros [1].") is True

    def test_detecte_plusieurs_citations(self):
        assert app_rh.cite_des_sources("Voir [1] et [2].") is True

    def test_retourne_faux_sans_citation(self):
        assert app_rh.cite_des_sources("La prime est de 215 euros.") is False

    def test_retourne_faux_pour_une_reponse_vide(self):
        assert app_rh.cite_des_sources("") is False


class FauxStreamlit:
    """Enregistre les appels d'affichage pour verifier la mise en page."""

    def __init__(self):
        self.appels = []

    def markdown(self, texte, **kwargs):  # noqa: ARG002
        self.appels.append(("markdown", texte))

    def caption(self, texte):
        self.appels.append(("caption", texte))

    def divider(self):
        self.appels.append(("divider",))

    def expander(self, libelle, expanded=None):
        self.appels.append(("expander", libelle, expanded))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestResumeRaisonnement:
    def _sources(self):
        return [
            {
                "nom": "a.pdf (p. 1)",
                "type": "pdf",
                "source": "DRH/a.pdf",
                "page": 0,
                "extraits": ["Le conge maternite est de 16 semaines.", "Il est de 16 semaines."],
            },
            {
                "nom": "note.pdf (p. 1)",
                "type": "piece_jointe",
                "source": "note.pdf",
                "page": 0,
                "extraits": ["Le conge maternite est de 20 semaines."],
            },
        ]

    def test_resume_le_nombre_d_extraits_et_de_sources(self):
        resume = app_rh.resume_raisonnement(self._sources())

        assert "3 extraits" in resume
        assert "2 sources" in resume
        assert "base documentaire RH" in resume
        assert "pieces jointes" in resume

    def test_resume_liste_les_sources_dans_l_ordre_du_contexte(self):
        resume = app_rh.resume_raisonnement(self._sources())

        assert "[1] a.pdf (p. 1)" in resume
        assert "[2] note.pdf (p. 1)" in resume

    def test_resume_signale_une_reponse_sans_citation(self):
        resume = app_rh.resume_raisonnement(
            self._sources(), reponse="Le conge dure 16 semaines."
        )

        assert "ne cite pas" in resume

    def test_resume_ne_signale_rien_quand_la_reponse_cite_ses_sources(self):
        resume = app_rh.resume_raisonnement(
            self._sources(), reponse="Le conge dure 16 semaines [1]."
        )

        assert "ne cite pas" not in resume

    def test_resume_vide_sans_source(self):
        assert app_rh.resume_raisonnement([]) == ""


class TestAfficherSources:
    def _sources(self):
        return [
            {
                "nom": "a.pdf (p. 1)",
                "type": "pdf",
                "source": "DRH/a.pdf",
                "page": 0,
                "extraits": ["Le conge maternite est de 16 semaines."],
            }
        ]

    def test_regroupe_les_sources_dans_un_volet_replie(self):
        st = FauxStreamlit()

        app_rh._afficher_sources(st, self._sources())

        assert st.appels[0][0] == "expander"
        assert st.appels[0][1] == "Détails"
        assert st.appels[0][2] in (None, False)

    def test_n_affiche_rien_en_dehors_du_volet(self):
        st = FauxStreamlit()

        app_rh._afficher_sources(st, self._sources())

        positions = [index for index, appel in enumerate(st.appels) if appel[0] == "expander"]
        assert positions == [0]

    def test_affiche_l_avertissement_dans_le_volet(self):
        st = FauxStreamlit()

        app_rh._afficher_sources(st, self._sources(), avertissement="⚠️ Sources non citees")

        assert ("caption", "⚠️ Sources non citees") in st.appels

    def test_affiche_un_resume_du_raisonnement_et_des_sources(self):
        st = FauxStreamlit()

        app_rh._afficher_sources(st, self._sources())

        textes = " ".join(
            appel[1] for appel in st.appels if len(appel) > 1 and isinstance(appel[1], str)
        )
        assert "Raisonnement" in textes
        assert "a.pdf (p. 1)" in textes
        assert "1 extrait" in textes

    def test_ne_cree_pas_de_volet_sans_source(self):
        st = FauxStreamlit()

        app_rh._afficher_sources(st, [])

        assert st.appels == []


class TestCompletionSources:
    class VectorStoreAvecGet(FakeVectorStore):
        def __init__(self, documents, morceaux):
            super().__init__(documents)
            self.morceaux = morceaux
            self.get_calls = []

        def get(self, where=None, limit=None, include=None):  # noqa: ARG002
            source = (where or {}).get("source")
            self.get_calls.append(source)
            documents = list(self.morceaux.get(source, []))
            if limit is not None:
                documents = documents[:limit]
            return {
                "documents": [document.page_content for document in documents],
                "metadatas": [document.metadata for document in documents],
            }

    def test_complete_une_source_courte_avec_tous_ses_morceaux(self):
        source = "https://code.travail.gouv.fr/contribution/1501-primes"
        morceaux = [
            document("Debut de la reponse sur les primes.", source=source),
            document("Tableau : 215 euros, 285 euros, 365 euros.", source=source),
            document("Fin de la reponse.", source=source),
        ]
        selection = [morceaux[0], morceaux[2]]
        vectorstore = self.VectorStoreAvecGet(selection, {source: morceaux})

        resultat = app_rh._completer_sources(selection, vectorstore)

        assert [doc.page_content for doc in resultat] == [
            "Debut de la reponse sur les primes.",
            "Tableau : 215 euros, 285 euros, 365 euros.",
            "Fin de la reponse.",
        ]

    def test_ignore_une_source_trop_volumineuse(self):
        source = "DRH/Code_du_travail-2026-10-08.pdf"
        morceaux = [
            document(f"article {numero}", source=source) for numero in range(20)
        ]
        selection = [morceaux[0], morceaux[1]]
        vectorstore = self.VectorStoreAvecGet(selection, {source: morceaux})

        resultat = app_rh._completer_sources(selection, vectorstore, max_morceaux=10)

        assert resultat == selection

    def test_sans_methode_get_conserve_la_selection(self):
        selection = [document("texte", source="a.pdf")]

        assert app_rh._completer_sources(selection, FakeVectorStore(selection)) == (
            selection
        )

    def test_ne_complete_pas_plus_de_deux_sources(self):
        source_a = "a.pdf"
        source_b = "b.pdf"
        source_c = "c.pdf"
        morceaux_a = [document("a1", source=source_a), document("a2", source=source_a)]
        morceaux_b = [document("b1", source=source_b), document("b2", source=source_b)]
        morceaux_c = [document("c1", source=source_c), document("c2", source=source_c)]
        selection = [morceaux_a[0], morceaux_b[0], morceaux_c[0]]
        vectorstore = self.VectorStoreAvecGet(
            selection,
            {source_a: morceaux_a, source_b: morceaux_b, source_c: morceaux_c},
        )

        resultat = app_rh._completer_sources(selection, vectorstore, max_sources=2)

        assert [doc.page_content for doc in resultat] == [
            "a1",
            "a2",
            "b1",
            "b2",
            "c1",
        ]


class TestRepondre:
    def test_sans_document_repond_sans_appeler_le_llm(self):
        resultat = app_rh.repondre("question hors base", FakeVectorStore([]), LLMInterdit())

        assert "Je ne trouve pas" in resultat["reponse"]
        assert resultat["sources"] == []

    def test_avec_documents_transmet_le_prompt_et_retourne_la_reponse(self):
        documents = [
            document(
                "Le conge maternite est de 16 semaines.",
                source="DRH/a.pdf",
                page="0",
                page_label="1",
            )
        ]
        llm = FakeLLM("Le conge maternite dure 16 semaines.")

        resultat = app_rh.repondre("Quelle est la duree du conge maternite ?", FakeVectorStore(documents), llm)

        assert resultat["reponse"] == "Le conge maternite dure 16 semaines."
        assert [source["nom"] for source in resultat["sources"]] == ["a.pdf (p. 1)"]
        assert len(llm.prompts) == 1
        assert "Quelle est la duree du conge maternite ?" in llm.prompts[0]
        assert "Le conge maternite est de 16 semaines." in llm.prompts[0]

    def test_enrichit_la_recherche_avec_la_question_precedente(self):
        documents = [document("Le CDD est encadre.", source="DRH/a.pdf", page="0")]
        vectorstore = FakeVectorStore(documents)
        llm = FakeLLM("Le CDD est encadre.")
        historique = [
            {"role": "user", "content": "Quelle est la duree du conge maternite ?"},
            {"role": "assistant", "content": "16 semaines."},
        ]

        app_rh.repondre("et pour un CDD ?", vectorstore, llm, historique=historique)

        assert vectorstore.mmr_calls[0]["question"] == (
            "Quelle est la duree du conge maternite ? et pour un CDD ?"
        )
        assert "QUESTION : et pour un CDD ?" in llm.prompts[0]

    def test_transmet_la_langue_choisie_au_prompt(self):
        documents = [document("Le CDD est encadre.", source="DRH/a.pdf", page="0")]
        llm = FakeLLM("The fixed-term contract is framed.")

        app_rh.repondre(
            "Is a fixed-term contract allowed?",
            FakeVectorStore(documents),
            llm,
            langue="en",
        )

        assert app_rh.LANGUES["en"]["consigne"] in llm.prompts[0]

    @pytest.mark.parametrize("langue", ["en", "ko"])
    def test_message_sans_resultat_traduit(self, langue):
        resultat = app_rh.repondre(
            "question hors base", FakeVectorStore([]), LLMInterdit(), langue=langue
        )

        assert resultat["reponse"] == app_rh.MESSAGES_SANS_RESULTAT[langue]
        assert resultat["sources"] == []


class TestRepondreAvecPiecesJointes:
    def _document_piece_jointe(self):
        return document(
            "Le conge maternite est de 20 semaines.",
            source="note.pdf",
            page="0",
            page_label="1",
            origine="piece_jointe",
        )

    def test_repond_uniquement_a_partir_des_pieces_jointes(self):
        base = [
            document(
                "Le teletravail est encadre.",
                source="DRH/a.pdf",
                page="0",
                page_label="1",
            )
        ]
        pieces = FakePiecesJointes([self._document_piece_jointe()])
        vectorstore = FakeVectorStore(base)
        llm = FakeLLM("Le conge dure 20 semaines.")

        resultat = app_rh.repondre(
            "Quelle est la duree du conge maternite ?",
            vectorstore,
            llm,
            pieces_jointes=pieces,
        )

        assert resultat["reponse"] == "Le conge dure 20 semaines."
        assert [source["nom"] for source in resultat["sources"]] == [
            "Piece jointe : note.pdf (p. 1)",
        ]
        assert pieces.calls == [
            {"question": "Quelle est la duree du conge maternite ?", "k": app_rh.TOP_K}
        ]
        assert vectorstore.calls == []
        assert vectorstore.mmr_calls == []
        prompt = llm.prompts[0]
        assert "Le conge maternite est de 20 semaines." in prompt
        assert "Le teletravail est encadre." not in prompt

    def test_utilise_la_base_rh_quand_aucune_piece_jointe_n_est_jointe(self):
        base = [
            document(
                "Le teletravail est encadre.",
                source="DRH/a.pdf",
                page="0",
                page_label="1",
            )
        ]
        vectorstore = FakeVectorStore(base)
        llm = FakeLLM("Le teletravail est encadre.")

        resultat = app_rh.repondre(
            "Le teletravail est-il encadre ?",
            vectorstore,
            llm,
            pieces_jointes=FakePiecesJointes([]),
        )

        assert [source["nom"] for source in resultat["sources"]] == ["a.pdf (p. 1)"]
        assert vectorstore.mmr_calls == [
            {
                "question": "Le teletravail est-il encadre ?",
                "k": app_rh.TOP_K * app_rh.FACTEUR_CANDIDATS,
                "fetch_k": max(
                    app_rh.FETCH_K,
                    app_rh.TOP_K * app_rh.FACTEUR_CANDIDATS * 4,
                ),
                "lambda_mult": app_rh.MMR_LAMBDA,
            }
        ]
        assert "Le teletravail est encadre." in llm.prompts[0]

    def test_repond_avec_les_pieces_jointes_sans_base_vectorielle(self):
        pieces = FakePiecesJointes([self._document_piece_jointe()])
        llm = FakeLLM("Le conge dure 20 semaines.")

        resultat = app_rh.repondre(
            "Quelle est la duree du conge ?", None, llm, pieces_jointes=pieces
        )

        assert resultat["reponse"] == "Le conge dure 20 semaines."
        assert [source["nom"] for source in resultat["sources"]] == [
            "Piece jointe : note.pdf (p. 1)"
        ]

    def test_sans_base_ni_piece_jointe_ne_sollicite_pas_le_llm(self):
        resultat = app_rh.repondre("question hors base", None, LLMInterdit(), pieces_jointes=FakePiecesJointes([]))

        assert "Je ne trouve pas" in resultat["reponse"]
        assert resultat["sources"] == []

    def test_envoie_tous_les_extraits_quand_la_piece_jointe_est_courte(self):
        fragments = [
            document(
                "Salaire brut : 3 000 euros.",
                source="bulletin.pdf",
                page="0",
                page_label="1",
                origine="piece_jointe",
            ),
            document(
                "Net a payer : 2 400 euros.",
                source="bulletin.pdf",
                page="0",
                page_label="1",
                origine="piece_jointe",
            ),
        ]
        pieces = FakePiecesJointes(
            documents=[fragments[0]], documents_complets=fragments
        )
        llm = FakeLLM("Le net a payer est de 2 400 euros.")

        resultat = app_rh.repondre(
            "Quel est le net a payer ?", None, llm, pieces_jointes=pieces
        )

        assert resultat["reponse"] == "Le net a payer est de 2 400 euros."
        assert [source["nom"] for source in resultat["sources"]] == [
            "Piece jointe : bulletin.pdf (p. 1)"
        ]
        assert pieces.calls == []
        assert "Salaire brut : 3 000 euros." in llm.prompts[0]
        assert "Net a payer : 2 400 euros." in llm.prompts[0]

    def test_revient_a_la_recherche_quand_la_piece_jointe_est_trop_longue(self):
        document_piece_jointe = self._document_piece_jointe()
        pieces = FakePiecesJointes(
            documents=[document_piece_jointe], documents_complets=None
        )
        llm = FakeLLM("Le conge dure 20 semaines.")

        app_rh.repondre(
            "Quelle est la duree du conge maternite ?",
            None,
            llm,
            pieces_jointes=pieces,
        )

        assert pieces.calls == [
            {"question": "Quelle est la duree du conge maternite ?", "k": app_rh.TOP_K}
        ]
        assert "Le conge maternite est de 20 semaines." in llm.prompts[0]


class TestCreerLlm:
    def test_configure_llama3_2_sur_ollama_local(self):
        llm = app_rh.creer_llm()

        assert llm.model == "llama3.2"
        assert "11434" in str(llm.base_url)
        assert llm.temperature == 0.0


class FakeStreamlit:
    """Capture les appels d'affichage de Streamlit."""

    def __init__(self):
        self.markdowns = []

    def markdown(self, body, **kwargs):  # noqa: ARG002 - signature imposee
        self.markdowns.append(body)


class TestStyle:
    def test_ne_personnalise_pas_l_animation_de_chargement(self):
        st = FakeStreamlit()

        app_rh._style(st)

        css = "\n".join(st.markdowns)
        assert '[data-testid="stSpinnerIcon"]' not in css
        assert '[data-testid="stStatusWidgetRunningIcon"]' not in css
        assert "points-clignotants" not in css
        assert 'content: "..."' not in css

    def test_masque_l_option_record_screen_du_menu(self):
        st = FakeStreamlit()

        app_rh._style(st)

        css = "\n".join(st.markdowns)
        assert '[data-testid="stMainMenuItem-recordScreencast"]' in css
        assert "display: none" in css


class TestInfosIngestion:
    def test_lit_le_manifeste_ecrit_par_l_ingestion(self, tmp_path):
        manifeste = tmp_path / "ingestion.json"
        manifeste.write_text(
            json.dumps(
                {
                    "date_ingestion": "2026-11-09T18:30:00",
                    "chunks": 15619,
                }
            ),
            encoding="utf-8",
        )

        infos = app_rh.infos_ingestion(tmp_path)

        assert infos["date"] == datetime(2026, 11, 9, 18, 30)
        assert infos["chunks"] == 15619

    def test_repli_sur_la_date_du_fichier_chroma_sans_manifeste(self, tmp_path):
        base = tmp_path / "chroma.sqlite3"
        base.write_bytes(b"")
        os.utime(base, (1700000000, 1700000000))

        infos = app_rh.infos_ingestion(tmp_path)

        assert infos["date"] == datetime.fromtimestamp(1700000000)
        assert infos["chunks"] is None

    def test_retourne_vide_sans_manifeste_ni_base(self, tmp_path):
        assert app_rh.infos_ingestion(tmp_path) == {}

    def test_ignore_un_manifeste_illisible(self, tmp_path):
        (tmp_path / "ingestion.json").write_text("{invalide", encoding="utf-8")

        assert app_rh.infos_ingestion(tmp_path) == {}


class TestTexteAPropos:
    def test_affiche_la_version_la_date_et_le_nombre_d_extraits(self):
        infos = {"date": datetime(2026, 11, 9, 18, 30), "chunks": 15619}

        texte = app_rh.texte_a_propos(infos, version="1.1.0")

        assert "1.1.0" in texte
        assert "09/11/2026 à 18:30" in texte
        assert "15 619" in texte
        assert app_rh.LLM_MODEL in texte
        assert app_rh.EMBEDDING_MODEL in texte

    def test_signale_une_date_d_ingestion_inconnue(self):
        texte = app_rh.texte_a_propos({})

        assert app_rh.APP_VERSION in texte
        assert "inconnue" in texte


@pytest.mark.integration
class TestIntegration:
    def test_la_base_chroma_repond_a_une_question_rh(self):
        from ingest import creer_embeddings

        vectorstore = app_rh.creer_vectorstore(embeddings=creer_embeddings())

        documents = app_rh.rechercher("duree legale du travail", vectorstore, k=3)

        assert documents
        assert all(doc.page_content.strip() for doc in documents)

    def test_llama_genere_une_reponse_avec_ses_sources(self):
        from ingest import creer_embeddings

        vectorstore = app_rh.creer_vectorstore(embeddings=creer_embeddings())
        llm = app_rh.creer_llm()

        try:
            resultat = app_rh.repondre(
                "Quelle est la duree legale du travail ?", vectorstore, llm, k=3
            )
        except Exception as exc:  # noqa: BLE001 - message clair si Ollama est arrete
            pytest.skip(f"Ollama indisponible : {exc}")

        assert resultat["reponse"].strip()
        assert resultat["sources"]
