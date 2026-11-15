from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from shared.info import InfoItem

from . import core, logic

logger = logging.getLogger(__name__)

SOUS_VUES = ("Q&R", "Déclaration de TVA")
SOUS_VUE_DEFAUT = "Q&R"
TEXTE_QR = "Posez vos questions finances : les réponses sont fondées sur les documents indexés, avec leurs sources."
# ancien : Posez vos questions Finances : les réponses sont fondées sur les documents indexés, avec leurs sources.
# ancien : Posez vos questions Finances : les reponses sont fondees sur les documents indexes, avec leurs sources.
AVERTISSEMENT_QR = "⚠️  Réponse génerée automatiquement : vérifiez toujours les sources affichées avant toute décision administrative et financière."


def _ensure_state(session_state: Any) -> None:
    if "fin_pieces_jointes" not in session_state:
        from pieces_jointes import IndexPiecesJointes

        try:
            embeddings = logic.creer_embeddings()
        except Exception:  # noqa: BLE001
            embeddings = None
        session_state.fin_pieces_jointes = IndexPiecesJointes(embeddings=embeddings or [])
    if "fin_mail_annee" not in session_state or "fin_mail_mois" not in session_state:
        a, m = core.mois_precedent()
        session_state.fin_mail_annee = a
        session_state.fin_mail_mois = m - 1
    if "fin_catering" not in session_state:
        session_state.fin_catering = {"present": False, "client": "", "montant_ht": 0.0, "tva": 0.0}
    if "fin_detect_nonce" not in session_state:
        session_state.fin_detect_nonce = 0
    if "fin_sous_vue" not in session_state or session_state.fin_sous_vue not in SOUS_VUES:
        session_state.fin_sous_vue = SOUS_VUE_DEFAUT
    if "fin_messages" not in session_state:
        session_state.fin_messages = []


@st.cache_resource(show_spinner=False)
def _vectorstore() -> Any:
    return logic.creer_vectorstore()


@st.cache_resource(show_spinner=False)
def _llm() -> Any:
    return logic.creer_llm()


def _lire_upload(o: Any):
    if hasattr(o, "read_bytes"):
        return o.read_bytes(), getattr(o, "name", str(o))
    if hasattr(o, "getvalue"):
        return o.getvalue(), getattr(o, "name", "upload")
    return None, None


def _nom_affiche(v: Any) -> str:
    if hasattr(v, "name"):
        return v.name
    if isinstance(v, (str, Path)):
        return str(v)
    return str(v) if v is not None else "manquant"


def _collect_infos(session_state: Any, etablissement: str, annee: int, mois: int, fichiers: dict[str, Any], statut: str | None = None) -> list[InfoItem]:
    items = [
        InfoItem(
            "fin_contexte",
            "Établissement et période",
            f"{etablissement} — {core.MOIS[mois-1]} {annee}",
            "Indique l’établissement et le mois sélectionnés pour préparer les pièces et les contrôles de TVA.",
        ),
    ]
    for cle, intitule in (("caisse", "Rapport de caisse"), ("banque", "Relevé bancaire"), ("obypay", "Export Obypay")):
        ok = bool(fichiers.get(cle))
        items.append(
            InfoItem(
                f"fin_piece_{cle}",
                intitule,
                "détecté" if ok else "manquant",
                "Fichier attendu pour le mois choisi. S’il est manquant, vous pouvez utiliser le dernier mois disponible, téléverser un fichier ou lancer la détection.",
                niveau="info" if ok else "warning",
            )
        )
    if statut:
        niveau = "info" if statut == "OK" else ("warning" if statut in ("A_JUSTIFIER", "INCOMPLET") else "info")
        items.append(
            InfoItem(
                "fin_statut",
                "Statut de rapprochement",
                statut,
                "Résultat global du dernier contrôle : OK si cohérent, A_JUSTIFIER si des écarts demandent une vérification, INCOMPLET si des pièces manquent.",
                niveau=niveau,
            )
        )
    return items


def _collect_qr_infos(session_state: Any) -> list[InfoItem]:
    base_ok = logic._base_disponible()
    infos_ing = logic.infos_ingestion()
    date_ing = infos_ing.get("date")
    chunks = infos_ing.get("chunks")

    module_dir = Path(getattr(logic, "CHROMA_DIR"))
    chemins_base = getattr(logic, "_chemins_base", None)
    candidats = chemins_base(module_dir) if callable(chemins_base) else [module_dir]
    base_module = (module_dir / "chroma.sqlite3").is_file()
    base_trouvee = next(
        (dossier for dossier in candidats if (Path(dossier) / "chroma.sqlite3").is_file()),
        None,
    )
    fallback_global = base_ok and not base_module and base_trouvee is not None and Path(base_trouvee) != module_dir

    if date_ing is None:
        ing_val = "inconnue"
    else:
        ing_val = date_ing.strftime("%d/%m/%Y %H:%M")
        if isinstance(chunks, int):
            ing_val += f" ({chunks:,} extraits)".replace(",", " ")

    base_val = "disponible" if base_ok else "indisponible"
    base_aide = "Indique si l'index des documents Finances (Ingestion/Finances) est présent."
    ing_libelle = "Dernière ingestion Finances"
    ing_aide = "Date de la dernière ingestion du module Finances."
    ing_niveau = "info" if date_ing else "warning"

    if fallback_global:
        base_val = "disponible (base globale héritée)"
        base_aide = (
            "Un index ChromaDB global historique est détecté ; "
            "pour un index dédié Finances, lancez : python ingest.py --module finances"
        )
        ing_libelle = "Dernière ingestion (base globale)"
        ing_aide = "Date de la dernière ingestion connue de la base globale héritée."
        ing_niveau = "warning"

    items = [
        InfoItem(
            "fin_qr_base",
            "Base documentaire Finances",
            base_val,
            base_aide,
            niveau="info" if base_ok and not fallback_global else "warning",
        ),
        InfoItem(
            "fin_qr_ingestion",
            ing_libelle,
            ing_val,
            ing_aide,
            niveau=ing_niveau,
        ),
        InfoItem(
            "fin_qr_modele",
            "Modèle de langage",
            logic.LLM_MODEL,
            "Modèle local utilisé pour générer les réponses Finances.",
        ),
        InfoItem(
            "fin_qr_embeddings",
            "Modèle d’indexation (embeddings)",
            logic.EMBEDDING_MODEL,
            "Modèle utilisé pour indexer et retrouver les passages pertinents.",
        ),
    ]
    if not base_ok:
        items.append(
            InfoItem(
                "fin_qr_disponibilite",
                "État Q&R Finances",
                "index absent",
                "Lancez l'ingestion du module Finances : python ingest.py --module finances",
                niveau="warning",
            )
        )
    return items


def _afficher_mail_popup(st_mod: Any, mail: str) -> None:
    dialog = getattr(st_mod, "dialog", None) or getattr(st_mod, "experimental_dialog", None)
    if dialog:
        @dialog("Mail comptable")
        def _dialog_mail():
            st_mod.code(mail, language="text")
        _dialog_mail()
    else:
        st_mod.code(mail, language="text")


def _afficher_historique_qr(st_mod: Any, session_state: Any) -> None:
    for message in session_state.fin_messages:
        role = message.get("role", "user")
        avatar = role if role in {"user", "assistant"} else "user"
        with st_mod.chat_message(role, avatar=avatar):
            st_mod.markdown(message["content"])
            if message["role"] == "assistant":
                sources = message.get("sources", [])
                if sources and hasattr(logic, "_afficher_sources"):
                    logic._afficher_sources(st_mod, sources, reponse=message.get("content", ""))
                elif sources:
                    with st_mod.expander("Sources", expanded=False):
                        for i, s in enumerate(sources, 1):
                            nom = getattr(s, "nom", None) or s.get("nom") if isinstance(s, dict) else str(s)
                            st_mod.caption(f"[{i}] {nom}")


def _render_qr(st_mod: Any, session_state: Any) -> list[InfoItem]:
    st_mod.caption(TEXTE_QR)
    st_mod.caption(AVERTISSEMENT_QR)

    _afficher_historique_qr(st_mod, session_state)

    question = st_mod.chat_input("Posez votre question finances...")
    if question is not None:
        question = (question or "").strip()
        if question:
            historique = list(session_state.fin_messages[-getattr(logic, "HISTORIQUE_MAX_MESSAGES", 6):])
            session_state.fin_messages.append({"role": "user", "content": question})
            with st_mod.chat_message("user", avatar="user"):
                st_mod.markdown(question)

            with st_mod.chat_message("assistant", avatar="assistant"):
                base_disponible = logic._base_disponible()
                pj = session_state.get("fin_pieces_jointes")
                utilise_pj = pj is not None and not getattr(pj, "est_vide", lambda: True)()
                if not base_disponible and not utilise_pj:
                    msg = getattr(logic, "MESSAGE_SANS_RESULTAT", None) or "Base Finances introuvable. Lancez l'ingestion du module Finances : python ingest.py --module finances"
                    st_mod.error(msg)
                else:
                    try:
                        with st_mod.spinner("Recherche dans les pièces de contexte..." if utilise_pj else "Recherche dans la base Finances..."):
                            resultat = logic.repondre(
                                question,
                                _vectorstore() if (base_disponible and not utilise_pj) else None,
                                _llm(),
                                pieces_jointes=pj if utilise_pj else None,
                                historique=historique,
                            )
                        st_mod.markdown(resultat["reponse"])
                        sources = resultat.get("sources", [])
                        if sources and hasattr(logic, "_afficher_sources"):
                            logic._afficher_sources(st_mod, sources, reponse=resultat.get("reponse", ""))
                        session_state.fin_messages.append(
                            {
                                "role": "assistant",
                                "content": resultat["reponse"],
                                "sources": sources,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Echec de la generation Finances")
                        st_mod.error(
                            "Impossible d'interroger la base Finances. "
                            f"Vérifiez qu'Ollama est démarré sur {getattr(logic, 'OLLAMA_BASE_URL', 'http://127.0.0.1:11434')}.\n\n"
                            f"Détail : {exc}"
                        )

    try:
        from streamlit.components.v1 import html as _st_html

        _st_html(
            "<script>const m=window.parent.document.querySelector('section.main'); if(m){m.scrollTo(0,m.scrollHeight);}</script>",
            height=0,
        )
    except Exception:  # noqa: BLE001
        pass

    return _collect_qr_infos(session_state)


def _render_declaration_tva(st_mod: Any, session_state: Any) -> list[InfoItem]:
    col1, col2, col3 = st_mod.columns(3)
    with col1:
        etablissement = st_mod.selectbox("Établissement", list(core.ETABLISSEMENTS), key="fin_etab")
    with col2:
        mois_idx = st_mod.selectbox("Mois", range(12), format_func=lambda i: core.MOIS[i], key="fin_mail_mois")
    with col3:
        annee = st_mod.selectbox("Année", core.ANNEES, key="fin_mail_annee")

    mois = mois_idx + 1
    # détection (rafraîchissable via bouton)
    _ = session_state.fin_detect_nonce
    fichiers = core.trouver_fichiers(etablissement, annee, mois)

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
    tab_mail, tab_verif = st_mod.tabs(["Mail comptable", "Vérification et rapprochement de TVA"])

    with tab_mail:
        st_mod.markdown("### Pièces détectées")
        if st_mod.button("Synchroniser et détecter les pièces", key="fin_detect_mail"):
            _, err = core.synchroniser_pieces(etablissement)
            if err:
                session_state["fin_sync_msg"] = ("warning", err)
            session_state.fin_detect_nonce += 1
            st_mod.rerun()
        sync_msg = session_state.pop("fin_sync_msg", None)
        if sync_msg:
            getattr(st_mod, sync_msg[0])(sync_msg[1])
        for cle, intitule in (("caisse", "Rapport de caisse"), ("banque", "Relevé bancaire"), ("obypay", "Export Obypay")):
            ok = bool(fichiers.get(cle))
            st_mod.write(f"{'✅' if ok else '❌'} {intitule} : {_nom_affiche(fichiers.get(cle))}")
        manquants = [k for k in ("caisse", "banque", "obypay") if not fichiers.get(k)]
        if manquants:
            st_mod.warning("Certaines pièces sont manquantes pour ce mois.")
            dernier = core.dernier_mois_disponible(etablissement)
            if dernier is not None:
                if st_mod.button("Utiliser le dernier mois disponible", key="btn_dernier_mois"):
                    session_state.fin_mail_annee = dernier[0]
                    session_state.fin_mail_mois = dernier[1] - 1
                    st_mod.rerun()

        with st_mod.expander("Remplacement des pièces", expanded=False):
            up_caisse = st_mod.file_uploader("Caisse", type=["pdf", "xlsx", "xls"], key="up_caisse")
            up_banque = st_mod.file_uploader("Banque", type=["pdf"], key="up_banque")
            up_obypay = st_mod.file_uploader("Obypay", type=["xlsx"], key="up_obypay")

        pieces = dict(fichiers)
        if up_caisse is not None:
            pieces["caisse"] = up_caisse
        if up_banque is not None:
            pieces["banque"] = up_banque
        if up_obypay is not None:
            pieces["obypay"] = up_obypay

        st_mod.markdown("### Catering")
        catering_present = st_mod.checkbox(
            "Facture catering ce mois-ci ?",
            value=session_state.fin_catering.get("present", False),
            key="cat_present",
        )
        session_state.fin_catering = {
            "present": catering_present,
            "client": session_state.fin_catering.get("client", ""),
            "montant_ht": session_state.fin_catering.get("montant_ht", 0.0),
            "tva": session_state.fin_catering.get("tva", 0.0),
        }
        if catering_present:
            st_mod.info("Attention il y a des ventes en catering ce mois-ci")
            session_state.fin_catering["client"] = st_mod.text_input("Client", value=session_state.fin_catering.get("client", ""), key="cat_client")
            session_state.fin_catering["montant_ht"] = st_mod.number_input("Montant HT (€)", min_value=0.0, value=float(session_state.fin_catering.get("montant_ht", 0.0)), key="cat_ht")
            session_state.fin_catering["tva"] = st_mod.number_input("TVA (€)", min_value=0.0, value=float(session_state.fin_catering.get("tva", 0.0)), key="cat_tva")

        fichiers_mail = {cle: _nom_affiche(pieces.get(cle)) if pieces.get(cle) is not None else None for cle in ("caisse", "banque", "obypay")}

        if st_mod.button("Générer le mail", key="btn_mail"):
            mail = core.generer_mail_comptable(
                etablissement, annee, mois, fichiers_mail, catering=session_state.fin_catering
            )
            session_state.fin_dernier_mail = mail
            _afficher_mail_popup(st_mod, mail)

    statut_res = session_state.get("fin_statut")
    with tab_verif:
        fichiers_det = core.trouver_fichiers(etablissement, annee, mois)
        use_detected = True
        ups_caisse = []
        ups_banque = []
        up_obypay = None
        cat = session_state.get("fin_catering", {})

        c1, c2, c3 = st_mod.columns(3)
        with c1:
            tva_deductible = st_mod.number_input(
                "TVA déductible (€)",
                min_value=0.0,
                value=0.0,
                key="v_tva_ded",
                help="Montant total de la TVA déductible sur les achats et factures fournisseurs du mois.",
            )
        with c2:
            total_factures = st_mod.number_input(
                "Total des factures fournisseurs (€)",
                min_value=0.0,
                value=0.0,
                key="v_fact",
                help="Montant total des factures fournisseurs du mois (indicatif, non utilisé dans le calcul de la TVA à décaisser).",
            )
        with c3:
            seuil_pct = st_mod.number_input(
                "Seuil d'écart (%)",
                min_value=0,
                max_value=50,
                value=20,
                key="v_seuil",
                help="Écart maximal accepté entre les montants attendus et les relevés bancaires avant signalement à justifier.",
            )
        seuil = seuil_pct / 100.0

        if st_mod.button("Lancer la vérification", key="btn_verif"):
            try:
                caisses = []
                banques = []
                obypay_res = None

                fichiers_det_utilises = fichiers_det if use_detected else {}
                caisse_files = []
                if use_detected and fichiers_det_utilises.get("caisse"):
                    caisse_files.append(fichiers_det_utilises["caisse"])
                for uf in (ups_caisse or []):
                    caisse_files.append(uf)
                for cf in caisse_files:
                    data, nom = _lire_upload(cf)
                    if data is None:
                        continue
                    typ = core.detecter_type_fichier(nom, data)
                    if typ == "caisse_pdf":
                        caisses.append(core.extraire_caisse_pdf(data))
                    elif typ == "caisse_excel":
                        caisses.append(core.extraire_caisse_excel(data, nom))
                    elif typ == "obypay_xlsx":
                        if obypay_res is None:
                            obypay_res = core.extraire_obypay_xlsx(data)
                            st_mod.warning(f"{nom} réaffecté vers Obypay.")
                        else:
                            st_mod.warning(f"Fichier Obypay supplémentaire ignoré : {nom}")
                    elif typ == "banque_pdf":
                        banques.append(core.extraire_banque_pdf(data))
                        st_mod.warning(f"{nom} réaffecté vers Banque.")
                    else:
                        st_mod.warning(f"Type inconnu pour {nom}")

                banque_files = []
                if use_detected and fichiers_det_utilises.get("banque"):
                    banque_files.append(fichiers_det_utilises["banque"])
                for uf in (ups_banque or []):
                    banque_files.append(uf)
                for bf in banque_files:
                    data, nom = _lire_upload(bf)
                    if data is None:
                        continue
                    typ = core.detecter_type_fichier(nom, data)
                    if typ == "banque_pdf":
                        banques.append(core.extraire_banque_pdf(data))
                    elif typ in ("caisse_pdf", "caisse_excel"):
                        if typ == "caisse_pdf":
                            caisses.append(core.extraire_caisse_pdf(data))
                        else:
                            caisses.append(core.extraire_caisse_excel(data, nom))
                        st_mod.warning(f"{nom} réaffecté vers Caisse.")
                    elif typ == "obypay_xlsx":
                        if obypay_res is None:
                            obypay_res = core.extraire_obypay_xlsx(data)
                        st_mod.warning(f"{nom} réaffecté vers Obypay.")
                    else:
                        st_mod.warning(f"Type inconnu pour {nom}")

                if up_obypay is not None:
                    data, nom = _lire_upload(up_obypay)
                    if data is not None:
                        obypay_res = core.extraire_obypay_xlsx(data)
                elif use_detected:
                    if fichiers_det_utilises.get("obypay") and obypay_res is None:
                        obypay_res = core.extraire_obypay_xlsx(fichiers_det_utilises["obypay"].read_bytes())

                if not caisses and not banques and obypay_res is None:
                    st_mod.info("Aucun fichier chargé.")
                caisse_for_verif = core.agreger_caisses(caisses) if caisses else None
                banque_for_verif = core.agreger_banques(banques) if banques else None
                catering_payload = cat if cat.get("present") else None

                res = core.verifier_rapprochement(
                    caisse_for_verif, banque_for_verif, obypay_res,
                    tva_deductible, total_factures, catering=catering_payload,
                    seuil_ecart_pct=seuil,
                )
                session_state.fin_statut = res.get("statut")
                statut_res = res.get("statut")

                def _fmt_montant(valeur):
                    if valeur is None:
                        return ""
                    return core.formater_euros(valeur)

                def _fmt_pct_comptable(valeur_pourcent):
                    if valeur_pourcent is None:
                        return ""
                    return f"{round(float(valeur_pourcent), 2):,.2f}".replace(",", " ").replace(".", ",") + " %"

                def _fmt_ratio_pct(valeur):
                    if valeur is None:
                        return ""
                    return _fmt_pct_comptable(valeur * 100)

                colm1, colm2, colm3 = st_mod.columns(3)
                colm1.metric("TVA collectée", core.formater_euros(res["tva_collectee"]))
                colm2.metric("TVA déductible", core.formater_euros(res["tva_deductible"]))
                tva_dec = res["tva_a_decaisser"]
                if tva_dec is not None and tva_dec < 0:
                    colm3.metric("Crédit de TVA", core.formater_euros(res["credit_tva"]))
                else:
                    colm3.metric("TVA à décaisser", core.formater_euros(tva_dec or 0.0))

                st_mod.write(f"Statut global : **{res['statut']}**")
                sources_df = pd.DataFrame(res["sources"]).copy()
                for col in ("attendu", "banque", "ecart"):
                    if col in sources_df.columns:
                        sources_df[col] = sources_df[col].map(_fmt_montant)
                if "ecart_pct" in sources_df.columns:
                    sources_df["ecart_pct"] = sources_df["ecart_pct"].map(_fmt_ratio_pct)
                cols_num_sources = [c for c in ("attendu", "banque", "ecart", "ecart_pct") if c in sources_df.columns]
                styler_sources = sources_df.style.set_table_styles(
                    [{"selector": "th", "props": [("text-align", "center")]}]
                )
                if cols_num_sources:
                    styler_sources = styler_sources.set_properties(subset=cols_num_sources, **{"text-align": "right"})
                st_mod.dataframe(styler_sources)
                st_mod.write(f"TVA collectée caisse : {_fmt_montant(res['tva_collectee_caisse'])}")
                if res.get("tva_collectee_catering"):
                    st_mod.write(f"TVA collectée catering : {_fmt_montant(res['tva_collectee_catering'])}")
                st_mod.caption(f"Total factures fournisseurs (informatif) : {core.formater_euros(res['total_factures_fournisseurs'])}")
                for av in res.get("avertissements", []):
                    st_mod.warning(av)

                details = []
                for c in caisses:
                    details.extend(c.get("detail_par_taux") or [])
                if details:
                    details_df = pd.DataFrame(details).copy()
                    if "taux" in details_df.columns:
                        details_df["taux"] = details_df["taux"].map(_fmt_pct_comptable)
                    for col in ("ht", "tva", "ttc"):
                        if col in details_df.columns:
                            details_df[col] = details_df[col].map(_fmt_montant)
                    cols_num_details = [c for c in ("taux", "ht", "tva", "ttc") if c in details_df.columns]
                    styler_details = details_df.style.set_table_styles(
                        [{"selector": "th", "props": [("text-align", "center")]}]
                    )
                    if cols_num_details:
                        styler_details = styler_details.set_properties(subset=cols_num_details, **{"text-align": "right"})
                    st_mod.dataframe(styler_details)
            except Exception as e:
                st_mod.error(f"Erreur lors de la vérification : {e}")

    # infos footer
    fichiers_footer = core.trouver_fichiers(etablissement, annee, mois)
    return _collect_infos(session_state, etablissement, annee, mois, fichiers_footer, statut=statut_res)


def _inject_sous_menu_style(st_mod: Any) -> None:
    st_mod.markdown(
        """
        <style>
        .fin-sous-menu { margin: 0rem 0 0.2rem; }
        .fin-sous-menu [data-testid="stHorizontalBlock"] { gap: 0.2rem; align-items: flex-start; }
        .fin-sous-menu [data-testid="column"] { width: auto !important; flex: 0 0 auto; min-width: 0; }
        .fin-sous-menu [data-testid="baseButton-secondary"],
        .fin-sous-menu [data-testid="baseButton-primary"] {
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
        .fin-sous-menu [data-testid="baseButton-secondary"]:hover {
            border-color: #c9c1b2;
            background: #ffffff;
            color: var(--ink, #1F2421);
        }
        .fin-sous-menu [data-testid="baseButton-primary"],
        .fin-sous-menu [data-testid="baseButton-primary"]:hover,
        .fin-sous-menu [data-testid="baseButton-primary"]:focus {
            border: 1px solid var(--brick-orange, #B85C38);
            background: var(--brick-orange, #B85C38);
            color: #ffffff;
        }
        .fin-sous-menu [data-baseweb="tab"][aria-selected="true"],
        .fin-sous-menu [role="tab"][aria-selected="true"],
        .fin-sous-menu button[aria-selected="true"] {
            border-bottom: 3px solid var(--brick-orange, #B85C38) !important;
            color: var(--brick-orange, #B85C38) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sous_menu(st_mod: Any, session_state: Any) -> str:
    _inject_sous_menu_style(st_mod)
    st_mod.markdown('<div class="fin-sous-menu">', unsafe_allow_html=True)

    segmented = getattr(st_mod, "segmented_control", None) or getattr(st_mod, "pills", None)
    if segmented is not None:
        selection = segmented(
            "Section Finances",
            options=list(SOUS_VUES),
            selection_mode="single",
            default=session_state.fin_sous_vue,
            key="fin_sous_vue_widget",
            label_visibility="collapsed",
        )
        if selection in SOUS_VUES:
            session_state.fin_sous_vue = selection
    else:
        cols = st_mod.columns([1, 1.2, 6])
        for idx, option in enumerate(SOUS_VUES):
            actif = session_state.fin_sous_vue == option
            with cols[idx]:
                if st_mod.button(
                    option,
                    key=f"fin_sous_vue_{idx}",
                    type="primary" if actif else "secondary",
                    use_container_width=True,
                ):
                    session_state.fin_sous_vue = option

    st_mod.markdown("</div>", unsafe_allow_html=True)
    if session_state.fin_sous_vue not in SOUS_VUES:
        session_state.fin_sous_vue = SOUS_VUE_DEFAUT
    return session_state.fin_sous_vue


def render(context: dict[str, Any]) -> list[InfoItem]:
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    _ensure_state(session_state)

    sous_vue = _render_sous_menu(st_mod, session_state)
    st_mod.header(sous_vue)

    if sous_vue == "Q&R":
        return _render_qr(st_mod, session_state)
    return _render_declaration_tva(st_mod, session_state)
