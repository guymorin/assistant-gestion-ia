# tests/test_rh_view.py
from types import SimpleNamespace

import rh.view as rh_view


class DummySt:
    def __init__(self):
        self.session_state = SimpleNamespace()

    def caption(self, *a, **k):
        pass

    def markdown(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def test_rh_render_returns_info_items(monkeypatch):
    st = DummySt()
    monkeypatch.setattr(rh_view, "_render_rh_body", lambda *a, **k: [])
    monkeypatch.setattr(rh_view, "_collect_rh_infos", lambda *a, **k: [])
    infos = rh_view.render({"langue": "fr", "st": st, "session_state": st.session_state})
    assert isinstance(infos, list)
