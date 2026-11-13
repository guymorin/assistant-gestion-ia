# tests/test_shared_info.py
from shared.info import InfoItem, collect_footer_infos, normalize_info_value


def test_normalize_info_value_handles_none_and_bool():
    assert normalize_info_value(None) == "indisponible"
    assert normalize_info_value(True) == "oui"
    assert normalize_info_value(False) == "non"
    assert normalize_info_value(12) == "12"


def test_collect_footer_infos_preserves_order_and_items():
    a = InfoItem("a", "A", "1", "aide A")
    b = InfoItem("b", "B", "indisponible", "aide B", niveau="warning")
    assert collect_footer_infos([a], [b]) == [a, b]
    assert b.niveau == "warning"
