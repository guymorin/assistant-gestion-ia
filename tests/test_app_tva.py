def test_import_app_tva():
    import app_tva

    assert app_tva.COMPTABLE_DIR == "./Comptable"
