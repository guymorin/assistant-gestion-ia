"""Assistant TVA - Comptabilite : automatisation de la declaration de TVA mensuelle.

Application Streamlit locale. La logique metier (extraction, rapprochement,
generation du mail) est isolee de Streamlit et testable unitairement ; les
dependances externes (lecture PDF/XLSX) sont injectables via des factories.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Configuration
COMPTABLE_DIR = "./Comptable"
ETABLISSEMENTS = ["HEE-REP-93100", "HEE-MAR-93100"]
MOIS = [
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
]
ANNEES = [2025, 2026, 2027]
TOLERANCE_RAPPROCHEMENT = 0.02
TOLERANCE_MIN_EUR = 100.0


def normaliser_montant(texte) -> float | None:
    if texte is None:
        return None
    s = str(texte).strip()
    if not s:
        return None
    # Nettoyer les espaces insécables et espaces multiples
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    # Conserver uniquement les chiffres et les séparateurs
    # Détecter le séparateur décimal : le dernier ',' ou '.' présent
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma == -1 and last_dot == -1:
        # Pas de séparateur : tenter un float direct
        try:
            return float(s.replace(" ", ""))
        except ValueError:
            return None
    # Le séparateur décimal est celui qui apparaît en dernier
    if last_comma > last_dot:
        decimal_sep = ","
        thousand_sep = "."
    else:
        decimal_sep = "."
        thousand_sep = ","
    # Supprimer les séparateurs de milliers (l'autre séparateur) et les espaces
    s = s.replace(" ", "")
    if thousand_sep:
        s = s.replace(thousand_sep, "")
    # Remplacer la virgule décimale par un point
    if decimal_sep == ",":
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


_MONTANT_EN_FIN = re.compile(r"^(?P<label>.*?)\s*(?P<montant>-?\d[\d\s.,]*)$")
_TAUX_TVA = re.compile(r"^tva\s+(?P<taux>\d+(?:[.,]\d+)?)\s*%$")
_LIBELLES_DEBUT_TAXES = {"b. taxes", "b taxes", "taxes"}
_LIBELLES_FIN_TAXES = {"c. ventes", "c ventes", "ventes"}


def _normaliser_libelle(libelle) -> str:
    """Normalise un libellé pour les comparaisons (espaces, casse, ponctuation)."""
    if libelle is None:
        return ""
    s = str(libelle).replace("\u00a0", " ").replace("\u202f", " ")
    s = " ".join(s.split())
    return s.strip().rstrip(":").lower()


def _paires_depuis_texte_pdf(texte: str) -> list[tuple[str, str | None]]:
    """Transforme chaque ligne en (libellé, dernier montant ou None).

    Une ligne vide est ignorée. Lorsque la ligne se termine par un montant
    au format français (ex. « 27 542,50 »), le libellé est la ligne privée de
    ce montant, sinon le montant vaut ``None``.
    """
    paires: list[tuple[str, str | None]] = []
    for ligne in (texte or "").splitlines():
        ligne = ligne.replace("\u00a0", " ").replace("\u202f", " ").strip()
        if not ligne:
            continue
        correspondance = _MONTANT_EN_FIN.match(ligne)
        if correspondance and correspondance.group("label").strip():
            paires.append(
                (
                    correspondance.group("label").strip(),
                    correspondance.group("montant").strip(),
                )
            )
        else:
            paires.append((ligne, None))
    return paires


def _extraire_caisse_depuis_paires(
    paires: list[tuple[str, str | None]],
) -> dict:
    """Extrait total des ventes, TVA collectée et détail par taux des paires."""
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
    }
    libelles = [_normaliser_libelle(label) for label, _ in paires]

    # total_ventes : première paire « total des ventes » portant une valeur.
    for label, montant in paires:
        if "total des ventes" in _normaliser_libelle(label):
            valeur = normaliser_montant(montant)
            if valeur is not None:
                resultat["total_ventes"] = valeur
                break

    # Section « B. Taxes » = de « B. Taxes » à « C. Ventes ».
    debut = next(
        (i for i, libelle in enumerate(libelles) if libelle in _LIBELLES_DEBUT_TAXES),
        None,
    )
    if debut is not None:
        fin = next(
            (
                i
                for i in range(debut + 1, len(paires))
                if libelles[i] in _LIBELLES_FIN_TAXES
            ),
            len(paires),
        )
        section = paires[debut:fin]
        libelles_section = libelles[debut:fin]

        # tva_collectee : après le dernier « Total » exact de la section,
        # première ligne dont le libellé est exactement « Taxe ».
        index_total = None
        for i, libelle in enumerate(libelles_section):
            if libelle == "total":
                index_total = i
        if index_total is not None:
            for i in range(index_total + 1, len(section)):
                if libelles_section[i] == "taxe":
                    resultat["tva_collectee"] = normaliser_montant(section[i][1])
                    break

        # detail_par_taux : bloc « TVA <taux>% » suivi de ses trois montants,
        # jusqu'au prochain taux ou au « Total ».
        for i in range(len(section)):
            correspondance = _TAUX_TVA.match(libelles_section[i])
            if not correspondance:
                continue
            taux = normaliser_montant(correspondance.group("taux"))
            if taux is None:
                continue
            valeurs = {"ht": None, "tva": None, "ttc": None}
            for j in range(i + 1, len(section)):
                libelle_suivant = libelles_section[j]
                if _TAUX_TVA.match(libelle_suivant) or libelle_suivant == "total":
                    break
                if libelle_suivant == "montant hors-taxe":
                    valeurs["ht"] = normaliser_montant(section[j][1])
                elif libelle_suivant == "taxe":
                    valeurs["tva"] = normaliser_montant(section[j][1])
                elif libelle_suivant == "montant taxe comprise":
                    valeurs["ttc"] = normaliser_montant(section[j][1])
            resultat["detail_par_taux"].append({"taux": taux, **valeurs})

    if resultat["total_ventes"] is not None or resultat["tva_collectee"] is not None:
        resultat["statut"] = "ok"
    return resultat


def extraire_caisse_pdf(contenu, reader_factory=None) -> dict:
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
        "type_fichier": "caisse_pdf",
        "erreur": None,
    }
    try:
        if reader_factory is None:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(contenu))
        else:
            reader = reader_factory(contenu)
        pages = getattr(reader, "pages", []) or []
        morceaux = []
        for page in pages:
            try:
                morceaux.append(page.extract_text() or "")
            except Exception:
                continue
        texte = "\n".join(morceaux)
        extrait = _extraire_caisse_depuis_paires(_paires_depuis_texte_pdf(texte))
        resultat["total_ventes"] = extrait["total_ventes"]
        resultat["tva_collectee"] = extrait["tva_collectee"]
        resultat["detail_par_taux"] = extrait["detail_par_taux"]
        resultat["statut"] = extrait["statut"]
    except Exception as exc:
        logger.warning("extraire_caisse_pdf: %s", exc)
        resultat["statut"] = "incomplet"
        resultat["erreur"] = str(exc)
    return resultat


def main() -> None:
    pass


if __name__ == "__main__":
    main()
