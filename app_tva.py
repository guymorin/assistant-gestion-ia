"""Assistant TVA - Comptabilite : automatisation de la declaration de TVA mensuelle.

Application Streamlit locale. La logique metier (extraction, rapprochement,
generation du mail) est isolee de Streamlit et testable unitairement ; les
dependances externes (lecture PDF/XLSX) sont injectables via des factories.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Configuration
COMPTABLE_DIR = "./Comptable"
ETABLISSEMENTS = {
    "HEE-REP-93100": {
        "prefixe_fichiers": "Republique",
        "banque": "CIC",
        "libelle": "HEE République",
    },
    "HEE-MAR-93100": {
        "prefixe_fichiers": "Marceau",
        "banque": "LCL",
        "libelle": "HEE Marceau",
    },
}
MOIS = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]
ANNEES = [2025, 2026, 2027]
SEUIL_ECART_PCT_DEFAUT = 0.20
SEUIL_ECART_PCT_MIN = 0.0
SEUIL_ECART_PCT_MAX = 0.5


def mois_precedent(jour: date | None = None) -> tuple[int, int]:
    """Mois précédant ``jour`` (aujourd'hui par défaut) : janvier → décembre N-1."""
    reference = jour if jour is not None else date.today()
    if reference.month == 1:
        return reference.year - 1, 12
    return reference.year, reference.month - 1


def _premier_existant(candidats) -> Path | None:
    for candidat in candidats:
        if candidat.is_file():
            return candidat
    return None


def _caisse_du_mois(dossier: Path, prefixe: str, annee: int, mois: int) -> Path | None:
    """Rapport de caisse du mois : PDF, puis Excel, puis business export."""
    base = f"{prefixe}-Caisse-{annee:04d}-{mois:02d}"
    trouve = _premier_existant(
        [dossier / f"{base}.pdf", dossier / f"{base}.xls", dossier / f"{base}.xlsx"]
    )
    if trouve is not None:
        return trouve
    return _premier_existant(
        sorted(dossier.glob(f"*business_export*_{annee:04d}{mois:02d}*.xls*"))
    )


def trouver_fichiers(
    etablissement: str,
    annee: int,
    mois: int,
    base_dir: str | Path = COMPTABLE_DIR,
) -> dict:
    """Localise les pièces d'un mois ; ``erreur`` si le dossier est absent."""
    resultat: dict[str, Any] = {
        "caisse": None,
        "banque": None,
        "obypay": None,
        "erreur": None,
    }
    dossier = Path(base_dir) / etablissement
    if not dossier.is_dir():
        resultat["erreur"] = f"Dossier {dossier} introuvable"
        return resultat

    prefixe = ETABLISSEMENTS[etablissement]["prefixe_fichiers"]
    resultat["caisse"] = _caisse_du_mois(dossier, prefixe, annee, mois)
    resultat["banque"] = _premier_existant(
        [dossier / f"{prefixe}-Banque-{annee:04d}-{mois:02d}.pdf"]
    )
    resultat["obypay"] = _premier_existant(
        sorted(dossier.glob(f"*obypay_monthly_{annee:04d}-{mois:02d}-*.xlsx"))
    )
    return resultat


def _mois_caisse_banque(
    dossier: Path, prefixe: str
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Mois (année, mois) couverts par une caisse et par un relevé bancaire."""
    motif_caisse = re.compile(
        rf"^{re.escape(prefixe)}-Caisse-(\d{{4}})-(\d{{2}})\.(?:pdf|xlsx?)$"
    )
    motif_banque = re.compile(
        rf"^{re.escape(prefixe)}-Banque-(\d{{4}})-(\d{{2}})\.pdf$"
    )
    caisses: set[tuple[int, int]] = set()
    banques: set[tuple[int, int]] = set()
    for fichier in dossier.iterdir():
        if not fichier.is_file():
            continue
        nom = fichier.name
        for motif, cible in ((motif_caisse, caisses), (motif_banque, banques)):
            correspondance = motif.match(nom)
            if correspondance:
                cible.add(
                    (int(correspondance.group(1)), int(correspondance.group(2)))
                )
                break
    return caisses, banques


def dernier_mois_disponible(
    etablissement: str, base_dir: str | Path = COMPTABLE_DIR
) -> tuple[int, int] | None:
    """Mois le plus récent avec caisse et banque, sinon avec l'une des deux."""
    dossier = Path(base_dir) / etablissement
    if not dossier.is_dir():
        return None
    prefixe = ETABLISSEMENTS[etablissement]["prefixe_fichiers"]
    caisses, banques = _mois_caisse_banque(dossier, prefixe)
    complets = caisses & banques
    if complets:
        return max(complets)
    partiels = caisses | banques
    return max(partiels) if partiels else None


def normaliser_montant(texte) -> float | None:
    if texte is None:
        return None
    s = str(texte).strip()
    if not s:
        return None
    # Nettoyer les espaces insécables et espaces multiples
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    # Conserver uniquement les chiffres et les séparateurs
    # Détecter le séparateur décimal : le dernier ',' ou '.' présent
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma == -1 and last_dot == -1:
        # Pas de séparateur : tenter un float direct
        try:
            return float(s.replace(" ", ""))
        except ValueError:
            return None
    # Le séparateur décimal est celui qui apparaît en dernier
    if last_comma > last_dot:
        decimal_sep = ","
        thousand_sep = "."
    else:
        decimal_sep = "."
        thousand_sep = ","
    # Supprimer les séparateurs de milliers (l'autre séparateur) et les espaces
    s = s.replace(" ", "")
    if thousand_sep:
        s = s.replace(thousand_sep, "")
    # Remplacer la virgule décimale par un point
    if decimal_sep == ",":
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


_MONTANT_EN_FIN = re.compile(r"^(?P<label>.*?)\s*(?P<montant>-?\d[\d\s.,]*)$")
_TAUX_TVA = re.compile(r"^tva\s+(?P<taux>\d+(?:[.,]\d+)?)\s*%$")
_LIBELLES_DEBUT_TAXES = {"b. taxes", "b taxes", "taxes"}
_LIBELLES_FIN_TAXES = {"c. ventes", "c ventes", "ventes"}


def _normaliser_libelle(libelle) -> str:
    """Normalise un libellé pour les comparaisons (espaces, casse, ponctuation)."""
    if libelle is None:
        return ""
    s = str(libelle).replace("\u00a0", " ").replace("\u202f", " ")
    s = " ".join(s.split())
    return s.strip().rstrip(":").lower()


def _paires_depuis_texte_pdf(texte: str) -> list[tuple[str, str | None]]:
    """Transforme chaque ligne en (libellé, dernier montant ou None).

    Une ligne vide est ignorée. Lorsque la ligne se termine par un montant
    au format français (ex. « 27 542,50 »), le libellé est la ligne privée de
    ce montant, sinon le montant vaut ``None``.
    """
    paires: list[tuple[str, str | None]] = []
    for ligne in (texte or "").splitlines():
        ligne = ligne.replace("\u00a0", " ").replace("\u202f", " ").strip()
        if not ligne:
            continue
        correspondance = _MONTANT_EN_FIN.match(ligne)
        if correspondance and correspondance.group("label").strip():
            paires.append(
                (
                    correspondance.group("label").strip(),
                    correspondance.group("montant").strip(),
                )
            )
        else:
            paires.append((ligne, None))
    return paires


def _extraire_caisse_depuis_paires(
    paires: list[tuple[str, str | None]],
) -> dict:
    """Extrait total des ventes, TVA collectée et détail par taux des paires."""
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
    }
    libelles = [_normaliser_libelle(label) for label, _ in paires]

    # total_ventes : première paire « total des ventes » portant une valeur.
    for label, montant in paires:
        if "total des ventes" in _normaliser_libelle(label):
            valeur = normaliser_montant(montant)
            if valeur is not None:
                resultat["total_ventes"] = valeur
                break

    # Section « B. Taxes » = de « B. Taxes » à « C. Ventes ».
    debut = next(
        (i for i, libelle in enumerate(libelles) if libelle in _LIBELLES_DEBUT_TAXES),
        None,
    )
    if debut is not None:
        fin = next(
            (
                i
                for i in range(debut + 1, len(paires))
                if libelles[i] in _LIBELLES_FIN_TAXES
            ),
            len(paires),
        )
        section = paires[debut:fin]
        libelles_section = libelles[debut:fin]

        # tva_collectee : après le dernier « Total » exact de la section,
        # première ligne dont le libellé est exactement « Taxe ».
        index_total = None
        for i, libelle in enumerate(libelles_section):
            if libelle == "total":
                index_total = i
        if index_total is not None:
            for i in range(index_total + 1, len(section)):
                if libelles_section[i] == "taxe":
                    resultat["tva_collectee"] = normaliser_montant(section[i][1])
                    break

        # detail_par_taux : bloc « TVA <taux>% » suivi de ses trois montants,
        # jusqu'au prochain taux ou au « Total ».
        for i in range(len(section)):
            correspondance = _TAUX_TVA.match(libelles_section[i])
            if not correspondance:
                continue
            taux = normaliser_montant(correspondance.group("taux"))
            if taux is None:
                continue
            valeurs = {"ht": None, "tva": None, "ttc": None}
            for j in range(i + 1, len(section)):
                libelle_suivant = libelles_section[j]
                if _TAUX_TVA.match(libelle_suivant) or libelle_suivant == "total":
                    break
                if libelle_suivant == "montant hors-taxe":
                    valeurs["ht"] = normaliser_montant(section[j][1])
                elif libelle_suivant == "taxe":
                    valeurs["tva"] = normaliser_montant(section[j][1])
                elif libelle_suivant == "montant taxe comprise":
                    valeurs["ttc"] = normaliser_montant(section[j][1])
            resultat["detail_par_taux"].append({"taux": taux, **valeurs})

    if resultat["total_ventes"] is not None or resultat["tva_collectee"] is not None:
        resultat["statut"] = "ok"
    return resultat


def _texte_depuis_reader(reader) -> str:
    """Concatène le texte de chaque page d'un reader (pypdf ou factice)."""
    morceaux = []
    for page in getattr(reader, "pages", []) or []:
        try:
            morceaux.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(morceaux)


def _texte_pdf_pypdf(contenu) -> str:
    import pypdf

    return _texte_depuis_reader(pypdf.PdfReader(io.BytesIO(contenu)))


def _texte_pdf_pdftotext(contenu) -> str:
    """Extrait le texte via ``pdftotext -layout`` (vide si indisponible)."""
    if shutil.which("pdftotext") is None:
        return ""
    resultat = subprocess.run(
        ["pdftotext", "-layout", "-", "-"],
        input=contenu,
        capture_output=True,
        timeout=60,
    )
    if resultat.returncode != 0:
        return ""
    return resultat.stdout.decode("utf-8", errors="replace")


def _texte_pdf_pdfplumber(contenu) -> str:
    import pdfplumber

    morceaux = []
    with pdfplumber.open(io.BytesIO(contenu)) as document:
        for page in document.pages:
            morceaux.append(page.extract_text(layout=True) or "")
    return "\n".join(morceaux)


def extraire_texte_pdf(contenu, reader_factory=None, layout=False) -> str:
    """Extrait le texte d'un PDF sans jamais lever : ``""`` en cas d'échec.

    ``reader_factory`` permet d'injecter un reader maison. En mode ``layout``,
    on privilégie ``pdftotext -layout`` puis ``pdfplumber`` pour préserver la
    disposition des colonnes ; ``pypdf`` sert toujours de repli final.
    """
    try:
        if reader_factory is not None:
            return _texte_depuis_reader(reader_factory(contenu))
        if layout:
            for extraction in (_texte_pdf_pdftotext, _texte_pdf_pdfplumber):
                try:
                    texte = extraction(contenu)
                except Exception as exc:
                    logger.debug(
                        "extraire_texte_pdf (%s): %s", extraction.__name__, exc
                    )
                    continue
                if texte:
                    return texte
        return _texte_pdf_pypdf(contenu)
    except Exception as exc:
        logger.warning("extraire_texte_pdf: %s", exc)
        return ""


def extraire_caisse_pdf(contenu, reader_factory=None) -> dict:
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
        "type_fichier": "caisse_pdf",
        "erreur": None,
    }
    try:
        if reader_factory is None:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(contenu))
        else:
            reader = reader_factory(contenu)
        pages = getattr(reader, "pages", []) or []
        morceaux = []
        for page in pages:
            try:
                morceaux.append(page.extract_text() or "")
            except Exception:
                continue
        texte = "\n".join(morceaux)
        extrait = _extraire_caisse_depuis_paires(_paires_depuis_texte_pdf(texte))
        resultat["total_ventes"] = extrait["total_ventes"]
        resultat["tva_collectee"] = extrait["tva_collectee"]
        resultat["detail_par_taux"] = extrait["detail_par_taux"]
        resultat["statut"] = extrait["statut"]
    except Exception as exc:
        logger.warning("extraire_caisse_pdf: %s", exc)
        resultat["statut"] = "incomplet"
        resultat["erreur"] = str(exc)
    return resultat


def _paires_depuis_rangees(rangees: list[list]) -> list[tuple[str, str | None]]:
    """Première cellule non vide = libellé, dernière non vide = valeur."""
    paires: list[tuple[str, str | None]] = []
    for rangee in rangees:
        cellules = []
        for cellule in rangee:
            if cellule is None:
                continue
            texte = str(cellule).strip()
            if texte:
                cellules.append(texte)
        if not cellules:
            continue
        if len(cellules) == 1:
            paires.append((cellules[0], None))
        else:
            paires.append((cellules[0], cellules[-1]))
    return paires


def extraire_caisse_excel(contenu, nom, reader_factory=None) -> dict:
    resultat = {
        "total_ventes": None,
        "tva_collectee": None,
        "detail_par_taux": [],
        "statut": "incomplet",
        "type_fichier": "caisse_excel",
        "erreur": None,
    }
    try:
        if reader_factory is None:
            import pandas

            moteur = "xlrd" if str(nom).lower().endswith(".xls") else "openpyxl"
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = pandas.read_excel(io.BytesIO(contenu), header=None, engine=moteur)
        else:
            df = reader_factory(contenu, nom)
        rangees = df.astype(object).where(df.notna(), "").astype(str).values.tolist()
        extrait = _extraire_caisse_depuis_paires(_paires_depuis_rangees(rangees))
        resultat["total_ventes"] = extrait["total_ventes"]
        resultat["tva_collectee"] = extrait["tva_collectee"]
        resultat["detail_par_taux"] = extrait["detail_par_taux"]
        resultat["statut"] = extrait["statut"]
    except Exception as exc:
        logger.warning("extraire_caisse_excel: %s", exc)
        resultat["statut"] = "incomplet"
        resultat["erreur"] = str(exc)
    return resultat


def _texte_cellule(cellule) -> str:
    """Représentation texte d'une cellule, vide pour None/NaN."""
    if cellule is None:
        return ""
    try:
        if cellule != cellule:  # NaN
            return ""
    except Exception:
        pass
    return str(cellule).strip()


def _normaliser_entete(cellule) -> str:
    """Normalise un libellé d'en-tête : accents ignorés, casse et espaces unifiés."""
    texte = unicodedata.normalize("NFKD", _texte_cellule(cellule))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split()).upper()


_OBYPAY_NUMERO = re.compile(r"^[A-Za-z0-9]{10}$")
_OBYPAY_COLONNES_MONTANT = (
    "MOYEN PAYMENT 1 TTC",
    "PRIX TTC APRES REMISE",
    "PRIX TTC AVANT REMISE",
)


def _trouver_entete_obypay(df):
    """Renvoie (index de la ligne d'en-tête, {libellé: colonne}, lignes) ou None."""
    if df is None or not hasattr(df, "values"):
        return None
    rangees = df.astype(object).where(df.notna(), None).values.tolist()
    for index, rangee in enumerate(rangees):
        entetes = [_normaliser_entete(cellule) for cellule in rangee]
        if "NUMERO" not in entetes or "TRANSACTION" not in entetes:
            continue
        colonnes: dict[str, int] = {}
        for position, entete in enumerate(entetes):
            if entete and entete not in colonnes:
                colonnes[entete] = position
        return index, colonnes, rangees
    return None


def extraire_obypay_xlsx(contenu, reader_factory=None) -> dict:
    """Extrait le total TTC et le nombre de transactions d'un export Obypay.

    Les feuilles sont parcourues dans l'ordre jusqu'à la première portant une
    ligne d'en-tête contenant « NUMÉRO » et « TRANSACTION » et au moins une
    colonne de montant ; elle seule est dépouillée. Seules les lignes dont la
    cellule NUMÉRO est un identifiant de 10 caractères alphanumériques sont
    retenues, ce qui écarte les marqueurs de section (« AVEC PAIEMENT »,
    « SANS PAIEMENT », « PRODUITS »...).
    """
    resultat = {
        "total_ttc": None,
        "nb_transactions": 0,
        "statut": "incomplet",
        "type_fichier": "obypay_xlsx",
        "erreur": None,
    }
    try:
        if reader_factory is None:
            import pandas

            feuilles = pandas.read_excel(
                io.BytesIO(contenu), sheet_name=None, header=None
            )
        else:
            feuilles = reader_factory(contenu)
        if not feuilles:
            return resultat

        total = 0.0
        nb_transactions = 0
        entete_trouvee = False

        for df in feuilles.values():
            trouve = _trouver_entete_obypay(df)
            if trouve is None:
                continue
            index_entete, colonnes, rangees = trouve
            if not any(
                libelle in colonnes for libelle in _OBYPAY_COLONNES_MONTANT
            ):
                continue
            entete_trouvee = True

            colonne_numero = colonnes["NUMERO"]
            for rangee in rangees[index_entete + 1 :]:
                if colonne_numero >= len(rangee):
                    continue
                numero = _texte_cellule(rangee[colonne_numero])
                if not _OBYPAY_NUMERO.match(numero):
                    continue

                montant = None
                for libelle in _OBYPAY_COLONNES_MONTANT:
                    position = colonnes.get(libelle)
                    if position is None or position >= len(rangee):
                        continue
                    montant = normaliser_montant(rangee[position])
                    if montant is not None:
                        break
                if montant is None:
                    continue

                total += montant
                nb_transactions += 1

            # Seule la première feuille portant un en-tête exploitable est lue :
            # additionner plusieurs feuilles fausserait le total.
            break

        if entete_trouvee:
            resultat["total_ttc"] = round(total, 2)
            resultat["nb_transactions"] = nb_transactions
            resultat["statut"] = "ok"
    except Exception as exc:
        logger.warning("extraire_obypay_xlsx: %s", exc)
        resultat["statut"] = "incomplet"
        resultat["erreur"] = str(exc)
    return resultat


# Un montant français : « 4.081,00 », « 3 874,30 » (espace fine ou insécable).
_MONTANT_BANQUE = r"(\d{1,3}(?:[ .\u00a0\u202f]\d{3})*,\d{2})"
_MONTANT_BANQUE_RE = re.compile(_MONTANT_BANQUE)
_TOTAL_CIC_RE = re.compile(
    r"Total\s+des\s+mouvements\s+" + _MONTANT_BANQUE + r"\s+" + _MONTANT_BANQUE,
    re.IGNORECASE,
)
_TOTAL_LCL_RE = re.compile(
    r"\bTOTAUX\b\s+" + _MONTANT_BANQUE + r"\s+" + _MONTANT_BANQUE,
    re.IGNORECASE,
)
_SOLDE_CIC_RE = re.compile(
    r"SOLDE\s+CREDITEUR\s+AU\s+\d{2}/\d{2}/\d{4}\s+" + _MONTANT_BANQUE,
    re.IGNORECASE,
)
_SOLDE_LCL_RE = re.compile(
    r"SOLDE\s+EN\s+EUROS\s+" + _MONTANT_BANQUE, re.IGNORECASE
)
_PERIODE_OBYPAY_RE = re.compile(r"OBYPAY\s+(\d{8})\s+(\d{8})", re.IGNORECASE)
_MOTIFS_EXCLUS_BANQUE = ("PRLV", "PAIEMENT", "ECH", "FACT", "VIR SALAIRE")


def _detecter_banque(texte: str, total_cic, total_lcl) -> str:
    """Identifie l'émetteur du relevé : LCL, CIC ou inconnu.

    Les en-têtes réels portent le nom de la banque, mais les textes dépouillés
    ou tronqués peuvent l'avoir perdu : la forme des lignes de totaux sert
    alors de repli.
    """
    texte_majuscules = (texte or "").upper()
    if "CREDIT LYONNAIS" in texte_majuscules or re.search(
        r"\bLCL\b", texte_majuscules
    ):
        return "LCL"
    if "CIC" in texte_majuscules:
        return "CIC"
    if total_cic is not None:
        return "CIC"
    if total_lcl is not None:
        return "LCL"
    return "inconnu"


def _source_credit(ligne: str) -> str | None:
    """Source d'une ligne créditrice, ou None si la ligne n'en est pas une."""
    ligne_majuscules = ligne.upper()
    if "VIR" not in ligne_majuscules:
        return None
    if any(motif in ligne_majuscules for motif in _MOTIFS_EXCLUS_BANQUE):
        return None
    if "LIGHTSPEED" in ligne_majuscules:
        return "LIGHTSPEED"
    if "2BEVENTS" in ligne_majuscules or "OBYPAY" in ligne_majuscules:
        return "OBYPAY"
    return None


def _dernier_montant(ligne: str) -> float | None:
    """Dernier montant français de la ligne (les milliers peuvent être espacés)."""
    montants = _MONTANT_BANQUE_RE.findall(ligne)
    if not montants:
        return None
    return normaliser_montant(montants[-1])


def _periode_obypay(lignes: list[str], index: int) -> tuple[str | None, str | None]:
    """Période « OBYPAY YYYYMMDD YYYYMMDD » de la ligne ou des deux suivantes."""
    for ligne in lignes[index : index + 3]:
        correspondance = _PERIODE_OBYPAY_RE.search(ligne)
        if correspondance:
            debut, fin = correspondance.groups()
            return (
                f"{debut[:4]}-{debut[4:6]}-{debut[6:]}",
                f"{fin[:4]}-{fin[4:6]}-{fin[6:]}",
            )
    return None, None


def extraire_banque_pdf(contenu, reader_factory=None, texte_factory=None) -> dict:
    """Extrait totaux, solde et crédits Obypay/Lightspeed d'un relevé CIC ou LCL.

    Le texte doit conserver les colonnes (``layout=True``) : sur un relevé LCL
    les milliers sont séparés par une espace, si bien que le montant ne peut
    pas être lu comme le dernier « mot » de la ligne.
    """
    resultat = {
        "banque": "inconnu",
        "total_debits": None,
        "total_credits": None,
        "solde_final": None,
        "credits_par_source": {},
        "versements_obypay": [],
        "statut": "incomplet",
        "type_fichier": "banque_pdf",
        "erreur": None,
    }
    try:
        if texte_factory is not None:
            texte = texte_factory(contenu)
        else:
            texte = extraire_texte_pdf(
                contenu, reader_factory=reader_factory, layout=True
            )
        texte = texte or ""
        lignes = texte.splitlines()

        total_cic = _TOTAL_CIC_RE.search(texte)
        total_lcl = _TOTAL_LCL_RE.search(texte)
        resultat["banque"] = _detecter_banque(texte, total_cic, total_lcl)
        lcl = resultat["banque"] == "LCL"

        # Le format propre à la banque identifiée est testé en premier, l'autre
        # servant de repli pour les relevés atypiques.
        totaux = (
            (_TOTAL_LCL_RE, _TOTAL_CIC_RE)
            if lcl
            else (_TOTAL_CIC_RE, _TOTAL_LCL_RE)
        )
        for motif_totaux in totaux:
            total = motif_totaux.search(texte)
            if total is not None:
                resultat["total_debits"] = normaliser_montant(total.group(1))
                resultat["total_credits"] = normaliser_montant(total.group(2))
                break

        for motif_solde in (
            (_SOLDE_LCL_RE, _SOLDE_CIC_RE)
            if lcl
            else (_SOLDE_CIC_RE, _SOLDE_LCL_RE)
        ):
            soldes = motif_solde.findall(texte)
            if soldes:
                # Le relevé CIC rappelle d'abord l'ancien solde : dernier match.
                resultat["solde_final"] = normaliser_montant(soldes[-1])
                break

        credits = {"OBYPAY": 0.0, "LIGHTSPEED": 0.0}
        for index, ligne in enumerate(lignes):
            source = _source_credit(ligne)
            if source is None:
                continue
            montant = _dernier_montant(ligne)
            if montant is None:
                continue
            credits[source] += montant
            if source == "OBYPAY":
                debut, fin = _periode_obypay(lignes, index)
                resultat["versements_obypay"].append(
                    {
                        "montant": montant,
                        "periode_debut": debut,
                        "periode_fin": fin,
                    }
                )

        total_credits = resultat["total_credits"]
        autres = 0.0
        if total_credits is not None:
            autres = total_credits - credits["OBYPAY"] - credits["LIGHTSPEED"]
            if autres < 0:
                autres = 0.0
        resultat["credits_par_source"] = {
            "OBYPAY": round(credits["OBYPAY"], 2),
            "LIGHTSPEED": round(credits["LIGHTSPEED"], 2),
            "AUTRES": round(autres, 2),
        }

        if (
            resultat["total_debits"] is not None
            and resultat["total_credits"] is not None
        ):
            if credits["OBYPAY"] or credits["LIGHTSPEED"]:
                resultat["statut"] = "ok"
            else:
                resultat["statut"] = "partiel"
    except Exception as exc:
        logger.warning("extraire_banque_pdf: %s", exc)
        resultat["statut"] = "incomplet"
        resultat["erreur"] = str(exc)
    return resultat


_RELEVE_BANCAIRE = re.compile(r"\breleve")


def _normaliser_texte_detection(texte) -> str:
    """Minuscules, accents retirés et espaces unifiés pour la détection."""
    normalise = unicodedata.normalize(
        "NFKD", "" if texte is None else str(texte)
    )
    normalise = "".join(c for c in normalise if not unicodedata.combining(c))
    return " ".join(normalise.lower().split())


def detecter_type_depuis_texte_pdf(texte) -> str:
    """Devine le type d'un PDF à partir de son texte : caisse, banque, inconnu.

    La caisse est testée en premier : un rapport de caisse contenant aussi
    « Total des ventes » ne doit jamais être classé comme relevé bancaire.
    """
    normalise = _normaliser_texte_detection(texte)
    if "resume fiscal" in normalise or "total des ventes" in normalise:
        return "caisse_pdf"
    if (
        _RELEVE_BANCAIRE.search(normalise)
        or "totaux" in normalise
        or "total des mouvements" in normalise
    ):
        return "banque_pdf"
    return "inconnu"


def _entetes_feuille(df) -> set[str]:
    """Ensemble des libellés normalisés (majuscules, sans accents) d'une feuille."""
    entetes: set[str] = set()
    if df is None or not hasattr(df, "values"):
        return entetes
    rangees = df.astype(object).where(df.notna(), None).values.tolist()
    for rangee in rangees:
        for cellule in rangee:
            entete = _normaliser_entete(cellule)
            if entete:
                entetes.add(entete)
    return entetes


def detecter_type_depuis_feuilles(feuilles) -> str:
    """Devine le type d'un classeur : export Obypay, caisse Excel ou inconnu."""
    try:
        entetes_par_feuille = [
            _entetes_feuille(df) for df in (feuilles or {}).values()
        ]
        # Obypay d'abord : un export de transactions reste identifiable même
        # s'il contient par ailleurs des libellés de caisse.
        for entetes in entetes_par_feuille:
            if "NUMERO" in entetes and "TRANSACTION" in entetes:
                return "obypay_xlsx"
        for entetes in entetes_par_feuille:
            if "RESUME" in entetes and "TAXES" in entetes:
                return "caisse_excel"
    except Exception as exc:
        logger.warning("detecter_type_depuis_feuilles: %s", exc)
    return "inconnu"


def detecter_type_fichier(
    nom, contenu, texte_factory=None, feuilles_factory=None
) -> str:
    """Détecte le type d'un fichier d'après son extension ; ne lève jamais."""
    try:
        suffixe = Path(str(nom or "")).suffix.lower()
        if suffixe == ".pdf":
            if texte_factory is not None:
                texte = texte_factory(contenu)
            else:
                texte = extraire_texte_pdf(contenu)
            return detecter_type_depuis_texte_pdf(texte)
        if suffixe in (".xls", ".xlsx"):
            if feuilles_factory is not None:
                feuilles = feuilles_factory(contenu, nom)
            else:
                import pandas

                moteur = "xlrd" if suffixe == ".xls" else "openpyxl"
                feuilles = pandas.read_excel(
                    io.BytesIO(contenu), sheet_name=None, header=None, engine=moteur
                )
            return detecter_type_depuis_feuilles(feuilles)
    except Exception as exc:
        logger.warning("detecter_type_fichier: %s", exc)
    return "inconnu"


_PIECES_MAIL = (
    ("caisse", "Rapport de caisse"),
    ("banque", "Relevé bancaire"),
    ("obypay", "Export Obypay"),
)


def formater_euros(valeur) -> str:
    """Montant au format français (« 1 234,50 € ») ; ``None`` → « non trouvé »."""
    if valeur is None:
        return "non trouvé"
    texte = f"{float(valeur):,.2f}".replace(",", " ").replace(".", ",")
    return f"{texte} €"


def _nom_piece(valeur) -> str:
    """Nom du fichier joint, ou « à fournir » si la pièce manque."""
    if valeur is None:
        return "à fournir"
    return Path(str(valeur)).name or "à fournir"


def _ligne_catering(catering) -> str:
    if not catering or not catering.get("present"):
        return "Facture catering : Non"
    montant_ht = catering.get("montant_ht")
    tva = catering.get("tva")
    ttc = montant_ht + tva if montant_ht is not None and tva is not None else None
    client = catering.get("client") or "non renseigné"
    return (
        f"Facture catering : Oui — {client} — "
        f"HT {formater_euros(montant_ht)}, TVA {formater_euros(tva)} "
        f"(TTC {formater_euros(ttc)})"
    )


def generer_mail_comptable(
    etablissement: str,
    annee: int,
    mois: int,
    fichiers,
    catering=None,
) -> str:
    """Rédige le mail de transmission des pièces du mois au comptable.

    Les pièces absentes sont signalées « à fournir » plutôt que de faire
    échouer la génération. Le mail se limite à la transmission des pièces :
    ni liste de factures d'achat, ni récapitulatif de TVA.
    """
    libelle = ETABLISSEMENTS[etablissement]["libelle"]
    pieces = fichiers or {}
    lignes_pieces = [
        f"{intitule} : {_nom_piece(pieces.get(cle))}"
        for cle, intitule in _PIECES_MAIL
    ]
    blocs = [
        f"Objet : Déclaration de TVA — {libelle} ({etablissement}) "
        f"— {MOIS[mois - 1]} {annee}",
        "Bonjour,",
        "Veuillez trouver ci-dessous les pièces du mois pour la déclaration "
        "de TVA.",
        "\n".join(lignes_pieces),
        _ligne_catering(catering),
        "Restant à votre disposition pour toute précision, je vous prie "
        "d'agréer mes salutations distinguées.",
        "Cordialement,\nL'équipe gestion",
    ]
    return "\n\n".join(blocs) + "\n"



def agreger_caisses(caisses) -> dict:
    total_ventes = 0.0
    tva_collectee = 0.0
    detail: dict = {}
    for c in (caisses or []):
        if not c:
            continue
        if c.get("total_ventes") is not None:
            total_ventes += c["total_ventes"]
        if c.get("tva_collectee") is not None:
            tva_collectee += c["tva_collectee"]
        for d in (c.get("detail_par_taux") or []):
            taux = d.get("taux")
            if taux not in detail:
                detail[taux] = {"taux": taux, "ht": 0.0, "tva": 0.0, "ttc": 0.0}
            for champ in ("ht", "tva", "ttc"):
                v = d.get(champ)
                if v is not None:
                    detail[taux][champ] += v
    return {
        "total_ventes": total_ventes,
        "tva_collectee": tva_collectee,
        "detail_par_taux": list(detail.values()),
    }


def agreger_banques(banques) -> dict:
    total_debits = 0.0
    total_credits = 0.0
    solde_final = 0.0
    credits_par_source: dict = {}
    versements = []
    for b in (banques or []):
        if not b:
            continue
        if b.get("total_debits") is not None:
            total_debits += b["total_debits"]
        if b.get("total_credits") is not None:
            total_credits += b["total_credits"]
        if b.get("solde_final") is not None:
            solde_final += b["solde_final"]
        for src, val in (b.get("credits_par_source") or {}).items():
            if val is not None:
                credits_par_source[src] = credits_par_source.get(src, 0.0) + val
        versements.extend(b.get("versements_obypay") or [])
    return {
        "total_debits": total_debits,
        "total_credits": total_credits,
        "solde_final": solde_final,
        "credits_par_source": credits_par_source,
        "versements_obypay": versements,
    }


def agreger_obypays(obypays) -> dict:
    total_ttc = 0.0
    nb_transactions = 0
    for o in (obypays or []):
        if not o:
            continue
        if o.get("total_ttc") is not None:
            total_ttc += o["total_ttc"]
        if o.get("nb_transactions") is not None:
            nb_transactions += o["nb_transactions"]
    return {"total_ttc": total_ttc, "nb_transactions": nb_transactions}


def verifier_rapprochement(
    caisse, banque, obypay, tva_deductible, total_factures_fournisseurs,
    catering=None, seuil_ecart_pct=SEUIL_ECART_PCT_DEFAUT,
) -> dict:
    caisse = caisse or {}
    banque = banque or {}
    obypay = obypay or {}
    catering = catering or {}
    catering_present = bool(catering.get("present"))

    tva_collectee_caisse = caisse.get("tva_collectee")
    tva_collectee_catering = None
    if catering_present:
        v = catering.get("tva")
        tva_collectee_catering = 0.0 if v is None else v

    if tva_collectee_caisse is None and not catering_present:
        tva_collectee = None
    else:
        tva_collectee = 0.0
        if tva_collectee_caisse is not None:
            tva_collectee += tva_collectee_caisse
        if tva_collectee_catering is not None:
            tva_collectee += tva_collectee_catering

    total_ventes_caisse = caisse.get("total_ventes")
    total_ventes_catering = None
    if catering_present:
        v = catering.get("montant_ht")
        total_ventes_catering = 0.0 if v is None else v

    if total_ventes_caisse is None:
        total_ventes_attendu = None
    else:
        total_ventes_attendu = total_ventes_caisse
        if total_ventes_catering is not None:
            total_ventes_attendu += total_ventes_catering

    tva_deductible = tva_deductible or 0.0
    total_factures = total_factures_fournisseurs or 0.0

    if tva_collectee is None:
        tva_a_decaisser = None
    else:
        tva_a_decaisser = tva_collectee - tva_deductible

    if tva_a_decaisser is None:
        credit_tva = 0.0
    else:
        credit_tva = max(0.0, -tva_a_decaisser)
        if tva_a_decaisser >= 0:
            credit_tva = 0.0

    total_credits_banque = banque.get("total_credits")
    credits_par_source = banque.get("credits_par_source") or {}
    obypay_banque = credits_par_source.get("OBYPAY", 0.0) or 0.0
    lightspeed_banque = credits_par_source.get("LIGHTSPEED", 0.0) or 0.0
    autres_banque = credits_par_source.get("AUTRES", 0.0) or 0.0
    credits_identifies = obypay_banque + lightspeed_banque

    obypay_attendu = obypay.get("total_ttc")
    if obypay_attendu is None:
        obypay_attendu = 0.0
    ecart_obypay = obypay_attendu - obypay_banque
    ecart_pct_obypay = (ecart_obypay / obypay_attendu) if obypay_attendu > 0 else None

    if total_ventes_attendu is not None and total_ventes_attendu > 0:
        ecart_global = total_ventes_attendu - credits_identifies
        ecart_global_pct = ecart_global / total_ventes_attendu
    else:
        ecart_global = None
        ecart_global_pct = None

    if not caisse or not banque or not total_ventes_attendu or total_ventes_attendu <= 0:
        statut = "INCOMPLET"
    elif ecart_global < 0 or (ecart_global_pct is not None and ecart_global_pct > seuil_ecart_pct):
        statut = "A_JUSTIFIER"
    else:
        statut = "OK"

    # obypay statut : écart négatif (banque > attendu) ou écart relatif > seuil -> A_JUSTIFIER
    if not obypay or obypay.get("total_ttc") is None or obypay_attendu <= 0:
        statut_obypay = "INCOMPLET"
    elif ecart_obypay < 0 or (ecart_pct_obypay is not None and ecart_pct_obypay > seuil_ecart_pct):
        statut_obypay = "A_JUSTIFIER"
    else:
        statut_obypay = "OK"

    sources = [
        {
            "source": "OBYPAY",
            "attendu": obypay_attendu,
            "banque": obypay_banque,
            "ecart": ecart_obypay,
            "ecart_pct": ecart_pct_obypay,
            "statut": statut_obypay,
            "commentaire": "Décalage de versement possible (payout lag).",
        },
        {
            "source": "LIGHTSPEED",
            "attendu": None,
            "banque": lightspeed_banque,
            "ecart": None,
            "ecart_pct": None,
            "statut": "NON_RAPPROCHABLE",
            "commentaire": "Virements agrégés, non rapprochables par transaction.",
        },
        {
            "source": "AUTRES",
            "attendu": None,
            "banque": autres_banque,
            "ecart": None,
            "ecart_pct": None,
            "statut": "INFORMATIF",
            "commentaire": "Autres crédits (pluxee, edenred, etc.).",
        },
    ]

    avertissements = []
    if not caisse:
        avertissements.append("Rapport de caisse manquant.")
    if not banque:
        avertissements.append("Relevé bancaire manquant.")
    if not obypay or obypay.get("total_ttc") is None:
        avertissements.append("Export Obypay manquant.")
    if lightspeed_banque > 0:
        avertissements.append("Source LIGHTSPEED non rapprochable.")
    if obypay_attendu > 0 and abs(ecart_obypay) / obypay_attendu > seuil_ecart_pct:
        avertissements.append("Décalage de versement Obypay supérieur au seuil configuré.")

    return {
        "tva_collectee_caisse": tva_collectee_caisse,
        "tva_collectee_catering": tva_collectee_catering,
        "tva_collectee": tva_collectee,
        "tva_deductible": tva_deductible,
        "tva_a_decaisser": tva_a_decaisser,
        "credit_tva": credit_tva,
        "total_factures_fournisseurs": total_factures,
        "total_ventes_caisse": total_ventes_caisse,
        "total_ventes_catering": total_ventes_catering,
        "total_ventes_attendu": total_ventes_attendu,
        "total_credits_banque": total_credits_banque,
        "credits_identifies": credits_identifies,
        "ecart_global": ecart_global,
        "ecart_global_pct": ecart_global_pct,
        "statut": statut,
        "sources": sources,
        "avertissements": avertissements,
    }


def _appliquer_mois_disponible(annee: int, mois: int) -> None:
    import streamlit as st

    st.session_state["mail_annee"] = annee
    st.session_state["mail_mois"] = mois - 1


def main() -> None:
    import streamlit as st
    import pandas as pd

    st.set_page_config(page_title="Assistant TVA - Comptabilité", page_icon="🧾", layout="wide")
    st.title("Assistant TVA - Comptabilité")

    if "mail_annee" not in st.session_state:
        a, m = mois_precedent()
        st.session_state["mail_annee"] = a
        st.session_state["mail_mois"] = m - 1
    if "catering" not in st.session_state:
        st.session_state["catering"] = {"present": False, "client": "", "montant_ht": 0.0, "tva": 0.0}

    col1, col2, col3 = st.columns(3)
    with col1:
        etablissement = st.selectbox("Établissement", list(ETABLISSEMENTS), key="mail_etab")
    with col2:
        mois_idx = st.selectbox("Mois", range(12), format_func=lambda i: MOIS[i], key="mail_mois")
    with col3:
        annee = st.selectbox("Année", ANNEES, key="mail_annee")

    mois = mois_idx + 1

    tab_mail, tab_verif = st.tabs(["Mail comptable", "Vérification et rapprochement de TVA"])

    with tab_mail:
        fichiers = trouver_fichiers(etablissement, annee, mois)
        st.markdown("### Pièces détectées")
        for cle, intitule in (("caisse", "Rapport de caisse"), ("banque", "Relevé bancaire"), ("obypay", "Export Obypay")):
            ok = bool(fichiers.get(cle))
            st.write(f"{'✅' if ok else '❌'} {intitule} : {fichiers.get(cle) or 'manquant'}")
        manquants = [k for k in ("caisse", "banque", "obypay") if not fichiers.get(k)]
        if manquants:
            st.warning("Certaines pièces sont manquantes pour ce mois.")
            dernier = dernier_mois_disponible(etablissement)
            if dernier is not None:
                st.button(
                    "Utiliser le dernier mois disponible",
                    key="btn_dernier_mois",
                    on_click=_appliquer_mois_disponible,
                    args=(dernier[0], dernier[1]),
                )
        st.markdown("### Remplacement des pièces")
        up_caisse = st.file_uploader("Caisse", type=["pdf", "xlsx", "xls"], key="up_caisse")
        up_banque = st.file_uploader("Banque", type=["pdf"], key="up_banque")
        up_obypay = st.file_uploader("Obypay", type=["xlsx"], key="up_obypay")

        pieces = dict(fichiers)
        if up_caisse is not None:
            pieces["caisse"] = up_caisse
        if up_banque is not None:
            pieces["banque"] = up_banque
        if up_obypay is not None:
            pieces["obypay"] = up_obypay

        st.markdown("### Catering")
        catering_present = st.checkbox(
            "Facture catering ce mois-ci ?",
            value=st.session_state["catering"].get("present", False),
            key="cat_present",
        )
        client = ""
        montant_ht = 0.0
        tva_cat = 0.0
        if catering_present:
            client = st.text_input("Client / référence", value=st.session_state["catering"].get("client", ""), key="cat_client")
            montant_ht = st.number_input("Montant HT (€)", min_value=0.0, value=float(st.session_state["catering"].get("montant_ht", 0.0) or 0.0), key="cat_ht")
            tva_cat = st.number_input("TVA (€)", min_value=0.0, value=float(st.session_state["catering"].get("tva", 0.0) or 0.0), key="cat_tva")
        st.session_state["catering"] = {
            "present": catering_present,
            "client": client,
            "montant_ht": montant_ht,
            "tva": tva_cat,
        }

        fichiers_mail = {}
        for cle in ("caisse", "banque", "obypay"):
            v = pieces.get(cle)
            if hasattr(v, "name"):
                fichiers_mail[cle] = v.name
            elif isinstance(v, (str, Path)):
                fichiers_mail[cle] = str(v)
            else:
                fichiers_mail[cle] = v

        if st.button("Générer le mail", key="btn_mail"):
            mail = generer_mail_comptable(
                etablissement, annee, mois, fichiers_mail, catering=st.session_state["catering"]
            )
            st.code(mail, language="text")

    with tab_verif:
        use_detected = st.checkbox("Utiliser les fichiers détectés dans ./Comptable", value=True, key="use_detected")
        st.markdown("### Uploads")
        ups_caisse = st.file_uploader("Caisse (multiple)", type=["pdf", "xlsx", "xls"], accept_multiple_files=True, key="v_caisse")
        ups_banque = st.file_uploader("Banque (multiple)", type=["pdf"], accept_multiple_files=True, key="v_banque")
        up_obypay = st.file_uploader("Obypay (optionnel)", type=["xlsx"], key="v_obypay")

        cat = st.session_state.get("catering", {})
        st.caption(f"TVA catering (onglet 1) : {cat.get('tva', 0.0)} € — modifier dans l'onglet Mail comptable.")

        tva_deductible = st.number_input("TVA déductible (€)", min_value=0.0, value=0.0, key="v_tva_ded")
        total_factures = st.number_input("Total des factures fournisseurs (€)", min_value=0.0, value=0.0, key="v_fact")
        st.caption("Informatif")
        seuil_pct = st.number_input("Seuil d'écart (%)", min_value=0, max_value=50, value=20, key="v_seuil")
        seuil = seuil_pct / 100.0

        if st.button("Lancer la vérification", key="btn_verif"):
            try:
                caisses = []
                banques = []
                obypay_res = None

                def _lire(o):
                    if hasattr(o, "read_bytes"):
                        return o.read_bytes(), getattr(o, "name", str(o))
                    if hasattr(o, "getvalue"):
                        return o.getvalue(), getattr(o, "name", "upload")
                    return None, None

                fichiers_det = trouver_fichiers(etablissement, annee, mois) if use_detected else {}
                if use_detected and fichiers_det.get("erreur"):
                    st.warning(fichiers_det["erreur"])
                caisse_files = []
                if use_detected and fichiers_det.get("caisse"):
                    caisse_files.append(fichiers_det["caisse"])
                for uf in (ups_caisse or []):
                    caisse_files.append(uf)
                for cf in caisse_files:
                    data, nom = _lire(cf)
                    if data is None:
                        continue
                    typ = detecter_type_fichier(nom, data)
                    if typ == "caisse_pdf":
                        caisses.append(extraire_caisse_pdf(data))
                    elif typ == "caisse_excel":
                        caisses.append(extraire_caisse_excel(data, nom))
                    elif typ == "obypay_xlsx":
                        if obypay_res is None:
                            obypay_res = extraire_obypay_xlsx(data)
                            st.warning(f"{nom} réaffecté vers Obypay.")
                        else:
                            st.warning(f"Fichier Obypay supplémentaire ignoré : {nom}")
                    elif typ == "banque_pdf":
                        banques.append(extraire_banque_pdf(data))
                        st.warning(f"{nom} réaffecté vers Banque.")
                    else:
                        st.warning(f"Type inconnu pour {nom}")

                banque_files = []
                if use_detected and fichiers_det.get("banque"):
                    banque_files.append(fichiers_det["banque"])
                for uf in (ups_banque or []):
                    banque_files.append(uf)
                for bf in banque_files:
                    data, nom = _lire(bf)
                    if data is None:
                        continue
                    typ = detecter_type_fichier(nom, data)
                    if typ == "banque_pdf":
                        banques.append(extraire_banque_pdf(data))
                    elif typ in ("caisse_pdf", "caisse_excel"):
                        if typ == "caisse_pdf":
                            caisses.append(extraire_caisse_pdf(data))
                        else:
                            caisses.append(extraire_caisse_excel(data, nom))
                        st.warning(f"{nom} réaffecté vers Caisse.")
                    elif typ == "obypay_xlsx":
                        if obypay_res is None:
                            obypay_res = extraire_obypay_xlsx(data)
                        st.warning(f"{nom} réaffecté vers Obypay.")
                    else:
                        st.warning(f"Type inconnu pour {nom}")

                if up_obypay is not None:
                    data, nom = _lire(up_obypay)
                    if data is not None:
                        obypay_res = extraire_obypay_xlsx(data)
                elif use_detected:
                    if fichiers_det.get("obypay") and obypay_res is None:
                        obypay_res = extraire_obypay_xlsx(fichiers_det["obypay"].read_bytes())

                if not caisses and not banques and obypay_res is None:
                    st.info("Aucun fichier chargé.")
                caisse_for_verif = agreger_caisses(caisses) if caisses else None
                banque_for_verif = agreger_banques(banques) if banques else None

                catering_payload = cat if cat.get("present") else None

                res = verifier_rapprochement(
                    caisse_for_verif, banque_for_verif, obypay_res,
                    tva_deductible, total_factures, catering=catering_payload,
                    seuil_ecart_pct=seuil,
                )

                colm1, colm2, colm3 = st.columns(3)
                colm1.metric("TVA collectée", formater_euros(res['tva_collectee']))
                colm2.metric("TVA déductible", f"{res['tva_deductible']:.2f} €")
                tva_dec = res["tva_a_decaisser"]
                if tva_dec is not None and tva_dec < 0:
                    colm3.metric("Crédit de TVA", f"{res['credit_tva']:.2f} €")
                else:
                    colm3.metric("TVA à décaisser", f"{tva_dec or 0:.2f} €")

                st.write(f"Statut global : **{res['statut']}**")
                st.dataframe(pd.DataFrame(res["sources"]))
                st.write(f"TVA collectée caisse : {res['tva_collectee_caisse']}")
                if res.get("tva_collectee_catering"):
                    st.write(f"TVA collectée catering : {res['tva_collectee_catering']}")
                st.caption(f"Total factures fournisseurs (informatif) : {res['total_factures_fournisseurs']:.2f} €")
                for av in res.get("avertissements", []):
                    st.warning(av)

                details = []
                for c in caisses:
                    details.extend(c.get("detail_par_taux") or [])
                if details:
                    st.dataframe(pd.DataFrame(details))
            except Exception as e:
                st.error(f"Erreur lors de la vérification : {e}")



if __name__ == "__main__":
    main()
