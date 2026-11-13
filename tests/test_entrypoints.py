# tests/test_entrypoints.py
from pathlib import Path


def test_scripts_target_portal():
    assert "app_portail.py" in Path("1-RH").read_text()
    assert "app_portail.py" in Path("2-Finances").read_text()
