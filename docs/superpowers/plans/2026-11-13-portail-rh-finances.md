# Portail RH / Finances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer un portail Streamlit unique avec header (navigation RH|Finances + langue globale) et footer d’informations ⓘ, en modularisant RH et Finances pour une maintenance isolée, en appliquant les correctifs `Fixes-needed.md`, et en nettoyant le code sans régression.

**Architecture:** Approche A’ : un shell mince `app_portail.py` orchestre header/navigation/langue globale et un footer commun d’`InfoItem` avec aides néophytes ; `rh/` et `finances/` exposent chacun une vue isolée via un contrat stable `render(context) -> list[InfoItem]` et possèdent leur logique/état namespacé. Les modules racines `app_rh.py`/`app_finances_tva.py` deviennent des wrappers de compatibilité réexportant les API existantes et déléguant l’UI, afin de préserver les imports/tests et d’éviter tout impact croisé.

**Tech Stack:** Python 3.12, Streamlit, LangChain/ChromaDB/Ollama (RH existant), pypdf/openpyxl/pandas (Finances existant), pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-portail-rh-finances-design.md`

## Global Constraints

- Portail **une seule application Streamlit** (point d’entrée unique) avec menu en header pour naviguer `RH | Finances` dans la même session.
- **Langue globale** dans le header/zone commune, stockée en session et appliquée partout où pertinent (réponses RH) ; **pièces jointes** et **“Effacer la conversation”** restent dans la **vue RH uniquement** ; paramètres/actions Finances restent dans la **vue Finances**.
- **Footer commun “Informations”** permanent : informations/affichages d’état mutualisés, chaque item avec **icône ⓘ** et explication adaptée aux néophytes ; pas de contrôles métier dans le footer (hors langue globale au header).
- **Aucune suppression** de fonctionnalité utile ; réorganisation/mutualisation. **Isolation** : `rh/*` et `finances/*` ne dépendent pas l’un de l’autre, seulement de `shared/*` et de leurs propres dépendances ; état session namespacé (`vue_active` et `langue` globaux uniquement).
- **Nettoyage large** (code mort/inutile, refactorings/simplifications, déduplication pertinents) avec **comportement préservé**.
- Inclure les **4 correctifs `Fixes-needed.md`** : (1) objet mail `f"Objet : {libelle} - TVA {MOIS[mois - 1]} {annee}"`, (2) catering jamais “Non” et message `Attention il y a des ventes en catering ce mois-ci` si présent avec détails conservés, (3) `st.expander("Remplacement des pièces", expanded=False)`, (4) bouton **“Détecter les pièces”** qui relance/rafraîchit la détection.
- `st.set_page_config` centralisé dans le shell ; wrappers/scripts (`app_rh.py`, `app_finances_tva.py`, `1-RH`, `2-Finances`) conservés/adaptés pour compatibilité ; données/config existantes (`RH/`, `Finances/`, `chroma_db/`, `.cache/`) non déplacées par défaut.
- Tests existants adaptés (imports/chemins) sans affaiblir leurs assertions ; validation par `pytest` et `py_compile`.

## Review Focus

- **Navigation/switch de vue** avec état namespacé : basculer RH↔Finances ne doit pas réinitialiser l’autre vue, mélanger `st.session_state`, ni casser navigation/langue/footer (comportement attendu : états propres persistants en session).
- **Upload/gestion pièces jointes RH via `st.chat_input`** après extraction hors monolithe : ajout, liste, retrait individuel/tout retirer et erreurs par fichier doivent rester fonctionnels dans la vue RH uniquement, sans régression de la conversation.
- **Finances — détection/rafraîchissement et flux mail/vérification** : le bouton “Détecter les pièces” doit relancer la détection effectivement (pas un affichage figé), les uploads/remplacements et l’agrégation/rapprochement doivent rester cohérents, et les 4 correctifs ne doivent pas altérer les cas sans catering/fichiers manquants.
- **Footer ⓘ sur informations indisponibles ou erreur de vue** : chaque item doit afficher une valeur explicite (“indisponible/inconnue/absent”) avec aide néophyte ; une exception dans une vue doit être contenue (message en zone centrale) sans casser header/footer.
- **Compatibilité d’import/lancement** : `import app_rh` / `import app_finances_tva` et l’exécution des wrappers/scripts (`1-RH`, `2-Finances`) doivent continuer à fonctionner avec les signatures/comportements attendus par les usages et tests existants.

---

## File Structure (map)

- Create: `shared/__init__.py` — exports partagés.
- Create: `shared/info.py` — `InfoItem` (dataclass/structure) et `footer_items_to_markdown/items` helpers.
- Create: `shared/ui.py` — rendu header (nav + langue), rendu footer ⓘ, capture d’erreur de vue, helpers état global.
- Create: `app_portail.py` — shell Streamlit unique (config, état global, routage, composition header/vue/footer).
- Create: `rh/__init__.py` — package RH.
- Create: `rh/logic.py` — logique pure/helpers RH extraits (recherche, contexte/prompt, sources, raisonnement, infos ingestion, etc.) réutilisant `pieces_jointes`/`recherche_lexicale`.
- Create: `rh/view.py` — `render(context) -> list[InfoItem]`, UI chat/contrôles RH dans la vue, état `rh_*` namespacé, caches ressources.
- Create: `finances/__init__.py` — package Finances.
- Create: `finances/core.py` — logique pure/métier Finances extraite (parsing, extraction, détection, calculs, mail, formatage) + correctifs métier `Fixes-needed.md`.
- Create: `finances/view.py` — `render(context) -> list[InfoItem]`, UI Finances, état `fin_*` namespacé, bouton détection, expander, catering corrigé.
- Modify: `app_rh.py` — wrapper de compatibilité : réexporte API publique attendue depuis `rh.logic`/existants et fournit `main()` déléguant au portail/vue RH (sans `st.set_page_config` en import-time).
- Modify: `app_finances_tva.py` — wrapper de compatibilité : réexporte API publique attendue depuis `finances.core` et fournit `main()` déléguant.
- Modify: `1-RH`, `2-Finances` — lancer `app_portail.py` en ciblant la vue (avec conservation démarrage Ollama/synchro/ports/navigateur).
- Modify: `tests/test_app.py`, `tests/test_app_tva.py` — adapter aux nouveaux emplacements/imports/comportements corrigés (`Fixes-needed.md`) sans affaiblir les assertions.
- Modify (si nécessaire, justifié): `pieces_jointes.py`, `recherche_lexicale.py` — uniquement nettoyage sûr/compat import (éviter déplacement sauf besoin prouvé).

---

### Task 1: Fondations partagées (`shared`) et contrat `InfoItem`

**Files:**
- Create: `shared/__init__.py`
- Create: `shared/info.py`
- Create: `tests/test_shared_info.py`

**Interfaces:**
- Consumes: valeurs d’état simples (str/int/bool/None) fournies par shell/vues.
- Produces: `InfoItem(cle: str, libelle: str, valeur: str, aide: str, niveau: str = "info")` immuable/simple ; `normalize_info_value(value) -> str` ; `collect_footer_infos(*groups) -> list[InfoItem]` (aplatissement + ordre stable, dédoublonnage optionnel par clé si utile).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shared_info.py
from shared.info import InfoItem, collect_footer_infos, normalize_info_value


def test_normalize_info_value_handles_none_and_bool():
    assert normalize_info_value(None) == "indisponible"
    assert normalize_info_value(True) == "oui"
    assert normalize_info_value(False) == "non"
    assert normalize_info_value(12) == "12"


def test_collect_footer_infos_preserves_order_and_items():
    a = InfoItem("a", "A", "1", "aide A")
    b = InfoItem("b", "B", "indisponible", "aide B", niveau="warning")
    assert collect_footer_infos([a], [b]) == [a, b]
    assert b.niveau == "warning"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_shared_info.py -q`
Expected: FAIL (module `shared.info` absent).

- [ ] **Step 3: Implement minimal `shared.info` and package export**

Create `shared/info.py` with `@dataclass(frozen=True) class InfoItem` (champs `cle, libelle, valeur, aide, niveau='info'`), `normalize_info_value` (None->`"indisponible"`, bool->`oui/non`, sinon `str`), `collect_footer_infos(*groups)` qui concatène en préservant l’ordre. Create `shared/__init__.py` exportant `InfoItem`, `normalize_info_value`, `collect_footer_infos`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_shared_info.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/__init__.py shared/info.py tests/test_shared_info.py
git commit -m "feat: add shared InfoItem contract for portal footer"
```

### Task 2: Shell portail (header, langue globale, routage, footer ⓘ)

**Files:**
- Create: `shared/ui.py`
- Create: `app_portail.py`
- Create: `tests/test_portail_shell.py`

**Interfaces:**
- Consumes: vues conformes `render(context) -> list[InfoItem]` (injectables/mappées) ; `st.session_state`.
- Produces: `init_global_state(state)` garantissant `vue_active` (défaut `"rh"`) et `langue` (défaut `app_rh.LANGUE_DEFAUT`/valeur compatible) ; `render_header(state) -> str` retourne vue active ; `render_footer(st, items)` affiche libellé+valeur+ⓘ (aide néophyte via `help`/popover/caption accessible) ; `run_portail(views, state, st_module)` orchestre header -> vue -> footer avec capture d’exception de vue (message zone centrale, footer rendu avec info d’erreur).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portail_shell.py
from types import SimpleNamespace
from shared.info import InfoItem
from shared.ui import init_global_state, run_portail


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.errors = []
        self.captions = []
    def error(self, msg):
        self.errors.append(msg)
    def caption(self, msg):
        self.captions.append(msg)
    # header/footer helpers will be monkeypatched/mocked in tests as needed


def test_init_global_state_defaults():
    st = SimpleNamespace(session_state={})
    init_global_state(st.session_state)
    assert st.session_state["vue_active"] in ("rh", "finances")
    assert "langue" in st.session_state


def test_run_portail_renders_footer_even_if_view_raises(monkeypatch):
    st = FakeSt()
    init_global_state(st.session_state)
    st.session_state["vue_active"] = "rh"

    def boom(_ctx):
        raise RuntimeError("boom")

    rendered = {}
    monkeypatch.setattr("shared.ui.render_header", lambda s: s.__setitem__("vue_active", "rh") or "rh")
    def fake_footer(_st, items):
        rendered["items"] = items
    monkeypatch.setattr("shared.ui.render_footer", fake_footer)

    run_portail({"rh": boom}, st.session_state, st)
    assert st.errors  # erreur affichée
    assert rendered["items"]  # footer quand même rendu
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_portail_shell.py -q`
Expected: FAIL (module/fonctions absents).

- [ ] **Step 3: Implement minimal shell helpers and `app_portail.py`**

Implement `init_global_state` (ne pas écraser valeurs existantes), `render_header` (utilise `st` pour nav `RH|Finances` + sélecteur langue globale basé sur `app_rh.LANGUES`/`LANGUE_DEFAUT` ou constantes locales partagées), `render_footer` (section/footer avec pour chaque `InfoItem` affichage valeur et aide ⓘ néophyte, valeurs indisponibles explicites), `run_portail` (header -> vue selectionnée -> fusion infos globales+vue+info erreur si exception -> footer). Implement `app_portail.py` comme point d’entrée : `st.set_page_config(...)`, init état, import/registre des vues (placeholders sûrs au début si RH/Finances pas encore extraits), appel `run_portail`. Centraliser **uniquement ici** `st.set_page_config`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_portail_shell.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/ui.py app_portail.py tests/test_portail_shell.py
git commit -m "feat: add Streamlit portal shell with global header and info footer"
```

### Task 3: Extraction logique RH et compatibilité `app_rh` (préservation API/tests)

**Files:**
- Create: `rh/__init__.py`
- Create: `rh/logic.py`
- Modify: `app_rh.py`
- Test: `tests/test_app.py` (adapter imports/attentes uniquement si nécessaire, sans affaiblir)

**Interfaces:**
- Consumes: `pieces_jointes.py`, `recherche_lexicale.py`, Chroma/Ollama/langchain comme aujourd’hui.
- Produces: `rh.logic` expose les fonctions/classes/constantes utilisées par `tests/test_app.py` et la vue (`LANGUES`, `LANGUE_DEFAUT`, `LLM_MODEL`, `EMBEDDING_MODEL`, `TOP_K`, `CHROMA_DIR`, `HISTORIQUE_MAX_MESSAGES`, `normaliser_langue`, `creer_vectorstore`, `creer_llm`, `rechercher`, `construire_contexte`, `construire_prompt`, `construire_historique`, `question_pour_recherche`, `nommer_source`, `extraire_sources`, `repondre`, `infos_ingestion`, `texte_a_propos`, `cite_des_sources`, `resume_raisonnement`, etc.) avec **mêmes signatures/comportements**. `app_rh.py` réexporte ces symboles (ex. `from rh.logic import ...`) pour compatibilité ; `app_rh.main` délègue au portail/vue RH (sans casser import-time).

- [ ] **Step 1: Write/adjust the failing test anchor (compat import)**

Add to `tests/test_app.py` (or create `tests/test_rh_compat.py`) a focused check if needed:

```python
import app_rh
from rh import logic as rh_logic

def test_app_rh_reexports_core_api():
    assert app_rh.normaliser_langue is rh_logic.normaliser_langue
    assert app_rh.construire_contexte("x") if False else True
```

(Préférer adapter minimalement l’existant : les tests actuels `import app_rh` doivent rester verts après extraction.)

- [ ] **Step 2: Run targeted tests to verify red/impact**

Run: `.venv/bin/python -m pytest -q tests/test_app.py -q`
Expected: PASS avant extraction ; servira de garde-fou (échoue si extraction casse API).

- [ ] **Step 3: Extract RH logic into `rh/logic.py` and make `app_rh.py` a facade**

Déplacer les fonctions/constantes pures et helpers non-UI de `app_rh.py` vers `rh/logic.py` (en conservant noms/signatures/valeurs). Garder dans `rh.logic` les dépendances nécessaires (`Document`, `recherche_lexicale`, `pieces_jointes`, etc.). Réécrire `app_rh.py` pour réexporter l’API publique attendue et définir `main()` qui lance le portail ciblé RH (ex. appel `app_portail` avec vue forcée) ; éviter tout effet de bord Streamlit à l’import. Ne pas déplacer `pieces_jointes.py`/`recherche_lexicale.py` hors racine sauf preuve que tests/imports restent compatibles (préférer les laisser et les importer).

- [ ] **Step 4: Run tests to verify behavior preserved**

Run: `.venv/bin/python -m pytest -q tests/test_app.py tests/test_pieces_jointes.py tests/test_recherche_lexicale.py -q`
Expected: PASS (adapter uniquement chemins/imports si inévitable, assertions inchangées).

- [ ] **Step 5: Commit**

```bash
git add rh/__init__.py rh/logic.py app_rh.py tests/test_app.py
git commit -m "refactor: extract RH logic module with backward-compatible app_rh API"
```

### Task 4: Vue RH intégrée au portail (UI dans la vue, langue globale, footer infos)

**Files:**
- Create: `rh/view.py`
- Modify: `shared/ui.py` (registre vues si nécessaire)
- Modify: `app_portail.py` (brancher vue RH réelle)
- Test: `tests/test_rh_view.py`

**Interfaces:**
- Consumes: `context` (`langue`, session_state/st), `rh.logic`, `pieces_jointes.IndexPiecesJointes`, caches ressources.
- Produces: `rh.view.render(context) -> list[InfoItem]` affichant chat + contrôles RH propres (**pièces jointes**, **Effacer la conversation**) dans la vue, sans `st.sidebar` ; utilise langue globale ; retourne infos footer RH (ex. base disponible, ingestion, modèle, embeddings, extraits, état pièces jointes, avertissements) avec aides ⓘ néophytes. État namespacé `rh_messages`, `rh_langue_effective` (ou suit globale), `rh_pieces_jointes`, etc.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rh_view.py
from types import SimpleNamespace
import rh.view as rh_view

class DummySt:
    def __init__(self):
        self.session_state = {}
    def caption(self, *a, **k): pass
    def markdown(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def test_rh_render_returns_info_items(monkeypatch):
    st = DummySt()
    # monkeypatch UI-heavy parts to no-op and force deterministic state
    monkeypatch.setattr(rh_view, "_render_rh_body", lambda *a, **k: None)
    monkeypatch.setattr(rh_view, "_collect_rh_infos", lambda *a, **k: [])
    infos = rh_view.render({"langue": "fr", "st": st, "session_state": st.session_state})
    assert isinstance(infos, list)
```

(Ajuster le test pour cibler les vraies helpers introduites : l’important est un contrat `render -> list[InfoItem]` et l’absence de dépendance à Finances.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_rh_view.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `rh.view.render` and integrate**

Porter l’UI de `main()` RH vers `rh/view.py` : initialisation session namespacée, rendu des contrôles pièces jointes + effacer **dans la vue**, chat, appels `repondre`/recherche avec `context["langue"]`, gestion erreurs/spinner/caches, collecte d’`InfoItem` (valeurs explicites si indisponibles, aides néophytes). Ne pas appeler `st.set_page_config`. Brancher la vue dans `app_portail.py`.

- [ ] **Step 4: Run tests to verify**

Run: `.venv/bin/python -m pytest -q tests/test_rh_view.py tests/test_app.py tests/test_pieces_jointes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rh/view.py app_portail.py shared/ui.py tests/test_rh_view.py
git commit -m "feat: integrate RH view into portal with global language and footer info"
```

### Task 5: Extraction logique Finances, correctifs `Fixes-needed.md` et compatibilité

**Files:**
- Create: `finances/__init__.py`
- Create: `finances/core.py`
- Modify: `app_finances_tva.py`
- Modify: `tests/test_app_tva.py`

**Interfaces:**
- Consumes: dépendances existantes (pypdf, openpyxl, pandas, filesystem/paths Finances).
- Produces: `finances.core` expose les fonctions/constantes utilisées par tests et vue (`MOIS`, `ETABLISSEMENTS`, `COMPTABLE_DIR`, `CONFIG_FILE`, `normaliser_montant`, `extraire_*`, `detecter_type_*`, `trouver_fichiers`, `dernier_mois_disponible`, `libelle_etablissement_mail`, `generer_mail_comptable`, `aggreger_*`, `verifier_rapprochement`, `formater_euros`, etc.) avec comportements préservés **sauf** correctifs demandés.

- [ ] **Step 1: Write the failing tests for `Fixes-needed.md` (mail & catering)**

Ajouter/adapter dans `tests/test_app_tva.py` :

```python
def test_generer_mail_objet_format_sans_etablissement_parenthese():
    mail = app_tva.generer_mail_comptable(
        "BOULANGERIE", 2026, 5,
        {"caisse": "c.pdf", "banque": "b.pdf", "obypay": "o.xlsx"},
        catering=None,
    )
    assert "Objet : " in mail
    # libellé attendu selon libelle_etablissement_mail/config
    assert " - TVA Mai 2026" in mail.splitlines()[0]
    assert "Déclaration de TVA —" not in mail
    assert "(BOULANGERIE)" not in mail.splitlines()[0]


def test_ligne_catering_absent_ne_produit_pas_de_ligne_non():
    assert app_tva._ligne_catering(None) == ""
    assert app_tva._ligne_catering({"present": False}) == ""


def test_ligne_catering_present_message_attention_et_details():
    ligne = app_tva._ligne_catering({"present": True, "client": "X", "montant_ht": 100.0, "tva": 10.0})
    assert "Attention il y a des ventes en catering ce mois-ci" in ligne
    assert "X" in ligne and "HT" in ligne
    assert "Facture catering : Non" not in ligne
```

- [ ] **Step 2: Run tests to verify they fail (or reveal current behavior)**

Run: `.venv/bin/python -m pytest -q tests/test_app_tva.py -q`
Expected: FAIL sur les nouvelles attentes liées à `Fixes-needed.md` (avant implémentation) ; les tests existants doivent guider la préservation.

- [ ] **Step 3: Extract to `finances/core.py`, apply fixes, make `app_finances_tva.py` a facade**

Déplacer logique/constantes vers `finances/core.py`. Appliquer correctifs (1) objet mail dans `generer_mail_comptable`, (2) `_ligne_catering`/texte mail : jamais “Non”, message attention si présent + détails client/HT/TVA/TTC lisibles. Réexporter API depuis `app_finances_tva.py` et déléguer `main()` (compat). Adapter `tests/test_app_tva.py` uniquement si des attentes reflétaient explicitement l’ancien format devenu incorrect (remplacer par le format spécifié), sans affaiblir la couverture.

- [ ] **Step 4: Run tests to verify**

Run: `.venv/bin/python -m pytest -q tests/test_app_tva.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finances/__init__.py finances/core.py app_finances_tva.py tests/test_app_tva.py
git commit -m "refactor: extract finances core and apply Fixes-needed mail/catering fixes"
```

### Task 6: Vue Finances intégrée au portail (détection, expander, footer infos)

**Files:**
- Create: `finances/view.py`
- Modify: `app_portail.py` (brancher vue Finances)
- Test: `tests/test_finances_view.py`

**Interfaces:**
- Consumes: `context`, `finances.core`, état session `fin_*`.
- Produces: `finances.view.render(context) -> list[InfoItem]` avec UI Finances dans la vue ; correctifs UI : **expander** `st.expander("Remplacement des pièces", expanded=False)` et bouton **“Détecter les pièces”** qui relance `trouver_fichiers(...)` et met à jour l’état/rerun pour rafraîchir l’affichage ; catering conforme (jamais “Non”, attention si présent) ; infos footer avec aides ⓘ.

- [ ] **Step 1: Write the failing test (contrat + helpers détectables)**

```python
# tests/test_finances_view.py
import inspect
import finances.view as fin_view

def test_finances_render_contract():
    assert callable(getattr(fin_view, "render", None))

def test_finances_view_mentions_detect_button_and_expander():
    src = inspect.getsource(fin_view)
    assert "Détecter les pièces" in src
    assert "Remplacement des pièces" in src
```

(Compléter si possible par tests unitaires sur helpers d’état de détection extraits en fonctions pures, ex. calcul de la clé de rafraîchissement/liste de fichiers.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_finances_view.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `finances.view.render` and integrate**

Porter l’UI de `main()` finances vers `finances/view.py` avec état namespacé, conservation des contrôles dans la vue, ajout bouton de détection (invalidation/rafraîchissement explicite des fichiers détectés), remplacement du titre par expander replié, comportement catering corrigé, génération mail/vérification inchangée hors correctifs. Retourner `InfoItem` pertinents (contexte, détection, statut/avertissements si disponibles) avec aides néophytes. Brancher dans `app_portail.py`.

- [ ] **Step 4: Run tests to verify**

Run: `.venv/bin/python -m pytest -q tests/test_finances_view.py tests/test_app_tva.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finances/view.py app_portail.py tests/test_finances_view.py
git commit -m "feat: integrate finances view with detection refresh and Fixes-needed UI updates"
```

### Task 7: Scripts/wrappers de lancement et ciblage de vue

**Files:**
- Modify: `1-RH`
- Modify: `2-Finances`
- Modify: `app_rh.py`
- Modify: `app_finances_tva.py`
- Modify: `app_portail.py` (lecture d’un sélecteur de vue initial, ex. env `PORTAIL_VUE` / query param / arg simple)

**Interfaces:**
- Consumes: conventions actuelles (ports `8501`/`8502`, checks Ollama/chroma/venv, synchro Finances).
- Produces: `1-RH` lance `streamlit run app_portail.py` avec vue initiale `rh` ; `2-Finances` conserve sa synchro/config puis lance le portail avec vue initiale `finances` ; wrappers `main()` compatibles.

- [ ] **Step 1: Write the failing/guard test or check**

Créer `tests/test_entrypoints.py` léger :

```python
from pathlib import Path

def test_scripts_target_portal():
    assert "app_portail.py" in Path("1-RH").read_text()
    assert "app_portail.py" in Path("2-Finances").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_entrypoints.py -q`
Expected: FAIL avant adaptation.

- [ ] **Step 3: Implement entrypoint targeting and script updates**

Ajouter dans `app_portail.py` une résolution de vue initiale sûre (priorité explicite, défaut `rh`, valeurs valides uniquement). Mettre à jour `1-RH`/`2-Finances` pour exécuter le portail (et transmettre la vue) tout en préservant leurs étapes existantes (Ollama, synchro, port, attente, ouverture navigateur). Ajuster wrappers `main()` si nécessaire.

- [ ] **Step 4: Run test to verify**

Run: `.venv/bin/python -m pytest -q tests/test_entrypoints.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 1-RH 2-Finances app_portail.py app_rh.py app_finances_tva.py tests/test_entrypoints.py
git commit -m "chore: route launch scripts and wrappers through unified portal"
```

### Task 8: Nettoyage large (code mort/déduplication) et consolidation

**Files:**
- Modify: `rh/logic.py`, `rh/view.py`, `finances/core.py`, `finances/view.py`, `shared/*.py`, `app_rh.py`, `app_finances_tva.py` (selon constats)
- Modify: `tests/test_app.py`, `tests/test_app_tva.py` et autres tests impactés (imports/chemins uniquement)

**Interfaces:**
- Produces: même comportement observable ; API publiques de compat préservées ; imports/fonctions/branches mortes retirés sur preuve d’inutilisation.

- [ ] **Step 1: Establish/adjust tests as guardrail**

Run: `.venv/bin/python -m pytest -q`
Expected: identifier l’état courant (viser PASS avant nettoyage) ; noter les échecs à corriger sans affaiblir assertions.

- [ ] **Step 2: Audit unused code and duplication (evidence-based)**

Run (exemples) : `.venv/bin/python -m compileall -q .` ; `grep -RIn "^def \|^class " app_rh.py app_finances_tva.py rh finances shared` puis vérifier références ; supprimer imports/symboles/branches non référencés et simplifier duplications internes, en gardant les wrappers/compat nécessaires.

- [ ] **Step 3: Apply safe cleanup/refactors**

Effectuer suppressions et simplifications incrémentales, module par module (RH puis Finances puis shared) pour ne pas impacter l’autre vue. Mettre à jour les tests uniquement pour refléter nouveaux emplacements/imports.

- [ ] **Step 4: Run verification suite**

Run: `.venv/bin/python -m py_compile app_portail.py app_rh.py app_finances_tva.py rh/*.py finances/*.py shared/*.py` puis `.venv/bin/python -m pytest -q`
Expected: PASS (ou écarts documentés/justifiés explicitement).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove dead code and consolidate portal modules"
```

### Task 9: Vérification finale du portail et critères d’acceptation

**Files:**
- Modify (si nécessaire): corrections mineures issues de la vérification
- Test: suite complète

**Interfaces:**
- Produces: portail conforme aux critères d’acceptation de la spec.

- [ ] **Step 1: Run automated checks**

Run: `.venv/bin/python -m compileall -q app_portail.py app_rh.py app_finances_tva.py rh finances shared` ; `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Manual/targeted portal verification checklist**

Vérifier (localement si possible) : header nav RH|Finances, langue globale affectant RH, footer ⓘ présent avec aides néophytes et valeurs explicites si indisponibles, pièces jointes + effacer uniquement en vue RH, vue Finances opérationnelle avec expander replié, bouton “Détecter les pièces”, objet mail et catering corrigés, absence d’impact d’état croisé au switch.

- [ ] **Step 3: Fix any issue found (test-first when feasible)**

Ajouter/ajuster un test ciblé pour toute régression détectée, corriger minimalement, rerun tests ciblés.

- [ ] **Step 4: Final verification run**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: finalize portal verification and acceptance fixes"
```

## Notes for implementers

- Préserver les signatures et constantes publiques consommées par `tests/test_app.py` et `tests/test_app_tva.py` (ex. `app_rh.TOP_K`, `app_rh.repondre`, `app_tva.COMPTABLE_DIR`, `app_tva.generer_mail_comptable`, helpers `_ligne_catering`/etc. si testés ou utilisés).
- `st.chat_input(..., accept_file=...)` renvoie un objet avec `.text` et `.files` dans la version Streamlit actuelle du projet : conserver cette intégration.
- Éviter de déplacer `pieces_jointes.py` et `recherche_lexicale.py` si cela complique la compatibilité des tests existants ; les importer depuis leur emplacement stable.
- Lors du nettoyage, ne pas supprimer les scripts/lanceurs ni les wrappers de compatibilité.
- Les textes ⓘ “néophytes” doivent expliquer simplement le sens de l’information (ex. ce qu’est un modèle, un embedding, un extrait, l’ingestion, un écart/TVA/statut) sans jargon inutile.
