"""Compatibilité : façade publique de l'assistant Finances/TVA.

L'implémentation est désormais modulaire (`finances.core`, `finances.view`)
pour le portail unifié, mais ce module conserve l'API publique historique.
"""

from __future__ import annotations

import os

import finances.core as _core

for _name in dir(_core):
    if _name in {"__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__", "__builtins__"}:
        continue
    globals()[_name] = getattr(_core, _name)

__doc__ = _core.__doc__


def main() -> None:
    """Point d'entrée compatibilité : lance le portail sur la vue Finances."""
    os.environ.setdefault("PORTAIL_VUE", "finances")
    try:
        from app_portail import main as portail_main

        portail_main()
    except Exception:
        _core.main()


if __name__ == "__main__":
    main()
