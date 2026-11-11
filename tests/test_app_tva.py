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