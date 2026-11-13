# tests/test_finances_view.py
import inspect

import finances.view as fin_view


def test_finances_render_contract():
    assert callable(getattr(fin_view, "render", None))


def test_finances_view_mentions_detect_button_and_expander():
    src = inspect.getsource(fin_view)
    assert "Détecter les pièces" in src
    assert "Remplacement des pièces" in src
