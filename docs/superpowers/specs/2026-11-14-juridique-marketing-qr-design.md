# Design — Modules Juridique Q&R et Marketing Q&R (uniformisation Q&R)

**Date :** 2026-11-14  
**Statut :** approuvé en discussion (sections 1–3) — en attente de relecture utilisateur du document  
**Périmètre :** architectural (nouveaux modules, refactor/uniformisation Q&R, intégration portail/ingestion/outillage)

## 1. Contexte et intention

### 1.1 Demande
Ajouter **un module Juridique Q&R** et **un module Marketing Q&R** à l’application portail (Streamlit, traitement local Ollama/Chroma).

### 1.2 Compréhension partagée (validée)
- **But** : permettre d’interroger en questions/réponses deux nouveaux corpus documentaires (**Juridique**, **Marketing**) avec des réponses fondées sur les documents indexés et **sourcées**.
- **Placement (validé)** : deux **vues de premier niveau** dans la barre de navigation principale, au même niveau que `RH` et `Finances` (`RH | Finances | Juridique | Marketing`).
- **Fonctionnalités Q&R (validé)** : **parité avec RH Q&R** pour les nouveaux modules **et uniformisation de tous les modules Q&R**, y compris **Finances Q&R** — chat sourcé (sources/détails), **pièces jointes de session** (PDF/TXT/MD) avec gestion dans le panneau latéral, historique de conversation, respect de la langue globale — **chaque module avec sa propre base documentaire**.
- **Périmètre de livraison (validé)** : intégré/complet — navigation + modules Q&R + ingestion/config/scaffolding + uniformisation Finances Q&R + mises à jour portail/UI, README, lanceurs/scripts cohérents et adaptation des tests existants impactés.

### 1.3 Contraintes et principes
- Traitement **100 % local** (Ollama/Chroma), cohérent avec l’existant.
- Modules isolés par domaine (index/sources/état dédiés), pas de mélange inter-modules.
- Préserver les comportements existants hors évolution explicitement demandée (notamment **RH Onboarding** et **Finances Déclaration de TVA**).

## 2. Approche retenue

**Approche 1 — Q&R générique factorisé (recommandée, validée).**

- Extraire une implémentation Q&R commune paramétrée par configuration de module et l’utiliser pour `rh`, `finances`, `juridique`, `marketing`.
- Les spécificités domaine restent locales (Onboarding pour RH, Déclaration de TVA pour Finances) ; la sous-vue Q&R Finances est migrée vers le composant commun.
- **Avantages** : uniformisation réelle, maintenance centralisée, ajout futur simplifié, duplication réduite.
- **Compromis** : refactor plus large nécessitant une attention forte à la non-régression (s’appuyer sur les tests et la préservation des contrats).

Approches écartées : duplication/adaptation par module (dette/divergences) et hybride partiel (uniformisation moins robuste).

## 3. Architecture et structure

### 3.1 Composant Q&R générique (cœur)
- Composant commun (vue/logique/helpers) paramétré par une **configuration de module** contenant au minimum :
  - identifiant technique (`rh`, `finances`, `juridique`, `marketing`) et libellé UI ;
  - chemins/index : `chroma_dir`, `pdf_dir`, `urls_file` ;
  - variable d’environnement du modèle LLM (ex. `ASSISTANT_<MODULE>_MODEL`) et modèle par défaut ;
  - namespace/préfixes des clés `session_state` (messages, index pièces jointes, etc.) ;
  - textes d’aide/infos (nom de base, messages de disponibilité).
- Responsabilités uniformes : chargement vectorstore/LLM (caché par module), recherche et génération sourcée, historique, **pièces jointes de session** (PDF/TXT/MD) via `IndexPiecesJointes`, affichage réponses/sources/détails, et infos d’état (base, ingestion/manifeste, modèle, embeddings, nb extraits/pièces, langue, disponibilité).
- Factoriser la duplication actuelle `rh.logic` / `finances.logic` (RAG/prompt/sources/manifeste) en conservant les paramètres et comportements existants (top-k/MMR, langue globale, messages d’erreur, etc.).

### 3.2 Modules de domaine (vues de premier niveau)
- **`rh/`** : vue top-level ; conserve **Onboarding** (sous-menu Q&R/Onboarding). Q&R rendu via composant générique (config RH).
- **`finances/`** : vue top-level ; conserve **Déclaration de TVA**. Sous-vue Q&R **uniformisée** (pièces jointes, parité RH) via composant générique (config Finances).
- **`juridique/`** (nouveau) : vue top-level Q&R uniquement (composant générique).
- **`marketing/`** (nouveau) : vue top-level Q&R uniquement (composant générique).
- Chaque domaine conserve/obtient son package dédié pour vue/config et spécificités, en s’appuyant sur le cœur partagé.

### 3.3 Portail, navigation et panneau latéral
- **`app_portail.py`** : enregistre les 4 vues (`rh`, `finances`, `juridique`, `marketing`).
- **`shared/ui.py`** : généralise `VUES`, navbar/header et routage pour 4 entrées ; **généralise le panneau droit “Pièces jointes”** (aujourd’hui spécifique RH) pour toute vue/module Q&R actif supportant les pièces jointes (Finances Q&R, Juridique, Marketing inclus), sans impact sur Paramètres/Aide.
- **`shared/info.py` / footer** : inchangé conceptuellement, alimenté par des `InfoItem` normalisés.

### 3.4 Ingestion, données et périphériques
- **`ingest.py`** : ajout de `juridique` et `marketing` dans `MODULES` et prise en charge CLI (`--module juridique|marketing|all` selon convention étendue).
- **Scaffolding (créé)** :
  - `Ingestion/Juridique/` + `Ingestion/Juridique/Juridique-web.txt`
  - `Ingestion/Marketing/` + `Ingestion/Marketing/Marketing-web.txt`
  - chemins/index dédiés `chroma_db/juridique`, `chroma_db/marketing` (selon comportement d’ingestion existant).
- **Lanceurs/README/tests** : `0-Accueil` et lanceurs dédiés cohérents pour Juridique/Marketing, README mis à jour (modules/bases/ingestion/ports/variables/uniformisation/structure), tests existants adaptés et tests ciblés ajoutés.

## 4. Flux de données et comportement

### 4.1 État par module (isolé)
- Session isolée par module : `<id>_messages`, `<id>_pieces_jointes` (`IndexPiecesJointes`), et clés de sous-vues existantes conservées (`rh_sous_vue`, état TVA Finances, etc.).
- Vectorstore/LLM cachés par configuration/module.

### 4.2 Flux Q&R uniforme
1. Saisie question et/ou ajout de fichiers (PDF/TXT/MD).
2. Ajout des pièces jointes valides à l’index de session du module (erreurs par fichier signalées, non bloquantes).
3. Sélection du contexte :
   - **pièces jointes présentes** → réponse fondée **uniquement** sur les pièces jointes du module (sans mélange avec la base) ;
   - **sinon** → recherche dans `chroma_db/<id>` puis génération.
4. Réponse dans la **langue globale**, avec **sources** et **détails/extraits** (format existant).
5. Mise à jour de l’historique du module ; effacement limité au module.

### 4.3 Panneau pièces jointes et sous-vues
- Panneau droit générique affiché pour le module Q&R actif exposant des pièces jointes ; actions : lister/retirer/vider, effacer la conversation (comportement uniformisé).
- **RH** : en sous-vue Q&R (préservé) ; Onboarding inchangé.
- **Finances** : en sous-vue **Q&R** (aligné) ; **Déclaration de TVA** inchangée et indépendante des pièces jointes Q&R.
- **Juridique/Marketing** : Q&R dédié avec panneau disponible.
- **Paramètres/Aide** : pas de panneau Q&R.

### 4.4 Cas limites
- Absence de base et de pièces jointes → message explicite invitant à l’ingestion du module concerné (sans traceback).
- Erreur Ollama/Chroma/inférence → message explicite contextualisé + log, UI non bloquée globalement.
- Pièces jointes invalides/illisibles → avertissement ciblé, poursuite avec le reste.
- Pas de persistance historique/pièces jointes hors session (inchangé).

## 5. Ingestion et conventions (validées)

| Élément | Juridique | Marketing |
|---|---|---|
| Identifiant module | `juridique` | `marketing` |
| Libellé UI/nav | `Juridique` | `Marketing` |
| Sources PDF | `Ingestion/Juridique/` | `Ingestion/Marketing/` |
| Liste URLs | `Ingestion/Juridique/Juridique-web.txt` | `Ingestion/Marketing/Marketing-web.txt` |
| Index Chroma | `chroma_db/juridique` | `chroma_db/marketing` |

- Scaffolding des dossiers/fichiers ci-dessus et entrées correspondantes dans `ingest.py` inclus dans le livrable.
- Chaque module interroge exclusivement sa propre base.

## 6. Erreurs, compatibilité et non-régression

- **Erreurs** : messages utilisateur explicites (base absente, service/modèle indisponible, fichier joint invalide) et journalisation des exceptions ; aucun traceback exposé en usage normal.
- **Compatibilité** : `app_rh.py`, `app_finances_tva.py` et contrats de rendu (`render(context) -> list[InfoItem]`) préservés ; `shared/info`/footer cohérents.
- **Préservations** : RH Onboarding, Finances Déclaration de TVA (mail, détection, vérification/rapprochement, catering/statuts), langue globale, Paramètres/Aide.
- **Évolutions assumées** : 4 vues de navigation ; Finances Q&R enrichi (pièces jointes/parité).

## 7. Tests, vérification et livrables

### 7.1 Tests
- Adapter les tests existants impactés (routage/navbar 4 vues, état session, panneau pièces jointes, `ingest.MODULES`, éventuels refactors).
- Ajouter des tests ciblés, sans dépendance réseau/Ollama/Chroma réelle quand possible :
  - config/routage/scaffolding des modules `juridique` et `marketing` ;
  - composant Q&R générique (sélection base par module, isolation d’état, messages d’indisponibilité) ;
  - pièces jointes en contexte non-RH (a minima Finances Q&R) au niveau logique/vue testable.
- Vérification : suite `pytest -q` (hors intégration par défaut) et contrôle manuel rapide du portail si possible.

### 7.2 Livrables
- Code/UI : packages `juridique/`, `marketing/`, cœur Q&R partagé, mises à jour `app_portail.py`, `shared/ui.py`, `rh/*`, `finances/*`, `ingest.py`.
- Données/scaffolding : `Ingestion/Juridique|Marketing` (+ `*-web.txt`), chemins `chroma_db/juridique|marketing`.
- Périphériques : lanceurs/`0-Accueil` et README mis à jour.
- Documentation de conception : ce document (spec).

## 8. Critères d’acceptation

- 4 onglets top-level visibles et fonctionnels : `RH`, `Finances`, `Juridique`, `Marketing`.
- Q&R uniformisé pour tous (chat sourcé, pièces jointes de session, historique, langue globale), **chaque module sur sa propre base**.
- RH Onboarding et Finances Déclaration de TVA fonctionnent comme avant.
- Ingestion/config/scaffolding opérationnels pour `juridique` et `marketing`.
- Tests pertinents passent (hors intégration).

## 9. Hors périmètre explicite
- Ajout de documents métier réels dans les nouveaux corpus (seul le scaffolding est créé).
- Changements fonctionnels à la Déclaration de TVA ou à l’Onboarding au-delà de l’intégration nécessaire.
- Persistance historique/pièces jointes, streaming, auth multi-utilisateurs, OCR (inchangé).
- Refactors non liés à l’uniformisation Q&R / intégration des nouveaux modules.
