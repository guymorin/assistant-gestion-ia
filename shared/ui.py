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


def _inject_global_styles(st: Any) -> None:
    """Injecte les tokens, la typographie Roboto et les styles globaux (refonte épurée)."""
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

[data-testid="stAppViewContainer"] * {
  font-family: inherit;
}

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
  border-radius: var(--radius-pill);
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

/* Boutons */
.stButton > button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"] {
  border-radius: var(--radius-pill);
  font-weight: 500;
  border: 1px solid var(--line);
  box-shadow: none;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.stButton > button[kind="primary"],
[data-testid="baseButton-primary"] {
  background: var(--green) !important;
  color: #fff !important;
  border-color: var(--green) !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover {
  background: #234a21 !important;
  border-color: #234a21 !important;
}
.stButton > button[kind="secondary"],
[data-testid="baseButton-secondary"],
.stButton > button:not([kind="primary"]) {
  background: var(--surface);
  color: var(--ink);
}
.stButton > button[kind="secondary"]:hover,
[data-testid="baseButton-secondary"]:hover,
.stButton > button:not([kind="primary"]):hover {
  border-color: #c9c1b2;
  background: #fff;
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
  padding: 0.25rem 0.25rem;
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

      // Ajouter Paramètres si absent
      const existingParam = doc.querySelector('[data-testid="stMainMenuItem-customParametres"]');
      if (!existingParam) {
        let anchor = null;
        doc.querySelectorAll('[data-testid="stMainMenu"] a, [data-testid="stMainMenu"] [role="menuitem"]').forEach(el => {
          const txt = (el.innerText || el.textContent || '').trim();
          if (/get help|aide|obtenir/i.test(txt) && !anchor) anchor = el;
        });
        if (!anchor) anchor = getHelp;
        if (anchor && anchor.parentNode) {
          const a = doc.createElement('a');
          a.setAttribute('data-testid', 'stMainMenuItem-customParametres');
          a.setAttribute('role', 'menuitem');
          a.setAttribute('tabindex', '0');
          a.href = '?vue=parametres';
          a.textContent = 'Paramètres';
          a.style.display = 'flex';
          a.style.alignItems = 'center';
          a.style.padding = '0.5rem 1rem';
          a.style.textDecoration = 'none';
          a.style.color = 'inherit';
          a.style.cursor = 'pointer';
          anchor.parentNode.insertBefore(a, anchor);
        }
      }

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


def render_header(st: Any) -> str:
    session_state = st.session_state
    init_global_state(session_state)
    _sync_vue_from_query(st)
    _inject_global_styles(st)
    _inject_menu_customizations(st)
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

    # Langue
    st.subheader("Langue")
    current_lang = session_state.get("langue", LANGUE_DEFAUT)
    if current_lang not in LANGUES:
        current_lang = LANGUE_DEFAUT
    langue = st.selectbox(
        "Langue de l’interface et des réponses compatibles",
        options=list(LANGUES.keys()),
        index=list(LANGUES.keys()).index(current_lang),
        format_func=lambda c: LANGUES.get(c, c),
        key="param_langue",
    )
    session_state["langue"] = langue

    # Thème
    st.subheader("Apparence")
    current_theme = session_state.get("theme_mode", "systeme")
    if current_theme not in THEME_MODES:
        current_theme = "systeme"
    theme_mode = st.radio(
        "Mode d’affichage",
        options=list(THEME_MODES),
        index=list(THEME_MODES).index(current_theme),
        format_func=lambda m: THEME_LABELS.get(m, m),
        horizontal=True,
        key="param_theme_mode",
    )
    if theme_mode != session_state.get("theme_mode"):
        session_state["theme_mode"] = theme_mode
        try:
            save_portal_settings({"theme_mode": theme_mode})
        except Exception:
            pass
    st.caption(
        "Préférence enregistrée (Système / Clair / Sombre). Le thème appliqué par Streamlit dépend "
        "de la configuration de l’application (.streamlit/config.toml) et du menu d’affichage ; "
        "selon l’environnement, le changement peut nécessiter de recharger l’application."
    )

    # Finances / TVA
    st.subheader("Chemins des pièces de TVA (Finances)")
    st.caption(
        "Paramètres de synchronisation et de localisation des pièces, correspondant au fichier "
        "`Finances/Finances-config.txt`."
    )
    try:
        from finances import core as finances_core
        config_path = Path(getattr(finances_core, "CONFIG_FILE", "Finances/Finances-config.txt"))
    except Exception:
        config_path = Path("Finances/Finances-config.txt")

    original_lines, entries = read_finances_config(config_path)
    if not entries:
        entries = _default_finances_entries()

    updates: dict[str, dict[str, str]] = {}
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
            updates[etab] = {"source": source, "cible": cible, "mode": mode, "libelle_mail": libelle}

    if st.button("Enregistrer les paramètres Finances", type="primary"):
        try:
            write_finances_config(config_path, updates, original_lines=original_lines)
            st.success(f"Paramètres enregistrés dans `{config_path}`.")
        except Exception as exc:
            st.error(f"Impossible d’enregistrer les paramètres Finances : {exc}")

    # retour
    if st.button("Retour au portail"):
        session_state["vue_speciale"] = None
        try:
            st.query_params["vue"] = session_state.get("vue_active", "rh")
        except Exception:
            pass
        st.rerun()

    infos = [
        InfoItem("param_langue", "Langue", LANGUES.get(session_state.get("langue", LANGUE_DEFAUT), session_state.get("langue", LANGUE_DEFAUT)), "Langue globale sélectionnée dans les paramètres."),
        InfoItem("param_theme", "Mode d’affichage (préférence)", THEME_LABELS.get(session_state.get("theme_mode", "systeme"), session_state.get("theme_mode", "systeme")), "Préférence d’apparence enregistrée pour le portail."),
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

    if st.button("Retour au portail", key="aide_retour"):
        session_state["vue_speciale"] = None
        try:
            st.query_params["vue"] = session_state.get("vue_active", "rh")
        except Exception:
            pass
        st.rerun()

    return [
        InfoItem(
            "aide_source",
            "Source de l’aide",
            str(readme_path),
            "Le contenu de cette page est lu depuis README.md à chaque affichage.",
        )
    ]


def render_navbar(st: Any) -> None:
    """Affiche la barre de navigation principale, fixée en haut de l'écran."""
    speciale = st.session_state.get("vue_speciale")
    active_vue = st.session_state.get("vue_active", "rh")
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
    if vue == VUE_PARAMETRES:
        vue_label = "Paramètres"
    elif vue == VUE_AIDE:
        vue_label = "Aide"
    else:
        vue_label = "RH" if vue_active == "rh" else "Finances"
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
        if is_qr_view:
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
        _render_info_items(st, collect_footer_infos(infos_globales, infos_vue), title="Informations", show_divider=False)
