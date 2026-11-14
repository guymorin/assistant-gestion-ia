"""Vue Q&R et déclaration spécifique au module Juridique.

Ce module expose une fonction ``render(context)`` qui rend l'interface Q&R
pour le module Juridique. Le flux Q&R réutilise le cœur ``shared.qr_view``
paramétré par la config ``juridique``, tandis que la sous-vue ``Déclaration
de TVA`` (non implémentée dans cette version) est laissée comme placeholder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import streamlit as st

from shared.info import InfoItem
from shared.qr_config import juridique_config
from shared.qr_view import render_qr as _render_qr_generic

logger = logging.getLogger(__name__)

SOUS_VUES = ("Q&R", "Déclaration de TVA")
SOUS_VUE_DEFAUT = "Q&R"


def _render_qr(st_mod: Any, session_state: Any) -> list[InfoItem]:
    # Délègue au cœur Q&R générique paramétré par la config Juridique
    cfg = juridique_config()
    return _render_qr_generic(st_mod, session_state, "fr", cfg=cfg)


def _render_declaration_tva(st_mod: Any, session_state: Any) -> list[InfoItem]:
    """Placeholder : la déclaration de TVA n'est pas encore intégrée."""
    st.info("Vue Déclaration de TVA en cours d'intégration dans le module Juridique.")
    return []


def render(context: dict[str, Any]) -> list[InfoItem]:
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    _ensure_state(session_state)

    sous_vue = _render_sous_menu(st_mod, session_state)
    st_mod.header(sous_vue)

    if sous_vue == "Q&R":
        return _render_qr(st_mod, session_state)
    return _render_declaration_tva(st_mod, session_state)


def _ensure_state(session_state: Any) -> None:
    if "jur_messages" not in session_state:
        session_state.jur_messages = []
    if "jur_pieces_jointes" not in session_state:
        from pieces_jointes import IndexPiecesJointes

        session_state.jur_pieces_jointes = IndexPiecesJointes()


def _render_sous_menu(st_mod: Any, session_state: Any) -> str:
    """Retourne le titre de la sous-vue courante."""
    return session_state.get("jur_sous_vue", SOUS_VUE_DEFAUT)