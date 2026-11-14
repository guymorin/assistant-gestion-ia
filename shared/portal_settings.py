from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PORTAL_SETTINGS_FILE = Path(".streamlit/portail_settings.json")
THEME_MODES = ("systeme", "clair", "sombre")
THEME_LABELS = {"systeme": "Système", "clair": "Clair", "sombre": "Sombre"}


def _default_settings() -> dict[str, Any]:
    return {"theme_mode": "systeme"}


def load_portal_settings(path: str | Path = PORTAL_SETTINGS_FILE) -> dict[str, Any]:
    settings = _default_settings()
    p = Path(path)
    if not p.is_file():
        return settings
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if data.get("theme_mode") in THEME_MODES:
                settings["theme_mode"] = data["theme_mode"]
    except Exception:
        return settings
    return settings


def save_portal_settings(settings: dict[str, Any], path: str | Path = PORTAL_SETTINGS_FILE) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "theme_mode": settings.get("theme_mode", "systeme")
        if settings.get("theme_mode") in THEME_MODES
        else "systeme"
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_finances_config(path: str | Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    """Retourne (lignes_brutes, entrées par établissement).

    Chaque entrée: source, cible, mode, libelle_mail.
    """
    p = Path(path)
    entries: dict[str, dict[str, str]] = {}
    lines: list[str] = []
    if not p.is_file():
        return lines, entries
    lines = p.read_text(encoding="utf-8").splitlines()
    for line in lines:
        brute = line.strip()
        if not brute or brute.startswith("#") or ":" not in brute:
            continue
        nom, reste = brute.split(":", 1)
        etab = nom.strip()
        champs = [c.strip() for c in reste.split(";")]
        entries[etab] = {
            "source": champs[0] if len(champs) > 0 else "",
            "cible": champs[1] if len(champs) > 1 else "",
            "mode": champs[2] if len(champs) > 2 else "",
            "libelle_mail": champs[3] if len(champs) > 3 else "",
        }
    return lines, entries


def _format_entry_line(etab: str, data: dict[str, str]) -> str:
    source = (data.get("source") or "").strip()
    cible = (data.get("cible") or "").strip()
    mode = (data.get("mode") or "").strip()
    libelle = (data.get("libelle_mail") or "").strip()
    parts = [source, cible, mode]
    if libelle:
        parts.append(libelle)
    return f"{etab}: " + ";".join(parts)


def write_finances_config(
    path: str | Path,
    updates: dict[str, dict[str, str]],
    original_lines: list[str] | None = None,
) -> None:
    """Met à jour les lignes d'établissements dans Finances-config.txt.

    Conserve les commentaires/lignes vides. Ajoute les établissements absents à la fin.
    """
    p = Path(path)
    if original_lines is None:
        original_lines, _ = read_finances_config(p)
    lines = list(original_lines)
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        brute = line.strip()
        if brute and not brute.startswith("#") and ":" in brute:
            nom = brute.split(":", 1)[0].strip()
            if nom in updates:
                new_lines.append(_format_entry_line(nom, updates[nom]))
                seen.add(nom)
                continue
        new_lines.append(line)
    for etab, data in updates.items():
        if etab not in seen:
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
            new_lines.append(_format_entry_line(etab, data))
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(new_lines)
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text, encoding="utf-8")
