from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class InfoItem:
    cle: str
    libelle: str
    valeur: str
    aide: str
    niveau: str = "info"


def normalize_info_value(value: Any) -> str:
    if value is None:
        return "indisponible"
    if isinstance(value, bool):
        return "oui" if value else "non"
    return str(value)


def collect_footer_infos(*groups: Iterable[InfoItem]) -> list[InfoItem]:
    items: list[InfoItem] = []
    for group in groups:
        items.extend(list(group))
    return items
