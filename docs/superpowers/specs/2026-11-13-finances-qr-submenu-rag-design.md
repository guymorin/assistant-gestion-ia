# Finances — sous-menu, titre dynamique et Q&R (RAG par module)

**Date :** 2026-11-13  
**Statut :** Design validé en conversation (en attente de validation écrite de la spec)  
**Portée :** application Streamlit du dépôt `Assistant-Gestion-IA`

## 1. Contexte et objectif

Le portail (`app_portail.py`, `shared/ui.py`) expose aujourd’hui deux vues principales (RH, Finances). La vue Finances (`finances/view.py`) affiche un titre statique `Finances` et regroupe le flux de préparation/déclaration de TVA (mail comptable, vérification et rapprochement de TVA) via `finances.core`. La vue RH (`rh/view.py`, `rh/logic.py`) propose une interface de questions-réponses fondée sur des documents indexés (RAG) avec affichage des sources.

L’objectif est de :
1. Ajouter une **navigation secondaire** propre au module Finances, sous la navigation principale, avec les options **`Q&R`** et **`Déclaration de TVA`**.
2. Rendre le **titre principal** de la page Finances **dynamique** : il doit correspondre exactement à l’option sélectionnée dans ce sous-menu (suppression du titre global statique `Finances`).
3. Créer dans **`Q&R`** une interface de questions-réponses similaire au module RH (textes et saisie demandés), fondée sur des documents indexés avec sources.
4. Rendre le Q&R **opérationnel** en s’appuyant sur `Ingestion/Finances`, et adapter le module RH pour qu’il utilise `Ingestion/RH`, avec une **séparation des index par module** (répertoires Chroma distincts) et une ingestion paramétrée.

## 2. Décisions validées

- **Organisation du contenu Finances (option 1)** : `Déclaration de TVA` reprend intégralement le flux Finances actuel (sélecteurs établissement/mois/année + onglets `Mail comptable` / `Vérification et rapprochement de TVA`). `Q&R` accueille la nouvelle vue questions-réponses.
- **Périmètre Q&R / ingestion (option 1)** : Q&R Finances fonctionnel (recherche + réponse avec sources) sur `Ingestion/Finances`, adaptation RH vers `Ingestion/RH`, séparation/configuration des index et ingestion par module.
- **Séparation des index (option 1)** : **répertoires Chroma distincts** par module (ex. `chroma_db/rh`, `chroma_db/finances`), ingestion paramétrée, sans mélange des documents.
- **Approche d’implémentation (option 1)** : module RAG paramétré + logique Finances dédiée (réutilisation du pipeline, logique `finances/logic.py` sur le modèle de `rh/logic.py`, adaptation de `rh/logic.py` et `ingest.py`), plutôt que duplication massive ou refonte entièrement générique intrusive.
- **Libellé / défaut** : le sous-menu Finances comporte **`Q&R`** et **`Déclaration de TVA`** ; le titre dynamique affiche l’option sélectionnée ; le sous-menu s’ouvre par défaut sur **`Q&R`** (remplace le libellé initialement envisagé `Accueil Finances`).

## 3. Design détaillé

### 3.1 Architecture & configuration par module (ingestion/index)

**Objectif** : isoler RH et Finances (sources, index, métadonnées) en réutilisant le même pipeline RAG.

- **Modules** : `rh` et `finances`, chacun avec sa configuration :
  - `rh` : sources `Ingestion/RH` (PDFs + fichier d’URLs, ex. `Ingestion/RH/RH-web.txt`, même rôle/format que l’actuel `DRH-web.txt`) ; index `chroma_db/rh` ; manifeste d’ingestion dédié (ex. `chroma_db/rh/ingestion.json`).
  - `finances` : sources `Ingestion/Finances` (PDFs + `Ingestion/Finances/Finances-web.txt`) ; index `chroma_db/finances` ; manifeste dédié (ex. `chroma_db/finances/ingestion.json`).
- **Ingestion (`ingest.py`)** : paramétrée par module (fonction/CLI permettant d’ingérer `rh`, `finances` ou les deux). Pour chaque module : lecture des documents du dossier module, chunking/embeddings identiques, écriture dans **son** répertoire Chroma et son manifeste, sans mélange.
- **Logiques RAG** :
  - `rh/logic.py` adapté pour cibler `Ingestion/RH` / `chroma_db/rh` (et manifeste associé) au lieu de `./DRH` / `chroma_db` global, en conservant le comportement et l’API attendus.
  - `finances/logic.py` (nouveau, même structure que RH : embeddings/vectorstore, recherche, construction du prompt/contexte, réponse avec sources, historique, gestion base absente) ciblant `Ingestion/Finances` / `chroma_db/finances`, avec prompts/messages et catégorisation/sources adaptés au domaine Finances, mais même mécanique de citations/sources.
- **Séparation des caches/états** : vectorstores/LLM mis en cache par module (clés/ressources distinctes) pour éviter toute collision entre RH et Finances.
- **Hypothèse** : le fichier d’URLs par module suit le format actuel (une URL par ligne, lignes vides/commentaires ignorés) et se trouve dans le dossier du module (`Ingestion/RH/RH-web.txt`, `Ingestion/Finances/Finances-web.txt`).

### 3.2 Navigation secondaire Finances & titre dynamique

- **Emplacement** : sous-menu rendu en tête de `finances/view.py` (immédiatement sous la barre de navigation principale du portail, dans la zone de contenu Finances), visible uniquement quand la vue principale active est `Finances`.
- **Options** : **`Q&R`** et **`Déclaration de TVA`** (contrôle Streamlit persistant en session, ex. `st.radio(..., horizontal=True)` ou équivalent, libellés exacts).
- **État** : sélection mémorisée dans `st.session_state` (clé dédiée, ex. `fin_sous_vue`), valeur par défaut **`Q&R`**.
- **Titre dynamique** : suppression du `st.header("Finances")` statique. Titre principal = `st.header(<option sélectionnée>)` → `Q&R` ou `Déclaration de TVA`.
- **Répartition du contenu** :
  - **`Déclaration de TVA`** : reprend intégralement le flux existant (sélecteurs établissement/mois/année, détection des pièces, onglets `Mail comptable` et `Vérification et rapprochement de TVA`, logique `finances.core`, informations de pied de vue), sans perte fonctionnelle.
  - **`Q&R`** : nouvelle interface questions-réponses (cf. 3.3).

### 3.3 Vue `Q&R` (interface questions-réponses)

- **Titre** : `Q&R` (titre dynamique).
- **Contenu sous le titre (ordre et texte exacts)** :
  1. Texte descriptif (ex. `st.caption`) : `Posez vos questions Finances : les reponses sont fondees sur les documents indexes, avec leurs sources.`
  2. Avertissement (ex. `st.caption` / conteneur markdown) : `⚠️ Reponse generee automatiquement : verifiez toujours les sources affichees avant toute decision administrative et financière.`
  3. Saisie de question : `st.chat_input` (recommandé, cohérent avec RH).
- **Comportement Q&R (similaire à RH)** :
  - Historique des échanges Finances en session (état dédié, ex. `fin_messages`), affichage utilisateur/assistant et sources des réponses.
  - À la soumission : ajout du message utilisateur, recherche dans l’index Finances (`chroma_db/finances`, alimenté par `Ingestion/Finances`) via `finances/logic`, génération par le LLM local, affichage de la réponse et des sources/citations (même principe que RH).
  - Base Finances indisponible : message d’erreur explicite invitant à lancer l’ingestion du module Finances (cohérent avec RH, adapté aux chemins Finances).
- **Périmètre** : pas d’ajout non demandé (ex. pièces jointes Finances) ; cœur de l’expérience RH (question → réponse fondée sur documents indexés + sources + avertissement).

### 3.4 Adaptation RH, ingestion par module & robustesse

- **RH migré vers `Ingestion/RH`** : `rh/logic.py` cible `Ingestion/RH`, `Ingestion/RH/RH-web.txt`, `chroma_db/rh` et son manifeste (plus de `./DRH` / `chroma_db` global). Comportement fonctionnel RH préservé hors changement de source documentaire.
- **Ingestion (`ingest.py`) paramétrée** :
  - Configuration explicite par module (`rh`, `finances`) : répertoire source, fichier d’URLs, répertoire Chroma cible, manifeste.
  - Exécution ciblée par module (ex. CLI `--module rh|finances|all`, défaut raisonnable et documenté) construisant l’index du module concerné dans son répertoire dédié sans toucher l’autre.
  - Manifestes d’ingestion (date, nombre de chunks, etc.) écrits/lus par module (dans le répertoire Chroma du module) pour refléter l’état correct dans les vues.
- **Compatibilité / migration** : l’ancienne base globale `chroma_db` (racine) n’est plus utilisée par RH/Finances après migration ; relancer l’ingestion pour `rh` et `finances` afin de peupler `chroma_db/rh` et `chroma_db/finances`. Les messages d’état/erreur en vue l’indiquent si l’index du module est absent.
- **Robustesse & erreurs** :
  - Base d’un module absente/vide → réponse UI explicite, pas de crash, invitation à exécuter l’ingestion du module correspondant.
  - Échecs Ollama/recherche/génération gérés comme aujourd’hui (messages clairs).
  - Sources affichées limitées aux extraits retrouvés pour le module interrogé (pas de mélange inter-modules).

### 3.5 Fichiers impactés, tests & vérification

- **Fichiers principalement impactés** :
  - `finances/view.py` : sous-menu `Q&R` / `Déclaration de TVA`, titre dynamique, routage interne, vue Q&R (textes/avertissement/saisie, historique, réponse+sources) branchée sur `finances.logic` ; flux existant déplacé sous `Déclaration de TVA`.
  - `finances/logic.py` (nouveau) : logique RAG Finances (index `chroma_db/finances`, sources `Ingestion/Finances`, prompt/messages domaine Finances, réponse avec sources).
  - `rh/logic.py` : chemins/config vers `Ingestion/RH` et `chroma_db/rh` (et manifeste dédié), comportement fonctionnel conservé.
  - `ingest.py` : paramétrage par module (`rh`/`finances`/`all`), lecture dossiers/fichiers d’URLs par module, écriture index/manifeste dédiés.
  - Ajustements mineurs possibles (exports/imports/constantes partagées) si nécessaires, sans modifier l’UX hors périmètre.
- **Non-objectifs** : refonte visuelle globale, modification du fonctionnement métier TVA/mail/rapprochement existant, ajout de pièces jointes Finances, changements non liés.
- **Tests & vérification** :
  - Inspecter et adapter les tests existants concernés (RH/ingestion/portail, etc.) aux nouveaux chemins et à la séparation par module.
  - Ajouter/ajuster des tests ciblés selon les conventions du dépôt pour les zones modifiées (config/ingestion par module, logique Finances de base) si pertinent.
  - Vérification manuelle : navigation principale inchangée ; sous-menu Finances et titre dynamique corrects ; `Déclaration de TVA` = comportement actuel préservé ; `Q&R` affiche les textes/avertissement/saisie et répond ou signale l’absence d’index à partir de `Ingestion/Finances` ; RH fonctionne avec `Ingestion/RH`/`chroma_db/rh`.

## 4. Critères d’acceptation

- Sous-menu Finances visible sous la navigation principale avec les options `Q&R` et `Déclaration de TVA`.
- Titre principal dynamique égal au libellé de l’option sélectionnée (plus de titre statique `Finances`).
- `Déclaration de TVA` conserve le comportement existant (mail comptable, vérification/rapprochement de TVA, détection/remplacement de pièces, catering, etc.).
- `Q&R` affiche, sous le titre, le texte descriptif exact, l’avertissement exact et un composant de saisie de question.
- Le Q&R Finances interroge l’index issu de `Ingestion/Finances` (`chroma_db/finances`) et retourne des réponses avec sources ; en l’absence d’index, un message explicite guide vers l’ingestion du module.
- Le module RH utilise `Ingestion/RH` et `chroma_db/rh` (séparé de Finances) ; pas de mélange de documents entre modules.
- `ingest.py` permet l’ingestion par module vers les répertoires Chroma dédiés.
- Aucun changement fonctionnel non demandé en dehors de ce périmètre.
