# Portail RH & Finances (IA locale)

Application locale **Streamlit** réunissant deux vues dans un même portail :

- **RH** : assistant documentaire (RAG) pour interroger une base RH (PDF/pages web) avec un LLM local via Ollama, avec sources et pièces jointes.
- **Finances** : préparation du mail comptable (TVA) et vérification/rapprochement de TVA à partir des pièces du mois.

Le portail propose un **menu en en-tête** (`RH | Finances`), une **langue globale** (FR/EN/KO, utilisée notamment pour les réponses RH) et un **pied de page « Informations »** avec icônes ⓘ et explications (état de la base, modèle, ingestion, pièces détectées, etc.).

> Traitement 100 % local : aucune donnée n’est envoyée hors de la machine (Ollama en local).

## Prérequis

- **Python 3.12** avec l’environnement `.venv`
- **Ollama** actif sur `http://127.0.0.1:11434`
- Modèles Ollama : `nomic-embed-text` (embeddings) et `llama3.2` (génération, configurable)
- Bases vectorielles présentes selon les modules utilisés : `./chroma_db/rh/chroma.sqlite3` (RH) et/ou `./chroma_db/finances/chroma.sqlite3` (Finances Q&R)

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull llama3.2
```

## Installation

```bash
# Dépendances d’exécution
.venv/bin/pip install -r requirements.txt

# Développement / tests
.venv/bin/pip install -r requirements-dev.txt
```

> Si `.venv` est absent : `python3.12 -m venv .venv` puis installer les dépendances ci-dessus.

## Lancer le portail

### Lanceurs (recommandés)

- **Portail (accueil)** (démarre Ollama si besoin, ouvre le navigateur, port 8501 par défaut) :
  ```bash
  ./0-Accueil
  # autre port : ASSISTANT_PORTAIL_PORT=8503 ./0-Accueil
  ```
- **Vue RH** (vérifie/démarre Ollama, ouvre le navigateur, port 8501 par défaut) :
  ```bash
  ./1-RH
  # autre port : ASSISTANT_DRH_PORT=8502 ./1-RH
  ```
- **Vue Finances** (synchronise les dossiers selon `Finances/Finances-config.txt`, démarre Ollama si besoin, port 8502 par défaut) :
  ```bash
  ./2-Finances
  # autre port : FINANCES_RH_PORT=8503 ./2-Finances
  ```

Arrêt : `Ctrl+C` dans le terminal.

### Lancement manuel

```bash
# Portail (vue par défaut : RH)
.venv/bin/python -m streamlit run app_portail.py

# Ouvrir directement une vue
PORTAIL_VUE=rh .venv/bin/python -m streamlit run app_portail.py
PORTAIL_VUE=finances .venv/bin/python -m streamlit run app_portail.py
```

> `app_rh.py` et `app_finances_tva.py` sont conservés comme points d’entrée de compatibilité et délèguent au portail.

## Utilisation

### Vue RH
- Posez une question dans le chat : la réponse s’appuie sur les extraits retrouvés dans l’index du module (`chroma_db/rh` ou `chroma_db/finances`, recherche hybride sémantique/lexicale) et affiche les **sources** + un volet **« Détails »** (raisonnement/extraits).
- **Langue** : choisie globalement dans l’en-tête (français, anglais, coréen) pour les réponses.
- **Pièces jointes** (PDF/TXT/MD) : ajoutables via le chat ; analysées **seules** (sans mélange avec la base RH) et gérées dans la vue RH (retrait, « Effacer la conversation »). Elles ne sont pas persistées.
- Historique de conversation récent utilisé pour les relances ; en l’absence de base et de pièce jointe, l’application l’indique.

### Vue Finances
- Sélection **établissement / mois / année**, détection des pièces (caisse, banque, Obypay) avec bouton **« Détecter les pièces »** et possibilité de remplacement (expander replié).
- **Mail comptable** : génération du message de transmission des pièces (objet au format société/mois de TVA) ; indication spécifique si des ventes de catering sont présentes.
- **Vérification et rapprochement de TVA** : calculs/rapprochements et statut à partir des fichiers détectés ou téléversés.

### Pied de page « Informations »
Affiche des informations d’état (vue/langue, base/ingestion/modèles côté RH, contexte/détection/statut côté Finances, etc.) avec une aide ⓘ explicative.

## Données : ingestion des bases documentaires (RH / Finances)

Les index sont construits par `ingest.py`, séparément par module, à partir de `./Ingestion/RH` et `./Ingestion/Finances` (PDF) et des listes d’URLs `./Ingestion/RH/RH-web.txt` et `./Ingestion/Finances/Finances-web.txt` (une par ligne, `#` pour commenter).

```bash
.venv/bin/python ingest.py --module rh        # -> chroma_db/rh
.venv/bin/python ingest.py --module finances  # -> chroma_db/finances
.venv/bin/python ingest.py --module all       # les deux (défaut)
```

> Pour ajouter durablement un document : le placer dans le dossier d’ingestion du module concerné (ou ajouter son URL dans son fichier `*-web.txt`), puis relancer l’ingestion de ce module. Les pièces jointes envoyées dans le chat RH sont analysées ponctuellement (session en cours) sans modifier la base.

## Configuration

| Élément | Valeur / remarque |
|---|---|
| Ollama | `http://127.0.0.1:11434` |
| Embeddings / LLM | `nomic-embed-text` / `llama3.2` (LLM surchargeable via `ASSISTANT_DRH_MODEL` / `ASSISTANT_FINANCES_MODEL`) |
| Bases documentaires (Q&R) | `./chroma_db/rh` (RH) et `./chroma_db/finances` (Finances), index séparés |
| Sources Q&R | `./Ingestion/RH` (+ `RH-web.txt`) et `./Ingestion/Finances` (+ `Finances-web.txt`) |
| Config Finances (TVA) | `Finances/Finances-config.txt` (paramètres/chemins des pièces TVA) |
| Ports par défaut | RH : 8501 (`ASSISTANT_DRH_PORT`) — Finances : 8502 (`FINANCES_RH_PORT`) |

Exemple (autre modèle) :
```bash
ASSISTANT_DRH_MODEL=qwen2.5:7b-instruct PORTAIL_VUE=rh .venv/bin/python -m streamlit run app_portail.py
```

## Structure (aperçu)

- `app_portail.py` : point d’entrée du portail (header, routage, footer informations)
- `shared/` : contrat `InfoItem` et rendu UI commun
- `rh/`, `finances/` : vues et logique métier modulaires (isolées)
- `app_rh.py`, `app_finances_tva.py` : wrappers de compatibilité
- `0-Accueil`, `1-RH`, `2-Finances` : lanceurs
- `pieces_jointes.py`, `recherche_lexicale.py`, `ingest.py` : composants RAG/recherche (ingestion par module)
- `tests/` : tests automatisés (`pytest`)

## Tests

```bash
.venv/bin/python -m pytest -q
# intégration (Ollama / données réelles) : .venv/bin/python -m pytest -q -m integration
```

## Limites connues

- Pas de streaming token par token, pas d’authentification multi-utilisateurs, pas de persistance de l’historique hors session.
- Pièces jointes de session non persistées ni indexées durablement ; formats limités à PDF/TXT/MD (pas d’OCR).
- Les réponses du LLM peuvent comporter des imprécisions : vérifier les sources (volet « Détails »), surtout pour les sujets sensibles.
- La qualité des réponses RH dépend de la base indexée et de la disponibilité d’Ollama/modèles.
