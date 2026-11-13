# tests/test_finances_view.py
import inspect

import finances.view as fin_view


def test_finances_render_contract():
    assert callable(getattr(fin_view, "render", None))


def test_finances_view_mentions_detect_button_and_expander():
    src = inspect.getsource(fin_view)
    assert "Détecter les pièces" in src
    assert "Remplacement des pièces" in src


def test_finances_view_has_submenu_dynamic_title_and_qr_texts():
    src = inspect.getsource(fin_view)
    assert "Q&R" in src
    assert "Déclaration de TVA" in src
    assert "fin_sous_vue" in src
    assert 'header("Finances")' not in src and "header('Finances')" not in src
    assert "Posez vos questions Finances : les reponses sont fondees sur les documents indexes, avec leurs sources." in src
    assert "⚠️ Reponse generee automatiquement : verifiez toujours les sources affichees avant toute decision administrative et financière." in src
    assert "chat_input" in src
