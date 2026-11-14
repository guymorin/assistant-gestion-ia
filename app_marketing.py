"""Compatibilité : façade publique de l'assistant Marketing.

L'implémentation est désormais modulaire (`marketing.logic`, `marketing.view`) pour le
portail unifié, mais ce module conserve l'API publique historique utilisée
par les scripts et les tests.
"""

from __future__ import annotations

import os

import marketing.logic as _logic

# Réexporte l'API historique (y compris helpers préfixés par _) pour compatibilité.
for _name in dir(_logic):
    if _name in {"__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__", "__builtins__"}:
        continue
    globals()[_name] = getattr(_logic, _name)

__doc__ = _logic.__doc__


def main() -> None:
    """Point d'entrée compatibilité : lance le portail sur la vue Marketing."""
    os.environ.setdefault("PORTAIL_VUE", "marketing")
    try:
        from app_portail import main as portail_main

        portail_main()
    except Exception:
        # Repli sur l'implémentation historique intégrée dans marketing.logic
        _logic.main()


if __name__ == "__main__":
    main()