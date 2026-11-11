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


def extraire_caisse_pdf(contenu, reader_factory=None) -> dict:
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
    }
    try:
        if reader_factory is None:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(contenu))
        else:
            reader = reader_factory(contenu)
        pages = getattr(reader, "pages", []) or []
        texte = ""
        for page in pages:
            try:
                texte += (page.extract_text() or "") + "\n"
            except Exception:
                continue
        # total_ventes : premiere occurrence de "Total des ventes"
        m = re.search(r"Total\s+des\s+ventes\s+([\d\s.,]+)", texte)
        if m:
            resultat["total_ventes"] = normaliser_montant(m.group(1))
        # tva_collectee : dans la section B. Taxes, bloc "Total" puis ligne "Taxe"
        # On cherche le dernier bloc "Total" de la section B Taxes (avant C. Ventes)
        section_b = texte
        idx_c = texte.find("C. Ventes")
        if idx_c != -1:
            section_b = texte[:idx_c]
        # trouver le dernier "Total" dans section_b
        positions = [m.start() for m in re.finditer(r"(?m)^\s*Total\s*$", section_b)]
        bloc_total = ""
        if positions:
            start = positions[-1]
            # prendre jusqu'a la fin de la section_b ou prochain titre
            bloc_total = section_b[start:]
        m_taxe = re.search(r"Taxe\s+([\d\s.,]+)", bloc_total)
        if m_taxe:
            resultat["tva_collectee"] = normaliser_montant(m_taxe.group(1))
        if resultat["total_ventes"] is not None or resultat["tva_collectee"] is not None:
            resultat["statut"] = "ok"
    except Exception as exc:
        logger.warning("extraire_caisse_pdf: %s", exc)
        resultat["statut"] = "incomplet"
    return resultat


def main() -> None:
    pass


if __name__ == "__main__":
    main()
