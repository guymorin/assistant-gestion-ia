# Webdesign épuré (logo HEE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refonte visuelle complète du portail Streamlit « Assistant de Gestion - IA » dans un style épuré et soigné, basé sur les tokens `--paper`, `--green`, `--brick`, la police Roboto et le logo HEE fourni.

**Architecture:** Centraliser les tokens/typo/composants dans une injection CSS globale (`shared/ui.py`) et une navbar HTML intégrant le logo ; aligner la config Streamlit et les styles locaux des vues (RH/Finances) sur les mêmes variables. Aucun changement de logique métier.

**Tech Stack:** Python 3 / Streamlit, CSS injecté via `st.markdown(..., unsafe_allow_html=True)`, Google Fonts (Roboto), SVG asset.

**Spec:** `docs/superpowers/specs/2026-11-14-webdesign-epure-he-logo-design.md`

## Global Constraints

- Palette strictement fondée sur `--paper: #F6F2EA`, `--green: #2C5B29`, `--brick: #B85C3A` (+ neutres de soutien `--ink: #1F2421`, `--ink-muted: #5E665F`, `--line: #DDD7CB`, `--surface: #FFFFFF`) ; `--green` accent dominant, `--brick` parcimonieux.
- Typographie : Roboto (Google Fonts import), pile de repli `system-ui, -apple-system, "Segoe UI", sans-serif` ; une seule famille, hiérarchie par taille/graisse.
- Style épuré : fond papier, bordures fines, coins cohérents, pas de dégradés/ombres lourdes ni d’ornements superflus ; focus clavier visible ; contrastes AA visés.
- Logo SVG fourni intégré en asset et dans la navbar (et en icône de page si supporté).
- Ne pas modifier la logique métier, les flux de données ni les signatures fonctionnelles des vues (hors signature/style d’affichage).

## Review Focus

- **Contraste & lisibilité :** texte sur `--paper/--surface` et texte clair sur boutons `--green/--brick` restent lisibles (notamment états hover/disabled/alertes).
- **Navbar & décalage contenu :** la navbar fixe avec logo ne chevauche pas le contenu (`padding-top` du conteneur principal correct) et reste utilisable sur viewport étroit.
- **Composants Streamlit natifs :** boutons primaires/secondaires, inputs, expanders, chat messages, tabs/segmented ou sous-menus, alertes héritent des tokens sans casser la mise en page existante.
- **Import Roboto & asset logo :** la fonte est chargée (fallback propre si réseau indisponible) et le logo s’affiche (chemin/encodage SVG correct, pas de casse du HTML injecté).
- **Régression fonctionnelle :** navigation `?vue=`, menu custom, panneau Informations/pièces jointes et vues RH/Finances fonctionnent comme avant.

---

### Task 1: Ajouter l’asset logo

**Files:**
- Create: `assets/logo_hee.svg`

- [ ] **Step 1: Créer le fichier SVG du logo**

Écrire `assets/logo_hee.svg` contenant exactement le SVG fourni par l’utilisateur (document Inkscape complet « HEE / KOREAN CHEF »), encodé en UTF-8.

- [ ] **Step 2: Vérifier la présence et le contenu**

Run: `python3 - <<'PY'
from pathlib import Path
p=Path('assets/logo_hee.svg')
s=p.read_text(encoding='utf-8')
assert p.is_file() and s.lstrip().startswith('<?xml') and 'KOREAN CHEF' in s and '#2c5b29' in s.lower()
print('ok', len(s))
PY`
Expected: `ok <taille>` sans erreur.

- [ ] **Step 3: Commit**

```bash
git add assets/logo_hee.svg
git commit -m "design: add HEE logo asset"
```

### Task 2: Aligner la configuration Streamlit sur les tokens

**Files:**
- Modify: `.streamlit/config.toml`

- [ ] **Step 1: Mettre à jour les couleurs de thème**

Remplacer le contenu pour aligner le thème clair « papier » sur les tokens (en conservant `client.toolbarMode = "viewer"`). Valeurs cibles :

```toml
[client]
# Masque les outils developpeur de Streamlit (Deploy, Rerun, Clear cache)
# tout en conservant les options spectateur (theme, impression, a propos).
toolbarMode = "viewer"

# Palette alignée sur les tokens --green / --paper / --ink
[theme]
primaryColor = "#2C5B29"
backgroundColor = "#F6F2EA"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#1F2421"
font = "sans serif"

[theme.light]
primaryColor = "#2C5B29"
backgroundColor = "#F6F2EA"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#1F2421"

[theme.dark]
primaryColor = "#2C5B29"
backgroundColor = "#1F2421"
secondaryBackgroundColor = "#2A302C"
textColor = "#F6F2EA"
```

- [ ] **Step 2: Vérifier la syntaxe TOML**

Run: `python3 - <<'PY'
import tomllib, pathlib
tomllib.loads(pathlib.Path('.streamlit/config.toml').read_text(encoding='utf-8'))
print('ok')
PY`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .streamlit/config.toml
git commit -m "design: align streamlit theme with paper/green tokens"
```

### Task 3: Refonte du shell global et de la navbar (shared/ui.py)

**Files:**
- Modify: `shared/ui.py`

- [ ] **Step 1: Ajouter les helpers de style/logo et l’injection CSS globale**

Dans `shared/ui.py` : ajouter imports `base64` et `Path` si besoin, une constante/lecture du logo SVG (`assets/logo_hee.svg`) pour produire un `data:image/svg+xml;base64,...` (ou inline SVG sûr) et une fonction `_inject_global_styles(st)` qui injecte (une fois par run via `st.markdown`) un bloc `<style>` définissant :
- `@import` Roboto (400,500,600,700) et `:root { --brick:#B85C3A; --paper:#F6F2EA; --green:#2C5B29; --ink:#1F2421; --ink-muted:#5E665F; --line:#DDD7CB; --surface:#FFFFFF; }`
- Base : `.stApp, [data-testid="stAppViewContainer"] { background: var(--paper); color: var(--ink); font-family: 'Roboto', system-ui, -apple-system, 'Segoe UI', sans-serif; }` ; titres/texte harmonisés ; liens et focus `var(--green)`.
- Composants : boutons (`[data-testid="baseButton-primary"]` -> fond `--green`, texte clair ; secondaires bordure `--line`/fond `--surface` ; hover discrets), inputs/selects bordure `--line` fond `--surface`, expanders/cartes à bordure fine, chat messages sobres, alertes teintées (succès/avert./erreur via green/brick) lisibles.
- Panneau droit/zone infos : styles pour la colonne infos (cartes/texte) sobres.
- Masquage header Streamlit et `padding-top` du conteneur principal conservés/adaptés à la nouvelle hauteur de navbar.

Appeler `_inject_global_styles(st)` depuis `render_header(st)` (avant rendu du contenu) afin que tous les écrans (vues + paramètres + aide) bénéficient du style.

- [ ] **Step 2: Refaire `render_navbar` avec logo et style épuré**

Réécrire le HTML/CSS de `render_navbar(st)` pour : fond `--paper/--surface`, bordure basse `--line`, pas d’ombre portée forte ; à gauche logo (img data-uri du SVG, ~28-32px de haut, `alt="HEE"`) + libellé « Assistant de Gestion » ; liens RH/Finances en pastilles (`border-radius: 999px`, bordure transparente), actif `background: var(--green); color: #fff; border-color: var(--green)`, inactif texte `--ink` hover fond léger. Conserver `role="navigation"`, `aria-label`, attributs `href="?vue=..."` et logique `active` existante.

- [ ] **Step 3: Vérifier la compilation Python**

Run: `python3 -m compileall shared/ui.py`
Expected: compilation réussie (pas de SyntaxError).

- [ ] **Step 4: Vérifier la présence des tokens et du logo dans le module**

Run: `python3 - <<'PY'
from pathlib import Path
s=Path('shared/ui.py').read_text(encoding='utf-8')
for t in ['--brick','#B85C3A','--paper','#F6F2EA','--green','#2C5B29','Roboto','logo_hee.svg','render_navbar','_inject_global_styles']:
    assert t in s, t
print('ok')
PY`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add shared/ui.py
git commit -m "design: refactor global shell and navbar with HEE branding"
```

### Task 4: Harmoniser le sous-menu et la vue RH

**Files:**
- Modify: `rh/view.py`

- [ ] **Step 1: Aligner `_inject_sous_menu_style` sur les tokens globaux**

Dans `rh/view.py`, mettre à jour le CSS injecté par `_inject_sous_menu_style` pour remplacer les couleurs codées en dur (`#0f172a`, `#e5e7eb`, `#f8fafc`, `#475569`, etc.) par les tokens : bordures `var(--line)`, fond secondaire `var(--surface)`/paper, texte `var(--ink)`/`var(--ink-muted)`, état actif/primaire `background: var(--green); border-color: var(--green); color: #fff;` hover discret, en conservant la disposition (pill, gap) existante.

- [ ] **Step 2: Vérifier la compilation et l’usage des tokens**

Run: `python3 -m compileall rh/view.py && python3 - <<'PY'
from pathlib import Path
s=Path('rh/view.py').read_text(encoding='utf-8')
assert 'var(--green)' in s and 'var(--line)' in s
print('ok')
PY`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add rh/view.py
git commit -m "design: align RH submenu styles with design tokens"
```

### Task 5: Harmoniser la vue Finances et l’icône de page

**Files:**
- Modify: `app_portail.py`
- Modify (si nécessaire): `finances/view.py`

- [ ] **Step 1: Utiliser le logo comme icône de page si possible**

Dans `app_portail.py`, faire pointer `page_icon` de `st.set_page_config` vers l’asset logo si Streamlit l’accepte (ex. `"assets/logo_hee.svg"` ou chemin résolu), avec repli simple (`"🧭"`) en cas d’échec non bloquant si nécessaire. Conserver `page_title`, `layout`, `menu_items`.

- [ ] **Step 2: Vérifier/ajuster les styles Finances**

Contrôler `finances/view.py` : il n’a pas de CSS local majeur ; s’assurer qu’aucune couleur codée en dur n’entre en conflit visible. Si des styles inline/locaux existent, les aligner sur `var(--green)/--line/--ink` (sinon aucun changement fonctionnel).

- [ ] **Step 3: Vérifier la compilation**

Run: `python3 -m compileall app_portail.py finances/view.py`
Expected: compilation réussie.

- [ ] **Step 4: Commit**

```bash
git add app_portail.py finances/view.py
git commit -m "design: use HEE logo as app icon and align finances view"
```

### Task 6: Vérification globale

**Files:**
- Test/Check: `shared/ui.py`, `rh/view.py`, `finances/view.py`, `app_portail.py`, `.streamlit/config.toml`, `assets/logo_hee.svg`

- [ ] **Step 1: Compilation de l’ensemble des modules modifiés**

Run: `python3 -m compileall shared/ui.py rh/view.py finances/view.py app_portail.py shared/portal_settings.py`
Expected: succès.

- [ ] **Step 2: Smoke test d’import (sans lancer Streamlit UI)**

Run: `python3 - <<'PY'
import importlib
for m in ['shared.ui','shared.portal_settings']:
    importlib.import_module(m)
print('ok')
PY`
Expected: `ok` (les modules de vue peuvent dépendre de `streamlit` au runtime ; l’import de `shared.ui` doit rester valide).

- [ ] **Step 3: Revue manuelle ciblée (si exécution possible)**

Run: `streamlit run app_portail.py` puis vérifier visuellement : navbar avec logo, fond papier, Roboto, onglets RH/Finances, sous-menus, panneau Informations, pages Paramètres/Aide, états focus/boutons. (Noter toute limite Streamlit.)

- [ ] **Step 4: Commit de finition (si ajustements mineurs)**

```bash
git add -A
git commit -m "design: polish refined UI styling"
```
(Sauter si aucun changement.)

## Notes d’exécution
- L’injection CSS cible des sélecteurs Streamlit (`data-testid`) susceptibles d’évoluer selon les versions ; privilégier des règles robustes et des fallbacks.
- Roboto dépend d’un accès réseau à Google Fonts ; la pile de repli garantit un rendu propre hors-ligne.
- La validation visuelle finale prime ; ajuster contrastes/espacements si le rendu réel l’exige, en restant dans les tokens définis.
