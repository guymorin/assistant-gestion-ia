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


def main() -> None:
    pass


if __name__ == "__main__":
    main()
