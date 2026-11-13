from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from shared.info import InfoItem

from . import core


def _ensure_state(session_state: Any) -> None:
    if "fin_mail_annee" not in session_state or "fin_mail_mois" not in session_state:
        a, m = core.mois_precedent()
        session_state.fin_mail_annee = a
        session_state.fin_mail_mois = m - 1
    if "fin_catering" not in session_state:
        session_state.fin_catering = {"present": False, "client": "", "montant_ht": 0.0, "tva": 0.0}
    if "fin_detect_nonce" not in session_state:
        session_state.fin_detect_nonce = 0


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


def _afficher_mail_popup(st_mod: Any, mail: str) -> None:
    dialog = getattr(st_mod, "dialog", None) or getattr(st_mod, "experimental_dialog", None)
    if dialog:
        @dialog("Mail comptable")
        def _dialog_mail():
            st_mod.code(mail, language="text")
        _dialog_mail()
    else:
        st_mod.code(mail, language="text")


def render(context: dict[str, Any]) -> list[InfoItem]:
    st_mod = context.get("st", st)
    session_state = context.get("session_state", st_mod.session_state)
    _ensure_state(session_state)

    st_mod.header("Finances")

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

    tab_mail, tab_verif = st_mod.tabs(["Mail comptable", "Vérification et rapprochement de TVA"])

    with tab_mail:
        st_mod.markdown("### Pièces détectées")
        if st_mod.button("Détecter les pièces", key="fin_detect_mail"):
            session_state.fin_detect_nonce += 1
            st_mod.rerun()
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
        col_left, col_right = st_mod.columns([2, 1])
        with col_left:
            st_mod.markdown("### Pièces détectées")
            if st_mod.button("Détecter les pièces", key="fin_detect_verif"):
                session_state.fin_detect_nonce += 1
                st_mod.rerun()
            for cle, intitule in (("caisse", "Rapport de caisse"), ("banque", "Relevé bancaire"), ("obypay", "Export Obypay")):
                ok = bool(fichiers_det.get(cle))
                st_mod.write(f"{'✅' if ok else '❌'} {intitule} : {_nom_affiche(fichiers_det.get(cle))}")
            if fichiers_det.get("erreur"):
                st_mod.warning(fichiers_det["erreur"])
            use_detected = st_mod.checkbox("Utiliser les fichiers détectés dans ./Finances", value=True, key="use_detected")
            with st_mod.expander("Uploads", expanded=False):
                ups_caisse = st_mod.file_uploader("Caisse (multiple)", type=["pdf", "xlsx", "xls"], accept_multiple_files=True, key="v_caisse")
                ups_banque = st_mod.file_uploader("Banque (multiple)", type=["pdf"], accept_multiple_files=True, key="v_banque")
                up_obypay = st_mod.file_uploader("Obypay (optionnel)", type=["xlsx"], key="v_obypay")

            cat = session_state.get("fin_catering", {})
            if cat.get("present"):
                st_mod.caption("Catering : présent.")
            else:
                st_mod.caption("Catering : absent.")

        with col_right:
            tva_deductible = st_mod.number_input("TVA déductible (€)", min_value=0.0, value=0.0, key="v_tva_ded")
            total_factures = st_mod.number_input("Total des factures fournisseurs (€)", min_value=0.0, value=0.0, key="v_fact")
            st_mod.caption("Informatif")
            seuil_pct = st_mod.number_input("Seuil d'écart (%)", min_value=0, max_value=50, value=20, key="v_seuil")
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
