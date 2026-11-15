# tests/test_portail_shell.py
from types import SimpleNamespace

from shared.info import InfoItem
from shared.ui import init_global_state, run_portail


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.errors = []
        self.captions = []
        self.markdowns = []

    def error(self, msg):
        self.errors.append(msg)

    def caption(self, msg):
        self.captions.append(msg)

    def markdown(self, msg, *a, **k):
        self.markdowns.append(msg)


def test_init_global_state_defaults():
    st = SimpleNamespace(session_state={})
    init_global_state(st.session_state)
    assert st.session_state["vue_active"] in ("rh", "finances")
    assert "langue" in st.session_state


def test_run_portail_renders_footer_even_if_view_raises(monkeypatch):
    st = FakeSt()
    init_global_state(st.session_state)
    st.session_state["vue_active"] = "rh"

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    st.container = lambda: _Col()
    st.columns = lambda *a, **k: (_Col(), _Col())

    def boom(_ctx):
        raise RuntimeError("boom")

    rendered = {}
    monkeypatch.setattr(
        "shared.ui.render_header",
        lambda st_obj: st_obj.session_state.__setitem__("vue_active", "rh") or "rh",
    )

    def fake_info_items(_st, items, *, title="Informations", show_divider=True):
        rendered["items"] = items

    monkeypatch.setattr("shared.ui._render_info_items", fake_info_items)

    run_portail({"rh": boom}, st.session_state, st)
    assert st.errors  # erreur affichée
    assert rendered["items"]  # infos quand même rendues dans la barre latérale droite


def test_theme_css_applique_le_mode_choisi():
    from shared.ui import _theme_css

    sombre = _theme_css("sombre")
    systeme = _theme_css("systeme")
    clair = _theme_css("clair")

    assert "#191D1B" in sombre and "--paper" in sombre and "--surface" in sombre
    assert "@media (prefers-color-scheme: dark)" in systeme and "#191D1B" in systeme
    assert clair == ""
