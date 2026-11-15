# Finances Q&R, Sous-menu et RAG par Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter au module Finances un sous-menu (`Q&R`, `Déclaration de TVA`) avec titre dynamique, créer une vue Q&R opérationnelle fondée sur `Ingestion/Finances` (sources incluses), et migrer RH/ingestion vers une configuration RAG par module avec répertoires Chroma distincts (`chroma_db/rh`, `chroma_db/finances`).

**Architecture:** Paramétrer le pipeline d’ingestion et les logiques RAG par module (sources, fichier d’URLs, répertoire Chroma, manifeste) sans mélange inter-modules. Conserver le comportement métier existant de `Déclaration de TVA` (`finances.core`) et le comportement fonctionnel RH hors changement de source documentaire, tout en introduisant `finances/logic.py` (calqué sur `rh/logic.py`, prompts domaine Finances) et en adaptant `finances/view.py` pour le routage interne et la nouvelle interface Q&R.

**Tech Stack:** Python 3.12, Streamlit, LangChain/Chroma/Ollama (pipeline existant), pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-finances-qr-submenu-rag-design.md`

## Global Constraints

- Sous-menu Finances sous la navigation principale avec options exactes `Q&R` et `Déclaration de TVA` ; sélection persistée en session (défaut `Q&R`).
- Titre principal dynamique égal à l’option sélectionnée ; supprimer le titre statique `Finances`.
- `Déclaration de TVA` reprend intégralement le flux actuel (sélecteurs établissement/mois/année, détection/remplacement de pièces, onglets `Mail comptable` et `Vérification et rapprochement de TVA`, `finances.core`, infos/statut) sans régression fonctionnelle.
- Vue `Q&R` : sous le titre, afficher exactement `Posez vos questions Finances : les reponses sont fondees sur les documents indexes, avec leurs sources.` puis `⚠️  Réponse génerée automatiquement : vérifiez toujours les sources affichées avant toute décision administrative et financière.` puis un composant de saisie (`st.chat_input`).
- Q&R Finances opérationnel sur `Ingestion/Finances` / `chroma_db/finances` avec réponses fondées sur documents indexés et sources ; RH opérationnel sur `Ingestion/RH` / `chroma_db/rh` ; séparation stricte des index (répertoires distincts) et absence de mélange inter-modules.
- Ingestion paramétrée par module (`rh`, `finances`, et les deux) avec manifeste par module ; en l’absence d’index, l’UI indique clairement d’ingérer le module concerné (pas de crash).
- Hors périmètre : refonte visuelle globale, changement métier TVA/mail/rapprochement, pièces jointes Finances, fonctionnalités non demandées.

## Review Focus

- **Index absent par module** : ouvrir `Q&R` (Finances) ou la vue RH sans `chroma_db/<module>/chroma.sqlite3` affiche un message explicite invitant à lancer l’ingestion du module (pas d’exception non gérée).
- **Isolation des données** : une question posée en Finances ne retourne que des sources/extraits issus de `Ingestion/Finances` (`chroma_db/finances`) et jamais des documents RH, et inversement après migration RH.
- **Préservation de `Déclaration de TVA`** : sous `Déclaration de TVA`, les contrôles/onglets (`Mail comptable`, `Vérification et rapprochement de TVA`), détection, uploads, catering et génération de mail/rapprochement fonctionnent comme avant.
- **Titre/sous-menu dynamiques** : basculer entre `Q&R` et `Déclaration de TVA` met à jour le titre principal pour qu’il corresponde exactement à l’option sélectionnée ; le libellé statique `Finances` n’apparaît plus comme titre principal de page.
- **Ingestion ciblée** : lancer l’ingestion pour un seul module n’écrase pas l’index/manifeste de l’autre module (répertoires `chroma_db/rh` et `chroma_db/finances` indépendants).

---

### Task 1: Configurations de modules et ingestion paramétrée (`ingest.py`)

**Files:**
- Modify: `ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: pipeline existant (`lire_urls`, `charger_pdf`, `charger_web`, `decouper_documents`, `creer_vectorstore`, `enregistrer_manifeste_ingestion`, `ingerer`, `main`) et ses fabriques injectables.
- Produces: configuration par module exposée et stable (ex. `MODULES`/`get_module_config`) couvrant au minimum `pdf_dir`, `urls_file`, `chroma_dir`, `manifest/chemins dérivés` pour `rh` (`Ingestion/RH`, `Ingestion/RH/RH-web.txt`, `chroma_db/rh`) et `finances` (`Ingestion/Finances`, `Ingestion/Finances/Finances-web.txt`, `chroma_db/finances`) ; `ingerer(...)`/API de haut niveau permettant d’ingérer un module ciblé ; CLI `python -m ingest` / `python ingest.py` acceptant `--module {rh,finances,all}` (défaut documenté, ex. `all`) et écrivant index+manifeste dans le répertoire du module ciblé uniquement.

- [ ] **Step 1: Mettre à jour/ajouter les tests d’ingestion pour la config par module et les chemins**

Dans `tests/test_ingest.py`, adapter les assertions obsolètes (`PDF_DIR == "./DRH"`, `URLS_FILE == "./DRH/DRH-web.txt"`, structure DRH) et ajouter des tests qui vérifient : la résolution des configs `rh`/`finances` vers `Ingestion/RH|Finances`, `.../*-web.txt`, `chroma_db/rh|finances` ; `ingerer`/fonction dédiée par module utilise les chemins du module et écrit le manifeste dans le `chroma_dir` du module ; la CLI parse `--module` et invoque l’ingestion des modules demandés sans toucher l’autre.

- [ ] **Step 2: Exécuter les tests d’ingestion ciblés pour constater l’échec**

Run: `pytest tests/test_ingest.py -q`  
Expected: FAIL tant que la configuration par module/CLI n’est pas implémentée (ou assertions anciennes incohérentes).

- [ ] **Step 3: Implémenter la configuration par module et le routage d’ingestion dans `ingest.py`**

Ajouter la source de vérité des modules et leurs chemins (compatibilité raisonnable pour imports existants si utile, sans réintroduire le mélange). Faire accepter à `ingerer` (ou à une nouvelle fonction d’orchestration utilisée par `main`) un identifiant de module/config et propager `pdf_dir`, `urls_file`, `chroma_dir`/manifeste dédiés ; implémenter le parsing CLI `--module {rh,finances,all}`.

- [ ] **Step 4: Vérifier que les tests d’ingestion passent**

Run: `pytest tests/test_ingest.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest.py tests/test_ingest.py
git commit -m "feat: paramétrer l’ingestion RAG par module"
```

### Task 2: Migration RH vers `Ingestion/RH` et `chroma_db/rh`

**Files:**
- Modify: `rh/logic.py`
- Modify: `rh/view.py` (si nécessaire pour libellés/état d’ingestion module, sans changer le comportement Q&R)
- Modify: `app_rh.py` (préserver compatibilité/réexports si requis par les tests existants)
- Test: `tests/test_rh_view.py`
- Test: `tests/test_app.py` (adapter uniquement les assertions directement liées aux chemins/config RH/ingestion si cassées)

**Interfaces:**
- Consumes: API publique historique de `rh.logic`/`app_rh` attendue par le dépôt (`normaliser_langue`, `creer_vectorstore`, `creer_llm`, `rechercher`, `construire_contexte`, `construire_prompt`, `repondre`, `infos_ingestion`, `texte_a_propos`, `_base_disponible`, constantes telles que `LANGUES`, `LANGUE_DEFAUT`, `LLM_MODEL`, `EMBEDDING_MODEL`, `TOP_K`, `HISTORIQUE_MAX_MESSAGES`, etc.).
- Produces: mêmes signatures/comportements fonctionnels, mais index/manifeste RH lus depuis `chroma_db/rh` et messages d’absence de base orientés « ingestion du module RH » ; état d’ingestion affiché basé sur le manifeste du module RH.

- [ ] **Step 1: Adapter/ajouter les tests RH pour les nouveaux chemins et le message d’index absent**

Mettre à jour les tests qui supposent `./chroma_db` global ou `./DRH` pour RH (ex. via `infos_ingestion`, `_base_disponible`, rendu/messages) afin d’attendre `chroma_db/rh` et des invites d’ingestion cohérentes par module. Conserver les assertions de comportement non liées aux chemins.

- [ ] **Step 2: Exécuter les tests RH ciblés pour constater l’échec**

Run: `pytest tests/test_rh_view.py -q` (et les sous-ensembles pertinents de `tests/test_app.py` si identifiés, ex. `pytest tests/test_app.py -k "rh or ingestion or infos" -q`)  
Expected: FAIL sur les chemins/messages obsolètes.

- [ ] **Step 3: Implémenter la migration RH dans `rh/logic.py` (et ajustements vue/réexports)**

Pointer les défauts RH vers `Ingestion/RH` et `chroma_db/rh` (via config module/import depuis `ingest` ou constantes alignées), conserver les signatures publiques, et garantir que la détection de base/manifeste utilise le répertoire RH. Ajuster les textes d’erreur/avertissement (« base RH » / ingestion module RH) sans changer la mécanique de réponse/sources.

- [ ] **Step 4: Vérifier les tests RH ciblés**

Run: `pytest tests/test_rh_view.py -q` (et sous-ensembles `tests/test_app.py` concernés)  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rh/logic.py rh/view.py app_rh.py tests/test_rh_view.py tests/test_app.py
git commit -m "refactor: migrer le module RH vers Ingestion/RH et chroma_db/rh"
```

### Task 3: Logique RAG Finances (`finances/logic.py`)

**Files:**
- Create: `finances/logic.py`
- Modify: `finances/__init__.py` (si présent/nécéssaire pour exposer le module)
- Test: `tests/test_finances_view.py` ou `tests/test_app.py` (ajouter des tests unitaires de logique Finances si l’emplacement est plus cohérent avec le dépôt)

**Interfaces:**
- Consumes: `ingest` (embeddings/config/module paths), dépendances LLM/Chroma comme `rh.logic`.
- Produces: API de `finances.logic` suffisante pour la vue Q&R, calquée sur RH : au minimum `creer_vectorstore`, `creer_llm`, `repondre`, `infos_ingestion`, `_base_disponible`, gestion historique/messages, constantes de modèle/`TOP_K`/langue réutilisables ; index par défaut `chroma_db/finances`, sources `Ingestion/Finances` ; prompts/messages adaptés au domaine Finances (réponses fondées sur documents indexés, sources citées) sans introduire de mélange avec RH.

- [ ] **Step 1: Écrire des tests pour la logique Finances (chemins module et réponse sans index)**

Ajouter des tests qui vérifient : `_base_disponible`/`infos_ingestion` ciblent `chroma_db/finances` ; `repondre` (ou la fonction de haut niveau utilisée par la vue) retourne un message explicite invitant à l’ingestion Finances lorsque l’index est absent/vide (sans crash) ; la construction du prompt/contexte Finances utilise les documents/sources fournis.

- [ ] **Step 2: Exécuter les nouveaux tests pour constater l’échec**

Run: `pytest -q -k "finances and logic"` (ou le fichier de test choisi)  
Expected: FAIL avec module/fonctions manquants.

- [ ] **Step 3: Implémenter `finances/logic.py`**

Créer la logique RAG Finances sur le modèle de `rh/logic.py` (mêmes mécanismes de recherche/contexte/sources/historique), branchée sur la config/chemins Finances, avec textes/prompts domaine Finances et sans références aux chemins RH.

- [ ] **Step 4: Vérifier les tests de logique Finances**

Run: `pytest -q -k "finances and logic"` (ou fichier ciblé)  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finances/logic.py finances/__init__.py tests
git commit -m "feat: ajouter la logique RAG du module Finances"
```

### Task 4: UI Finances — sous-menu, titre dynamique et vue `Q&R`

**Files:**
- Modify: `finances/view.py`
- Modify: `tests/test_finances_view.py`

**Interfaces:**
- Consumes: `finances.core` (flux TVA/mail existant), `finances.logic` (Q&R), `shared.info.InfoItem`, `streamlit` via contexte/session.
- Produces: sous-menu Finances avec options `Q&R` et `Déclaration de TVA` (défaut `Q&R`, état session ex. `fin_sous_vue`) ; titre principal dynamique `st.header(<option>)` ; vue `Q&R` affichant les deux textes exacts demandés puis `st.chat_input`, historique/réponses/sources via `finances.logic` ; vue `Déclaration de TVA` contenant le flux actuel intact ; infos de pied de vue cohérentes selon la sous-vue (incluant état index/ingestion Finances pour `Q&R`).

- [ ] **Step 1: Mettre à jour/ajouter les tests de vue Finances**

Dans `tests/test_finances_view.py`, couvrir : présence/choix du sous-menu `Q&R`/`Déclaration de TVA` et titre dynamique ; affichage des deux textes exacts et d’un champ de saisie dans `Q&R` ; absence du titre statique `Finances` comme en-tête principal ; conservation du rendu/flux `Déclaration de TVA` (mail/vérification, sélecteurs/détection) sous l’option correspondante. Utiliser les doubles/mocks Streamlit existants dans le dépôt.

- [ ] **Step 2: Exécuter les tests de vue Finances pour constater l’échec**

Run: `pytest tests/test_finances_view.py -q`  
Expected: FAIL sur la nouvelle navigation/textes/comportement Q&R.

- [ ] **Step 3: Implémenter le sous-menu, le titre dynamique et `Q&R` dans `finances/view.py`**

Refactoriser le rendu en deux sous-vues pilotées par la sélection session : extraire/réutiliser le corps actuel comme contenu `Déclaration de TVA`, ajouter le sous-menu en tête et `st.header` dynamique, implémenter `Q&R` (textes exacts, avertissement, `st.chat_input`, historique, appel à `finances.logic`, affichage sources/erreurs d’index module) sans modifier `finances.core`.

- [ ] **Step 4: Vérifier les tests de vue Finances**

Run: `pytest tests/test_finances_view.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finances/view.py tests/test_finances_view.py
git commit -m "feat: ajouter le sous-menu Finances, le titre dynamique et la vue Q&R"
```

### Task 5: Adaptations transverses, tests de régression et vérification finale

**Files:**
- Modify: `tests/test_portail_shell.py` (si impacté)
- Modify: `tests/test_app.py` / autres tests existants (uniquement là où les nouveaux chemins/config par module l’exigent)
- Modify: `README.md` (si des commandes d’ingestion/chemins documentés doivent refléter `--module` et les dossiers par module)
- Modify: scripts/constantes de documentation mineures si strictement nécessaire (ex. références explicites à `./DRH`/`chroma_db` global devenues obsolètes pour RH)

**Interfaces:**
- Consumes: l’ensemble des modules modifiés et la suite de tests existante.
- Produces: dépôt cohérent avec la spec (navigation/titres/Q&R Finances, RH/Finances séparés par index et sources), suite de tests non-intégration pertinente au vert.

- [ ] **Step 1: Identifier et corriger les régressions de tests liées à la migration**

Exécuter la suite non-intégration et ajuster les tests/assertions impactés par la séparation des chemins/modules (sans affaiblir les vérifications métier hors périmètre).

Run: `pytest -q`  
Expected: initialement FAIL possible sur des références résiduelles aux anciens chemins ; corriger jusqu’à PASS.

- [ ] **Step 2: Mettre à jour la documentation d’usage si nécessaire**

Aligner les instructions d’ingestion/chemins (ex. `ingest.py --module ...`, `Ingestion/RH`, `Ingestion/Finances`, `chroma_db/rh`, `chroma_db/finances`) avec le comportement implémenté.

- [ ] **Step 3: Vérification finale**

Run: `pytest -q`  
Expected: PASS (suite par défaut, `not integration`).

Vérification manuelle (à réaliser avec l’environnement applicatif/Ollama et, si besoin, index ingérés) : navigation principale inchangée ; sous-menu Finances `Q&R`/`Déclaration de TVA` sous la nav ; titre dynamique correct ; `Déclaration de TVA` fonctionnel comme avant ; `Q&R` affiche les textes/avertissement/saisie et répond ou signale l’absence d’index depuis `Ingestion/Finances` ; RH fonctionne depuis `Ingestion/RH`/`chroma_db/rh` ; ingérer un module ne modifie pas l’autre.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: aligner la suite et la documentation avec le RAG par module"
```

> Note : avant le commit final, vérifier `git status` et n’inclure que les fichiers liés à cette fonctionnalité (ne pas embarquer de modifications utilisateur non pertinentes).
