"""Vue Q&R et déclaration spécifique au module Marketing.

Ce module expose une fonction ``render(context)`` qui rend l'interface Q&R
pour le module Marketing. Le flux Q&R réutilise le cœur ``shared.qr_view``
paramétré par la config ``marketing``, tandis que la sous-vue est laissée
comme placeholder.
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from shared.info import InfoItem
from shared.qr_config import marketing_config
from shared.qr_view import render_qr as _render_qr_generic  # chat_input, historique, sources
from shared.qr_logic import creer_embeddings

logger = logging.getLogger(__name__)

SOUS_VUES = ("Q&R", "Déclaration de campagne")
SOUS_VUE_DEFAUT = "Q&R"

TEXTE_QR = "Posez vos questions marketing : les réponses sont fondées sur les documents indexés, avec leurs sources."
# ancien : Posez vos questions Marketing : les reponses sont fondees sur les documents indexes, avec leurs sources.
AVERTISSEMENT_QR = "⚠️  Réponse génerée automatiquement : vérifiez toujours les sources affichées avant toute décision."


def _state_has(session_state: Any, key: str) -> bool:
    try:
        return key in session_state
    except TypeError:
        return hasattr(session_state, key)


def _state_get(session_state: Any, key: str, default: Any = None) -> Any:
    try:
        if key in session_state:
            return session_state[key]
    except TypeError:
        pass
    return getattr(session_state, key, default)


def _ensure_state(session_state: Any) -> None:
    if "mar_messages" not in session_state:
        session_state.mar_messages = []
    if "mar_pieces_jointes" not in session_state:
        from pieces_jointes import IndexPiecesJointes

        try:
            embeddings = creer_embeddings(marketing_config())
        except Exception:  # noqa: BLE001
            embeddings = None
        session_state.mar_pieces_jointes = IndexPiecesJointes(embeddings=embeddings or [])
    if not _state_has(session_state, "mar_sous_vue") or _state_get(session_state, "mar_sous_vue") not in SOUS_VUES:
        session_state.mar_sous_vue = SOUS_VUE_DEFAUT


def _inject_sous_menu_style(st_mod: Any) -> None:
    st_mod.markdown(
        """
        <style>
.mar-sous-menu { margin: 0rem 0 0.2rem; }
        .mar-sous-menu [data-testid="stHorizontalBlock"] { gap: 0.2rem; align-items: flex-start; }
        .mar-sous-menu [data-testid="column"] { width: auto !important; flex: 0 0 auto; min-width: 0; }
        .mar-sous-menu [data-testid="baseButton-secondary"],
        .mar-sous-menu [data-testid="baseButton-primary"] {
            border-radius: 10px;
            padding: 0.35rem 0.8rem;
            font-size: 0.88rem;
            font-weight: 500;
            line-height: 1.2;
            border: 1px solid var(--line, #DDD7CB);
            background: var(--surface, #FFFFFF);
            color: var(--ink-muted, #5E665F);
            box-shadow: none;
            transition: background-color 120ms ease, color 120ms ease, border-color 120ms ease;
        }
        .mar-sous-menu [data-testid="baseButton-secondary"]:hover {
            border-color: #c9c1b2;
            background: #ffffff;
            color: var(--ink, #1F2421);
        }
        .mar-sous-menu [data-testid="baseButton-primary"],
        .mar-sous-menu [data-testid="baseButton-primary"]:hover,
        .mar-sous-menu [data-testid="baseButton-primary"]:focus {
            border: 1px solid var(--green, #2C5B29);
            background: var(--green, #2C5B29);
            color: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sous_menu(st_mod: Any, session_state: Any) -> str:
    _inject_sous_menu_style(st_mod)
    st_mod.markdown('<div class="mar-sous-menu">', unsafe_allow_html=True)

    segmented = getattr(st_mod, "segmented_control", None) or getattr(st_mod, "pills", None)
    if segmented is not None:
        selection = segmented(
            "Section Marketing",
            options=list(SOUS_VUES),
            selection_mode="single",
            default=session_state.mar_sous_vue,
            key="mar_sous_vue_widget",
            label_visibility="collapsed",
        )
        if selection in SOUS_VUES:
            session_state.mar_sous_vue = selection
    else:
        cols = st_mod.columns([1, 1.2, 6])
        for idx, option in enumerate(SOUS_VUES):
            actif = session_state.mar_sous_vue == option
            with cols[idx]:
                if st_mod.button(
                    option,
                    key=f"mar_sous_vue_{idx}",
                    type="primary" if actif else "secondary",
                    use_container_width=True,
                ):
                    session_state.mar_sous_vue = option

    st_mod.markdown("</div>", unsafe_allow_html=True)
    if session_state.mar_sous_vue not in SOUS_VUES:
        session_state.mar_sous_vue = SOUS_VUE_DEFAUT
    return session_state.mar_sous_vue


def _render_qr(st_mod: Any, session_state: Any, langue: str) -> list[InfoItem]:
    cfg = marketing_config()
    result = _render_qr_generic(st_mod, session_state, cfg, langue)
    return result


def _render_declaration_campagne(st_mod: Any, session_state: Any) -> list[InfoItem]:
    """Placeholder : la déclaration de campagne n'est pas encore intégrée."""
    st_mod.info("Vue Déclaration de campagne en cours d'intégration dans le module Marketing.")
    return []


def render(context: dict[str, Any]) -> list[InfoItem]:
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    try:
        from marketing import logic as _logic

        langue = _logic.normaliser_langue(context.get("langue") or session_state.get("langue") or _logic.LANGUE_DEFAUT)
    except Exception:  # noqa: BLE001
        langue = "fr"
    _ensure_state(session_state)

    sous_vue = _render_sous_menu(st_mod, session_state)
    st_mod.header(sous_vue)

    if sous_vue == "Déclaration de campagne":
        return _render_declaration_campagne(st_mod, session_state)
    return _render_qr(st_mod, session_state, langue)