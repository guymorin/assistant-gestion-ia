# Refonte webdesign épurée — Assistant de Gestion IA (logo HEE)

**Date :** 2026-11-14  
**Statut :** Approuvé (plan) — en attente de relecture de la spec écrite  
**Périmètre :** Portail Streamlit unifié (RH, Finances, Paramètres, Aide)

## 1. Contexte et objectif
- **Produit :** « Assistant de Gestion - IA », portail interne avec modules RH (Q&R documentaire, Onboarding) et Finances (Q&R, Déclaration de TVA), page Paramètres/Aide et panneau latéral d’informations.
- **Objectif :** refonte visuelle complète, style **épuré et soigné**, fondée sur les trois couleurs `--brick`, `--paper`, `--green` et intégrant le logo SVG fourni (« HEE / KOREAN CHEF »).
- **Contraintes :** application Streamlit ; personnalisation via CSS injecté (`st.markdown`), structure/composants existants et `.streamlit/config.toml`. Certains éléments natifs Streamlit restent partiellement contraints.

## 2. Système de design (tokens & fondations)

### 2.1 Couleurs
| Token | Valeur | Rôle |
|---|---|---|
| `--paper` | `#F6F2EA` | Fond papier chaud, base des surfaces |
| `--green` | `#2C5B29` | Vert profond du logo : marque, nav active, titres/accents structurels, liens, focus |
| `--brick` | `#B85C3A` | Accent chaud secondaire (actions/alertes ponctuelles), parcimonieux |

Neutres de soutien : `--ink: #1F2421`, `--ink-muted: #5E665F`, `--line: #DDD7CB`, `--surface: #FFFFFF`. Fonds d’état pâles dérivés des tokens. Contraste texte/fond visé AA (ink sur paper/surface, blanc sur green/brick).

### 2.2 Typographie
- **Famille :** Roboto (import Google Fonts via CSS global) + pile de repli `system-ui, -apple-system, "Segoe UI", sans-serif`.
- **Hiérarchie (une seule famille) :** corps 15–16px / lh ~1.6, meta 13px, titres de section 20–24px, en-tête de vue 28–32px ; graisses 400/500/600/700.
- Libellés en casse phrase, focus clavier visible, longueurs de ligne confortables pour le contenu.

### 2.3 Mise en page & principes
- **Navbar fixe sobre :** fond paper/surface, bordure fine `--line`, logo SVG à gauche + « Assistant de Gestion » ; onglets RH/Finances en pastilles discrètes, actif en `--green` plein (texte clair). Pas de dégradé/ombres lourdes.
- **Canevas :** fond `--paper`, contenu aéré, colonnes existantes conservées ; panneau droit « Informations » en carte calme (`--surface`, bordure fine).
- **Composants :** champs, boutons, expanders, chat, tableaux, alertes harmonisés (coins cohérents, bordures fines, accent/focus `--green`, `--brick` pour actions/avertissements clés). Sous-menus RH/Finances alignés sur le même langage.
- **Logo :** SVG fourni enregistré comme asset et intégré à la navbar (et favicon/page icon si supporté).
- **Style :** hiérarchie nette, peu d’ornements, une couleur d’accent dominante (`--green`) ; pas de cartes clonées décoratives, pas de numérotation artificielle, pas d’étiquettes uppercase superflues.

## 3. Changements prévus (fichiers)
- `assets/logo_hee.svg` : logo fourni (nouvel asset).
- `shared/ui.py` : injection CSS globale (tokens, Roboto, navbar avec logo, panneau infos, composants/états, responsive), mise à jour `render_navbar`.
- `rh/view.py` : harmonisation des styles du sous-menu RH et éléments de vue avec les tokens globaux.
- `finances/view.py` : harmonisation des éléments de vue avec les tokens globaux (si styles spécifiques).
- `app_portail.py` : usage du logo comme icône de page si possible, métadonnées conservées.
- `.streamlit/config.toml` : alignement `primaryColor`/thème sur `--green` et compatibilité avec le rendu papier.

## 4. Accessibilité & qualité
- Contrastes conformes aux choix de tokens, états focus visibles, cibles interactives confortables, structure sémantique/hiérarchie préservée, comportement responsive.

## 5. Hors périmètre / notes
- Pas de refonte fonctionnelle ni de changement de logique métier (RH/Finances/ingestion).
- Mode sombre : la palette « papier » est prioritaire pour le rendu épuré demandé ; l’alignement des thèmes Streamlit sera ajusté au mieux sans garantir une parité sombre complète si non requise.
- Validation visuelle finale dépend du rendu Streamlit réel ; des ajustements mineurs de contraste/espacement peuvent être nécessaires.
