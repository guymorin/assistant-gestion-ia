from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from pieces_jointes import IndexPiecesJointes
from shared.info import InfoItem

from . import logic

logger = logging.getLogger(__name__)


def _ensure_state(session_state: Any) -> None:
    if "rh_messages" not in session_state:
        session_state.rh_messages = []
    if "rh_pieces_jointes" not in session_state:
        session_state.rh_pieces_jointes = IndexPiecesJointes(logic.creer_embeddings())


@st.cache_resource(show_spinner=False)
def _vectorstore() -> Any:
    return logic.creer_vectorstore()


@st.cache_resource(show_spinner=False)
def _llm() -> Any:
    return logic.creer_llm()


def _collect_rh_infos(session_state: Any, langue: str) -> list[InfoItem]:
    base_ok = logic._base_disponible()
    infos_ing = logic.infos_ingestion()
    date_ing = infos_ing.get("date")
    chunks = infos_ing.get("chunks")
    if date_ing is None:
        ing_val = "inconnue"
    else:
        ing_val = date_ing.strftime("%d/%m/%Y %H:%M")
        if isinstance(chunks, int):
            ing_val += f" ({chunks:,} extraits)".replace(",", " ")
    pj = session_state.get("rh_pieces_jointes")
    nb_pj = len(pj.noms()) if pj is not None else 0
    items = [
        InfoItem(
            "rh_base",
            "Base documentaire RH",
            "disponible" if base_ok else "indisponible",
            "Indique si la base de documents RH (index de recherche) est présente. Sans elle, seules les pièces jointes peuvent être utilisées.",
            niveau="info" if base_ok else "warning",
        ),
        InfoItem(
            "rh_ingestion",
            "Dernière ingestion",
            ing_val,
            "Date à laquelle les documents RH ont été intégrés dans la base. Des documents ajoutés après cette date ne sont pas pris en compte sans nouvelle ingestion.",
            niveau="info" if date_ing else "warning",
        ),
        InfoItem(
            "rh_modele",
            "Modèle de langage",
            logic.LLM_MODEL,
            "Programme d’IA local qui rédige les réponses à partir des extraits trouvés.",
        ),
        InfoItem(
            "rh_embeddings",
            "Modèle d’indexation (embeddings)",
            logic.EMBEDDING_MODEL,
            "Programme qui transforme le texte en repères numériques pour retrouver les passages pertinents.",
        ),
        InfoItem(
            "rh_topk",
            "Extraits par question",
            str(logic.TOP_K),
            "Nombre de passages documentaires sélectionnés pour préparer chaque réponse (recherche diversifiée).",
        ),
        InfoItem(
            "rh_langue",
            "Langue de réponse",
            logic.LANGUES.get(logic.normaliser_langue(langue), {}).get("nom", langue),
            "Langue globale demandée pour les réponses de l’assistant RH.",
        ),
        InfoItem(
            "rh_pieces_jointes",
            "Pièces jointes en session",
            f"{nb_pj} fichier(s)",
            "Documents que vous avez joints dans la conversation RH. Ils sont analysés seuls (non mélangés à la base RH) et disparaissent à la fermeture de la session.",
        ),
    ]
    if not base_ok and nb_pj == 0:
        items.append(
            InfoItem(
                "rh_disponibilite",
                "État RH",
                "non prêt",
                "Ni base RH ni pièce jointe disponible : ajoutez des pièces jointes ou lancez l’ingestion (python ingest.py).",
                niveau="warning",
            )
        )
    return items


def _afficher_historique(st_mod: Any, session_state: Any) -> None:
    for message in session_state.rh_messages:
        with st_mod.chat_message(message["role"]):
            st_mod.markdown(message["content"])
            if message.get("fichiers"):
                st_mod.caption("Pieces jointes : " + ", ".join(message["fichiers"]))
            if message["role"] == "assistant":
                logic._afficher_sources(
                    st_mod,
                    message.get("sources", []),
                    reponse=message.get("content", ""),
                )


def _render_rh_body(context: dict[str, Any]) -> list[InfoItem]:
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    langue = logic.normaliser_langue(context.get("langue") or session_state.get("langue") or logic.LANGUE_DEFAUT)
    session_state.langue = langue  # compat avec logique existante
    _ensure_state(session_state)
    index_pj = session_state.rh_pieces_jointes

    st_mod.header("RH")
    st_mod.caption(
        "Posez vos questions RH (droit du travail, convention collective de la "
        "restauration rapide, contrats, paie, absences, Odoo...) : les reponses "
        "sont fondees sur les documents indexes, avec leurs sources."
    )
    st_mod.caption(
        "⚠️ Reponse generee automatiquement : verifiez toujours les sources "
        "affichees avant toute decision juridique ou disciplinaire."
    )

    # Contrôles propres à la vue RH (conservés dans la vue)
    with st_mod.expander("Pièces jointes et conversation", expanded=True):
        noms_pj = index_pj.noms()
        if not noms_pj:
            st_mod.caption("Aucun fichier joint (PDF, TXT, Markdown).")
        else:
            for nom in noms_pj:
                c1, c2 = st_mod.columns([5, 1])
                with c1:
                    st_mod.caption(f"📎 {nom}")
                with c2:
                    if st_mod.button("✕", key=f"rh_retirer_{nom}", help=f"Retirer {nom}"):
                        index_pj.retirer(nom)
                        st_mod.rerun()
            if st_mod.button("Tout retirer", key="rh_retirer_tout"):
                for nom in list(index_pj.noms()):
                    index_pj.retirer(nom)
                st_mod.rerun()
        if st_mod.button("Effacer la conversation", key="rh_effacer"):
            session_state.rh_messages = []
            st_mod.rerun()
        if not logic._base_disponible():
            st_mod.warning(
                "Base RH introuvable : seules les pieces jointes seront utilisees."
            )

    _afficher_historique(st_mod, session_state)

    saisie = st_mod.chat_input(
        "Posez votre question RH...",
        accept_file="multiple",
        file_type=["pdf", "txt", "md"],
        max_upload_size=20,
    )
    if saisie is not None:
        question = (getattr(saisie, "text", "") or "").strip()
        fichiers = list(getattr(saisie, "files", None) or [])
        if question or fichiers:
            noms_joints = []
            for fichier in fichiers:
                try:
                    with st_mod.spinner(f"Lecture de {fichier.name}..."):
                        index_pj.ajouter(fichier.name, fichier.getvalue())
                    noms_joints.append(fichier.name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Piece jointe ignoree (%s) : %s", fichier.name, exc)
                    st_mod.warning(f"Impossible d'ajouter {fichier.name} : {exc}")

            if not question and noms_joints:
                question = "Resume le(s) document(s) joint(s)."

            if question:
                historique = list(session_state.rh_messages[-logic.HISTORIQUE_MAX_MESSAGES :])
                message_utilisateur = {"role": "user", "content": question}
                if noms_joints:
                    message_utilisateur["fichiers"] = noms_joints
                session_state.rh_messages.append(message_utilisateur)
                with st_mod.chat_message("user"):
                    st_mod.markdown(question)
                    if noms_joints:
                        st_mod.caption("Pieces jointes : " + ", ".join(noms_joints))

                with st_mod.chat_message("assistant"):
                    base_disponible = logic._base_disponible()
                    if not base_disponible and index_pj.est_vide():
                        st_mod.error(
                            "Base vectorielle introuvable dans ./chroma_db et aucun fichier "
                            "joint. Lancez d'abord : python ingest.py"
                        )
                    else:
                        utilise_pieces_jointes = not index_pj.est_vide()
                        try:
                            vectorstore = (
                                _vectorstore()
                                if base_disponible and not utilise_pieces_jointes
                                else None
                            )
                            if utilise_pieces_jointes:
                                st_mod.caption(
                                    "Reponse fondee uniquement sur les pieces jointes, sans "
                                    "melange avec la base RH."
                                )
                                texte_spinner = "Analyse des pieces jointes..."
                            else:
                                texte_spinner = "Recherche dans la base RH..."
                            with st_mod.spinner(texte_spinner):
                                resultat = logic.repondre(
                                    question,
                                    vectorstore,
                                    _llm(),
                                    pieces_jointes=index_pj,
                                    historique=historique,
                                    langue=langue,
                                )
                            st_mod.markdown(resultat["reponse"])
                            logic._afficher_sources(
                                st_mod, resultat["sources"], reponse=resultat["reponse"]
                            )
                            session_state.rh_messages.append(
                                {
                                    "role": "assistant",
                                    "content": resultat["reponse"],
                                    "sources": resultat["sources"],
                                }
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Echec de la generation")
                            st_mod.error(
                                "Impossible d'interroger la base RH ou les pieces jointes. "
                                f"Verifiez qu'Ollama est demarre sur {logic.OLLAMA_BASE_URL}.\n\n"
                                f"Detail : {exc}"
                            )

    return _collect_rh_infos(session_state, langue)


def render(context: dict[str, Any]) -> list[InfoItem]:
    """Point d'entrée de la vue RH pour le portail."""
    try:
        return _render_rh_body(context)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erreur dans la vue RH : {exc}")
        session_state = context.get("session_state", st.session_state)
        langue = context.get("langue", logic.LANGUE_DEFAUT)
        infos = _collect_rh_infos(session_state, langue) if "rh_pieces_jointes" in session_state else []
        infos.append(
            InfoItem(
                "rh_erreur",
                "État RH",
                "erreur",
                "La vue RH a rencontré un problème. Les informations ci-dessus peuvent être partielles.",
                niveau="error",
            )
        )
        return infos
