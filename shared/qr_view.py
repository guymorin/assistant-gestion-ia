"""Vue Q&R générique et panneau pièces jointes réutilisables.

Fournit helpers paramétrés par ``QRModuleConfig`` pour l'initialisation
d'état, le rendu chat/historique/saisie, le panneau pièces jointes et
la collecte d'informations. Conçu pour être utilisé par tous les modules
(RH, Finances, Juridique, Marketing) sans code redondant.

L'utilisation typique depuis une vue domaine ``view.render(context)`` :

````python
from shared.qr_view import ensure_state, render_qr, render_pieces_jointes, collect_qr_infos

def render(context: dict[str, Any]) -> list[InfoItem]:
    st = context["st"]
    ctx = context["session_state"]
    langue = context.get("langue") or ctx.get("langue") or "fr"
    ensure_state(ctx, ctx_cfg)  # ctx_cfg = QRModuleConfig for the module
    render_pieces_jointes(st, ctx, ctx_cfg)  # panneau latéral droit
    result = render_qr(st, ctx, ctx_cfg, langue)  # zone chat Q&R
    return collect_qr_infos(ctx, ctx_cfg, langue)  # infos footer
````
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import streamlit as st

from shared.qr_config import QRModuleConfig, QR_MODULES, get_module_config
from shared.qr_logic import (
    base_disponible,
    creer_llm,
    creer_vectorstore,
    infos_ingestion,
    normaliser_langue,
    repondre,
    construire_historique,
    question_pour_recherche,
    LANGUES,
    ROLES_HISTORIQUE,
    MESSAGES_SANS_RESULTAT,
)
from shared.info import InfoItem, collect_footer_infos

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Noms de clés session namespacés par module
# ---------------------------------------------------------------------------

def _key_messages(cfg: QRModuleConfig | str | None = None) -> str:
    """Clé session pour les messages de conversation du module."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    return f"{cfg.state_prefix}_messages"


def _key_pieces_jointes(cfg: QRModuleConfig | str | None = None) -> str:
    """Clé session pour l'index des pièces jointes du module."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)
    return f"{cfg.state_prefix}_pieces_jointes"


# ---------------------------------------------------------------------------
# Assurance d'état initialisé (namespace par module)
# ---------------------------------------------------------------------------

def ensure_state(
    session_state: Any,
    cfg: QRModuleConfig | str | None = None,
) -> None:
    """Initialise les clés de session namespacées pour un module donné.

    Crée ``<state_prefix>_messages`` et ``<state_prefix>_pieces_jointes``
    s'ils n'existent pas encore. Doit être appelé au début de chaque vue
    Q&R.
    """
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    prefix = cfg.state_prefix
    messages_key = _key_messages(cfg)
    pieces_jointes_key = _key_pieces_jointes(cfg)

    if messages_key not in session_state:
        session_state[messages_key] = []

    if pieces_jointes_key not in session_state:
        from pieces_jointes import IndexPiecesJointes

        try:
            embeddings = creer_embeddings(cfg)
        except Exception:  # noqa: BLE001 -_embeddings dispo plus tard
            embeddings = None
        session_state[pieces_jointes_key] = IndexPiecesJointes(
            embeddings=embeddings or []
        )


# ---------------------------------------------------------------------------
# Rendu chat Q&R (saisie, historique, réponse, sources)
# ---------------------------------------------------------------------------

def render_qr(
    st_mod: Any,
    session_state: Any,
    cfg: QRModuleConfig | str | None = None,
    langue: str = "fr",
) -> list[InfoItem]:
    """Rendu complet de l'interface Q&R pour un module donné.

    Affiche :
    - Le prompt d'introduction
    - L'historique des messages
    - Le champ de saisie avec accept_file (PDF, TXT, Markdown)
    - La génération de réponse (base vectorielle ou pièces jointes)
    - L'affichage des sources/détails

    Retourne la liste d''InfoItem'' pour le panneau footer.
    """
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    prefix = cfg.state_prefix
    messages_key = _key_messages(cfg)
    pieces_jointes_key = _key_pieces_jointes(cfg)
    messages = session_state.get(messages_key, [])

    # --- Prompt d'introduction ---
    if cfg.id == "marketing":
        st_mod.caption(
            "Posez vos questions marketing : les réponses sont fondées sur les documents indexés, avec leurs sources."
        )
    elif cfg.id == "juridique":
        st_mod.caption(
            "Posez vos questions juridiques : les réponses sont fondées sur les documents indexés, avec leurs sources."
        )
    elif cfg.id == "rh":
        st_mod.caption(
            "Posez vos questions RH : les réponses sont fondées sur les documents indexés, avec leurs sources."
        )
    else:
        st_mod.caption(
            f"Posez vos questions {cfg.label} (droit, convention, communication...) : "
            "les réponses sont fondées sur les documents indexés, avec leurs sources."
        )
    st_mod.caption(
        "⚠️  Réponse génerée automatiquement : vérifiez toujours les sources "
        "affichées avant toute décision."
    )

    # --- Saisie utilisateur (en haut) ---
    module_name = cfg.label if cfg.label.isupper() else cfg.label.lower()
    saisie = st_mod.chat_input(
        f"Posez votre question {module_name}...",
        accept_file="multiple",
        file_type=["pdf", "txt", "md"],
        max_upload_size=20,
    )

    if saisie is not None:
        question = (getattr(saisie, "text", "") or "").strip()
        fichiers = list(getattr(saisie, "files", None) or [])

        if question or fichiers:
            # Ajouter les fichiers joints à l'index
            noms_joints = []
            for fichier in fichiers:
                try:
                    with st_mod.spinner(f"Lecture de {fichier.name}..."):
                        session_state[pieces_jointes_key].ajouter(
                            fichier.name, fichier.getvalue()
                        )
                    noms_joints.append(fichier.name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Piece jointe ignoree (%s) : %s", fichier.name, exc)
                    st_mod.warning(f"Impossible d'ajouter {fichier.name} : {exc}")

            # Si pas de question mais des fichiers joints, proposer un résumé
            if not question and noms_joints:
                question = f"Resume le(s) document(s) joint(s)."

            # Enregistrer le message utilisateur
            message_utilisateur: dict[str, Any] = {"role": "user", "content": question}
            if noms_joints:
                message_utilisateur["fichiers"] = noms_joints
            messages.append(message_utilisateur)

            # --- Génération de la réponse ---
            # Déterminer si on utilise les pièces jointes ou la base
            utilise_pieces_jointes = not session_state[pieces_jointes_key].est_vide()

            # Préparer l'historique (messages précédents, hors le courant)
            historique = list(messages[-6:])  # HISTORIQUE_MAX_MESSAGES

            # Déterminer le vectorstore si besoin
            base_dispo = base_disponible(cfg)
            if base_dispo and not utilise_pieces_jointes:
                vectorstore = creer_vectorstore(cfg)
            else:
                vectorstore = None

            # Interroger le LLM
            llm = creer_llm(cfg)

            try:
                with st_mod.spinner(
                    "Analyse des pièces jointes..."
                    if utilise_pieces_jointes
                    else "Recherche dans la base..."
                ):
                    resultat = repondre(
                        question,
                        vectorstore=vectorstore,
                        llm=llm,
                        pieces_jointes=session_state[pieces_jointes_key],
                        historique=historique,
                        langue=langue,
                    )

                # Enregistrer le message assistant
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": resultat["reponse"],
                    "sources": resultat.get("sources", []),
                }
                if noms_joints and utilise_pieces_jointes:
                    assistant_msg["fichiers"] = noms_joints
                messages.append(assistant_msg)

            except Exception as exc:  # noqa: BLE001
                logger.exception("Echec de la génération Q&R")
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"Erreur : {exc}",
                        "sources": [],
                    }
                )

    # Mettre à jour l'état de la session
    session_state[messages_key] = messages

    # --- Affichage de l'historique (ordre chronologique croissant) ---
    # Avatars Streamlit natifs (icônes Material) : humain / robot
    for message in messages:
        role = message.get("role", "user")
        avatar = role if role in {"user", "assistant"} else "user"
        content = message.get("content", "")
        fichiers = message.get("fichiers", [])
        with st_mod.chat_message(role, avatar=avatar):
            st_mod.markdown(content)
            if fichiers:
                st_mod.caption("Pièces jointes : " + ", ".join(fichiers))
            if role == "assistant":
                sources = message.get("sources", [])
                if sources:
                    with st_mod.expander("Détails", expanded=False):
                        for i, source in enumerate(sources, 1):
                            st_mod.markdown(f"**Source [{i}]** : {source.get('nom', 'inconnue')}")
                            for extrait in source.get("extraits", []):
                                txt = extrait if len(extrait) <= 600 else extrait[:600] + "..."
                                st_mod.caption(txt)

    # Auto-scroll vers le bas pour afficher la dernière question/réponse
    try:
        from streamlit.components.v1 import html as _st_html

        _st_html(
            "<script>const m=window.parent.document.querySelector('section.main'); if(m){m.scrollTo(0,m.scrollHeight);}</script>",
            height=0,
        )
    except Exception:  # noqa: BLE001
        pass

    # Retourner les infos footer
    return collect_qr_infos(session_state, cfg, langue)


# ---------------------------------------------------------------------------
# Panneau pièces jointes générique (barre latérale droite)
# ---------------------------------------------------------------------------

def render_pieces_jointes(
    st_mod: Any,
    session_state: Any,
    cfg: QRModuleConfig | str | None = None,
    *,
    expanded: bool = True,
) -> None:
    """Affiche le panneau de gestion des pièces jointes pour un module donné.

    Identique au panneau RH mais cléed par ``<state_prefix>_pieces_jointes``
    au lieu de ``rh_pieces_jointes``.
    """
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    prefix = cfg.state_prefix
    pj_key = _key_pieces_jointes(cfg)
    index_pj = session_state.get(pj_key)

    if index_pj is None:
        # Ne pas créer l'index ici ; attendre qu'assure_state l'ait fait
        return

    # --- Section pièces jointes en haut (dans l'expander) ---
    with st_mod.expander("Fichiers de contexte", expanded=expanded):
        # Champ d'upload de fichier (contexte pour le LLM/RAG)
        fichiers_uploades = st_mod.file_uploader(
            "Ajouter un fichier",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            key=f"{prefix}_upload",
        )
        if fichiers_uploades:
            for fichier in fichiers_uploades:
                try:
                    with st_mod.spinner(f"Lecture de {fichier.name}..."):
                        index_pj.ajouter(fichier.name, fichier.getvalue())
                    st_mod.success(f"{fichier.name} ajouté au contexte.")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Piece jointe ignoree (%s) : %s", fichier.name, exc)
                    st_mod.warning(f"Impossible d'ajouter {fichier.name} : {exc}")
            st_mod.rerun()

        noms_pj = index_pj.noms()
        if not noms_pj:
            st_mod.caption("Aucun fichier joint (PDF, TXT, Markdown).")
        else:
            for nom in noms_pj:
                c1, c2 = st_mod.columns([5, 1])
                with c1:
                    st_mod.caption(f"📎 {nom}")
                with c2:
                    if st_mod.button("✕", key=f"{prefix}_retirer_{nom}", help=f"Retirer {nom}"):
                        index_pj.retirer(nom)
                        st_mod.rerun()
            if st_mod.button("Tout retirer", key=f"{prefix}_retirer_tout"):
                for nom in list(index_pj.noms()):
                    index_pj.retirer(nom)
                st_mod.rerun()

    # --- Espacement et bouton "Effacer la conversation" en dessous de l'expander ---
    st_mod.divider()
    if st_mod.button("Effacer la conversation", key=f"{prefix}_effacer", use_container_width=True):
        session_state[_key_messages(cfg)] = []
        st_mod.rerun()

    # Avertissement affiché uniquement si la base documentaire du module
    # n'a pas été ingérée : dans ce cas, seules les pièces jointes jointes
    # peuvent être utilisées. Lancez l'ingestion pour activer la recherche.
    if not base_disponible(cfg):
        st_mod.warning(
            f"Base {cfg.label.lower()} introuvable : seules les pieces jointes seront utilisees. "
            f"Lancez l'ingestion du module {cfg.label.lower()} (python ingest.py --module {cfg.id})."
        )


# ---------------------------------------------------------------------------
# Collecte d'informations footer (état base, ingestion, modèle, etc.)
# ---------------------------------------------------------------------------

def collect_qr_infos(
    session_state: Any,
    cfg: QRModuleConfig | str | None = None,
    langue: str = "fr",
) -> list[InfoItem]:
    """Retourne la liste d''InfoItem'' pour le panneau footer d'un module Q&R."""
    if isinstance(cfg, str):
        cfg = get_module_config(cfg)

    prefix = cfg.state_prefix
    messages_key = _key_messages(cfg)
    pieces_jointes_key = _key_pieces_jointes(cfg)

    base_ok = base_disponible(cfg)
    infos_ing = infos_ingestion(cfg)
    date_ing = infos_ing.get("date")
    chunks = infos_ing.get("chunks")

    if date_ing is None:
        ing_val = "inconnue"
    else:
        ing_val = date_ing.strftime("%d/%m/%Y %H:%M")
        if isinstance(chunks, int):
            ing_val += f" ({chunks:,} extraits)".replace(",", " ")

    module_dir = Path(cfg.chroma_dir)
    base_module = (module_dir / "chroma.sqlite3").is_file()

    base_val = "disponible" if base_ok else "indisponible"
    base_aide = "Base documentaire {}".format(cfg.label)
    ing_libelle = "Dernière ingestion"
    ing_aide = "Date de la dernière ingestion du module."
    ing_niveau = "info" if date_ing else "warning"

    items = [
        InfoItem(
            f"{prefix}_base",
            "Base documentaire",
            base_val,
            base_aide,
            niveau="info" if base_ok else "warning",
        ),
        InfoItem(
            f"{prefix}_ingestion",
            "Dernière ingestion",
            ing_val,
            ing_aide,
            niveau=ing_niveau,
        ),
        InfoItem(
            f"{prefix}_modele",
            "Modèle de langage",
            cfg.default_model,
            f"Modèle par défaut ({cfg.default_model}) pour le module {cfg.label}.",
        ),
        InfoItem(
            f"{prefix}_etat",
            "État conversation",
            f"{len(session_state.get(messages_key, []))} message(s)",
            "Nombre de messages dans l'historique de la conversation courante.",
        ),
    ]

    # Message d'avertissement si ni base ni PJ
    nb_pj = len(index_pj.noms()) if (index_pj := session_state.get(pieces_jointes_key)) else 0
    if not base_ok and nb_pj == 0:
        items.append(
            InfoItem(
                f"{prefix}_disponibilite",
                "État",
                "non prêt",
                f"Ni base documentaire ni pièce jointe disponible pour le module {cfg.label}. "
                f"Lancez l'ingestion (python ingest.py --module {cfg.id}).",
                niveau="warning",
            )
        )

    return items


# ---------------------------------------------------------------------------
# Points d'entrée compatibilité : réexporter les noms attendus par les vues
# existantes (rh.view, finances.view) qui importent depuis ce module.
# ---------------------------------------------------------------------------

# Ces fonctions sont des wrappers qui délèguent à la configuration du module
# courant. Les vues existantes qui font ``from shared.qr_view import ...``
# trouveront ces noms disponibles.

__all__ = [
    "ensure_state",
    "render_qr",
    "render_pieces_jointes",
    "collect_qr_infos",
    "QRModuleConfig",
]