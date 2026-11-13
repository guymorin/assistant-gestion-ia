from __future__ import annotations

import os
from typing import Any

import streamlit as st

from shared.info import InfoItem
from shared.ui import VUE_AIDE, VUE_PARAMETRES, init_global_state, run_portail


def _vue_initiale() -> str:
    vue = os.environ.get("PORTAIL_VUE", "").strip().lower()
    if vue in {"rh", "finances"}:
        return vue
    try:
        params = st.query_params
        qp = params.get("vue", "") if hasattr(params, "get") else ""
        if isinstance(qp, list):
            qp = qp[0] if qp else ""
        qp = str(qp).strip().lower()
        if qp in {"rh", "finances", VUE_PARAMETRES, VUE_AIDE}:
            return qp
    except Exception:
        pass
    return "rh"


def _placeholder_view(nom: str):
    def _render(_context: dict[str, Any]) -> list[InfoItem]:
        st.info(f"Vue {nom} en cours d’intégration dans le portail.")
        return [InfoItem(f"{nom}_placeholder", "État", "en cours", "Cette vue sera branchée lors des prochaines étapes.", niveau="warning")]
    return _render


def main() -> None:
    port = os.environ.get("ASSISTANT_PORTAIL_PORT", "8501")
    help_url = f"http://localhost:{port}/?vue=aide"
    st.set_page_config(
        page_title="Assistant de Gestion - IA",
        page_icon="assets/logo_hee.svg",
        layout="wide",
        menu_items={
            "Get help": help_url,
            "About": (
                "Assistant de Gestion - IA\n\n"
                "Paramètres (langue, pièces de TVA, apparence) et aide accessibles depuis le menu.\n\n"
                "Made with Streamlit"
            ),
        },
    )
    init_global_state(st.session_state)
    vue_init = _vue_initiale()
    if vue_init == VUE_PARAMETRES:
        st.session_state["vue_speciale"] = VUE_PARAMETRES
    elif vue_init == VUE_AIDE:
        st.session_state["vue_speciale"] = VUE_AIDE
    elif "vue_active" not in st.session_state or st.session_state.get("vue_active") not in ("rh", "finances"):
        st.session_state["vue_active"] = vue_init
    # vues branchées progressivement
    try:
        from rh.view import render as render_rh
    except Exception:
        render_rh = _placeholder_view("RH")
    try:
        from finances.view import render as render_finances
    except Exception:
        render_finances = _placeholder_view("Finances")
    views = {
        "rh": render_rh,
        "finances": render_finances,
    }
    run_portail(views, st.session_state, st)


if __name__ == "__main__":
    main()
