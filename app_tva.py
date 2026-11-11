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


def main() -> None:
    pass


if __name__ == "__main__":
    main()
