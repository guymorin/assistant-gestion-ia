from __future__ import annotations

import traceback
from typing import Any, Callable

from .info import InfoItem, collect_footer_infos, normalize_info_value

VUES = ("rh", "finances")
LANGUE_DEFAUT = "fr"


def init_global_state(session_state: Any) -> None:
    if "vue_active" not in session_state:
        session_state["vue_active"] = "rh"
    if session_state.get("vue_active") not in VUES:
        session_state["vue_active"] = "rh"
    if "langue" not in session_state:
        session_state["langue"] = LANGUE_DEFAUT


def render_header(st: Any) -> str:
    session_state = st.session_state
    init_global_state(session_state)
    cols = st.columns([2, 1])
    with cols[0]:
        vue = st.radio(
            "Navigation",
            options=list(VUES),
            format_func=lambda v: "RH" if v == "rh" else "Finances",
            horizontal=True,
            key="vue_active",
        )
    with cols[1]:
        # choix de langue global (valeurs simples; la vue RH interprète)
        st.selectbox(
            "Langue",
            options=["fr", "en", "ko"],
            format_func=lambda c: {"fr": "Français", "en": "English", "ko": "한국어"}.get(c, c),
            key="langue",
        )
    return session_state.get("vue_active", "rh")


def _format_info_value(item: InfoItem) -> str:
    return normalize_info_value(item.valeur) if item.valeur is None else str(item.valeur)


def render_footer(st: Any, items: list[InfoItem]) -> None:
    st.divider()
    st.markdown("#### Informations")
    if not items:
        st.caption("Aucune information disponible.")
        return
    for item in items:
        valeur = _format_info_value(item)
        prefix = "⚠️ " if item.niveau == "warning" else ("❌ " if item.niveau == "error" else "ℹ️ ")
        label = f"{prefix}**{item.libelle}** : {valeur}"
        # aide néophyte accessible via help/caption
        try:
            st.caption(label, help=item.aide)
        except TypeError:
            st.caption(label)
            if item.aide:
                st.caption(f"ⓘ {item.aide}")


def run_portail(
    views: dict[str, Callable[[dict[str, Any]], list[InfoItem]]],
    session_state: Any,
    st: Any,
) -> None:
    init_global_state(session_state)
    vue = render_header(st)
    context = {"langue": session_state.get("langue", LANGUE_DEFAUT), "session_state": session_state, "st": st}
    infos_vue: list[InfoItem] = []
    try:
        render = views.get(vue)
        if render is None:
            st.error(f"Vue inconnue: {vue}")
            infos_vue = [InfoItem("vue_inconnue", "Vue", vue, "La vue demandée n’existe pas dans le portail.", niveau="error")]
        else:
            result = render(context)
            infos_vue = list(result or [])
    except Exception as exc:  # noqa: BLE001
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
    infos_globales = [
        InfoItem("vue_active", "Vue active", "RH" if vue == "rh" else "Finances", "Indique quelle partie du portail vous utilisez actuellement."),
        InfoItem("langue", "Langue", session_state.get("langue", LANGUE_DEFAUT), "Langue globale utilisée pour les réponses et affichages compatibles."),
    ]
    render_footer(st, collect_footer_infos(infos_globales, infos_vue))
