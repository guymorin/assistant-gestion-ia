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
    assert "st.radio" not in src

class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e
    def __setattr__(self, name, value):
        self[name] = value


class DummyCtx:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class DummySt:
    def __init__(self, *, radio_value="Q&R", chat_input_value=None):
        self.session_state = SessionState()
        self._radio_value = radio_value
        self._chat_input_value = chat_input_value
        self.headers = []
        self.captions = []
        self.errors = []
        self.warnings = []
        self.infos = []
        self.markdowns = []
        self.chat_inputs = []

    def _set_sous_vue(self):
        self.session_state.fin_sous_vue = self._radio_value

    def radio(self, label, options, horizontal=False, key=None, label_visibility=None):
        self._set_sous_vue()
        return self._radio_value

    def button(self, *a, **k):
        # Simule le clic sur l'option de sous-menu demandée par le test.
        label = a[0] if a else ""
        key = k.get("key", "")
        if key.startswith("fin_sous_vue_") and label == self._radio_value:
            self.session_state.fin_sous_vue = label
            return True
        return False

    def header(self, text):
        self.headers.append(text)

    def caption(self, text):
        self.captions.append(text)

    def chat_input(self, placeholder, **kwargs):
        self.chat_inputs.append(placeholder)
        return self._chat_input_value

    def chat_message(self, role):
        return DummyCtx()

    def markdown(self, text, **kwargs):
        self.markdowns.append(text)

    def spinner(self, text):
        return DummyCtx()

    def error(self, text):
        self.errors.append(text)

    def warning(self, text):
        self.warnings.append(text)

    def info(self, text):
        self.infos.append(text)

    def write(self, *a, **k):
        pass

    def rerun(self):
        pass

    def columns(self, spec):
        n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [DummyCtx() for _ in range(n)]

    def tabs(self, names):
        return [DummyCtx() for _ in names]

    def selectbox(self, *a, **k):
        # defaults for declaration flow
        if a:
            opts = a[1] if len(a) > 1 else []
            if opts:
                return opts[0]
        return 0

    def button(self, *a, **k):
        return False

    def checkbox(self, *a, **k):
        return k.get("value", False)

    def expander(self, *a, **k):
        return DummyCtx()

    def file_uploader(self, *a, **k):
        return None

    def text_input(self, *a, **k):
        return k.get("value", "")

    def number_input(self, *a, **k):
        return k.get("value", 0.0)

    def metric(self, *a, **k):
        pass

    def dataframe(self, *a, **k):
        pass

    def code(self, *a, **k):
        pass

    def dialog(self, *a, **k):
        def deco(fn):
            return fn
        return deco


def test_render_qr_index_absent_affiche_message_explicite(monkeypatch):
    st = DummySt(radio_value="Q&R", chat_input_value="question")
    st.session_state.fin_sous_vue = "Q&R"
    monkeypatch.setattr(fin_view.logic, "_base_disponible", lambda: False)
    monkeypatch.setattr(fin_view.logic, "infos_ingestion", lambda *a, **k: {})
    infos = fin_view.render({"st": st, "session_state": st.session_state})
    assert st.headers == ["Q&R"]
    assert any(fin_view.TEXTE_QR in c for c in st.captions)
    assert any(fin_view.AVERTISSEMENT_QR in c for c in st.captions)
    assert st.chat_inputs
    assert any("ingestion" in e.lower() or "finances" in e.lower() for e in st.errors)
    assert isinstance(infos, list)


def test_render_declaration_tva_conserve_flux_existant(monkeypatch):
    st = DummySt(radio_value="Déclaration de TVA")
    st.session_state.fin_sous_vue = "Déclaration de TVA"
    # avoid heavy detection side effects variations by stubbing core helpers minimally
    monkeypatch.setattr(fin_view.core, "trouver_fichiers", lambda *a, **k: {"caisse": None, "banque": None, "obypay": None})
    infos = fin_view.render({"st": st, "session_state": st.session_state})
    assert st.headers == ["Déclaration de TVA"]
    assert isinstance(infos, list)
    assert any(i.libelle == "Établissement et période" for i in infos)
