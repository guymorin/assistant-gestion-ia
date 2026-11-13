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
