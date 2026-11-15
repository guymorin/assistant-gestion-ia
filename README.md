# Assistant de gestion (IA locale)

Application Streamlit locale pour centraliser plusieurs modules de gestion : RH, Finances, Juridique et Marketing.

## Prérequis

- Python 3.12
- Environnement virtuel `.venv`
- Ollama installé et lancé localement (`http://127.0.0.1:11434`)
- Modèles Ollama recommandés :
  - `nomic-embed-text` (embeddings)
  - `llama3.2` (génération, selon configuration)

## Installation

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
```

## Lancement

```bash
./Assistant-de-Gestion
```

Le lanceur démarre Ollama si nécessaire, lance l’application Streamlit puis ouvre le portail dans le navigateur (port `8501` par défaut, ou la valeur de `ASSISTANT_PORTAIL_PORT`).

Arrêt : `Ctrl+C` dans le terminal.

### Lancement manuel

```bash
.venv/bin/python -m streamlit run app_portail.py
```

## Modules

- **RH** : questions-réponses sur les documents RH (RAG local), affichage des sources, pièces jointes de session.
- **Finances** : préparation du mail comptable (TVA), détection des pièces, vérification et rapprochement de TVA.
- **Juridique** : module en cours d’intégration dans le portail.
- **Marketing** : module en cours d’intégration dans le portail.

## Données et indexation

Les bases documentaires sont séparées par module et stockées dans `chroma_db/`.

Sources d’ingestion :
- `Ingestion/RH` et `Ingestion/RH/RH-web.txt`
- `Ingestion/Finances` et `Ingestion/Finances/Finances-web.txt`

Indexer les documents :

```bash
.venv/bin/python ingest.py --module rh
.venv/bin/python ingest.py --module finances
.venv/bin/python ingest.py --module all
```

## Configuration

- **Ollama** : `http://127.0.0.1:11434`
- **Modèles** : `nomic-embed-text` (embeddings), `llama3.2` par défaut (génération)
- **Variables utiles** :
  - `ASSISTANT_DRH_MODEL`
  - `ASSISTANT_FINANCES_MODEL`
  - `ASSISTANT_PORTAIL_PORT`
  - `ASSISTANT_DRH_PORT`
  - `FINANCES_RH_PORT`
  - `PORTAIL_VUE`
- **Paramètres Finances (TVA)** : `Assistant-de-Gestion.config`

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Remarques

- Le traitement est local (données non envoyées hors de la machine).
- Les pièces jointes ajoutées dans le chat ne sont pas sauvegardées durablement.
- Les réponses générées doivent être vérifiées, surtout pour les sujets sensibles.
