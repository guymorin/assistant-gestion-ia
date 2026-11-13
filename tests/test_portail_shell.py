# tests/test_portail_shell.py
from types import SimpleNamespace

from shared.info import InfoItem
from shared.ui import init_global_state, run_portail


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.errors = []
        self.captions = []

    def error(self, msg):
        self.errors.append(msg)

    def caption(self, msg):
        self.captions.append(msg)


def test_init_global_state_defaults():
    st = SimpleNamespace(session_state={})
    init_global_state(st.session_state)
    assert st.session_state["vue_active"] in ("rh", "finances")
    assert "langue" in st.session_state


def test_run_portail_renders_footer_even_if_view_raises(monkeypatch):
    st = FakeSt()
    init_global_state(st.session_state)
    st.session_state["vue_active"] = "rh"

    def boom(_ctx):
        raise RuntimeError("boom")

    rendered = {}
    monkeypatch.setattr(
        "shared.ui.render_header",
        lambda st_obj: st_obj.session_state.__setitem__("vue_active", "rh") or "rh",
    )

    def fake_footer(_st, items):
        rendered["items"] = items

    monkeypatch.setattr("shared.ui.render_footer", fake_footer)

    run_portail({"rh": boom}, st.session_state, st)
    assert st.errors  # erreur affichée
    assert rendered["items"]  # footer quand même rendu
