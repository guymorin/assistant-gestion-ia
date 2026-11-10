# Assistant DRH – IA

Application locale de **RAG (Retrieval-Augmented Generation)** permettant d'interroger en langage naturel une base documentaire RH (PDF et pages web), avec des réponses générées par un LLM local, **en français, en anglais ou en coréen**, et un volet replié **« Détails »** sous chaque réponse qui résume le raisonnement et les sources. Il est aussi possible de **joindre des fichiers PDF, TXT ou Markdown** à une question : leur contenu est alors analysé **seul**, sans être mélangé aux PDF de la base RH.

- **Interface** : Streamlit (`app.py`)
- **Base vectorielle** : ChromaDB (`./chroma_db`, ~202 Mo, ≈15 619 chunks)
- **Embeddings** : `nomic-embed-text` via Ollama
- **LLM** : `llama3.2` via Ollama (modèle configurable, voir §8)
- **Ingestion** : `ingest.py` (PDF de `./DRH` + URLs de `./DRH/DRH-web.txt`)

Aucune donnée ne quitte la machine : tout tourne localement (Ollama sur `http://127.0.0.1:11434`).

---

## 1. Prérequis

| Composant | Version / état attendu |
|---|---|
| Python | 3.12 (environnement `.venv` fourni) |
| Ollama | démarré sur `http://127.0.0.1:11434` |
| Modèle d'embeddings | `nomic-embed-text` |
| Modèle de génération | `llama3.2` |
| Base vectorielle | `./chroma_db/chroma.sqlite3` présente |

Vérifier Ollama et les modèles :

```bash
ollama list
# doit contenir nomic-embed-text:latest et llama3.2:latest

# si Ollama n'est pas lancé :
ollama serve
```

Télécharger les modèles manquants :

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

---

## 2. Installation

```bash
cd Assistant-DRH-IA

# Dépendances d'exécution
.venv/bin/pip install -r requirements.txt

# Ou, pour développer et lancer les tests
.venv/bin/pip install -r requirements-dev.txt
```

> Si le `.venv` est absent ou cassé, le recréer :
> ```bash
> python3.12 -m venv .venv
> .venv/bin/pip install -r requirements-dev.txt
> ```

---

## 3. Lancer l'application

### Lanceur (recommandé)

Le script `Assistant-DRH-IA.sh` démarre Ollama si nécessaire, lance Streamlit puis ouvre automatiquement l'onglet du navigateur sur **http://localhost:8501** :

```bash
cd Assistant-DRH-IA
./Assistant-DRH-IA.sh
```

Pour choisir un autre port :

```bash
ASSISTANT_DRH_PORT=8502 ./Assistant-DRH-IA.sh
```

Arrêt : `Ctrl+C` dans le terminal.

### Lancement manuel

```bash
cd Assistant-DRH-IA
.venv/bin/python -m streamlit run app.py
```

Ouvrir ensuite **http://localhost:8501** (l'URL exacte est affichée dans le terminal).

### Variantes utiles

```bash
# Choisir un port
.venv/bin/python -m streamlit run app.py --server.port 8502

# Mode serveur sans ouverture automatique du navigateur
.venv/bin/python -m streamlit run app.py --server.headless true

# Écouter sur toutes les interfaces (accès depuis une autre machine)
.venv/bin/python -m streamlit run app.py --server.address 0.0.0.0
```

Arrêt : `Ctrl+C` dans le terminal.

---

## 4. Utilisation

1. Saisir une question RH dans le champ de chat (ex. « Quelle est la durée légale du travail ? »).
2. L'application recherche les **8 extraits** les plus pertinents dans ChromaDB (`TOP_K = 8`), en **fusionnant deux classements** :
   - une recherche sémantique **MMR** (`fetch_k = 40`), qui diversifie les sources et évite huit passages quasi identiques du même article ;
   - une recherche **lexicale BM25**, qui retrouve un passage contenant exactement les mots-clés de la question (« 30 jours ouvrables », « prime annuelle », un nom de module Odoo) même si le classement sémantique le place plus loin.
   Les deux classements sont fusionnés par **RRF** (Reciprocal Rank Fusion), puis les sources hors sujet sont écartées.
   - **Routage par famille** : une question contenant « Odoo » ou « PGI » interroge en priorité la documentation Odoo (et directement la page du module concerné : congés, pointage, recrutement, entretiens, paie) ; une question sur la « restauration rapide », la convention collective, les primes ou les grilles réserve des extraits à la convention collective. Sans ce routage, le Code du travail (plus de 80 % des chunks) noierait ces sources.
3. `llama3.2` rédige une réponse **uniquement à partir de ces extraits**, dans la langue choisie dans la barre latérale (français par défaut, anglais ou coréen). Pour que le modèle obéisse vraiment, **le prompt complet — consignes, règles et historique — est rédigé dans la langue choisie** : un petit modèle comme `llama3.2` suit la langue dominante des instructions, pas une consigne isolée. Le prompt couvre l'ensemble des domaines RH (contrats, temps de travail, paie, absences, rupture, formation, dialogue social, santé-sécurité, RSE, RGPD, Odoo) et demande de distinguer loi, convention collective de la restauration rapide (IDCC 1501) et documents internes.
4. Le volet **« Détails » replié par défaut** sous la réponse présente un **résumé synthétique du raisonnement** (nombre d'extraits et de sources, origine : base RH, web ou pièces jointes, avertissement si la réponse ne cite pas ses sources), la liste numérotée des sources et les extraits utilisés. Rien ne s'affiche en dehors du volet.
5. Les **6 derniers messages** de la conversation sont transmis au LLM : les questions de suivi (« et pour un CDD ? ») sont comprises, et la question envoyée à la recherche est enrichie avec la question précédente lorsqu'il s'agit d'une relance courte.
6. La barre latérale permet de **choisir la langue de la réponse** (français, anglais, coréen ; l'interface reste en français) et d'**effacer la conversation**.
7. Le menu **⋯** en haut à droite propose l'**affichage Système / Clair / Sombre**, l'impression et **À propos** (version de l'application, date de la dernière ingestion de la base RH, modèle et embeddings utilisés).

### Joindre des fichiers

1. Cliquer sur le trombone du champ de chat et choisir un ou plusieurs fichiers **PDF, TXT ou Markdown** (20 Mo maximum par fichier).
2. Saisir la question, ou laisser le champ vide pour demander un résumé du ou des documents joints.
3. Le texte des fichiers est découpé, vectorisé avec `nomic-embed-text`, puis utilisé **seul** pour construire la réponse : la base RH (`./chroma_db`) n'est pas interrogée tant qu'une pièce jointe est présente. Le contenu des pièces jointes n'est donc jamais mélangé avec les PDF de `./DRH`.
   - Si le texte total des pièces jointes fait **8 000 caractères ou moins** (cas d'un bulletin de paie d'une à deux pages), il est transmis **entier** au LLM, sans recherche par similarité : aucune ligne du document n'est écartée.
   - Au-delà, seuls les 8 extraits les plus proches de la question (`TOP_K`) sont utilisés.
   - L'extraction des PDF utilise le mode **`layout`** de pypdf : il respecte la position des colonnes et évite le texte « éclaté » (`N e t à p a y e r`) produit par certains bulletins générés (EBP, etc.). Un repli automatique sur l'extraction simple reste prévu si ce mode n'est pas disponible.
4. Les fichiers joints restent disponibles pour les questions suivantes de la session. La barre latérale permet de les retirer un par un ou tous à la fois ; une fois la liste vidée, les questions suivantes portent de nouveau sur la base RH.
5. Les passages issus des fichiers joints apparaissent dans le volet « Détails » avec la mention « Pièce jointe ».

> Les pièces jointes vivent uniquement en mémoire de session : elles ne sont **pas** ajoutées à ChromaDB et disparaissent à la fermeture de l'application. Pour intégrer durablement un document, le déposer dans `./DRH` puis relancer `ingest.py`.
>
> L'historique récent (6 messages) est utilisé pour comprendre les questions de suivi, mais il n'est jamais considéré comme une source de faits : seuls les extraits du contexte fondent la réponse.

---

## 5. Construire / reconstruire l'index

L'index est déjà présent dans `./chroma_db`. Pour le reconstruire après une modification des documents :

```bash
cd Assistant-DRH-IA
.venv/bin/python ingest.py
```

Le pipeline :

1. charge les PDF de `./DRH` (avec cache dans `./.cache/pdf`) ;
2. charge les pages web listées dans `./DRH/DRH-web.txt` (lignes vides et `#` ignorées), en se limitant au **contenu principal** (`<main>`) pour écarter les menus et la navigation, avec repli automatique sur la page complète ;
3. découpe le texte avec un splitter adapté au juridique (`chunk_size=1000`, `chunk_overlap=200`) ;
4. ajoute à chaque chunk une métadonnée `categorie` (`code_travail`, `convention`, `odoo`, `referentiel`, `web_rh`, `interne`) pour le routage de la recherche ;
5. calcule les embeddings avec `nomic-embed-text` ;
6. persiste les chunks dans `./chroma_db` ;
7. écrit `./chroma_db/ingestion.json` (date de l'ingestion et nombre de chunks), lu par l'application pour l'entrée **À propos** du menu.

Les pages web ajoutées couvrent notamment : contrats (CDD, fin de CDD, contrat d'extra), rupture (licenciement, faute, rupture conventionnelle, préavis), congés payés, arrêt maladie, paie et cotisations (fiche de paie, Smic, primes), synthèses du Code du travail numérique, RSE, RGPD/CNIL et les modules RH d'Odoo (employés, congés, pointage, recrutement, entretiens, paie).

Le corpus inclut aussi les **45 réponses officielles du Code du travail numérique propres à la convention collective de la restauration rapide (IDCC 1501)** : primes (dont la prime annuelle conventionnelle et son barème), congés, préavis, période d'essai, CDD d'extra, heures supplémentaires, travail du dimanche, arrêt maladie, maternité, etc. Ces pages sont rédigées par le ministère du Travail et remplacent avantageusement le PDF de la convention pour les questions précises : celui-ci contient un texte visuellement brouillé sur de nombreuses pages (lettres permutées, par exemple « pmire allnenue conventionnelle ») qui le rend peu exploitable par le modèle.

Legifrance et l'URSSAF ne sont pas utilisés : leurs pages bloquent le chargement automatique (anti-bot).

Pour ajouter un document : déposer un PDF dans `./DRH` ou ajouter une URL dans `./DRH/DRH-web.txt`, puis relancer `ingest.py`. La collection ChromaDB est remplacée à chaque exécution (pas de doublons).

> **Migration après renommage `DRH-pdf` → `DRH`** : l'index et le cache construits avant le renommage peuvent encore référencer `DRH-pdf/...`. L'affichage des sources reste correct (nom de fichier seul), mais pour obtenir des métadonnées propres :
> 1. supprimer l'ancien cache PDF : `rm -f .cache/pdf/pdf-*.json` (le nouveau cache inclut le nom du dossier, l'ancien est de toute façon ignoré) ;
> 2. reconstruire l'index : `.venv/bin/python ingest.py`.

---

## 6. Tests

```bash
cd Assistant-DRH-IA

# Tests unitaires (sans réseau, sans Ollama, sans Streamlit)
.venv/bin/python -m pytest -q

# Tests d'intégration (nécessitent Ollama et les fichiers réels)
.venv/bin/python -m pytest -q -m integration
```

État actuel : **152 tests verts**, 5 tests d'intégration désélectionnés par défaut (voir `pytest.ini`).

---

## 7. Structure du projet

```
Assistant-DRH-IA/
├── app.py                  # Interface Streamlit + logique RAG
├── recherche_lexicale.py   # Index BM25 (recherche lexicale fusionnée à la recherche sémantique)
├── pieces_jointes.py       # Fichiers joints de session (extraction, découpage, recherche)
├── Assistant-DRH-IA.sh     # Lanceur (Streamlit + ouverture du navigateur)
├── ingest.py               # Pipeline d'ingestion (PDF + web → ChromaDB)
├── requirements.txt        # Dépendances d'exécution
├── requirements-dev.txt    # Dépendances de développement (pytest)
├── pytest.ini              # Configuration pytest (marker « integration »)
├── plan.json               # Plan de la phase d'ingestion
├── plan-app.json           # Plan de la phase Streamlit
├── DRH/                    # Documents PDF sources + DRH-web.txt
│   └── DRH-web.txt         # URLs sources (une par ligne)
├── chroma_db/              # Base vectorielle persistée
├── .cache/pdf/             # Cache d'extraction des PDF
├── tests/
│   ├── test_ingest.py
│   ├── test_app.py
│   ├── test_recherche_lexicale.py
│   └── test_pieces_jointes.py
└── .venv/                  # Environnement Python
```

---

## 8. Configuration

Constantes principales (dans `app.py` et `ingest.py`) :

| Constante | Valeur |
|---|---|
| `APP_VERSION` | `1.1.0` (incrémentée à chaque évolution de l'application) |
| `PDF_DIR` | `./DRH` |
| `URLS_FILE` | `./DRH/DRH-web.txt` |
| `CHROMA_DIR` | `./chroma_db` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |
| `EMBEDDING_MODEL` | `nomic-embed-text` |
| `LLM_MODEL` | `llama3.2`, ou valeur de `ASSISTANT_DRH_MODEL` |
| `TOP_K` | `8` |
| `FETCH_K` | `40` (candidats MMR) |
| `MMR_LAMBDA` | `0.7` (équilibre pertinence / diversité) |
| `FACTEUR_CANDIDATS` | `4` (candidats par classement avant fusion RRF) |
| `HISTORIQUE_MAX_MESSAGES` | `6` |
| `LLM_TEMPERATURE` | `0.0` |
| `LLM_NUM_CTX` | `8192` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` |
| Formats de pièces jointes | PDF, TXT, Markdown (`.md`) |
| Taille max. par pièce jointe | `20 Mo` |
| Morceaux max. par pièce jointe | `300` |
| Contexte entier d'une pièce jointe | `8000` caractères max. |

Pour utiliser un autre modèle Ollama, sans modifier le code :

```bash
ollama pull qwen2.5:7b-instruct
ASSISTANT_DRH_MODEL=qwen2.5:7b-instruct ./Assistant-DRH-IA.sh
```

Un modèle **instruct généraliste** plus grand améliore le raisonnement juridique et la fidélité au contexte, au prix de la vitesse. `llama3.2` reste le défaut pour rester fluide.

> Les modèles de la famille `*-coder` (par exemple `qwen2.5-coder:latest`) sont spécialisés pour le code : ils peuvent être utilisés ponctuellement, mais ils sont **moins fiables sur le droit** et inventent plus facilement des articles ou des montants. Pour les questions RH sensibles, préférer un modèle instruct généraliste et vérifier systématiquement les sources affichées.

---

## 9. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Base vectorielle introuvable dans ./chroma_db » | Index absent ou supprimé | `.venv/bin/python ingest.py` |
| « Impossible d'interroger la base RH… Ollama » | Ollama arrêté ou modèle manquant | `ollama serve` puis `ollama list` / `ollama pull llama3.2` |
| `ModuleNotFoundError` | Dépendances non installées | `.venv/bin/pip install -r requirements.txt` |
| Page blanche / port occupé | Port 8501 déjà utilisé | `--server.port 8502` |
| Réponses lentes | Génération locale CPU | Normal ; réduire `TOP_K` ou `LLM_NUM_CTX` si nécessaire |
| « Je ne trouve pas cette information… » | Question hors corpus | Reformuler ou ajouter le document puis réingérer |
| « Impossible d'ajouter *fichier* : PDF illisible » / « Aucun texte exploitable » | PDF corrompu, protégé ou scanné (image sans texte) | Utiliser un PDF avec texte extractible, ou faire un OCR au préalable |
| « Format non supporté » | Extension hors PDF/TXT/MD | Convertir le document dans l'un des formats acceptés |
| « Fichier vide » | Fichier sans texte | Vérifier le contenu du fichier |

---

## 10. Limites connues (v1)

- Pas de streaming token par token.
- Mémoire conversationnelle limitée aux 6 derniers messages et à une fenêtre de contexte de 8 192 tokens.
- Les relances très longues ou sans lien explicite avec la question précédente ne sont pas reformulées par le LLM.
- Le routage Odoo / convention repose sur des mots-clés : une question très indirecte peut ne pas déclencher la bonne famille de sources.
- Le PDF de la convention collective contient un texte brouillé sur de nombreuses pages (lettres permutées) : les réponses précises sur la convention s'appuient donc sur les 45 réponses officielles du Code du travail numérique (IDCC 1501) ajoutées au corpus.
- Avec `llama3.2` (3 B), des erreurs de citation ou d'invention restent possibles malgré les consignes. Le volet « Détails » résume le raisonnement et signale les réponses qui ne citent aucune source. Pour un usage sensible, utiliser un modèle instruct plus grand (§8) et vérifier les sources.
- Pas d'authentification ni de gestion multi-utilisateurs.
- Pas de persistance de l'historique hors session.
- Pas de déploiement distant / Docker.
- Pas de réingestion depuis l'interface.
- Les pièces jointes ne sont ni persistées ni indexées durablement : elles disparaissent à la fermeture de la session.
- Formats de pièces jointes limités à PDF (texte extractible), TXT et Markdown ; pas de DOCX, XLSX ni OCR des PDF scannés.
- Les pièces jointes sont traitées indépendamment pour chaque question ; aucun résumé préalable n'est conservé.
