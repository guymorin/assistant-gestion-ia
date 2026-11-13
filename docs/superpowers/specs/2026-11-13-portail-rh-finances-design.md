# Portail RH / Finances — Spec de conception

**Date :** 2026-11-13  
**Statut :** Validé en brainstorming (sections 1–5 approuvées) — en attente de revue utilisateur du document écrit avant plan d’implémentation  
**Périmètre :** Application Streamlit du dépôt `Assistant-Gestion-IA`

## 1. Contexte et objectifs

### 1.1 Contexte constaté
- Le dépôt contient deux applications Streamlit distinctes :
  - `app_rh.py` : assistant RH (RAG local via ChromaDB/Ollama), chat, affichage des sources/détails, gestion de pièces jointes en session, barre latérale (langue, informations modèle/embeddings/extraits, gestion pièces jointes, “Effacer la conversation”, avertissements base).
  - `app_finances_tva.py` : workflow finances/TVA (onglets mail comptable et vérification/rapprochement, sélections établissement/mois/année, détection/uploads de pièces, génération de mail, calculs/affichages de rapprochement).
- Lancement actuel séparé via les scripts `1-RH` et `2-Finances`.
- Des correctifs finances sont déjà décrits dans `Fixes-needed.md`.
- Des modules partagés/utilitaires existent déjà (`pieces_jointes.py`, `recherche_lexicale.py`, `ingest.py`).

### 1.2 Objectifs
1. **Nettoyer le code** des apps RH et Finances : nettoyage large (code manifestement inutile/mort, refactorings/simplifications et déduplication pertinents) en **préservant le comportement** fonctionnel existant, et en incluant les correctifs listés dans `Fixes-needed.md`.
2. **Créer un portail unique** (une seule application Streamlit, point d’entrée unique) avec un **menu en header** permettant de naviguer entre les vues **RH** et **Finances** dans la même session.
3. **Mutualiser paramètres et affichages** selon les arbitrages validés :
   - **Langue globale** : sélectionnée globalement (header/zone commune) et appliquée partout où pertinent (notamment réponses RH).
   - **Informations/affichages d’état** mutualisés dans un **footer commun** avec une **icône d’information (ⓘ)** et une explication adaptée aux néophytes pour chaque information.
   - **Contrôles propres à la vue RH** conservés dans la vue RH : gestion des pièces jointes et “Effacer la conversation”.
   - **Paramètres/actions propres à Finances** conservés dans la vue Finances.
   - Aucune suppression de fonctionnalité utile ; réorganisation/mutualisation.

### 1.3 Critère directeur d’architecture
L’approche retenue doit être **la plus simple pour modulariser et maintenir RH ou Finances sans impacter le reste** (isolation forte, contrat stable, surface partagée minimale).

## 2. Approche retenue

**A’ — Portail orchestrateur mince + modules RH/Finances indépendants (retenue)**

- Un petit point d’entrée “shell” gère uniquement : **header** (navigation `RH | Finances` + langue globale), routage de la vue active, et **footer commun d’informations (ⓘ)**.
- `RH` et `Finances` sont isolés dans leurs propres modules avec une **interface de rendu stable**. Le shell ne connaît que cette interface.
- La logique métier, l’état propre à chaque vue et les évolutions/correctifs restent internes au module concerné.
- Le code partagé est réduit au strict nécessaire (shell, contexte commun, contrat/rendu du footer d’infos, utilitaires réellement transverses).

**Approches écartées (au profit de A’)** : B (multi-pages natif, contraintes de rendu/partage header-footer et d’état partagé) ; C (enveloppe minimale, mutualisation/nettoyage large plus fragiles) ; A (équivalent sans exigence explicite d’isolation maximale par contrat).

## 3. Architecture cible et structure modulaire

### 3.1 Point d’entrée et shell
- **`app_portail.py`** (nouveau point d’entrée unique Streamlit)
  - Appelle `st.set_page_config` (centralisé, unique).
  - Initialise l’état global partagé : `vue_active` (`rh` | `finances`, défaut explicite) et `langue` (valeur par défaut alignée sur le comportement RH actuel).
  - Rend le **header commun** : navigation `RH | Finances` + sélecteur de **langue globale**.
  - Construit un **contexte partagé minimal** (ex. langue, accès session/helpers) et invoque la vue active via son interface.
  - Agrège les **informations d’affichage** (globales + vues) et rend le **footer commun “Informations”**.

### 3.2 Modules métier isolés
- **`rh/`** (module autonome)
  - `rh/view.py` (ou équivalent) : point d’entrée UI de la vue, ex. `render(context) -> list[InfoItem]`.
    - Affiche la vue RH dans la zone centrale : chat RAG, historique, sources/détails, messages/erreurs, upload via saisie chat.
    - Conserve **dans la vue RH** les contrôles propres : gestion des pièces jointes (liste/retrait/tout retirer selon comportement existant) et **“Effacer la conversation”**.
    - Utilise la **langue globale** du contexte pour la génération/rendu des réponses.
    - Retourne les `InfoItem` d’état RH pour le footer.
  - Logique RH (retrieval, contexte/prompt, génération/réponse, sources/raisonnement, ingestion/état base, etc.) réorganisée en fonctions/modules internes à `rh/` en préservant le comportement.
  - Réutilisation des composants existants pertinents (`pieces_jointes.py`, `recherche_lexicale.py`, constantes/helpers) de manière cohérente, sans impacter Finances.

- **`finances/`** (module autonome)
  - `finances/view.py` : ex. `render(context) -> list[InfoItem]`.
    - Affiche la vue Finances avec ses paramètres/actions propres conservés dans la vue (établissement, période, seuils, uploads, actions mail/vérification, affichages de résultats).
    - Intègre les **4 correctifs de `Fixes-needed.md`** (voir §5.3).
    - Retourne les `InfoItem` d’état Finances pour le footer.
  - Logique métier extraite/réorganisée (parsing/extraction, détection fichiers, calculs TVA/rapprochement, génération mail, formatage) en modules internes à `finances/`.

### 3.3 Partagé (strictement transversal)
- **`shared/`** (ou `ui_commun/`)
  - Contrat/type `InfoItem` (champs indicatifs : `cle`, `libelle`, `valeur`, `aide_neophyte`, `niveau` info/avertissement/erreur, optionnellement `source_vue`).
  - Rendu du **footer “Informations”** : pour chaque item, libellé + valeur + icône **ⓘ** exposant une explication simple (“ce que ça signifie / pourquoi c’est utile”).
  - Helpers UI communs minimaux (header, primitives d’affichage) et utilitaires réellement transverses.
- **Règle d’isolation** : `rh/*` et `finances/*` ne dépendent pas l’un de l’autre ; dépendances autorisées vers `shared/*` et leurs propres modules/dépendances. Toute évolution confinée au module concerné ; le contrat partagé n’évolue que si nécessaire.

### 3.4 Compatibilité et points d’entrée
- **`app_rh.py`** et **`app_finances_tva.py`** conservés comme **wrappers minces de compatibilité** déléguant au module/vue correspondant (ou au portail en vue ciblée), sans duplication de logique métier.
- **`1-RH`** et **`2-Finances`** adaptés pour lancer le portail (en ouvrant/ciblant la vue correspondante si possible via mécanisme simple : paramètre, query param ou variable d’environnement) tout en conservant leurs responsabilités actuelles (vérifications, démarrage Ollama si nécessaire pour RH, synchro/config Finances, choix de port, ouverture navigateur, attente de disponibilité).
- Emplacements de données/config existants (`RH/`, `Finances/`, `chroma_db/`, `.cache/`, `Finances-config.txt`, etc.) conservés sauf nécessité technique justifiée.

## 4. Composition UI, état et footer “Informations (ⓘ)”

### 4.1 Header commun (permanent)
- **Navigation** : contrôle explicite `RH | Finances` (boutons/segmented control/radio horizontal au choix d’implémentation) pilotant `st.session_state["vue_active"]`.
- **Langue globale** : sélecteur dans le header, visible en permanence, stocké dans `st.session_state["langue"]` (défaut = langue par défaut actuelle). Transmise via le contexte ; utilisée par RH pour les réponses. Finances l’ignore si non pertinent (sans effet de bord).
- Header léger : navigation + langue uniquement (pas de contrôles métier déplacés).

### 4.2 Vues (contenu central)
- **RH** (dans la vue, spécifique) : chat, upload via saisie, historique, réponses/sources/détails selon comportement existant ; **pièces jointes** et **“Effacer la conversation”** présents et opérationnels uniquement ici. Pas de sidebar latérale ; réintégration dans la vue et/ou informations reflétées au footer selon nature (contrôle vs information).
- **Finances** (dans la vue, spécifique) : établissement/mois/année, gestion/détection/uploads de pièces, paramètres (seuil, TVA déductible, factures, etc.), génération mail, vérification/rapprochement et résultats — conservés dans la vue, avec correctifs `Fixes-needed.md`.

### 4.3 Footer commun “Informations (ⓘ)”
- Rendu permanent par le shell sur toutes les vues, dédié aux **informations/affichages d’état**.
- Agrège des `InfoItem` globaux (ex. vue active, langue, version/application si pertinent) et contextuels de la vue active.
- **Exemples indicatifs** (à affiner à l’implémentation, chaque item avec aide ⓘ néophyte) :
  - *RH* : état/base Chroma disponible, date/nombre d’extraits d’ingestion (si connu), modèle LLM, modèle d’embeddings, nombre d’extraits/recherche, état informatif des pièces jointes en session, avertissements d’état pertinents.
  - *Finances* : contexte sélectionné informatif (établissement/période) si utile, état de détection des pièces, statut/avertissements de rapprochement disponibles, paramètres informatifs pertinents.
  - *Global* : langue active, vue active, version/app si disponible.
- **Règle** : le footer informe (pas de contrôles métier). Valeur explicite si indisponible/inconnue ; les alertes critiques d’action peuvent rester contextuelles en vue mais leur état peut être reflété en info.

### 4.4 État et flux de données
1. Header met à jour `vue_active` et `langue`.
2. Shell appelle `vue_active.render(context)` → la vue lit/écrit uniquement son état, rend l’UI, exécute ses actions.
3. La vue retourne/expose ses `InfoItem` ; le shell fusionne (global + vue) et rend le footer.
4. Rerun Streamlit standard ; caches ressources coûteux (vectorstore/LLM/embeddings RH, index pièces jointes) gérés pour éviter recréation inutile, sans couplage avec Finances.

## 5. Refactoring, nettoyage et correctifs

### 5.1 Contrat d’intégration
- Interface de vue stable, ex. `render(context) -> list[InfoItem]`.
- Contexte minimal (langue, accès session/helpers) ; aucune dépendance croisée RH↔Finances.

### 5.2 RH
- Extraire l’orchestration Streamlit de `app_rh.py` vers `rh/view.py` et la logique vers modules internes `rh/`.
- Préserver : chat/RAG, construction prompt/contexte, recherche (sémantique/MMR + lexicale/BM25 et routage existants), gestion historique, pièces jointes (session, non persistées), sources/détails/raisonnement, gestion d’erreurs et caches.
- Remplacer la sidebar par intégration en vue + footer infos, sans perte de capacité.
- Nettoyage large interne (imports/fonctions/branches mortes, duplication, découpage UI/logique) à comportement constant.

### 5.3 Finances (inclut `Fixes-needed.md`)
- Extraire UI (`finances/view.py`) et logique (`finances/core.py` ou sous-modules) depuis `app_finances_tva.py`.
- **Correctifs obligatoires** :
  1. **Objet mail** : `f"Objet : {libelle} - TVA {MOIS[mois - 1]} {annee}"` (suppression de “Déclaration de TVA —” et de `({etablissement})`).
  2. **Catering** : ne jamais afficher `Facture catering : Non`. Si catering présent, afficher `Attention il y a des ventes en catering ce mois-ci` et conserver les détails client/HT/TVA/TTC de manière lisible.
  3. **Remplacement des pièces** : utiliser `st.expander("Remplacement des pièces", expanded=False)` (replié par défaut) à la place du titre fixe.
  4. **Détection des pièces** : conserver la détection automatique et ajouter un bouton **“Détecter les pièces”** permettant de relancer/rafraîchir la détection.
- Nettoyage large interne à comportement constant (hors changements demandés).

### 5.4 Stratégie de nettoyage (large, sûr)
- Suppression du code manifestement inutilisé/inaccessible (imports, fonctions, constantes, branches mortes) fondée sur l’analyse d’usage/références.
- Refactorings/simplifications et déduplication lorsque bénéfiques à la maintenabilité, sans modifier le comportement observable.
- Mises à jour incrémentales avec validation par tests/compilation après étapes significatives.

## 6. Robustesse, erreurs et cas limites

- **Isolation d’état** : namespaces distincts par vue (ex. préfixes `rh_` / `finances_`) ; seuls `vue_active` et `langue` sont globaux.
- **Shell résilient** : une erreur dans une vue est capturée et affichée clairement dans la zone centrale sans casser navigation, langue ni footer (footer reflète l’état d’erreur/indisponibilité).
- **Infos indisponibles** : valeurs explicites + aide ⓘ (pas de masquage silencieux).
- **RH** : conserver gestion base absente, Ollama injoignable, erreurs génération/jointure, validation fichiers joints.
- **Finances** : conserver robustesse parsing/détection/rapprochement et avertissements ; bouton de détection idempotent/relançable.
- **Streamlit** : `set_page_config` unique (shell), préservation des patterns `chat_input`/uploads/caches ressources, reruns standards.

## 7. Lancement, migration et compatibilité

- `app_portail.py` devient l’entrée principale du portail.
- `1-RH` / `2-Finances` adaptés pour lancer le portail (vue ciblée si possible) en conservant démarrage/ports/ouverture navigateur et logiques spécifiques existantes (Ollama pour RH, synchro/config pour Finances).
- `app_rh.py` / `app_finances_tva.py` : wrappers de compatibilité minces.
- Aucune migration de données requise par défaut.

## 8. Vérification et critères d’acceptation

### 8.1 Vérification
- **Tests existants** : exécuter la suite `pytest` ; adapter imports/chemins aux nouveaux emplacements en conservant l’intention et les assertions.
- **Sanité** : compilation (`py_compile`) des modules modifiés.
- **Ciblé** : vérifier les 4 correctifs `Fixes-needed.md` (idéalement via fonctions pures extraites/testables) et les comportements clés du portail.
- **Portail** : navigation header, langue globale effective, footer ⓘ (items + aides néophytes), contrôles RH (pièces jointes, effacer) confinés à la vue RH, absence d’impact croisé d’état entre vues.

### 8.2 Critères d’acceptation
- Portail unique avec header `RH | Finances` et **langue globale** fonctionnelle.
- Vue **RH** pleinement fonctionnelle dans le portail (chat/RAG, sources/détails, pièces jointes et effacer en vue RH, langue appliquée).
- Vue **Finances** fonctionnelle avec **4 correctifs `Fixes-needed.md`** appliqués.
- **Footer commun “Informations”** présent, mutualisé, avec ⓘ et explications néophytes pour chaque information affichée.
- **Modularité/isolation** : modules séparés, contrat stable, état namespacé ; modification de RH/Finances sans impact croisé.
- **Nettoyage large** réalisé avec comportement préservé ; tests existants mis à jour et passants (écarts éventuels explicitement justifiés).
- Scripts/points d’entrée de lancement utilisables (compatibilité).

## 9. Séquencement de mise en œuvre (indicatif)

1. Fondations : shell `app_portail.py`, `shared/` (contrat `InfoItem`, footer ⓘ, header, état global).
2. Extraction et intégration du module **RH** (`rh/`) + wrapper compatibilité.
3. Extraction et intégration du module **Finances** (`finances/`) + correctifs `Fixes-needed.md` + wrapper compatibilité.
4. Adaptation des scripts `1-RH` / `2-Finances` et points d’entrée.
5. Nettoyage large, déduplication, mise à jour tests/imports.
6. Vérification finale (tests, compilation, contrôles portail).

## 10. Risques et parades

| Risque | Parade |
|---|---|
| Régression lors de l’extraction des monolithes | Refactor incrémental, délégation/wrappers, tests fréquents |
| Couplage via `session_state` | Namespacing strict, contexte minimal, pas de lecture croisée |
| Spécificités Streamlit (`set_page_config`, reruns, `chat_input`, caches) | Centralisation config, préservation patterns, validation flux |
| Nettoyage trop agressif | Suppression fondée sur preuves d’usage + validation tests |
| Rupture des lanceurs/ports | Conservation comportements existants, validation des deux scripts |

## 11. Hors périmètre / hypothèses
- Pas d’ajout de nouvelles capacités métier non demandées ; pas de changement de modèle/infra (Ollama/Chroma) hors nécessité de câblage.
- Pas de déplacement des jeux de données/config existants par défaut.
- Les libellés exacts et la liste exhaustive des `InfoItem` du footer (et leurs textes ⓘ) sont précisés à l’implémentation en respectant les principes de cette spec (informations d’état, explications néophytes, pas de contrôles métier).
- La validation et l’exécution du plan d’implémentation font l’objet d’une étape ultérieure (`writing-plans`) après approbation écrite de cette spec.
