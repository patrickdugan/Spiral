import pytest

from conftest import menu_dict
from iob import btc, menu
from iob.errors import Refusal


def test_real_menu(real_menu):
    m = real_menu
    assert m.in_spk.hex() == "00148e0461b1590aed0a723e21ac16f48317cdb2ea96"
    assert m.in_script_sha256 == "58432f41ce2b63d9a8e65e9b5bed183cd2ed12a03fe2b6020cda00235c147283"
    pol = m.gate_policy()
    assert set(pol) == {"network", "min_confirmations", "min_tip_chainwork", "scripts", "pins"}
    assert pol["min_tip_chainwork"] == "000000000000000000000000000000000000000156c4c3c54ad473bac5daf261"
    assert pol["scripts"] == [{"id": "in-address", "script_sha256": m.in_script_sha256, "min_value_sats": 10_000}]


def test_dynamic_payout(real_menu):
    m = real_menu
    assert m.payout_sats(940_000, "p2wpkh") == (948_400, menu.Tier(500_000, 1_010_000))  # 1% over 500k, less 1,000
    assert m.payout_sats(100_000, "p2wpkh")[0] == 99_000
    assert m.payout_sats(10_000, "p2wpkh")[0] == 9_000
    assert m.payout_sats(5_000_000, "p2wpkh")[0] == 2_000_000  # capped
    with pytest.raises(Refusal) as e:
        m.payout_sats(9_999, "p2wpkh")
    assert e.value.reason == "value_below_menu"


def test_dust():
    m = menu.from_dict(menu_dict(**{"out.fee_sats": 9_500}))
    assert m.payout_sats(10_000, "p2wpkh")[0] == 500
    with pytest.raises(Refusal) as e:
        m.payout_sats(10_000, "p2pkh")
    assert e.value.reason == "payout_below_dust"


@pytest.mark.parametrize("path,value", [
    ("in.min_tip_chainwork", "0x0"),
    ("in.min_confirmations", 0),
    ("in.network", "regtest"),
    ("in.address", "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"),
    ("out.tiers", [{"min_value_sats": 20_000, "rate_ppm": 1_000_000}]),
    ("pins.nova_vk_sha256", "00"),
])
def test_bad_menus(path, value):
    with pytest.raises(ValueError):
        menu.from_dict(menu_dict(**{path: value}))


def test_payout_address_on_other_network(real_menu):
    spk = bytes.fromhex("0014c2501cc1c4158b0b940637691f80736954ebc88a")
    assert btc.spk_to_address(spk, real_menu.out_network) == "bcrt1qcfgpeswyzk9sh9qxxa53lqrnd92whjy2qs9rzj"
