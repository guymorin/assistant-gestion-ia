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