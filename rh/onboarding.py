from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

RH_ONBOARDING_DIR = Path(__file__).resolve().parent.parent / "RH-Onboarding"

CHAMPS_DEFAUT: dict[str, Any] = {
    "civilite": "M.",
    "prenom": "",
    "nom": "",
    "adresse": "",
    "date_naissance": "",
    "lieu_naissance": "",
    "nationalite": "",
    "numero_secu": "",
    "type_emploi": "ÉQUIPIER POLYVALENT, Niveau 1, Échelon A (coeff. 120)",
    "date_debut_contrat": "",
    "heure_debut": "09:00",
    "duree_hebdo": 35.0,
    "horaires": "",
    "salaire_brut_mensuel": 0.0,
    "taux_horaire_brut": 0.0,
}


def etablissements_disponibles(base_dir: Path | None = None) -> list[str]:
    base = base_dir or RH_ONBOARDING_DIR
    if not base.is_dir():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir()])


def lister_modeles(etablissement: str, base_dir: Path | None = None) -> list[Path]:
    base = (base_dir or RH_ONBOARDING_DIR) / etablissement
    if not base.is_dir():
        return []
    fichiers = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() in {".ott", ".odt", ".pdf"}]
    return sorted(fichiers, key=lambda p: p.name.lower())


def _to_float(val: Any) -> float:
    try:
        if val is None or val == "":
            return 0.0
        if isinstance(val, str):
            val = val.replace("\u202f", "").replace(" ", "").replace(",", ".")
        return float(val)
    except Exception:
        return 0.0


def heures_mensuelles(duree_hebdo: float) -> float:
    h = _to_float(duree_hebdo)
    if h <= 0:
        return 0.0
    return h * 52.0 / 12.0


def calculer_salaire_depuis_taux(duree_hebdo: float, taux_horaire: float) -> float:
    base = heures_mensuelles(duree_hebdo)
    taux = _to_float(taux_horaire)
    if base <= 0 or taux <= 0:
        return 0.0
    return round(base * taux, 2)


def calculer_taux_depuis_salaire(duree_hebdo: float, salaire_mensuel: float) -> float:
    base = heures_mensuelles(duree_hebdo)
    salaire = _to_float(salaire_mensuel)
    if base <= 0 or salaire <= 0:
        return 0.0
    return round(salaire / base, 2)


def _fmt_date(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return s


def _fmt_montant(val: float) -> str:
    v = _to_float(val)
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return s


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def nom_complet(data: dict[str, Any]) -> str:
    civ = (data.get("civilite") or "").strip()
    prenom = (data.get("prenom") or "").strip()
    nom = (data.get("nom") or "").strip().upper()
    parts = [p for p in [civ, prenom, nom] if p]
    return " ".join(parts).strip()


def construire_mapping(data: dict[str, Any]) -> dict[str, str]:
    prenom = (data.get("prenom") or "").strip()
    nom = (data.get("nom") or "").strip().upper()
    civilite = (data.get("civilite") or "M.").strip()
    adresse = (data.get("adresse") or "").strip()
    naissance = _fmt_date(data.get("date_naissance"))
    lieu_naissance = (data.get("lieu_naissance") or "").strip()
    nationalite = (data.get("nationalite") or "").strip()
    secu = (data.get("numero_secu") or "").strip()
    emploi = (data.get("type_emploi") or "").strip()
    debut = _fmt_date(data.get("date_debut_contrat"))
    heure = (data.get("heure_debut") or "").strip()
    duree = _to_float(data.get("duree_hebdo"))
    horaires = (data.get("horaires") or "").strip()
    salaire = _to_float(data.get("salaire_brut_mensuel"))
    taux = _to_float(data.get("taux_horaire_brut"))
    etab = (data.get("etablissement") or "").strip()

    naissance_complete = naissance
    if lieu_naissance:
        naissance_complete = f"{naissance} à {lieu_naissance}" if naissance else lieu_naissance

    mapping = {
        # identite courante
        "M. Prénom NOM": f"{civilite} {prenom} {nom}".strip(),
        "Mme Prénom NOM": f"{civilite} {prenom} {nom}".strip(),
        "Prénom NOM": f"{prenom} {nom}".strip(),
        "NOM Prénom": f"{nom} {prenom}".strip(),
        # coordonnees / perso
        "1 rue centrale 93100 MONTREUIL": adresse,
        "01/01/2000": naissance or "01/01/2000",
        "sud-coréenne": nationalite or "sud-coréenne",
        "01000000000": secu or "01000000000",
        # emploi / contrat
        "ÉQUIPIER POLYVALENT, Niveau 1, Échelon A (coeff. 120)": emploi or "ÉQUIPIER POLYVALENT, Niveau 1, Échelon A (coeff. 120)",
        "01/02/2026": debut or "01/02/2026",
        "35 heures par semaine": f"{duree:g} heures par semaine" if duree > 0 else "35 heures par semaine",
    }
    # champs contextuels enrichis
    mapping["__prenom__"] = prenom
    mapping["__nom__"] = nom
    mapping["__civilite__"] = civilite
    mapping["__adresse__"] = adresse
    mapping["__naissance__"] = naissance
    mapping["__lieu_naissance__"] = lieu_naissance
    mapping["__naissance_complete__"] = naissance_complete
    mapping["__nationalite__"] = nationalite
    mapping["__secu__"] = secu
    mapping["__emploi__"] = emploi
    mapping["__debut__"] = debut
    mapping["__heure_debut__"] = heure or "09:00"
    mapping["__duree__"] = f"{duree:g}" if duree > 0 else ""
    mapping["__horaires__"] = horaires
    mapping["__salaire__"] = _fmt_montant(salaire) if salaire > 0 else ""
    mapping["__taux__"] = _fmt_montant(taux) if taux > 0 else ""
    mapping["__etablissement__"] = etab
    return mapping


def _remplacer_user_fields(xml: str, data: dict[str, Any]) -> str:
    mapping = construire_mapping(data)
    prenom = (data.get("prenom") or "").strip()
    nom = (data.get("nom") or "").strip().upper()
    civilite = (data.get("civilite") or "M.").strip()
    nom_prenom = f"{prenom} {nom}".strip()
    identite = f"{civilite} {prenom} {nom}".strip()
    adresse = (data.get("adresse") or "").strip()
    naissance = mapping.get("__naissance__") or ""
    lieu_naissance = mapping.get("__lieu_naissance__") or ""
    naissance_complete = mapping.get("__naissance_complete__") or ""
    nationalite = mapping.get("__nationalite__") or ""
    secu = mapping.get("__secu__") or ""
    emploi = mapping.get("__emploi__") or ""
    debut = mapping.get("__debut__") or ""
    duree = mapping.get("__duree__") or ""
    horaires = mapping.get("__horaires__") or ""
    salaire = mapping.get("__salaire__") or ""
    taux = mapping.get("__taux__") or ""
    etab = mapping.get("__etablissement__") or ""

    def set_field(content: str, field_name: str, value: str) -> str:
        if not value:
            return content
        esc = _xml_escape(value)
        # office:string-value="..." ... text:name="field_name" (value before name)
        pattern_a = re.compile(r'(office:string-value=")[^"]*("(?=[^>]*\btext:name="' + re.escape(field_name) + r'"))')
        content = pattern_a.sub(lambda m: m.group(1) + esc + m.group(2), content)
        # text:name="field_name" ... office:string-value="..." (name before value)
        pattern_b = re.compile(r'(\btext:name="' + re.escape(field_name) + r'"(?=[^>]*\boffice:string-value=")[^>]*\boffice:string-value=")[^"]*(")')
        content = pattern_b.sub(lambda m: m.group(1) + esc + m.group(2), content)
        # displayed value <text:user-field-get ... text:name="field_name">...</text:user-field-get>
        pattern_c = re.compile(r'(<text:user-field-get\b[^>]*\btext:name="' + re.escape(field_name) + r'"[^>]*>)(.*?)(</text:user-field-get>)', re.DOTALL)
        content = pattern_c.sub(lambda m: m.group(1) + esc + m.group(3), content)
        return content

    # valeurs explicites par noms probables
    exact_fields = {
        "SalaireSalarie": (salaire + " €") if salaire else "",
        "SalaireTauxHoraireBrutSalarie": (taux + " €") if taux else "",
        "TauxHoraireBrutSalarie": (taux + " €") if taux else "",
        "DureeTravailSalarie": (f"{duree} heures par semaine") if duree else "",
        "DureeHebdomadaire": (f"{duree} heures par semaine") if duree else "",
        "PosteSalarie": emploi,
        "EmploiSalarie": emploi,
        "TypeEmploi": emploi,
        "DateDebutContrat": debut,
        "DateDebutSalarie": debut,
        "DateDebut": debut,
        "HeureDebut": (data.get("heure_debut") or "").strip(),
        "HorairesSalarie": horaires,
        "Horaires": horaires,
        "NomPrenomSalarie": identite or nom_prenom,
        "NomPrenom": identite or nom_prenom,
        "NomPren": identite or nom_prenom,
        "PrenomNomSalarie": f"{prenom} {nom}".strip(),
        "PrenomNom": f"{prenom} {nom}".strip(),
        "NomSalarie": nom,
        "PrenomSalarie": prenom,
        "CiviliteSalarie": civilite,
        "AdresseSalarie": adresse,
        "Adresse": adresse,
        "DateNaissanceSalarie": naissance,
        "DateNaissance": naissance,
        "NaissanceSalarie": naissance_complete or naissance,
        "LieuNaissanceSalarie": lieu_naissance,
        "LieuNaissance": lieu_naissance,
        "NationaliteSalarie": nationalite,
        "Nationalite": nationalite,
        "NumeroSecuriteSocialeSalarie": secu,
        "NumeroSecuriteSociale": secu,
        "NumeroSecuSalarie": secu,
        "NumeroSecu": secu,
        "NumeroSSSalarie": secu,
        "NSS": secu,
        "Etablissement": etab,
    }
    for fname, fval in exact_fields.items():
        xml = set_field(xml, fname, fval)

    # heuristique par nom de champ (user-field-decl/get quelconques)
    rules = [
        (re.compile(r"salaire(?!.*taux)|montant.*brut|brut.*mensuel", re.I), (salaire + " €") if salaire else ""),
        (re.compile(r"taux", re.I), (taux + " €") if taux else ""),
        (re.compile(r"duree|hebdo", re.I), (f"{duree} heures par semaine") if duree else ""),
        (re.compile(r"emploi|poste|qualification|coeff", re.I), emploi),
        (re.compile(r"debut", re.I), debut),
        (re.compile(r"heure(?!.*hebdo)", re.I), (data.get("heure_debut") or "").strip()),
        (re.compile(r"horaire", re.I), horaires),
        (re.compile(r"adresse", re.I), adresse),
        (re.compile(r"naissance", re.I), naissance_complete or naissance),
        (re.compile(r"national", re.I), nationalite),
        (re.compile(r"secu|securite|nss|numero.?s|\bss\b", re.I), secu),
        (re.compile(r"nom.?prenom|prenom.?nom|identite", re.I), identite or nom_prenom),
        (re.compile(r"civil", re.I), civilite),
        (re.compile(r"prenom", re.I), prenom),
        (re.compile(r"(^|[^a-z])nom([^a-z]|$)|nomsalarie|nomfamille", re.I), nom),
    ]

    # trouver tous les noms de champs présents
    field_names = set(re.findall(r'text:name="([^"]+)"', xml))
    for fname in field_names:
        low = fname.lower()
        if "employeur" in low or "societe" in low or "entreprise" in low or "signature" in low:
            continue
        if fname in exact_fields and exact_fields.get(fname):
            continue
        # éviter d'écraser un champ combiné nom+prenom par nom seul
        if "prenom" in low and "nom" in low:
            if identite or nom_prenom:
                xml = set_field(xml, fname, identite or nom_prenom)
            continue
        for rx, value in rules:
            if not value:
                continue
            if rx.search(fname):
                xml = set_field(xml, fname, value)
                break

    return xml


def _remplacer_texte(xml: str, data: dict[str, Any]) -> str:
    mapping = construire_mapping(data)
    # remplacements explicites fréquents
    pairs = [
        ("M. Prénom NOM", mapping["M. Prénom NOM"]),
        ("Mme Prénom NOM", mapping["Mme Prénom NOM"]),
        ("Prénom NOM", mapping["Prénom NOM"]),
        ("1 rue centrale 93100 MONTREUIL", mapping["1 rue centrale 93100 MONTREUIL"]),
        ("ÉQUIPIER POLYVALENT, Niveau 1, Échelon A (coeff. 120)", mapping["ÉQUIPIER POLYVALENT, Niveau 1, Échelon A (coeff. 120)"]),
        ("35 heures par semaine", mapping["35 heures par semaine"]),
    ]
    # placeholders salaire textuels
    salaire = mapping.get("__salaire__")
    taux = mapping.get("__taux__")
    if salaire:
        pairs.append(("[Indiquer montant, ex: 1 801,80 €]", f"{salaire} €"))
    if taux:
        pairs.append(("[Indiquer taux, ex: 11,88 €]", f"{taux} €"))

    # dates/identité contextuelles (CDI exemples) - faire prudemment
    debut = mapping.get("__debut__")
    naissance = mapping.get("__naissance__")
    nat = mapping.get("__nationalite__")
    secu = mapping.get("__secu__")
    if debut:
        pairs.append(("prendra effet le 01/02/2026", f"prendra effet le {debut}"))
        pairs.append(("soit du 01/02/2026", f"soit du {debut}"))
        pairs.append(("Fait en double exemplaire à MONTREUIL le 01/02/2026", f"Fait en double exemplaire à MONTREUIL le {debut}"))
        # fin période essai indicative +1 mois non calculée ici (prudence), on laisse si non certain
    if naissance:
        pairs.append((f"Né(e) le 01/01/2000", f"Né(e) le {naissance}"))
    if nat:
        pairs.append((f"de nationalité sud-coréenne", f"de nationalité {nat}"))
    if secu:
        pairs.append((f"N° de Sécurité sociale 01000000000", f"N° de Sécurité sociale {secu}"))
        pairs.append(("01000000000", secu))

    for old, new in pairs:
        if old and new and old != new and old in xml:
            xml = xml.replace(old, _xml_escape(new) if ("<" not in old and "&" not in old) else new)
    # version échappée XML pour certains textes
    for old, new in pairs:
        if not old or not new or old == new:
            continue
        old_esc = _xml_escape(old)
        new_esc = _xml_escape(new)
        if old_esc != old and old_esc in xml:
            xml = xml.replace(old_esc, new_esc)
    return xml


def generer_document_rempli(template_path: Path, data: dict[str, Any]) -> tuple[bytes, str]:
    """Génère une copie pré-remplie d'un modèle ODT/OTT. PDF renvoyé tel quel."""
    suffix = template_path.suffix.lower()
    out_name = template_path.name
    if suffix == ".ott":
        out_name = template_path.stem + "-rempli.odt"
    elif suffix == ".odt":
        out_name = template_path.stem + "-rempli.odt"
    else:
        # pdf ou autre : pas de remplissage auto fiable
        return template_path.read_bytes(), out_name

    raw = template_path.read_bytes()
    in_buf = io.BytesIO(raw)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename in ("content.xml", "styles.xml"):
                try:
                    xml = content.decode("utf-8")
                    xml = _remplacer_user_fields(xml, data)
                    xml = _remplacer_texte(xml, data)
                    content = xml.encode("utf-8")
                except Exception:
                    pass
            # adapter mimetype si ott->odt
            if item.filename == "mimetype" and suffix == ".ott":
                content = b"application/vnd.oasis.opendocument.text"
            zout.writestr(item, content)
    return out_buf.getvalue(), out_name


def message_dpae(data: dict[str, Any]) -> str:
    prenom = (data.get("prenom") or "Prénom").strip() or "Prénom"
    nom = (data.get("nom") or "NOM").strip().upper() or "NOM"
    naissance = _fmt_date(data.get("date_naissance")) or "01/01/2002"
    lieu = (data.get("lieu_naissance") or "Ville (Pays)").strip() or "Ville (Pays)"
    nat = (data.get("nationalite") or "Nationalité").strip() or "Nationalité"
    secu = (data.get("numero_secu") or "1 02 34 56 789 123 45").strip() or "1 02 34 56 789 123 45"
    adresse = (data.get("adresse") or "9 rue de la Liberté 75010 Paris").strip() or "9 rue de la Liberté 75010 Paris"
    duree = _to_float(data.get("duree_hebdo"))
    contrat = f"CDI à {duree:g} heures par semaine" if duree > 0 else "CDI à 35 heures par semaine"
    debut = _fmt_date(data.get("date_debut_contrat")) or "06/05/2026"
    heure = (data.get("heure_debut") or "09h00").strip() or "09h00"
    # normaliser affichage heure
    heure_aff = heure.replace(":", "h") if ":" in heure and "h" not in heure else heure
    if len(heure_aff) == 2 and heure_aff.isdigit():
        heure_aff = heure_aff + "h00"
    return (
        "Bonjour,\n\n"
        "Pourriez-vous effectuer la déclaration pour notre nouvel employé svp ?\n\n"
        f"NOM : {nom}\n"
        f"Prénom : {prenom}\n"
        f"Né(e) le : {naissance} à {lieu}\n"
        f"Nationalité : {nat}\n"
        f"N° Sécu : {secu}\n"
        f"Adresse : {adresse}\n"
        f"Contrat : {contrat}\n"
        f"Début le : {debut} à {heure_aff}\n\n"
        "Ci-joint les documents : pièce d'identité (ou titre de séjour) et attestation Ameli.\n\n"
        "En vous remerciant par avance."
    )


def recapitulatif(data: dict[str, Any]) -> str:
    lines = [
        f"Civilité : {data.get('civilite','')}",
        f"Prénom : {data.get('prenom','')}",
        f"NOM : {(data.get('nom') or '').upper()}",
        f"Adresse : {data.get('adresse','')}",
        f"Date de naissance : {_fmt_date(data.get('date_naissance'))}",
        f"Lieu de naissance : {data.get('lieu_naissance','')}",
        f"Nationalité : {data.get('nationalite','')}",
        f"N° Sécurité sociale : {data.get('numero_secu','')}",
        f"Type d'emploi (CCN) : {data.get('type_emploi','')}",
        f"Date de début : {_fmt_date(data.get('date_debut_contrat'))}",
        f"Heure de début : {data.get('heure_debut','')}",
        f"Durée hebdomadaire : {data.get('duree_hebdo','')} h",
        f"Horaires : {data.get('horaires','')}",
        f"Salaire brut mensuel : {_fmt_montant(_to_float(data.get('salaire_brut_mensuel')))} €" if _to_float(data.get('salaire_brut_mensuel')) else "Salaire brut mensuel :",
        f"Taux horaire brut : {_fmt_montant(_to_float(data.get('taux_horaire_brut')))} €" if _to_float(data.get('taux_horaire_brut')) else "Taux horaire brut :",
        f"Établissement : {data.get('etablissement','')}",
    ]
    return "\n".join(lines)
