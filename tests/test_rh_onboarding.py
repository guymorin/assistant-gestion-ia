import json
from pathlib import Path

import rh.onboarding as onboarding


def sample_data(**overrides):
    data = dict(onboarding.CHAMPS_DEFAUT)
    data.update(
        {
            "civilite": "Mme",
            "prenom": "Alice",
            "nom": "Martin",
            "etablissement": "HEE-REP-93100",
            "adresse": "1 rue Test",
            "duree_hebdo": 35.0,
            "salaire_brut_mensuel": 1801.8,
            "taux_horaire_brut": 11.88,
        }
    )
    data.update(overrides)
    return data


def test_creer_dossier_salarie_ecrit_config(tmp_path):
    data = sample_data()
    ok, msg = onboarding.creer_dossier_salarie(data, base_paths={"HEE-REP-93100": str(tmp_path)})

    assert ok is True
    dossier = tmp_path / "Martin_Alice"
    assert Path(msg) == dossier
    config_path = dossier / ".config"
    assert config_path.is_file()

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["prenom"] == "Alice"
    assert saved["nom"] == "Martin"
    assert saved["etablissement"] == "HEE-REP-93100"
    assert saved["adresse"] == "1 rue Test"


def test_charger_config_salarie_retourne_donnees(tmp_path):
    data = sample_data(prenom="Bob", nom="Durand")
    dossier = tmp_path / "DURAND_Bob"
    dossier.mkdir()
    (dossier / ".config").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    charge = onboarding.charger_config_salarie(dossier)

    assert charge is not None
    assert charge["prenom"] == "Bob"
    assert charge["nom"] == "Durand"
    # fusion avec défauts pour champs manquants
    for k in onboarding.CHAMPS_DEFAUT:
        assert k in charge


def test_lister_dossiers_salaries_avec_config(tmp_path):
    (tmp_path / "A").mkdir()
    (tmp_path / "A" / ".config").write_text(json.dumps(sample_data(nom="A")), encoding="utf-8")
    (tmp_path / "B").mkdir()  # sans config
    (tmp_path / "C").mkdir()
    (tmp_path / "C" / ".config").write_text("pas du json", encoding="utf-8")

    items = onboarding.lister_dossiers_salaries_avec_config(tmp_path)

    assert [p.name for p in items] == ["A"]
