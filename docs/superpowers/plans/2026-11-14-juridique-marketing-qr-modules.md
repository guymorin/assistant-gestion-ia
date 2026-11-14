# Modules Juridique Q&R et Marketing Q&R (uniformisation Q&R) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter les vues Q&R de premier niveau `Juridique` et `Marketing` et uniformiser tous les modules Q&R (RH, Finances, Juridique, Marketing) sur une implémentation commune avec base documentaire dédiée par module et pièces jointes de session, sans régression sur RH Onboarding ni Finances Déclaration de TVA.

**Architecture:** Extraire un cœur Q&R générique paramétré par configuration de module (identité, chemins ingestion/Chroma, modèle, clés session, textes) pour la logique RAG (vectorstore/LLM/recherche/génération/sources/infos) et la vue (chat, historique, pièces jointes, panneau latéral). Les modules domaine (`rh`, `finances`, `juridique`, `marketing`) déclarent leur config et composent le cœur : RH garde Onboarding, Finances garde la Déclaration de TVA tout en migrant sa sous-vue Q&R vers le composant commun. Le portail/nav, l’ingestion, les lanceurs, le README et les tests sont alignés sur 4 modules.

**Tech Stack:** Python 3.12, Streamlit, LangChain/ChromaDB/Ollama (local), pytest, bash launchers.

**Spec:** `docs/superpowers/specs/2026-11-14-juridique-marketing-qr-design.md`

## Global Constraints

- Traitement **100 % local** : Ollama `http://127.0.0.1:11434`, embeddings `nomic-embed-text`, aucune donnée envoyée hors machine.
- Q&R uniformisé (parité RH) pour **tous** les modules : chat sourcé (sources/détails), pièces jointes de session **PDF/TXT/MD**, historique, langue globale ; chaque module utilise **sa propre base** (`chroma_db/<id>`).
- Conventions validées : `juridique` → UI `Juridique`, `Ingestion/Juridique/`, `Ingestion/Juridique/Juridique-web.txt`, `chroma_db/juridique` ; `marketing` → UI `Marketing`, `Ingestion/Marketing/`, `Ingestion/Marketing/Marketing-web.txt`, `chroma_db/marketing`.
- Isolation stricte : état session et index/recherche par module ; pièces jointes présentes ⇒ réponse fondée **uniquement** sur les pièces jointes du module (sans mélange base).
- Préserver sans régression : **RH Onboarding**, **Finances Déclaration de TVA** (mail, détection, vérification/rapprochement, catering/statuts), vues Paramètres/Aide, langue globale, footer/`InfoItem`, contrats `app_rh.py`/`app_finances_tva.py` et `render(context) -> list[InfoItem]`.
- Erreurs explicites, jamais de traceback exposé en usage normal ; indisponibilité base/service/modèle ou fichier joint invalide gérée avec messages contextualisés et logs.
- Pas de persistance historique/pièces jointes hors session, pas de streaming/auth/OCR (inchangé). Pas de documents métier ajoutés aux nouveaux corpus (scaffolding uniquement).
- Tests automatisés sans dépendance réseau/Ollama/Chroma réelle quand possible ; suite `pytest -q` (hors intégration) doit passer.

## Review Focus

1. **Panneau pièces jointes hors RH** : en vue `Finances` (sous-vue Q&R), `Juridique` ou `Marketing`, le panneau droit liste/retire/vide les pièces du **bon module actif** et « Effacer la conversation » n’efface que l’historique du module — jamais fuite d’état entre modules ni affichage en Paramètres/Aide/TVA.
2. **Isolation base vs pièces jointes** : avec des pièces jointes présentes, la réponse ne doit **pas** interroger la base documentaire du module (et inversement sans PJ utilise uniquement la base du module), pour chaque module.
3. **Non-régression domaines spécifiques** : RH Onboarding (checklist/formulaires/génération) et Finances Déclaration de TVA (détection, mail, rapprochement, statuts/catering) restent fonctionnels après migration du Q&R Finances.
4. **Routage/navigation 4 vues** : `?vue=juridique|marketing|rh|finances`, navbar active correcte, `PORTAIL_VUE`/lanceurs ouvrent la bonne vue, `app_portail.py` et `shared/ui` acceptent les 4 identifiants sans casser les vues spéciales.
5. **Ingestion/scaffolding et messages d’indisponibilité** : `ingest.MODULES`/CLI incluent `juridique` et `marketing` avec les chemins exacts, dossiers/fichiers web créés, et absence de base (sans PJ) affiche un message guidant vers `python ingest.py --module <id>` propre au module.

## File Structure

### À créer
- `shared/qr_config.py` — `QRModuleConfig` (dataclass/frozen) et registre/configs `RH`, `FINANCES`, `JURIDIQUE`, `MARKETING` (id, label, chroma/pdf/urls, env modèle, défaut, préfixes clés session, textes). Responsabilité : source de vérité des conventions/modules Q&R.
- `shared/qr_logic.py` — logique RAG générique paramétrée par config : résolution chemins/base/manifest, `creer_vectorstore/creer_llm` (cache par config), `rechercher/repondre/construire_prompt/sources/infos_ingestion`, gestion langue/historique, messages d’indisponibilité contextualisés. Responsabilité : comportement Q&R uniforme.
- `shared/qr_view.py` — vue Q&R générique : init état module, rendu chat+historique+saisie avec pièces jointes, panneau `render_pieces_jointes`, collecte `InfoItem` Q&R, hooks pour panneau latéral. Responsabilité : UI Q&R uniforme.
- `juridique/__init__.py`, `juridique/view.py` — vue top-level Q&R Juridique (wrapper config).
- `marketing/__init__.py`, `marketing/view.py` — vue top-level Q&R Marketing (wrapper config).
- `Ingestion/Juridique/Juridique-web.txt`, `Ingestion/Marketing/Marketing-web.txt` — listes URLs (vides/commentées, prêtes).
- `3-Juridique`, `4-Marketing` — lanceurs dédiés cohérents avec `1-RH`/`2-Finances` (ouvrir portail sur la vue, port dédié par défaut).
- `tests/test_qr_modules.py` — tests config/ingestion/scaffolding/routage de base du cœur générique et nouveaux modules.

### À modifier
- `ingest.py` — ajouter `juridique`/`marketing` à `MODULES`, étendre CLI `--module`, conserver défauts/compat.
- `shared/ui.py` — généraliser `VUES`/navbar/routage/init pour 4 vues, panneau pièces jointes générique piloté par la vue Q&R active, libellés/infos footer adaptés.
- `app_portail.py` — enregistrer vues `juridique`/`marketing`, `PORTAIL_VUE`/query param acceptant 4 vues.
- `rh/view.py` — composer la sous-vue Q&R via `shared.qr_*` (config RH) tout en conservant Onboarding et API `render`/helpers publics nécessaires.
- `rh/logic.py` — déléguer au cœur générique ou réexporter API/constantes attendues pour compat (`app_rh`, tests).
- `finances/view.py` — migrer sous-vue Q&R vers composant générique (ajout PJ/parité) en conservant Déclaration de TVA et collecte d’infos.
- `finances/logic.py` — idem compat/délégation vers cœur générique.
- `app_rh.py`, `app_finances_tva.py` — préserver façade/API publique.
- `0-Accueil`, `1-RH`, `2-Finances` — cohérence texte/comportement si nécessaire (ports/vues), sans casser usages existants.
- `README.md` — documenter 4 modules, uniformisation Q&R, ingestion/bases/variables/lanceurs/structure.
- `tests/test_ingest.py`, `tests/test_portail_shell.py`, `tests/test_finances_view.py`, `tests/test_rh_view.py`, `tests/test_app.py`, `tests/test_entrypoints.py` (et autres impactés) — adapter aux 4 vues et au Q&R uniformisé tout en vérifiant non-régressions clés.

### Convention de décomposition
- Un fichier = une responsabilité claire (config, logique RAG, vue Q&R, vue domaine). Changements liés regroupés.
- Respecter les patterns existants (`render(context)->list[InfoItem]`, `shared.info.InfoItem`, `IndexPiecesJointes`, caching Streamlit) ; éviter refactors non liés.

---

### Task 1: Conventions modules, scaffolding ingestion et config Q&R

**Files:**
- Create: `Ingestion/Juridique/.gitkeep` (optionnel si dossier vide requis), `Ingestion/Juridique/Juridique-web.txt`, `Ingestion/Marketing/.gitkeep`, `Ingestion/Marketing/Marketing-web.txt`
- Create: `shared/qr_config.py`
- Modify: `ingest.py`
- Test: `tests/test_qr_modules.py` (nouveau), `tests/test_ingest.py` (ajustements minimaux si assertions figées sur 2 modules)

**Interfaces:**
- Produces: `shared.qr_config.QRModuleConfig` avec champs au moins `id`, `label`, `chroma_dir`, `pdf_dir`, `urls_file`, `model_env_var`, `default_model`, `state_prefix` (ou équivalent explicite) ; constantes/registre `QR_MODULES` (ou `get_qr_config(id)`) exposant configs pour `rh`, `finances`, `juridique`, `marketing` avec les chemins/labels de la spec.
- Produces: `ingest.MODULES` contient `juridique` et `marketing` avec chemins exacts de la table spec ; `ingest.get_module_config`/CLI acceptent ces modules ; scaffolding fichiers présents.
- Consumes: conventions existantes `ingest.py` (`MODULES`, `get_module_config`, manifeste/chroma_dir).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qr_modules.py
from pathlib import Path
import ingest
from shared import qr_config

def test_ingest_modules_include_juridique_marketing():
    assert ingest.MODULES["juridique"] == {
        "pdf_dir": "./Ingestion/Juridique",
        "urls_file": "./Ingestion/Juridique/Juridique-web.txt",
        "chroma_dir": "./chroma_db/juridique",
    }
    assert ingest.MODULES["marketing"]["chroma_dir"] == "./chroma_db/marketing"

def test_qr_scaffolding_files_exist():
    assert Path("Ingestion/Juridique/Juridique-web.txt").is_file()
    assert Path("Ingestion/Marketing/Marketing-web.txt").is_file()

def test_qr_configs_match_spec():
    assert qr_config.QR_MODULES["juridique"].label == "Juridique"
    assert qr_config.QR_MODULES["marketing"].chroma_dir.endswith("chroma_db/marketing")
    assert set(qr_config.QR_MODULES) >= {"rh", "finances", "juridique", "marketing"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py -v`
Expected: FAIL (module/fichiers/config absents).

- [ ] **Step 3: Implement scaffolding, `ingest.MODULES`/CLI support, and `shared/qr_config.py`**

Create `Ingestion/Juridique/Juridique-web.txt` and `Ingestion/Marketing/Marketing-web.txt` (vides ou avec commentaire d’usage, ex. une URL par ligne, `#` ignoré). Extend `ingest.MODULES` and argument parsing to include `juridique`, `marketing` (and `all` covers them per existing semantics). Define `QRModuleConfig` (frozen/dataclass) and `QR_MODULES`/lookup with exact values from spec; include `model_env_var`/defaults consistent with existing pattern (`ASSISTANT_DRH_MODEL`/`ASSISTANT_FINANCES_MODEL`, new `ASSISTANT_JURIDIQUE_MODEL`/`ASSISTANT_MARKETING_MODEL` defaulting to `llama3.2`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_ingest.py -v`
Expected: PASS (ajuster `tests/test_ingest.py` uniquement si une assertion impose l’ancien ensemble fermé de 2 modules).

- [ ] **Step 5: Commit**

```bash
git add ingest.py shared/qr_config.py Ingestion/Juridique Ingestion/Marketing tests/test_qr_modules.py tests/test_ingest.py
git commit -m "feat: add Juridique/Marketing ingestion config and Q&R scaffolding"
```

---

### Task 2: Cœur logique Q&R générique (RAG, état, infos)

**Files:**
- Create: `shared/qr_logic.py`
- Modify: `rh/logic.py`, `finances/logic.py` (délégation/wrappers compat)
- Test: `tests/test_qr_modules.py` (étendre), `tests/test_finances_logic.py`, `tests/test_app.py`

**Interfaces:**
- Produces: `shared.qr_logic` API paramétrée par `QRModuleConfig`, au minimum : `base_disponible(cfg)`, `infos_ingestion(cfg)`, `creer_vectorstore(cfg, embeddings=None)`, `creer_llm(cfg)`, `repondre(question, cfg, vectorstore, llm, pieces_jointes=None, historique=None, langue=...) -> {reponse, sources}` (ou équivalent compatible), helpers de nommage/sources/prompt et constantes/messages contextualisés par module.
- Consumes: `shared.qr_config`, `ingest` (embeddings/manifeste/chemins), `pieces_jointes.IndexPiecesJointes`.
- Preserves: `rh.logic` et `finances.logic` continuent d’exposer les symboles/constantes utilisés par `app_rh.py`, vues et tests (ex. `LLM_MODEL`, `EMBEDDING_MODEL`, `CHROMA_DIR`, `TOP_K`, `_base_disponible`, `infos_ingestion`, `repondre`, `creer_vectorstore`, `creer_llm`, `normaliser_langue`, `LANGUES`, `HISTORIQUE_MAX_MESSAGES`, `_afficher_sources` si requis) — implémentés via le cœur générique avec la config du module.

- [ ] **Step 1: Write the failing tests**

```python
# extend tests/test_qr_modules.py
from shared.qr_config import QR_MODULES
from shared import qr_logic

def test_qr_logic_base_disponible_false_when_missing(tmp_path):
    cfg = QR_MODULES["juridique"]
    # point to empty/nonexistent chroma path via cfg override or by asserting on helper with explicit dir
    assert qr_logic.base_disponible(cfg, chroma_dir=str(tmp_path / "nope")) is False

def test_module_message_mentions_module_id():
    msg = qr_logic.message_base_absente(QR_MODULES["marketing"])
    assert "marketing" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py -k qr_logic -v`
Expected: FAIL.

- [ ] **Step 3: Implement generic logic and compat wrappers**

Extract/refactor the shared RAG behavior (currently duplicated in `rh.logic`/`finances.logic`) into `shared/qr_logic.py` driven by `QRModuleConfig` (paths, model env/default, labels). Ensure: recherche base par module, réponse PJ-only si PJ non vide, langue/historique respectés, messages d’absence de base/service contextualisés. Reimplement `rh.logic` and `finances.logic` as thin wrappers around the generic core bound to their configs, preserving exported names/signatures/constants used by existing callers/tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_app.py tests/test_finances_logic.py -v`
Expected: PASS (adapter assertions uniquement si elles dépendaient d’un détail interne non contractuel, pas du comportement observable).

- [ ] **Step 5: Commit**

```bash
git add shared/qr_logic.py rh/logic.py finances/logic.py tests/test_qr_modules.py tests/test_app.py tests/test_finances_logic.py
git commit -m "refactor: introduce generic Q&R logic core for all modules"
```

---

### Task 3: Vue Q&R générique et panneau pièces jointes réutilisable

**Files:**
- Create: `shared/qr_view.py`
- Modify: `shared/ui.py` (support panneau générique), éventuellement `rh/view.py`/`finances/view.py` (points d’intégration préparatoires)
- Test: `tests/test_qr_modules.py`, `tests/test_portail_shell.py`, `tests/test_rh_view.py`

**Interfaces:**
- Produces: `shared.qr_view` helpers paramétrés par config, par ex. `ensure_state(session_state, cfg)`, `render_pieces_jointes(st, session_state, cfg, ...)`, `render_qr(st, session_state, cfg, langue, ...) -> list[InfoItem]`, `collect_qr_infos(session_state, cfg, langue) -> list[InfoItem]`, exposant l’état PJ via clés namespacées (`<id>_messages`, `<id>_pieces_jointes` ou getters stables).
- Produces: contrat permettant à `shared.ui` d’afficher le panneau PJ pour la vue Q&R active (ex. fonction `get_active_qr_attachment_renderer(session_state, vue)` / registre, ou `view` expose `render_pieces_jointes` compatible) sans spécial-caser uniquement `rh`.
- Consumes: `shared.qr_logic`, `shared.qr_config`, `pieces_jointes.IndexPiecesJointes`.

- [ ] **Step 1: Write the failing tests**

```python
# extend tests/test_qr_modules.py (logic-level / fake session_state, no Streamlit runtime required where possible)
class S(dict):
    __getattr__ = dict.get
    def __setattr__(self,k,v): self[k]=v

from shared.qr_config import QR_MODULES
from shared import qr_view

def test_ensure_state_isolated_per_module():
    s = S()
    qr_view.ensure_state(s, QR_MODULES["juridique"])
    qr_view.ensure_state(s, QR_MODULES["marketing"])
    assert "juridique_messages" in s and "marketing_messages" in s
    assert s["juridique_messages"] is not s["marketing_messages"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py -k ensure_state -v`
Expected: FAIL.

- [ ] **Step 3: Implement generic view/panel and generalized UI hook**

Implement `shared/qr_view.py` mirroring RH Q&R behavior (chat, historique, accept_file multiple pdf/txt/md, ajout/retrait PJ, effacer conversation, spinner/messages, affichage sources/détails, infos) but driven by config and namespaced state. Update `shared/ui.py` so the right column renders the attachment panel for the active Q&R-capable view/module (not only `vue_active == "rh"`), and never for Paramètres/Aide or non-Q&R contexts; keep footer/global infos behavior intact.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_portail_shell.py tests/test_rh_view.py -v`
Expected: PASS (mettre à jour les tests qui supposent le câblage RH-spécifique du panneau vers le câblage générique équivalent).

- [ ] **Step 5: Commit**

```bash
git add shared/qr_view.py shared/ui.py rh/view.py tests/test_qr_modules.py tests/test_portail_shell.py tests/test_rh_view.py
git commit -m "feat: add generic Q&R view and generalized attachments panel"
```

---

### Task 4: Intégrer RH et uniformiser Finances Q&R (préserver Onboarding/TVA)

**Files:**
- Modify: `rh/view.py`, `finances/view.py`, `finances/logic.py` (si requis), `app_rh.py`, `app_finances_tva.py`
- Test: `tests/test_rh_view.py`, `tests/test_finances_view.py`, `tests/test_app.py`, `tests/test_app_tva.py`

**Interfaces:**
- Consumes: `shared.qr_view`, `shared.qr_logic`, configs RH/Finances.
- Preserves: RH sous-menus Q&R/Onboarding et comportement Onboarding inchangés ; Finances sous-menus Q&R/Déclaration de TVA inchangés côté TVA, Q&R gagne parité (PJ/historique/langue/infos) via cœur générique ; `render(context)->list[InfoItem]` et façades compat préservés.

- [ ] **Step 1: Write/update failing tests for uniformized Finances Q&R and preserved specifics**

Add/adjust tests to assert: Finances Q&R accepte pièces jointes (chat input avec fichiers ou état PJ namespacé utilisable) et expose infos/panneau PJ en contexte Q&R ; `Déclaration de TVA` conserve ses infos/actions clés (détection, période, flux existant) ; RH garde Onboarding et Q&R fonctionnel.

- [ ] **Step 2: Run tests to verify they fail (or capture delta)**

Run: `.venv/bin/python -m pytest tests/test_finances_view.py tests/test_rh_view.py tests/test_app.py tests/test_app_tva.py -v`
Expected: FAIL on new/updated expectations before migration.

- [ ] **Step 3: Implement integration**

Wire `rh/view.py` Q&R path to generic Q&R with RH config while keeping Onboarding rendering/state untouched. Wire `finances/view.py` Q&R subview to generic Q&R with Finances config (namespaced `finances_*`/agreed keys) and keep TVA subview logic/UI intact; ensure panel visibility only in Q&R context for Finances. Keep compat reexports in `rh.logic`/`finances.logic`/entry wrappers aligned.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_finances_view.py tests/test_rh_view.py tests/test_app.py tests/test_app_tva.py tests/test_finances_logic.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rh finances app_rh.py app_finances_tva.py tests/test_finances_view.py tests/test_rh_view.py tests/test_app.py tests/test_app_tva.py
git commit -m "refactor: integrate generic Q&R into RH and Finances and uniformize Finances Q&R"
```

---

### Task 5: Nouveaux modules Juridique et Marketing et enregistrement portail

**Files:**
- Create: `juridique/__init__.py`, `juridique/view.py`, `marketing/__init__.py`, `marketing/view.py`
- Modify: `app_portail.py`, `shared/ui.py` (si restant: labels `VUES`, navbar, mapping vue label)
- Test: `tests/test_qr_modules.py`, `tests/test_portail_shell.py`, `tests/test_entrypoints.py`

**Interfaces:**
- Produces: `juridique.view.render(context)->list[InfoItem]` et `marketing.view.render(context)->list[InfoItem]` rendant un Q&R top-level via cœur générique + configs dédiées.
- Produces: `app_portail.py` expose/route `rh, finances, juridique, marketing`; `PORTAIL_VUE` et `?vue=` acceptent les 4 valeurs ; navbar affiche les 4 entrées avec état actif correct.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qr_modules.py or test_portail_shell additions
import app_portail

def test_portail_accepts_new_views_env(monkeypatch):
    monkeypatch.setenv("PORTAIL_VUE", "juridique")
    assert app_portail._vue_initiale() == "juridique"
```
Add assertions that `shared.ui` `VUES`/labels include `juridique` and `marketing` and navbar contains their labels/links (string/structure per existing test style).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_portail_shell.py tests/test_entrypoints.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement new modules and portal wiring**

Create minimal domain packages calling generic Q&R with `QR_MODULES["juridique"/"marketing"]`. Register views in `app_portail.py` (with safe fallbacks consistent with current pattern). Update `shared/ui.py` to include the 4 vues in navigation/init/label mapping and active-state handling, preserving special views.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_portail_shell.py tests/test_entrypoints.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app_portail.py shared/ui.py juridique marketing tests/test_qr_modules.py tests/test_portail_shell.py tests/test_entrypoints.py
git commit -m "feat: add Juridique and Marketing portal views"
```

---

### Task 6: Lanceurs, README et finitions intégrées

**Files:**
- Create: `3-Juridique`, `4-Marketing` (exécutables)
- Modify: `0-Accueil`, `1-RH`, `2-Finances` (si ajustements nécessaires), `README.md`
- Test: `tests/test_entrypoints.py` (et smoke checks manuels/scriptables si existants)

**Interfaces:**
- Produces: lanceurs dédiés démarrant le portail sur `PORTAIL_VUE=juridique|marketing` (ports par défaut dédiés, ex. cohérents/proposés et documentés) avec le même schéma robuste qu’existant (venv, Ollama, attente health, ouverture navigateur) ; `0-Accueil` inchangé fonctionnellement mais compatible 4 vues.
- Produces: README à jour (modules RH/Finances/Juridique/Marketing, uniformisation Q&R+PJ pour tous, bases `chroma_db/<id>`, ingestion `--module juridique|marketing|all`, sources `Ingestion/<Module>`, variables modèle par module, lanceurs/ports, structure).

- [ ] **Step 1: Write/update failing tests or checks for entrypoints/docs expectations**

If `tests/test_entrypoints.py` asserts on launcher presence/behavior, extend it for `3-Juridique`/`4-Marketing`; otherwise add lightweight assertions (files exist, contain `PORTAIL_VUE=juridique|marketing` and `app_portail.py`). Ensure README mentions new modules/bases/commands.

- [ ] **Step 2: Run tests/checks to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_entrypoints.py -v` and/or targeted grep checks.
Expected: FAIL/missing before implementation.

- [ ] **Step 3: Implement launchers and documentation updates**

Create `3-Juridique` and `4-Marketing` modeled on `1-RH` (Q&R modules, no sync Finance spécifique), set appropriate `PORTAIL_VUE`, default port env vars (documented), and `chmod +x`. Update README and any help text in `0-Accueil` if it enumerates modules.

- [ ] **Step 4: Run tests/checks to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_entrypoints.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 0-Accueil 1-RH 2-Finances 3-Juridique 4-Marketing README.md tests/test_entrypoints.py
git commit -m "docs: add launchers and documentation for Juridique and Marketing modules"
```

---

### Task 7: Stabilisation, non-régression et vérification finale

**Files:**
- Modify: fichiers de tests/modules ci-dessus uniquement pour corrections issues de la suite complète (pas de refactor opportuniste)
- Test: suite complète ciblée

**Interfaces:**
- Consumes: ensemble du livrable.
- Produces: base de code cohérente satisfaisant les critères d’acceptation de la spec.

- [ ] **Step 1: Run full relevant test suite and capture failures**

Run: `.venv/bin/python -m pytest -q`
Expected: identifier les échecs résiduels liés au périmètre (4 vues, Q&R générique, PJ, ingestion, compat).

- [ ] **Step 2: Fix failures with minimal, targeted changes**

For each failure: add/adjust the specific test or implementation to meet spec/compat (preserve behavior unless spec requires change, e.g. Finances Q&R gains PJ). Keep changes scoped.

- [ ] **Step 3: Re-run verification to green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (0 failed), hors tests marqués intégration.

- [ ] **Step 4: Sanity-check key acceptance points**

Run (spot checks): `.venv/bin/python -m pytest tests/test_qr_modules.py tests/test_portail_shell.py tests/test_ingest.py -q`
Expected: PASS, confirming 4 modules/routing, configs/scaffolding, panneau/état génériques.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: stabilize Juridique/Marketing Q&R integration"
```

(If all changes already committed in prior tasks and suite is green, skip creating an empty commit.)

## Notes d’exécution

- Suivre TDD par tâche quand un comportement est testable unitairement ; pour l’UI Streamlit, privilégier tests sur helpers/logique/contrats et mise à jour des tests de vue existants avec doubles/fakes cohérents.
- Lors du refactor `rh.logic`/`finances.logic`, préserver les noms importés par `app_rh.py`, `tests/test_app.py`, `tests/test_finances_logic.py` et les vues.
- Vérifier explicitement l’absence de fuite d’état PJ entre modules (clés namespacées) et le mode « PJ uniquement ».
- Ne pas modifier `chroma_db` existant ni ajouter de documents réels ; ne créer que le scaffolding demandé.
