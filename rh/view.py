from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from pieces_jointes import IndexPiecesJointes
from shared.info import InfoItem
from shared.qr_config import rh_config
from shared.qr_view import render_qr as _render_qr_generic

from . import logic, onboarding

logger = logging.getLogger(__name__)

SOUS_VUES = ("Q&R", "Onboarding")
SOUS_VUE_DEFAUT = "Q&R"


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
    if not _state_has(session_state, "rh_messages"):
        session_state.rh_messages = []
    if not _state_has(session_state, "rh_pieces_jointes"):
        session_state.rh_pieces_jointes = IndexPiecesJointes(logic.creer_embeddings())
    if not _state_has(session_state, "rh_sous_vue") or _state_get(session_state, "rh_sous_vue") not in SOUS_VUES:
        session_state.rh_sous_vue = SOUS_VUE_DEFAUT
    if not _state_has(session_state, "rh_onb_checklist") or not isinstance(_state_get(session_state, "rh_onb_checklist"), dict):
        session_state.rh_onb_checklist = {}
    if not _state_has(session_state, "rh_onb_data") or not isinstance(_state_get(session_state, "rh_onb_data"), dict):
        session_state.rh_onb_data = dict(onboarding.CHAMPS_DEFAUT)


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
                "Ni base RH ni pièce jointe disponible : ajoutez des pièces jointes ou lancez l’ingestion du module RH (python ingest.py --module rh).",
                niveau="warning",
            )
        )
    return items


def _collect_onboarding_infos(session_state: Any) -> list[InfoItem]:
    checklist = session_state.get("rh_onb_checklist") or {}
    total = 7
    fait = sum(1 for i in range(1, total + 1) if checklist.get(f"etape_{i}"))
    data = session_state.get("rh_onb_data") or {}
    etab = data.get("etablissement") or "non sélectionné"
    nom = onboarding.nom_complet(data) or "non renseigné"
    return [
        InfoItem(
            "rh_onb_vue",
            "Sous-module RH",
            "Onboarding",
            "Vue de gestion de l’onboarding : checklist interactive, formulaire salarié et génération depuis les modèles RH-Onboarding.",
        ),
        InfoItem(
            "rh_onb_avancement",
            "Avancement onboarding",
            f"{fait}/{total} étape(s) cochée(s)",
            "Progression de la checklist d’onboarding (mémorisée en session).",
            niveau="info" if fait == total else "warning",
        ),
        InfoItem(
            "rh_onb_salarie",
            "Salarié (formulaire)",
            nom,
            "Identité renseignée dans le formulaire d’onboarding (session en cours).",
        ),
        InfoItem(
            "rh_onb_etablissement",
            "Établissement",
            str(etab),
            "Établissement sélectionné pour la recherche des modèles dans RH-Onboarding.",
        ),
    ]


def _afficher_historique(st_mod: Any, session_state: Any) -> None:
    # Avatars Streamlit natifs (icônes Material)
    for message in session_state.rh_messages:
        role = message.get("role", "user")
        avatar = role if role in {"user", "assistant"} else "user"
        with st_mod.chat_message(role, avatar=avatar):
            st_mod.markdown(message["content"])
            if message.get("fichiers"):
                st_mod.caption("Pièces jointes : " + ", ".join(message["fichiers"]))
            if message["role"] == "assistant":
                logic._afficher_sources(
                    st_mod,
                    message.get("sources", []),
                    reponse=message.get("content", ""),
                )


def render_pieces_jointes(st_mod: Any, session_state: Any, *, expanded: bool = True) -> None:
    """Affiche le bloc de gestion des pièces jointes RH (barre latérale droite)."""
    _ensure_state(session_state)
    index_pj = session_state.rh_pieces_jointes
    # --- Section pièces jointes en haut (dans l'expander) ---
    with st_mod.expander("Pièces jointes", expanded=expanded):
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
    # --- Bouton "Effacer la conversation" placé en dessous de l'expander, sans chevauchement ---
    st_mod.divider()
    if st_mod.button("Effacer la conversation", key="rh_effacer", help="Supprimer tout l'historique de conversation"):
        session_state.rh_messages = []
        st_mod.rerun()
    if not logic._base_disponible():
        st_mod.warning(
            "Base RH introuvable (chroma_db/rh) : seules les pieces jointes seront utilisees. "
            "Lancez l'ingestion du module RH (python ingest.py --module rh)."
        )


def _inject_sous_menu_style(st_mod: Any) -> None:
    st_mod.markdown(
        """
        <style>
.rh-sous-menu { margin: 0rem 0 0.2rem; }
        .rh-sous-menu [data-testid="stHorizontalBlock"] { gap: 0.2rem; align-items: flex-start; }
        .rh-sous-menu [data-testid="column"] { width: auto !important; flex: 0 0 auto; min-width: 0; }
        .rh-sous-menu [data-testid="baseButton-secondary"],
        .rh-sous-menu [data-testid="baseButton-primary"] {
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
        .rh-sous-menu [data-testid="baseButton-secondary"]:hover {
            border-color: #c9c1b2;
            background: #ffffff;
            color: var(--ink, #1F2421);
        }
        .rh-sous-menu [data-testid="baseButton-primary"],
        .rh-sous-menu [data-testid="baseButton-primary"]:hover,
        .rh-sous-menu [data-testid="baseButton-primary"]:focus {
            border: 1px solid var(--brick-orange, #B85C38);
            background: var(--brick-orange, #B85C38);
            color: #ffffff;
        }
        .rh-sous-menu [data-baseweb="tab"][aria-selected="true"],
        .rh-sous-menu [role="tab"][aria-selected="true"],
        .rh-sous-menu button[aria-selected="true"] {
            border-bottom: 3px solid var(--brick-orange, #B85C38) !important;
            color: var(--brick-orange, #B85C38) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sous_menu(st_mod: Any, session_state: Any) -> str:
    _inject_sous_menu_style(st_mod)
    st_mod.markdown('<div class="rh-sous-menu">', unsafe_allow_html=True)

    segmented = getattr(st_mod, "segmented_control", None) or getattr(st_mod, "pills", None)
    if segmented is not None:
        selection = segmented(
            "Section RH",
            options=list(SOUS_VUES),
            selection_mode="single",
            default=session_state.rh_sous_vue,
            key="rh_sous_vue_widget",
            label_visibility="collapsed",
        )
        if selection in SOUS_VUES:
            session_state.rh_sous_vue = selection
    else:
        # Utilisation de colonnes alignées en haut pour matcher l'axe des blocs latéraux droits
        cols = st_mod.columns([1, 1.2, 6])
        for idx, option in enumerate(SOUS_VUES):
            actif = session_state.rh_sous_vue == option
            with cols[idx]:
                if st_mod.button(
                    option,
                    key=f"rh_sous_vue_{idx}",
                    type="primary" if actif else "secondary",
                    use_container_width=True,
                ):
                    session_state.rh_sous_vue = option

    st_mod.markdown("</div>", unsafe_allow_html=True)
    if session_state.rh_sous_vue not in SOUS_VUES:
        session_state.rh_sous_vue = SOUS_VUE_DEFAUT
    return session_state.rh_sous_vue


def _render_qr(st_mod: Any, session_state: Any, langue: str) -> list[InfoItem]:
    # Délègue au cœur Q&R générique paramétré par la config RH
    cfg = rh_config()
    return _render_qr_generic(
        st_mod, session_state, cfg, langue
    )


def _render_rh_body(context: dict[str, Any]) -> list[InfoItem]:
    """Compatibilité tests/appels existants : rendu du corps Q&R RH."""
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    langue = logic.normaliser_langue(context.get("langue") or session_state.get("langue") or logic.LANGUE_DEFAUT)
    _ensure_state(session_state)
    return _render_qr(st_mod, session_state, langue)


def _onb_update_data(session_state: Any, key: str, value: Any) -> None:
    data = session_state.rh_onb_data
    data[key] = value


def _render_formulaire_onboarding(st_mod: Any, session_state: Any) -> dict[str, Any]:
    data = session_state.rh_onb_data
    etabs = onboarding.etablissements_disponibles()
    if not data.get("etablissement") and etabs:
        data["etablissement"] = etabs[0]

    st_mod.subheader("Informations du salarié")
    st_mod.caption(
        "Ces informations servent à pré-remplir les documents RH et la DPAE. "
        "Vérifiez toujours les documents générés avant signature ou envoi."
    )

    # --- Identité ---
    st_mod.markdown("#### Identité")
    col1, col2, col3 = st_mod.columns([1, 2, 2], gap="medium")
    with col1:
        data["civilite"] = st_mod.selectbox(
            "Civilité",
            ["M.", "Mme"],
            index=0 if data.get("civilite", "M.") == "M." else 1,
            key="onb_civilite",
        )
    with col2:
        data["prenom"] = st_mod.text_input("Prénom", value=data.get("prenom", ""), key="onb_prenom")
    with col3:
        data["nom"] = st_mod.text_input("Nom", value=data.get("nom", ""), key="onb_nom")

    data["adresse"] = st_mod.text_input(
        "Adresse postale",
        value=data.get("adresse", ""),
        placeholder="Numéro, voie, code postal, ville",
        key="onb_adresse",
    )

    st_mod.markdown("#### État civil et identification")
    c1, c2, c3 = st_mod.columns(3, gap="medium")
    with c1:
        data["date_naissance"] = st_mod.text_input(
            "Date de naissance", value=data.get("date_naissance", ""), placeholder="JJ/MM/AAAA", key="onb_dnaiss"
        )
    with c2:
        data["lieu_naissance"] = st_mod.text_input(
            "Lieu de naissance", value=data.get("lieu_naissance", ""), placeholder="Ville (pays)", key="onb_lnaiss"
        )
    with c3:
        data["nationalite"] = st_mod.text_input("Nationalité", value=data.get("nationalite", ""), key="onb_nat")

    c1, c2 = st_mod.columns(2, gap="medium")
    with c1:
        data["numero_secu"] = st_mod.text_input(
            "N° de sécurité sociale", value=data.get("numero_secu", ""), placeholder="15 chiffres", key="onb_secu"
        )
    with c2:
        if etabs:
            idx = etabs.index(data["etablissement"]) if data.get("etablissement") in etabs else 0
            data["etablissement"] = st_mod.selectbox("Établissement", etabs, index=idx, key="onb_etab")
        else:
            st_mod.warning("Aucun établissement trouvé dans RH-Onboarding.")
            data["etablissement"] = st_mod.text_input("Établissement", value=data.get("etablissement", ""), key="onb_etab_txt")

    st_mod.divider()

    # --- Contrat ---
    st_mod.markdown("#### Poste et contrat")
    data["type_emploi"] = st_mod.text_input(
        "Intitulé du poste / emploi (CCN restauration rapide)",
        value=data.get("type_emploi", onboarding.CHAMPS_DEFAUT["type_emploi"]),
        key="onb_emploi",
    )

    c1, c2, c3 = st_mod.columns(3, gap="medium")
    with c1:
        data["date_debut_contrat"] = st_mod.text_input(
            "Date de début du contrat", value=data.get("date_debut_contrat", ""), placeholder="JJ/MM/AAAA", key="onb_debut"
        )
    with c2:
        data["heure_debut"] = st_mod.text_input(
            "Heure de début", value=data.get("heure_debut", "09:00"), placeholder="09:00", key="onb_heure"
        )
    with c3:
        data["duree_hebdo"] = st_mod.number_input(
            "Durée hebdomadaire (h)", min_value=0.0, max_value=60.0, value=float(data.get("duree_hebdo", 35.0) or 0.0), step=0.5, key="onb_duree"
        )

    data["horaires"] = st_mod.text_input(
        "Horaires prévisionnels",
        value=data.get("horaires", ""),
        placeholder="Ex. 09:00–17:00, du lundi au vendredi",
        key="onb_horaires",
    )

    st_mod.divider()

    # --- Rémunération ---
    st_mod.markdown("#### Rémunération")
    st_mod.caption(
        "Saisissez le salaire ou le taux horaire, puis utilisez le recalcul adapté "
        "(base : durée hebdomadaire × 52 / 12). Les valeurs restent modifiables."
    )
    c1, c2 = st_mod.columns(2, gap="medium")
    with c1:
        data["salaire_brut_mensuel"] = st_mod.number_input(
            "Salaire brut mensuel (€)", min_value=0.0, value=float(onboarding._to_float(data.get("salaire_brut_mensuel"))), step=10.0, key="onb_salaire"
        )
    with c2:
        data["taux_horaire_brut"] = st_mod.number_input(
            "Taux horaire brut (€)", min_value=0.0, value=float(onboarding._to_float(data.get("taux_horaire_brut"))), step=0.1, format="%.2f", key="onb_taux"
        )

    b1, b2, _ = st_mod.columns([1.4, 1.4, 2], gap="small")
    with b1:
        if st_mod.button("Calculer le taux depuis le salaire", key="onb_calc_taux", use_container_width=True):
            data["taux_horaire_brut"] = onboarding.calculer_taux_depuis_salaire(data.get("duree_hebdo", 0), data.get("salaire_brut_mensuel", 0))
            session_state["onb_taux"] = data["taux_horaire_brut"]
            st_mod.rerun()
    with b2:
        if st_mod.button("Calculer le salaire depuis le taux", key="onb_calc_salaire", use_container_width=True):
            data["salaire_brut_mensuel"] = onboarding.calculer_salaire_depuis_taux(data.get("duree_hebdo", 0), data.get("taux_horaire_brut", 0))
            session_state["onb_salaire"] = data["salaire_brut_mensuel"]
            st_mod.rerun()

    session_state.rh_onb_data = data
    return data





def _render_modeles(st_mod: Any, data: dict[str, Any], filtre: list[str] | None = None, key_prefix: str = "m") -> None:
    etab = data.get("etablissement") or ""
    if not etab:
        st_mod.caption("Sélectionnez un établissement pour accéder aux modèles.")
        return
    modeles = onboarding.lister_modeles(etab)
    if filtre:
        fl = [f.lower() for f in filtre]
        modeles = [m for m in modeles if any(tok in m.name.lower() for tok in fl)]
    if not modeles:
        st_mod.caption("Aucun modèle correspondant dans RH-Onboarding pour cet établissement.")
        return
    for modele in modeles:
        cols = st_mod.columns([3, 1.2, 1.2])
        suffix = modele.suffix.lower()
        base_key = f"{key_prefix}_{etab}_{modele.name}"
        with cols[0]:
            st_mod.caption(f"📄 {modele.name}")
        try:
            original = modele.read_bytes()
        except Exception as exc:
            st_mod.caption(f"Erreur: {exc}")
            continue
        with cols[1]:
            st_mod.download_button(
                "Originale",
                data=original,
                file_name=modele.name,
                mime="application/octet-stream",
                key=f"dl_orig_{base_key}",
                use_container_width=True,
            )
        with cols[2]:
            if suffix in {".ott", ".odt"}:
                try:
                    rempli, out_name = onboarding.generer_document_rempli(modele, data)
                    st_mod.download_button(
                        "Pré-remplie",
                        data=rempli,
                        file_name=out_name,
                        mime="application/vnd.oasis.opendocument.text",
                        key=f"dl_fill_{base_key}",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st_mod.caption(f"Génération indisponible: {exc}")
            else:
                st_mod.caption("PDF (sans pré-remplissage)")


def _checklist_item(st_mod: Any, session_state: Any, key: str, label: str) -> bool:
    val = bool(session_state.rh_onb_checklist.get(key, False))
    new_val = st_mod.checkbox(label, value=val, key=f"onb_ck_{key}")
    session_state.rh_onb_checklist[key] = bool(new_val)
    return bool(new_val)


def _render_onboarding(st_mod: Any, session_state: Any) -> list[InfoItem]:
    st_mod.caption(
        "Interface de gestion de l’onboarding : renseignez les informations du salarié, "
        "générez les documents pré-remplis depuis les modèles de RH-Onboarding et suivez la checklist."
    )
    st_mod.info(
        "Les documents sont pré-remplis au mieux à partir des informations saisies (substitution dans les modèles). "
        "Ouvrez-les dans LibreOffice pour vérifier/compléter avant signature ou envoi."
    )

    st_mod.markdown(
        """
        <style>
        .stTabs [data-baseweb="tab-highlight"] { background-color: var(--brick-orange, #B85C38) !important; }
        .stTabs [aria-selected="true"][data-baseweb="tab"] { color: var(--brick-orange, #B85C38) !important; }
        .stTabs [data-baseweb="tab-border"] { border-bottom-color: var(--line, #DDD7CB) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tab_creer, tab_checklist = st_mod.tabs(["Créer un nouveau salarié", "Checklist"])

    with tab_creer:
        data = _render_formulaire_onboarding(st_mod, session_state)
        if st_mod.button("Valider", type="primary", key="onb_valider"):
            ok, msg = onboarding.creer_dossier_salarie(data)
            if ok:
                st_mod.success(
                    f"Dossier salarié créé : {msg}. Les informations ont été mémorisées (.config) et peuvent être réutilisées pour la checklist."
                )
            else:
                st_mod.error(msg)

    with tab_checklist:
        data = session_state.rh_onb_data
        st_mod.subheader("Checklist d’onboarding")

        # Chargement d'un salarié enregistré (infos mémorisées dans le dossier)
        etab_charge = (data.get("etablissement") or "").strip()
        try:
            from shared.portal_settings import load_portal_settings

            base_charge = str((load_portal_settings().get("rh_base_paths") or {}).get(etab_charge) or "").strip()
        except Exception:
            base_charge = ""
        if base_charge:
            dossiers = onboarding.lister_dossiers_salaries_avec_config(base_charge)
            if dossiers:
                options = ["(formulaire en cours)"] + [d.name for d in dossiers]
                selection = st_mod.selectbox(
                    "Salarié enregistré (charger les informations mémorisées)",
                    options=options,
                    key="onb_select_salarie",
                    help="Charge les informations enregistrées dans le fichier .config du dossier salarié pour réutiliser la checklist.",
                )
                if selection != "(formulaire en cours)":
                    if st_mod.button("Charger", key="onb_charger_salarie"):
                        choisi = next((d for d in dossiers if d.name == selection), None)
                        if choisi is not None:
                            charge = onboarding.charger_config_salarie(choisi)
                            if charge is not None:
                                merged = dict(onboarding.CHAMPS_DEFAUT)
                                merged.update(charge)
                                session_state.rh_onb_data = merged
                                # synchronise les champs du formulaire pour refléter les données chargées
                                session_state["onb_civilite"] = merged.get("civilite", "M.")
                                session_state["onb_prenom"] = merged.get("prenom", "")
                                session_state["onb_nom"] = merged.get("nom", "")
                                session_state["onb_adresse"] = merged.get("adresse", "")
                                session_state["onb_dnaiss"] = merged.get("date_naissance", "")
                                session_state["onb_lnaiss"] = merged.get("lieu_naissance", "")
                                session_state["onb_nat"] = merged.get("nationalite", "")
                                session_state["onb_secu"] = merged.get("numero_secu", "")
                                session_state["onb_etab"] = merged.get("etablissement", "")
                                session_state["onb_etab_txt"] = merged.get("etablissement", "")
                                session_state["onb_emploi"] = merged.get(
                                    "type_emploi", onboarding.CHAMPS_DEFAUT.get("type_emploi", "")
                                )
                                session_state["onb_debut"] = merged.get("date_debut_contrat", "")
                                session_state["onb_heure"] = merged.get("heure_debut", "09:00")
                                session_state["onb_duree"] = float(onboarding._to_float(merged.get("duree_hebdo", 35.0)))
                                session_state["onb_horaires"] = merged.get("horaires", "")
                                session_state["onb_salaire"] = float(
                                    onboarding._to_float(merged.get("salaire_brut_mensuel", 0.0))
                                )
                                session_state["onb_taux"] = float(
                                    onboarding._to_float(merged.get("taux_horaire_brut", 0.0))
                                )
                                st_mod.success(f"Informations chargées depuis : {choisi}")
                                st_mod.rerun()
                            else:
                                st_mod.error("Impossible de lire le fichier .config de ce salarié.")
            else:
                st_mod.caption(
                    "Aucun salarié enregistré (.config) trouvé pour cet établissement dans le chemin RH configuré."
                )
        elif etab_charge:
            st_mod.caption(
                "Chemin racine RH non configuré pour cet établissement : enregistrez-le dans Paramètres pour charger des salariés mémorisés."
            )
        else:
            st_mod.caption("Sélectionnez un établissement dans le formulaire pour charger un salarié enregistré.")

        checklist = session_state.rh_onb_checklist

        # Étape 1
        with st_mod.expander("1. Informations RH — Pour la gestion de son dossier RH", expanded=not checklist.get("etape_1")):
            _checklist_item(st_mod, session_state, "etape_1", "Étape 1 terminée")
            st_mod.markdown(
                "- Remettre le document **Informations RH** au salarié pour qu’il le complète.\n"
                "- Demander au salarié d’envoyer les informations par mail à l’adresse indiquée."
            )
            _render_modeles(st_mod, data, filtre=["Informations", "Accuse", "Accusé"], key_prefix="etape1")

        # Étape 2
        with st_mod.expander("2. Fiche salarié Odoo — Création de la fiche salarié", expanded=not checklist.get("etape_2")):
            _checklist_item(st_mod, session_state, "etape_2", "Étape 2 terminée")
            st_mod.markdown("- Créer une nouvelle fiche pour le salarié sur Odoo à partir des informations recueillies.")

        # Étape 3
        with st_mod.expander("3. Contrat de travail — Pour la signature de son contrat et des documents annexes", expanded=not checklist.get("etape_3")):
            _checklist_item(st_mod, session_state, "etape_3", "Étape 3 terminée")
            st_mod.markdown(
                "- Imprimer le document en deux exemplaires et faire signer.\n"
                "- Imprimer les autres documents si nécessaire : dispense de mutuelle, moins de 24h..."
            )
            _render_modeles(st_mod, data, filtre=["CDI", "Contrat", "Avenant", "Dispense", "Moins", "mutuelle"], key_prefix="etape3")

        # Étape 4
        with st_mod.expander("4. Adhésion à SwissLife — Pour l’adhésion à la prévoyance et à la mutuelle", expanded=not checklist.get("etape_4")):
            _checklist_item(st_mod, session_state, "etape_4", "Étape 4 terminée")
            st_mod.markdown(
                "- Remplir le document et l’envoyer par mail à l’agence SwissLife accompagné de l’attestation Ameli et du RIB-IBAN du salarié : "
                "📧 [vincennes@agence-swisslife.fr](mailto:vincennes@agence-swisslife.fr)"
            )
            _render_modeles(st_mod, data, filtre=["Swiss", "Mutuelle", "Adhesion", "Adhésion"], key_prefix="etape4")

        # Étape 5
        with st_mod.expander("5. Règlement intérieur — Pour que le règlement soit connu du salarié", expanded=not checklist.get("etape_5")):
            _checklist_item(st_mod, session_state, "etape_5", "Étape 5 terminée")
            st_mod.markdown(
                "- Imprimer et faire signer."
            )
            _render_modeles(st_mod, data, filtre=["Reglement", "Règlement", "Interieur", "Intérieur"], key_prefix="etape5")

        # Étape 6
        with st_mod.expander("6. Déclaration d’embauche (DPAE) — Conformité Urssaf (~48h avant le début de contrat)", expanded=not checklist.get("etape_6")):
            _checklist_item(st_mod, session_state, "etape_6", "Étape 6 terminée")
            st_mod.markdown(
                "- Envoyer le message au cabinet comptable Bruno Encaoua : 📧 [r.benassayag@orange.fr](mailto:r.benassayag@orange.fr)\n"
                "  - avec en PJ : pièce d’identité et attestation Ameli"
            )
            msg = onboarding.message_dpae(data)
            st_mod.text_area("Modèle de message DPAE (pré-rempli)", value=msg, height=320, key="onb_dpae_msg")

        # Étape 7
        with st_mod.expander("7. Visite d’Information et de Prévention (VIP) — Visite médicale obligatoire", expanded=not checklist.get("etape_7")):
            _checklist_item(st_mod, session_state, "etape_7", "Étape 7 terminée")
            st_mod.markdown("- Demander sur Amet : 🌐 [https://amet.padoa.fr/](https://amet.padoa.fr/)")

    return _collect_onboarding_infos(session_state)


def render(context: dict[str, Any]) -> list[InfoItem]:
    """Point d'entrée de la vue RH pour le portail."""
    try:
        st_mod = context.get("st", st)
        session_state = context.get("session_state", st_mod.session_state)
        langue = logic.normaliser_langue(context.get("langue") or session_state.get("langue") or logic.LANGUE_DEFAUT)
        _ensure_state(session_state)

        sous_vue = _render_sous_menu(st_mod, session_state)
        st_mod.header(sous_vue)

        if sous_vue == "Onboarding":
            return _render_onboarding(st_mod, session_state)
        return _render_qr(st_mod, session_state, langue)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erreur dans la vue RH : {exc}")
        session_state = context.get("session_state", st.session_state)
        langue = context.get("langue", logic.LANGUE_DEFAUT)
        try:
            _ensure_state(session_state)
        except Exception:
            pass
        infos = _collect_rh_infos(session_state, langue) if _state_has(session_state, "rh_pieces_jointes") else []
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
