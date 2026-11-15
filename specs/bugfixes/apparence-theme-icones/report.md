# Bugfix Report: Apparence — icônes de thème et prise en compte du mode

**Date:** 2026-11-15
**Status:** Fixed

## Description of the Issue

Dans Paramètres > Apparence, le choix du mode d’affichage (Système/Clair/Sombre) utilisait des boutons radio et le mode choisi n’était pas appliqué visuellement dans l’application.

**Reproduction steps:**
1. Ouvrir Paramètres > Apparence.
2. Observer les boutons radio Système/Clair/Sombre.
3. Sélectionner Sombre (ou Clair/Système).
4. Constater que l’interface ne change pas de thème.

**Impact:** Les utilisateurs ne pouvaient pas activer un thème sombre/clair effectif depuis les paramètres.

## Investigation Summary

- **Symptoms examined:** préférence enregistrée mais UI inchangée.
- **Code inspected:** `shared/ui.py` (`render_settings_page`, `_inject_global_styles`), `shared/portal_settings.py`, `.streamlit/config.toml`.
- **Hypotheses tested:** la préférence était bien sauvegardée en session/fichier ; le CSS global injecté forçait une palette claire fixe sans tenir compte de `theme_mode`.

## Discovered Root Cause

`_inject_global_styles` injectait des variables/couleurs claires fixes et `render_settings_page` affichait des radios sans appliquer de styles conditionnels au mode choisi.

**Defect type:** Missing behavior / UI wiring (thème non appliqué)

**Why it occurred:** Le mode était stocké comme préférence mais jamais traduit en CSS effectif.

**Contributing factors:** Nombreuses couleurs de fond/bordures forcées en clair dans les styles globaux.

## Resolution for the Issue

**Changes made:**
- `shared/ui.py` - ajout de `_theme_css(theme_mode)` générant les surcharges de variables/CSS pour `sombre` et pour `systeme` via `@media (prefers-color-scheme: dark)`.
- `shared/ui.py` - `_inject_global_styles` injecte désormais les styles de thème selon `session_state.theme_mode`.
- `shared/ui.py` - Paramètres > Apparence : remplacement des radios par des boutons-icônes (🖥️/☀️/🌙), sauvegarde + `rerun` pour application immédiate, libellé d’état mis à jour.

**Approach rationale:** Réutiliser les variables et l’injection CSS existantes pour appliquer le thème sans dépendance supplémentaire, en conservant le comportement système via media query.

**Alternatives considered:**
- S’appuyer uniquement sur le thème natif Streamlit/config — insuffisant car les styles personnalisés du portail imposaient la palette claire.
- `segmented_control`/`pills` — remplacé par des boutons-icônes compatibles pour garantir des icônes dédiées.

## Regression Test

**Test file:** `tests/test_portail_shell.py`
**Test name:** `test_theme_css_applique_le_mode_choisi`

**What it verifies:** `_theme_css` produit des variables sombres pour `sombre`, une règle `prefers-color-scheme: dark` pour `systeme`, et rien pour `clair`.

**Run command:** `pytest tests/test_portail_shell.py -q` (ou exécution ciblée du test)

## Affected Files

| File | Change |
|------|--------|
| `shared/ui.py` | Application du thème (CSS) et sélecteur d’apparence en icônes |
| `tests/test_portail_shell.py` | Test de régression sur la génération CSS de thème |
| `specs/bugfixes/apparence-theme-icones/report.md` | Rapport de correctif |

## Verification

**Automated:**
- [x] Regression test passes (`python3 -m pytest tests/test_portail_shell.py -q` → 3 passed)
- [ ] Full test suite passes (non exécuté)
- [x] Linters/validators pass (`py_compile` OK sur fichiers modifiés)

**Manual verification:**
- Vérifier visuellement le basculement Clair/Sombre/Système et la persistance après rechargement.

## Prevention

**Recommendations to avoid similar bugs:**
- Toute préférence UI persistée doit être branchée à un rendu effectif (CSS/comportement), pas seulement sauvegardée.
- Centraliser les overrides de thème lorsque des couleurs sont forcées en `!important`.

## Related

- `shared/portal_settings.py` (persistance `theme_mode`)
- `.streamlit/config.toml` (thèmes Streamlit natifs)
