from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .info import InfoItem, collect_footer_infos, normalize_info_value
from .portal_settings import (
    THEME_LABELS,
    THEME_MODES,
    load_portal_settings,
    read_finances_config,
    save_portal_settings,
    write_finances_config,
)

VUES = ("rh", "finances", "juridique", "marketing")
VUE_PARAMETRES = "parametres"
VUE_AIDE = "aide"
VUES_SPECIALES = (VUE_PARAMETRES, VUE_AIDE)
LANGUE_DEFAUT = "fr"
LANGUES = {"fr": "Français", "en": "English", "ko": "한국어"}


def _get_query_vue(st: Any) -> str | None:
    try:
        params = st.query_params
        qp = params.get("vue", "") if hasattr(params, "get") else ""
        if isinstance(qp, list):
            qp = qp[0] if qp else ""
        qp = str(qp).strip().lower()
        if qp in VUES or qp in VUES_SPECIALES:
            return qp
    except Exception:
        pass
    return None


def init_global_state(session_state: Any) -> None:
    if "vue_active" not in session_state or session_state.get("vue_active") not in VUES:
        session_state["vue_active"] = "rh"
    if "langue" not in session_state or session_state.get("langue") not in LANGUES:
        session_state["langue"] = LANGUE_DEFAUT
    if "theme_mode" not in session_state or session_state.get("theme_mode") not in THEME_MODES:
        settings = load_portal_settings()
        session_state["theme_mode"] = settings.get("theme_mode", "systeme")
    if "vue_speciale" not in session_state:
        session_state["vue_speciale"] = None


def _sync_vue_from_query(st: Any) -> None:
    qp_vue = _get_query_vue(st)
    if qp_vue in VUES_SPECIALES:
        st.session_state["vue_speciale"] = qp_vue
    elif qp_vue in VUES:
        st.session_state["vue_active"] = qp_vue
        st.session_state["vue_speciale"] = None


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    candidates = [
        Path(__file__).resolve().parent.parent / "assets" / "logo_hee.svg",
        Path.cwd() / "assets" / "logo_hee.svg",
    ]
    for path in candidates:
        try:
            if path.is_file():
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                return f"data:image/svg+xml;base64,{data}"
        except Exception:
            continue
    return ""


def _theme_css(theme_mode: str) -> str:
    dark_vars = """
  --brick: #D07A58;
  --paper: #191D1B;
  --green: #4A8F52;
  --ink: #ECEAE4;
  --ink-muted: #9FA8A2;
  --line: #353C37;
  --surface: #232826;
  --focus-ring: 0 0 0 3px rgba(74, 143, 82, 0.35);
"""
    dark_rules = """
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
  background: var(--paper) !important;
  color: var(--ink);
}
.portal-navbar {
  background: rgba(25, 29, 27, 0.94) !important;
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(8px);
}
.portal-navbar .brand, .portal-navbar a.nav-item, .portal-navbar .nav-menu > summary { color: var(--ink) !important; }
.portal-navbar .nav-menu > summary,
.portal-navbar .nav-menu,
[data-testid="stMainMenuButton"],
[data-testid="stMainMenu"] button,
[data-testid="stMainMenu"] [role="button"],
[data-testid="stToolbar"] button,
header[data-testid="stHeader"] button {
  background: rgba(25, 29, 27, 0.94) !important;
  color: var(--ink) !important;
}
[data-testid="stMainMenuButton"]:hover,
[data-testid="stMainMenu"] button:hover,
[data-testid="stToolbar"] button:hover {
  background: rgba(35, 40, 38, 0.98) !important;
}
.portal-navbar a.nav-item:hover { background: var(--surface) !important; border-color: var(--line); }
.portal-navbar .nav-dropdown { background: var(--surface); border-color: var(--line); box-shadow: 0 10px 28px rgba(0,0,0,0.35); }
.portal-navbar .nav-dropdown a { color: var(--ink) !important; }
.stButton > button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"] {
  border-color: var(--line) !important;
  background: var(--surface) !important;
  color: var(--ink) !important;
}
.stButton > button:hover,
.stButton > button:focus-visible,
[data-testid="baseButton-secondary"]:hover,
[data-testid="baseButton-secondary"]:focus-visible {
  border-color: #465049 !important;
  background: #2C322F !important;
  color: var(--ink) !important;
}
[data-testid="stChatMessage"], details, [data-testid="stExpander"], [data-testid="stChatInput"],
[data-testid="stDataFrame"], [data-testid="stTable"] {
  background: var(--surface) !important;
  border-color: var(--line) !important;
}
[data-testid="stAlert"] { border-color: var(--line) !important; }
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-testid="stChatInput"] textarea {
  background: #1E2321 !important;
  border-color: var(--line) !important;
  color: var(--ink) !important;
}
small, .stCaption, [data-testid="stCaptionContainer"], p, li, label, .stMarkdown, [data-testid="stMarkdownContainer"] { color: var(--ink); }
small, .stCaption, [data-testid="stCaptionContainer"] { color: var(--ink-muted) !important; }
hr { border-color: var(--line); }
"""
    if theme_mode == "sombre":
        return f"<style>:root {{{dark_vars}}}\n{dark_rules}</style>"
    if theme_mode == "systeme":
        return f"<style>@media (prefers-color-scheme: dark) {{ :root {{{dark_vars}}}\n{dark_rules} }}</style>"
    return ""


def _inject_global_styles(st: Any) -> None:
    """Injecte les tokens, la typographie Roboto et les styles globaux (refonte épurée)."""
    theme_mode = st.session_state.get("theme_mode", "systeme")
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&display=swap');

:root {
  --brick: #B85C3A;
  --paper: #F6F2EA;
  --green: #2C5B29;
  --ink: #1F2421;
  --ink-muted: #5E665F;
  --line: #DDD7CB;
  --surface: #FFFFFF;
  --focus-ring: 0 0 0 3px rgba(44, 91, 41, 0.22);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-pill: 999px;
}

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
  background: var(--paper) !important;
  color: var(--ink);
  font-family: 'Roboto', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

/* Ne pas forcer font-family sur tous les éléments : cela casse les icônes
   Material Symbols (flèches, upload, etc.) utilisées par Streamlit. */

section.main > div.block-container,
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.stMainBlockContainer {
  padding-top: 4.75rem !important;
  padding-bottom: 2rem;
  max-width: 1280px;
}

h1, h2, h3, h4 {
  color: var(--ink);
  letter-spacing: -0.01em;
}

/* Légèrement plus d'air dans les messages de conversation Q&R */
[data-testid="stChatMessage"] {
  padding: 0.75rem 1rem !important;
}
h1 { font-size: 1.9rem; font-weight: 600; line-height: 1.2; }
h2 { font-size: 1.4rem; font-weight: 600; line-height: 1.3; }
h3 { font-size: 1.15rem; font-weight: 600; line-height: 1.35; }

p, li, label, .stMarkdown, [data-testid="stMarkdownContainer"] {
  color: var(--ink);
  line-height: 1.6;
}

small, .stCaption, [data-testid="stCaptionContainer"] {
  color: var(--ink-muted) !important;
}

a, a:visited {
  color: var(--green);
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}
a:hover { color: #234a21; }

:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* Masquer la bande d'en-tête native Streamlit */
header[data-testid="stHeader"],
[data-testid="stHeader"] {
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  pointer-events: none !important;
}

/* Menu principal Streamlit (hamburger haut droit) : fond transparent, sans bordure, sans ombre */
[data-testid="stMainMenuButton"],
[data-testid="stMainMenu"] button,
[data-testid="stMainMenu"] [role="button"],
[data-testid="stToolbar"] button,
header[data-testid="stHeader"] button {
  background: rgba(246, 242, 234, 0.96) !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: none !important;
  border-radius: 0 !important;
}
[data-testid="stMainMenuButton"]:hover,
[data-testid="stMainMenu"] button:hover,
[data-testid="stToolbar"] button:hover {
  background: rgba(246, 242, 234, 0.96) !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: none !important;
}

/* Masquer l'animation native Streamlit (vélo, fauteuil roulant, etc.) */
[data-testid="stSpinnerIcon"],
[data-testid="stStatusWidgetRunningIcon"],
[data-testid="stStatusWidgetRunningManIcon"] {
  display: none !important;
}
[data-testid="stStatusWidget"] * {
  animation: none !important;
}

/* Navbar */
.portal-navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000001;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 1.25rem;
  margin: 0;
  background: rgba(246, 242, 234, 0.96);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--line);
}
.portal-navbar .brand-wrap {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  margin-right: 0.75rem;
  text-decoration: none;
}
.portal-navbar .brand-logo {
  height: 34px;
  width: 34px;
  display: block;
}
.portal-navbar .brand {
  font-weight: 600;
  color: var(--ink);
  font-size: 1rem;
  letter-spacing: 0.01em;
}
.portal-navbar a.nav-item {
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.95rem;
  border-radius: 10px;
  text-decoration: none !important;
  font-weight: 500;
  font-size: 0.95rem;
  color: var(--ink) !important;
  border: 1px solid transparent;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.portal-navbar a.nav-item:hover {
  background: var(--surface);
  border-color: var(--line);
}
.portal-navbar a.nav-item.active {
  background: var(--green);
  color: #fff !important;
  border-color: var(--green);
}

/* Menu hamburger intégré dans la navbar */
.portal-navbar .nav-menu {
  position: relative;
  display: inline-flex;
  align-items: center;
  background: rgba(246, 242, 234, 0.96) !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: none !important;
  border-radius: 0 !important;
}
.portal-navbar .nav-menu > summary {
  list-style: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.3rem 0.4rem;
  border-radius: 0 !important;
  background: rgba(246, 242, 234, 0.96) !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: none !important;
  color: var(--ink);
  user-select: none;
}
.portal-navbar .nav-hamburger-dots {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
}
.portal-navbar .nav-hamburger-dots span {
  display: block;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentColor;
  border: 0;
}
.portal-navbar .nav-dropdown a {
  transition: background-color 0.15s ease, color 0.15s ease;
}
.portal-navbar .nav-dropdown a:hover {
  background: var(--green) !important;
  color: #fff !important;
}
.portal-navbar .nav-menu > summary::-webkit-details-marker { display: none; }
.portal-navbar .nav-dropdown {
  position: absolute;
  top: calc(100% + 0.4rem);
  right: 0;
  min-width: 11rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(31, 36, 33, 0.12);
  padding: 0.4rem;
  z-index: 1000002;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.portal-navbar .nav-dropdown a {
  display: block;
  padding: 0.45rem 0.75rem;
  border-radius: var(--radius-sm);
  text-decoration: none !important;
  color: var(--ink) !important;
  font-weight: 500;
  font-size: 0.92rem;
}
.portal-navbar .nav-dropdown a:hover {
  background: var(--paper);
}
.portal-navbar .nav-menu:not([open]) .nav-dropdown { display: none; }

/* Boutons - même style que les boutons de sous-menu des vues */
.stButton > button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"] {
  border-radius: 10px;
  padding: 0.35rem 0.8rem;
  font-size: 0.88rem;
  font-weight: 500;
  line-height: 1.2;
  border: 1px solid var(--line, #DDD7CB) !important;
  background: var(--surface, #FFFFFF) !important;
  color: var(--ink, #1F2421) !important;
  box-shadow: none;
  transition: background-color 120ms ease, color 120ms ease, border-color 120ms ease;
}
.stButton > button:hover,
.stButton > button:focus-visible,
[data-testid="baseButton-primary"]:hover,
[data-testid="baseButton-primary"]:focus-visible,
[data-testid="baseButton-secondary"]:hover,
[data-testid="baseButton-secondary"]:focus-visible {
  border-color: #c9c1b2 !important;
  background: #ffffff !important;
  color: var(--ink, #1F2421) !important;
}

/* Champs de formulaire */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-testid="stChatInput"] textarea {
  background: var(--surface) !important;
  border-color: var(--line) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--ink) !important;
}
[data-baseweb="input"] > div:focus-within,
[data-baseweb="select"] > div:focus-within,
[data-baseweb="textarea"] > div:focus-within {
  border-color: var(--green) !important;
  box-shadow: var(--focus-ring) !important;
}

/* Expanders / cartes */
details, [data-testid="stExpander"] {
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-md);
}
[data-testid="stExpander"] summary p { font-weight: 500; }

/* Chat */
[data-testid="stChatMessage"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 0.85rem 1rem;
  margin-bottom: 0.6rem;
  box-shadow: 0 1px 2px rgba(31, 36, 33, 0.04);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
  line-height: 1.55;
}
[data-testid="stChatInput"] {
  border-radius: var(--radius-pill);
  border: 1px solid var(--line);
  background: var(--surface);
  box-shadow: 0 4px 14px rgba(31, 36, 33, 0.08);
}
[data-testid="stChatInput"] textarea {
  padding: 0.7rem 1rem;
}

/* Alertes */
[data-testid="stAlert"] {
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
}

/* Panneau infos / colonnes droites */
[data-testid="column"]:last-child [data-testid="stVerticalBlockBorderWrapper"],
[data-testid="column"]:last-child .stMarkdown {
  /* garder sobre */
}

/* Dividers */
hr { border-color: var(--line); }

/* Tableaux / dataframes */
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}

@media (max-width: 768px) {
  .portal-navbar { padding: 0.5rem 0.75rem; gap: 0.35rem; flex-wrap: wrap; }
  .portal-navbar .brand { font-size: 0.92rem; }
  .portal-navbar .brand-logo { height: 28px; width: 28px; }
  section.main > div.block-container,
  [data-testid="stAppViewBlockContainer"],
  [data-testid="stMainBlockContainer"],
  .stMainBlockContainer { padding-top: 5.5rem !important; }
}
</style>
""",
        unsafe_allow_html=True,
    )
    extra = _theme_css(theme_mode)
    if extra:
        st.markdown(extra, unsafe_allow_html=True)


def _inject_menu_customizations(st: Any) -> None:
    """Personnalise le menu Streamlit (traductions, Paramètres, masquage mentions)."""
    try:
        from streamlit.components.v1 import html as components_html

        components_html(
            r"""
<script>
(function() {
  const doc = window.parent && window.parent.document ? window.parent.document : document;
  function customizeMenu() {
    try {
      // Masquer "Record a screencast"
      const recSelectors = [
        '[data-testid="stMainMenuItem-recordScreencast"]',
        'button[data-testid="stMainMenuItem-recordScreencast"]',
        'li [data-testid="stMainMenuItem-recordScreencast"]'
      ];
      recSelectors.forEach(sel => doc.querySelectorAll(sel).forEach(el => {
        const item = el.closest('[role="menuitem"]') || el.closest('li') || el;
        if (item) item.style.display = 'none';
      }));
      doc.querySelectorAll('[data-testid="stMainMenu"] [role="menuitem"], [data-testid="stMainMenu"] li, ul[role="menu"] [role="menuitem"]').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        if (/record/i.test(txt) && /screen|screencast/i.test(txt)) {
          el.style.display = 'none';
        }
      });

      // Masquer la mention "Made with Streamlit" dans le menu déroulant (mais pas dans À propos)
      doc.querySelectorAll('[data-testid="stMainMenu"] div, [data-testid="stMainMenu"] span, [data-testid="stMainMenu"] footer, ul[role="menu"] div').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        if (/^Made with Streamlit/i.test(txt) && !el.querySelector('[role="menuitem"]')) {
          el.style.display = 'none';
        }
      });

      // Lien Aide / Obtenir de l'aide
      const getHelp = doc.querySelector('[data-testid="stMainMenuItem-getHelp"]') || doc.querySelector('a[href*="vue=aide"]');
      if (getHelp) {
        try {
          getHelp.setAttribute('href', '?vue=aide');
          getHelp.removeAttribute('target');
          getHelp.setAttribute('rel', 'noopener');
        } catch (e) { /* noop */ }
      }

      // Paramètres est accessible via le menu hamburger de la navbar ; ne pas
      // dupliquer l'entrée dans le menu principal de Streamlit.

      // Traductions best-effort des libellés connus
      const translations = [
        [/^Get help$/i, "Obtenir de l'aide"],
        [/^About$/i, 'À propos'],
        [/^Print$/i, 'Imprimer'],
        [/^Rerun$/i, 'Relancer'],
        [/^Settings$/i, 'Réglages'],
        [/^Clear cache$/i, 'Vider le cache'],
        [/^Deploy$/i, 'Déployer'],
      ];
      doc.querySelectorAll('[data-testid="stMainMenu"] [role="menuitem"], [data-testid="stMainMenu"] a, [data-testid="stMainMenu"] span, [data-testid="stMainMenu"] div, ul[role="menu"] [role="menuitem"]').forEach(el => {
        if (el.children && el.children.length > 0) return;
        const txt = (el.innerText || el.textContent || '').trim();
        for (const [re, label] of translations) {
          if (re.test(txt)) { el.textContent = label; break; }
        }
      });
    } catch (e) { /* noop */ }
  }
  customizeMenu();
  const obs = new MutationObserver(() => customizeMenu());
  obs.observe(doc.body, { childList: true, subtree: true });
  setTimeout(() => obs.disconnect(), 15000);
})();
</script>
""",
            height=0,
            width=0,
        )
    except Exception:
        pass


def _inject_hamburger_outside_click(st: Any) -> None:
    try:
        from streamlit.components.v1 import html as components_html

        components_html(
            r"""
<script>
(function() {
  const doc = window.parent && window.parent.document ? window.parent.document : document;
  function closeOnOutside(e) {
    doc.querySelectorAll('details.nav-menu[open]').forEach(d => {
      if (!d.contains(e.target)) d.removeAttribute('open');
    });
  }
  if (!doc.__hamburgerOutsideBound) {
    doc.addEventListener('click', closeOnOutside, true);
    doc.__hamburgerOutsideBound = true;
  }
})();
</script>
""",
            height=0,
            width=0,
        )
    except Exception:
        pass


def render_header(st: Any) -> str:
    session_state = st.session_state
    init_global_state(session_state)
    _sync_vue_from_query(st)
    _inject_global_styles(st)
    _inject_menu_customizations(st)
    _inject_hamburger_outside_click(st)
    speciale = session_state.get("vue_speciale")
    if speciale in VUES_SPECIALES:
        return speciale
    return session_state.get("vue_active", "rh")


def _format_info_value(item: InfoItem) -> str:
    return normalize_info_value(item.valeur) if item.valeur is None else str(item.valeur)


def _render_info_items(st: Any, items: list[InfoItem], *, title: str = "Informations", show_divider: bool = True) -> None:
    if show_divider:
        st.divider()
    st.markdown(f"#### {title}")
    if not items:
        st.caption("Aucune information disponible.")
        return
    for item in items:
        valeur = _format_info_value(item)
        prefix = "⚠️ " if item.niveau == "warning" else ("❌ " if item.niveau == "error" else "ℹ️ ")
        label = f"{prefix}**{item.libelle}** : {valeur}"
        try:
            st.caption(label, help=item.aide)
        except TypeError:
            st.caption(label)
            if item.aide:
                st.caption(f"ⓘ {item.aide}")


def render_footer(st: Any, items: list[InfoItem]) -> None:
    _render_info_items(st, items, title="Informations", show_divider=True)


def _default_finances_entries() -> dict[str, dict[str, str]]:
    return {
        "HEE-MAR-93100": {
            "source": "./Finances/HEE-MAR-93100",
            "cible": "./Finances/HEE-MAR-93100",
            "mode": "automatique",
            "libelle_mail": "HEE COFFEE SHOP",
        },
        "HEE-REP-93100": {
            "source": "./Finances/HEE-REP-93100",
            "cible": "./Finances/HEE-REP-93100",
            "mode": "automatique",
            "libelle_mail": "HEE",
        },
    }


def render_settings_page(st: Any) -> list[InfoItem]:
    session_state = st.session_state
    init_global_state(session_state)

    st.header("Paramètres")
    st.caption("Réglez ici les paramètres modifiables par l’utilisateur.")

    st.subheader("Paramètres généraux")

    current_lang = session_state.get("langue", LANGUE_DEFAUT)
    if current_lang not in LANGUES:
        current_lang = LANGUE_DEFAUT
    langue = st.selectbox(
        "Langue",
        options=list(LANGUES.keys()),
        index=list(LANGUES.keys()).index(current_lang),
        format_func=lambda c: LANGUES.get(c, c),
        key="param_langue",
        help="Langue de l’interface et des réponses compatibles.",
    )
    session_state["langue"] = langue

    current_theme = session_state.get("theme_mode", "systeme")
    if current_theme not in THEME_MODES:
        current_theme = "systeme"
    icons = {"systeme": "🖥️", "clair": "☀️", "sombre": "🌙"}
    st.markdown(
        """
<style>
.appearance-picker [data-testid="stRadio"] > div { gap: 0.6rem; }
.appearance-picker [data-testid="stRadio"] [role="radiogroup"] { display: flex; gap: 0.75rem; }
.appearance-picker [data-testid="stRadio"] label {
  flex: 1; margin: 0 !important; padding: 0.85rem 1rem !important;
  border: 1px solid var(--line); border-radius: 14px; background: var(--surface);
  justify-content: center; transition: border-color 120ms ease, box-shadow 120ms ease, background-color 120ms ease;
}
.appearance-picker [data-testid="stRadio"] label:hover { border-color: #c9c1b2; background: color-mix(in srgb, var(--surface) 92%, var(--paper)); }
.appearance-picker [data-testid="stRadio"] label:has(input:checked) { border-color: var(--green); box-shadow: 0 0 0 2px color-mix(in srgb, var(--green) 22%, transparent); }
.appearance-picker [data-testid="stRadio"] label > div:first-child { margin-right: 0.45rem; }
.appearance-picker [data-testid="stRadio"] label p { font-size: 0.95rem; font-weight: 500; }
</style>
<div class="appearance-picker">
""",
        unsafe_allow_html=True,
    )
    choix_theme = st.radio(
        "Apparence",
        options=list(THEME_MODES),
        index=list(THEME_MODES).index(current_theme),
        format_func=lambda m: f"{icons.get(m, '')}  {THEME_LABELS.get(m, m)}",
        horizontal=True,
        key="param_theme_mode",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    session_state["theme_mode"] = choix_theme
    st.caption("« Système » suit le réglage de votre appareil.")

    st.subheader("RH")
    st.caption("Chemin racine du dossier RH pour chaque établissement (création du dossier salarié à la validation).")
    try:
        from rh import onboarding as rh_onboarding

        etabs_rh = rh_onboarding.etablissements_disponibles()
    except Exception:
        etabs_rh = []
        rh_onboarding = None
    settings = load_portal_settings()
    rh_paths = dict(settings.get("rh_base_paths") or {})
    updates_rh: dict[str, str] = {}
    if not etabs_rh:
        st.caption("Aucun établissement détecté dans RH-Onboarding.")
    for etab in etabs_rh:
        default_path = rh_onboarding.chemin_base_rh_defaut(etab) if rh_onboarding else ""
        val = rh_paths.get(etab) or default_path
        updates_rh[etab] = st.text_input(
            f"Chemin racine RH — {etab}",
            value=val,
            key=f"cfg_rh_base_{etab}",
        )

    st.subheader("Finances")
    st.caption(
        "Paramètres de synchronisation et de localisation des pièces de TVA "
        "(`Assistant-de-Gestion.config`)."
    )
    try:
        from finances import core as finances_core
        config_path = Path(getattr(finances_core, "CONFIG_FILE", "Assistant-de-Gestion.config"))
    except Exception:
        config_path = Path("Assistant-de-Gestion.config")

    original_lines, entries = read_finances_config(config_path)
    if not entries:
        entries = _default_finances_entries()

    updates_fin: dict[str, dict[str, str]] = {}
    for etab in sorted(entries.keys()):
        data = entries[etab]
        with st.expander(etab, expanded=True):
            source = st.text_input("Répertoire source", value=data.get("source", ""), key=f"cfg_{etab}_source")
            cible = st.text_input("Répertoire cible", value=data.get("cible", ""), key=f"cfg_{etab}_cible")
            modes = ["automatique", "manuel"]
            mode_val = data.get("mode", "automatique") or "automatique"
            if mode_val not in modes:
                modes = [mode_val] + [m for m in modes if m != mode_val]
            mode = st.selectbox("Mode de synchronisation", options=modes, index=modes.index(mode_val), key=f"cfg_{etab}_mode")
            libelle = st.text_input("Libellé mail (objet)", value=data.get("libelle_mail", ""), key=f"cfg_{etab}_libelle")
            updates_fin[etab] = {"source": source, "cible": cible, "mode": mode, "libelle_mail": libelle}

    if st.button("Enregistrer", type="primary", key="btn_enregistrer_parametres"):
        erreurs = []
        try:
            save_portal_settings({"theme_mode": session_state.get("theme_mode", "systeme"), "rh_base_paths": updates_rh})
        except Exception as exc:
            erreurs.append(f"Paramètres généraux/RH : {exc}")
        try:
            write_finances_config(config_path, updates_fin, original_lines=original_lines)
        except Exception as exc:
            erreurs.append(f"Finances : {exc}")
        if erreurs:
            st.error(" ; ".join(erreurs))
        else:
            st.success("Paramètres enregistrés.")
            st.rerun()

    infos = [
        InfoItem("param_langue", "Langue", LANGUES.get(session_state.get("langue", LANGUE_DEFAUT), session_state.get("langue", LANGUE_DEFAUT)), "Langue globale sélectionnée dans les paramètres."),
        InfoItem("param_theme", "Mode d’affichage", THEME_LABELS.get(session_state.get("theme_mode", "systeme"), session_state.get("theme_mode", "systeme")), "Préférence d’apparence enregistrée pour le portail."),
        InfoItem("param_finances_config", "Fichier de configuration Finances", str(config_path), "Fichier des chemins et paramètres des pièces de TVA."),
    ]
    return infos


def render_aide_page(st: Any) -> list[InfoItem]:
    session_state = st.session_state
    init_global_state(session_state)

    st.header("Aide")
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    try:
        content = readme_path.read_text(encoding="utf-8")
        st.caption(f"Contenu synchronisé depuis `{readme_path.name}`.")
        st.markdown(content)
    except Exception as exc:
        st.error(f"Impossible de charger l’aide depuis `{readme_path}` : {exc}")
        content = ""

    return [
        InfoItem(
            "aide_source",
            "Source de l’aide",
            str(readme_path),
            "Le contenu de cette page est lu depuis README.md à chaque affichage.",
        )
    ]


def render_navbar(st: Any) -> None:
    """Affiche la barre de navigation principale, fixée en haut de l'écran.

    Le menu hamburger (☰) est intégré dans la navbar, entre les modules,
    et donne accès aux pages Paramètres et Aide.
    """
    session_state = st.session_state
    init_global_state(session_state)
    speciale = session_state.get("vue_speciale")
    active_vue = session_state.get("vue_active", "rh")
    active_rh = "active" if speciale not in VUES_SPECIALES and active_vue == "rh" else ""
    active_fin = "active" if speciale not in VUES_SPECIALES and active_vue == "finances" else ""
    active_jur = "active" if speciale not in VUES_SPECIALES and active_vue == "juridique" else ""
    active_mar = "active" if speciale not in VUES_SPECIALES and active_vue == "marketing" else ""
    logo_src = _logo_data_uri()
    logo_html = (
        f'<img class="brand-logo" src="{logo_src}" alt="HEE" />' if logo_src else ""
    )

    st.markdown(
        f"""
<div class="portal-navbar" role="navigation" aria-label="Navigation principale">
  <span class="brand-wrap">{logo_html}<span class="brand">Assistant de Gestion</span></span>
  <a class="nav-item {active_rh}" href="?vue=rh" target="_self">RH</a>
  <a class="nav-item {active_fin}" href="?vue=finances" target="_self">Finances</a>
  <a class="nav-item {active_jur}" href="?vue=juridique" target="_self">Juridique</a>
  <a class="nav-item {active_mar}" href="?vue=marketing" target="_self">Marketing</a>
  <details class="nav-menu" style="margin-left:auto;">
    <summary class="nav-hamburger" title="Menu" aria-label="Menu"><span class="nav-hamburger-dots" aria-hidden="true"><span></span><span></span><span></span></span></summary>
    <div class="nav-dropdown">
      <a href="?vue=parametres" target="_self">Paramètres</a>
      <a href="?vue=aide" target="_self">Aide</a>
    </div>
  </details>
</div>
""",
        unsafe_allow_html=True,
    )


def run_portail(
    views: dict[str, Callable[[dict[str, Any]], list[InfoItem]]],
    session_state: Any,
    st: Any,
) -> None:
    init_global_state(session_state)
    container = getattr(st, "container", None)
    if callable(container):
        with container():
            vue = render_header(st)
    else:
        vue = render_header(st)
    context = {"langue": session_state.get("langue", LANGUE_DEFAUT), "session_state": session_state, "st": st}
    infos_vue: list[InfoItem] = []
    render_navbar(st)
    main_col, right_col = st.columns([3, 1], gap="large")
    try:
        with main_col:
            if vue == VUE_PARAMETRES:
                infos_vue = list(render_settings_page(st) or [])
            elif vue == VUE_AIDE:
                infos_vue = list(render_aide_page(st) or [])
            else:
                render = views.get(vue)
                if render is None:
                    st.error(f"Vue inconnue: {vue}")
                    infos_vue = [InfoItem("vue_inconnue", "Vue", vue, "La vue demandée n’existe pas dans le portail.", niveau="error")]
                else:
                    result = render(context)
                    infos_vue = list(result or [])
    except Exception as exc:  # noqa: BLE001
        with main_col:
            st.error(f"Erreur dans la vue '{vue}': {exc}")
        infos_vue = [
            InfoItem(
                "erreur_vue",
                "État de la vue",
                "erreur",
                "La vue a rencontré un problème. Le détail est affiché au-dessus ; vous pouvez changer de vue ou réessayer.",
                niveau="error",
            )
        ]

    vue_active = session_state.get("vue_active", "rh")
    vue_labels = {"rh": "RH", "finances": "Finances", "juridique": "Juridique", "marketing": "Marketing"}
    if vue == VUE_PARAMETRES:
        vue_label = "Paramètres"
    elif vue == VUE_AIDE:
        vue_label = "Aide"
    else:
        vue_label = vue_labels.get(vue_active, vue_active.capitalize())
    langue_code = session_state.get("langue", LANGUE_DEFAUT)
    infos_globales = [
        InfoItem(
            "vue_active",
            "Vue active",
            vue_label,
            "Indique quelle partie du portail vous utilisez actuellement.",
        ),
        InfoItem(
            "langue",
            "Langue",
            LANGUES.get(langue_code, langue_code),
            "Langue globale utilisée pour les réponses et affichages compatibles.",
        ),
    ]

    with right_col:
        is_qr_view = vue not in VUES_SPECIALES and vue in VUES
        rh_onboarding = vue == "rh" and session_state.get("rh_sous_vue") == "Onboarding"
        masquer_pieces_jointes = (
            vue == "finances"
            and session_state.get("fin_sous_vue") == "Déclaration de TVA"
        ) or rh_onboarding
        if is_qr_view and not masquer_pieces_jointes:
            try:
                from shared.qr_view import render_pieces_jointes as _render_pj

                # On passe le cfg correspondant au module actif
                cfg_map = {
                    "rh": "rh",
                    "finances": "finances",
                    "juridique": "juridique",
                    "marketing": "marketing",
                }
                cfg_id = cfg_map.get(vue)
                if cfg_id:
                    from shared.qr_config import get_module_config

                    cfg = get_module_config(cfg_id)
                    _render_pj(st, session_state, cfg, expanded=True)
                    st.divider()
            except Exception:
                pass
        if rh_onboarding:
            from rh import onboarding as _rh_onboarding

            data = session_state.get("rh_onb_data") or {}
            recap = _rh_onboarding.recapitulatif(data)
            st.subheader("Récapitulatif")
            st.code(recap, language="text")
            st.divider()
        _render_info_items(st, collect_footer_infos(infos_globales, infos_vue), title="Informations", show_divider=False)
