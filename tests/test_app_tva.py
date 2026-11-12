def test_import_app_tva():
    import app_tva

    assert app_tva.COMPTABLE_DIR == "./Comptable"


import app_tva


def test_normaliser_montant_simple():
    assert app_tva.normaliser_montant("2 193,71") == 2193.71


def test_normaliser_montant_point_milliers():
    assert app_tva.normaliser_montant("1.234,56") == 1234.56


def test_normaliser_montant_sans_separateur():
    assert app_tva.normaliser_montant("1234,56") == 1234.56


def test_normaliser_montant_point_decimal():
    assert app_tva.normaliser_montant("1 234.56") == 1234.56


def test_normaliser_montant_none():
    assert app_tva.normaliser_montant(None) is None


def test_normaliser_montant_vide():
    assert app_tva.normaliser_montant("") is None


def test_normaliser_montant_invalide():
    assert app_tva.normaliser_montant("abc") is None


CAISSE_PDF_TEXTE = """Généré par Hee Korean Chef

HEE REPUBLIQUE
5 Rue de la République
93100 Montreuil

Résumé fiscal 1 septembre 2026 - 30 septembre 2026
A. Résumé

Total des ventes                                                                                              27 542,50
Paiements attendus                                                                                            27 542,50

B. Taxes

TVA 10%
    Montant hors-taxe                                                                                         17 670,09
    Taxe                                                                                                       1 765,41
    Montant taxe comprise                                                                                     19 435,50
TVA 5.5%
    Montant hors-taxe                                                                                          7 637,87
    Taxe                                                                                                        420,13
    Montant taxe comprise                                                                                      8 058,00
TVA 20%
    Montant hors-taxe                                                                                            40,83
    Taxe                                                                                                           8,17
    Montant taxe comprise                                                                                        49,00
Total
    Montant hors-taxe                                                                                         25 348,79
    Taxe                                                                                                       2 193,71
    Montant taxe comprise                                                                                     27 542,50

C. Ventes

Total des ventes                                                                                             27 542,50
"""


class _FakePage:
    def __init__(self, texte):
        self._texte = texte

    def extract_text(self):
        return self._texte


class _FakeReader:
    def __init__(self, texte):
        self.pages = [_FakePage(texte)]


def test_extraire_caisse_pdf_ok():
    def factory(contenu):
        return _FakeReader(CAISSE_PDF_TEXTE)

    res = app_tva.extraire_caisse_pdf(b"dummy", reader_factory=factory)
    assert res["total_ventes"] == 27542.50
    assert res["tva_collectee"] == 2193.71
    assert res["statut"] != "incomplet"


def test_extraire_caisse_pdf_illisible():
    def factory(contenu):
        raise ValueError("boom")

    res = app_tva.extraire_caisse_pdf(b"dummy", reader_factory=factory)
    assert res["total_ventes"] is None
    assert res["tva_collectee"] is None
    assert res["statut"] == "incomplet"


def test_extraire_caisse_pdf_detail_par_taux():
    res = app_tva.extraire_caisse_pdf(
        b"dummy", reader_factory=lambda _: _FakeReader(CAISSE_PDF_TEXTE)
    )
    assert res["detail_par_taux"] == [
        {"taux": 10.0, "ht": 17670.09, "tva": 1765.41, "ttc": 19435.50},
        {"taux": 5.5, "ht": 7637.87, "tva": 420.13, "ttc": 8058.00},
        {"taux": 20.0, "ht": 40.83, "tva": 8.17, "ttc": 49.00},
    ]


def test_extraire_caisse_pdf_prend_le_dernier_total():
    texte = CAISSE_PDF_TEXTE.replace(
        "TVA 5.5%",
        "Total\nMontant hors-taxe 0,00\nTaxe 111,11\nMontant taxe comprise 0,00\nTVA 5.5%",
    )
    res = app_tva.extraire_caisse_pdf(
        b"dummy", reader_factory=lambda _: _FakeReader(texte)
    )
    assert res["tva_collectee"] == 2193.71


import pandas as pd

ROWS_CAISSE = [
    ["Résumé", None],
    ["Total des ventes", "27 542,50"],
    ["Taxes", None],
    ["TVA 10%", None],
    ["Montant hors-taxe", "17 670,09"],
    ["Taxe", "1 765,41"],
    ["Montant taxe comprise", "19 435,50"],
    ["TVA 5.5%", None],
    ["Montant hors-taxe", "7 637,87"],
    ["Taxe", "420,13"],
    ["Montant taxe comprise", "8 058,00"],
    ["TVA 20%", None],
    ["Montant hors-taxe", "40,83"],
    ["Taxe", "8,17"],
    ["Montant taxe comprise", "49,00"],
    ["Total", None],
    ["Montant hors-taxe", "25 348,79"],
    ["Taxe", "2 193,71"],
    ["Montant taxe comprise", "27 542,50"],
    ["C. Ventes", None],
    ["Total des ventes", "27 542,50"],
]


def test_extraire_caisse_excel():
    df = pd.DataFrame(ROWS_CAISSE)
    res = app_tva.extraire_caisse_excel(
        b"dummy", nom="caisse.xlsx", reader_factory=lambda *_: df
    )
    assert res["total_ventes"] == 27542.50
    assert res["tva_collectee"] == 2193.71
    assert len(res["detail_par_taux"]) == 3


def test_extraire_caisse_excel_illisible():
    def factory(*_):
        raise ValueError("boom")

    res = app_tva.extraire_caisse_excel(
        b"dummy", nom="caisse.xlsx", reader_factory=factory
    )
    assert res["statut"] == "incomplet"
    assert res["total_ventes"] is None


ROWS_OBYPAY = [
    ["NUMÉRO", "TRANSACTION", "DATE", "PRIX TTC AVANT REMISE",
     "PRIX TTC APRES REMISE", "MOYEN PAYMENT 1 TTC", "STATUT CAISSE"],
    ["AVEC PAIEMENT", None, None, None, None, None, None],
    ["AJU4SGdnnX", "t1", "46266", "27", "27", "27", "Acceptée"],
    ["xiYA38SD6E", "t2", "46266", "14", "14", "14", "Acceptée"],
    ["tCbudaXFX1", "t3", "46266", "22.5", "22.5", "22.5", "Acceptée"],
    ["SANS PAIEMENT", None, None, None, None, None, None],
    ["PRODUIT HORS PAIEMENT", None, None, None, None, "999", None],
]


def test_extraire_obypay_xlsx():
    feuilles = {"Transactions": pd.DataFrame(ROWS_OBYPAY)}
    res = app_tva.extraire_obypay_xlsx(
        b"dummy", reader_factory=lambda *_: feuilles
    )
    assert res["total_ttc"] == 63.5
    assert res["nb_transactions"] == 3
    assert res["statut"] == "ok"


def test_extraire_obypay_xlsx_sans_entete():
    feuilles = {"Feuille": pd.DataFrame([["a", "b"], ["1", "2"]])}
    res = app_tva.extraire_obypay_xlsx(
        b"dummy", reader_factory=lambda *_: feuilles
    )
    assert res["statut"] == "incomplet"


def test_extraire_obypay_xlsx_premiere_feuille_seulement():
    autre = [list(rangee) for rangee in ROWS_OBYPAY]
    autre[2] = ["ZZZZZZZZZ9", "t4", "46266", "100", "100", "100", "Acceptée"]
    feuilles = {
        "Transactions": pd.DataFrame(ROWS_OBYPAY),
        "Copie": pd.DataFrame(autre),
    }
    res = app_tva.extraire_obypay_xlsx(
        b"dummy", reader_factory=lambda *_: feuilles
    )
    assert res["total_ttc"] == 63.5
    assert res["nb_transactions"] == 3


def test_extraire_texte_pdf_reader_factory():
    texte = app_tva.extraire_texte_pdf(
        b"dummy", reader_factory=lambda _: _FakeReader("abc")
    )
    assert "abc" in texte


def test_extraire_texte_pdf_ne_leve_pas():
    def factory(_):
        raise ValueError("boom")

    assert app_tva.extraire_texte_pdf(b"dummy", reader_factory=factory) == ""


def test_detecter_type_texte_caisse():
    texte = "Résumé fiscal\nTotal des ventes 27 542,50"
    assert app_tva.detecter_type_depuis_texte_pdf(texte) == "caisse_pdf"


def test_detecter_type_texte_banque():
    texte = "RELEVE DE COMPTE\nTOTAUX 19 605,34 42 537,94"
    assert app_tva.detecter_type_depuis_texte_pdf(texte) == "banque_pdf"


def test_detecter_type_texte_caisse_prioritaire():
    texte = "Résumé fiscal\nTotal des ventes 27 542,50\nTOTAUX 1,00 2,00"
    assert app_tva.detecter_type_depuis_texte_pdf(texte) == "caisse_pdf"


def test_detecter_type_feuilles_obypay():
    feuilles = {"F": pd.DataFrame([["NUMÉRO", "TRANSACTION", "DATE"]])}
    assert app_tva.detecter_type_depuis_feuilles(feuilles) == "obypay_xlsx"


def test_detecter_type_feuilles_caisse():
    feuilles = {"F": pd.DataFrame([["Résumé"], ["Taxes"]])}
    assert app_tva.detecter_type_depuis_feuilles(feuilles) == "caisse_excel"


def test_detecter_type_inconnu():
    assert app_tva.detecter_type_depuis_texte_pdf("bonjour") == "inconnu"


def test_detecter_type_fichier_pdf_et_excel():
    assert app_tva.detecter_type_fichier(
        "banque.pdf", b"x", texte_factory=lambda _: "RELEVE DE COMPTE TOTAUX 1,00 2,00"
    ) == "banque_pdf"
    assert app_tva.detecter_type_fichier(
        "caisse.xlsx",
        b"x",
        feuilles_factory=lambda *_: {"F": pd.DataFrame([["Résumé"], ["Taxes"]])},
    ) == "caisse_excel"
    assert app_tva.detecter_type_fichier("notes.txt", b"x") == "inconnu"


def test_detecter_type_fichier_ne_leve_pas():
    def texte_factory(_):
        raise ValueError("boom")

    def feuilles_factory(*_):
        raise ValueError("boom")

    assert app_tva.detecter_type_fichier(
        "banque.pdf", b"x", texte_factory=texte_factory
    ) == "inconnu"
    assert app_tva.detecter_type_fichier(
        "caisse.xlsx", b"x", feuilles_factory=feuilles_factory
    ) == "inconnu"


TEXTE_CIC = """\
01/09/2026 01/09/2026 VIR LIGHTSPEED NETHERLANDS B 200,41
03/09/2026 03/09/2026 VIR 2BEVENTS 4.081,00
2BEVENTS
OBYPAY 20260824 20260830
10/09/2026 10/09/2026 VIR LIGHTSPEED NETHERLANDS B 336,26
10/09/2026 10/09/2026 VIR 2BEVENTS 3.897,00
OBYPAY 20260901 20260906
30/09/2026 30/09/2026 VIR SALAIRE EMPLOYE 1.451,76
Total des mouvements 21.170,25 23.960,43
Réf : 009 SOLDE CREDITEUR AU 30/09/2026 26.288,71
"""

TEXTE_LCL = """\
01.09     VIR SEPA LIGHTSPEED NETHERLANDS B      01.09.26      637,54
03.09     VIR SEPA 2BEVENTS                       03.09.26    3 874,30
          LIBELLE:Obypay 20260824 20260830
10.09     VIR SEPA LIGHTSPEED NETHERLANDS B      10.09.26      492,64
10.09     VIR SEPA 2BEVENTS                       10.09.26    3 124,60
          LIBELLE:Obypay 20260901 20260906
30.09     VIR SEPA LIGHTSPEED NETHERLANDS B      30.09.26      796,05
TOTAUX 19 605,34 42 537,94
30.09     SOLDE EN EUROS 22 932,60
"""


def test_extraire_banque_cic():
    res = app_tva.extraire_banque_pdf(b"dummy", texte_factory=lambda _: TEXTE_CIC)
    assert res["banque"] == "CIC"
    assert res["total_debits"] == 21170.25
    assert res["total_credits"] == 23960.43
    assert res["solde_final"] == 26288.71
    assert res["credits_par_source"]["OBYPAY"] == 7978.00
    assert res["credits_par_source"]["LIGHTSPEED"] == 536.67
    assert res["versements_obypay"][0]["montant"] == 4081.00
    assert res["versements_obypay"][0]["periode_debut"] == "2026-08-24"


def test_extraire_banque_lcl_montants_a_milliers():
    res = app_tva.extraire_banque_pdf(b"dummy", texte_factory=lambda _: TEXTE_LCL)
    assert res["banque"] == "LCL"
    assert res["total_debits"] == 19605.34
    assert res["total_credits"] == 42537.94
    assert res["solde_final"] == 22932.60
    assert res["credits_par_source"]["OBYPAY"] == 6998.90
    assert res["credits_par_source"]["LIGHTSPEED"] == 1926.23
    assert res["versements_obypay"][0]["periode_debut"] == "2026-08-24"


def test_extraire_banque_ignore_les_vir_de_debit():
    texte = (
        "30/09/2026 30/09/2026 VIR SALAIRE EMPLOYE 1.451,76\n"
        "Total des mouvements 1.451,76 0,00\n"
    )
    res = app_tva.extraire_banque_pdf(b"dummy", texte_factory=lambda _: texte)
    assert res["credits_par_source"].get("OBYPAY", 0) == 0
    assert res["credits_par_source"].get("LIGHTSPEED", 0) == 0


def test_extraire_banque_illisible():
    res = app_tva.extraire_banque_pdf(b"dummy", texte_factory=lambda _: "")
    assert res["statut"] == "incomplet"
