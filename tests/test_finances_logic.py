from pathlib import Path

import finances.logic as fin_logic


def test_finances_logic_paths_point_to_finances_module():
    assert str(fin_logic.CHROMA_DIR).replace("\\", "/").endswith("chroma_db/finances")
    assert str(fin_logic.PDF_DIR).replace("\\", "/").endswith("Ingestion/Finances")
    assert str(fin_logic.URLS_FILE).replace("\\", "/").endswith("Ingestion/Finances/Finances-web.txt")


def test_finances_infos_ingestion_empty_when_missing(tmp_path):
    assert fin_logic.infos_ingestion(tmp_path) == {}


def test_finances_repondre_sans_base_ni_documents_retourne_message_ingestion():
    class DummyLLM:
        def invoke(self, prompt):
            return "ne devrait pas etre appele"

    res = fin_logic.repondre(
        "question",
        vectorstore=None,
        llm=DummyLLM(),
        pieces_jointes=None,
        historique=[],
    )
    assert "sources" in res
    assert res["sources"] == []
    assert "ingestion" in res["reponse"].lower()
    assert "finances" in res["reponse"].lower()


def test_finances_prompts_et_raisonnement_sont_adaptes_au_domaine_finances():
    prompt_fr = fin_logic.PROMPTS_PAR_LANGUE["fr"]
    assert "DRH strategique" not in prompt_fr
    assert "financ" in prompt_fr.lower() or "comptab" in prompt_fr.lower() or "tva" in prompt_fr.lower()
    resume = fin_logic.resume_raisonnement([{"nom": "doc.pdf", "type": "pdf", "extraits": [{"texte": "x"}]}], "ok [1]")
    assert "base documentaire RH" not in resume
    assert "Finances" in resume or "financ" in resume.lower()
    apropos = fin_logic.texte_a_propos({})
    assert "base documentaire RH" not in apropos
    assert "Finances" in apropos or "financ" in apropos.lower()
