from __future__ import annotations

import os
from typing import Any

import streamlit as st

from shared.info import InfoItem
from shared.ui import init_global_state, run_portail


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
        if qp in {"rh", "finances"}:
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
    st.set_page_config(page_title="Portail RH / Finances", page_icon="🧭", layout="wide")
    init_global_state(st.session_state)
    if "vue_active" not in st.session_state or st.session_state.get("vue_active") not in ("rh", "finances"):
        st.session_state["vue_active"] = _vue_initiale()
    # vues réelles branchées aux tâches suivantes
    views = {
        "rh": _placeholder_view("RH"),
        "finances": _placeholder_view("Finances"),
    }
    run_portail(views, st.session_state, st)


if __name__ == "__main__":
    main()
