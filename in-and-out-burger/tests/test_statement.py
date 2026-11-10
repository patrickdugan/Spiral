import pytest

from iob import statement
from iob.errors import Refusal


def test_real_m16_statement(real):
    st = statement.parse(real["statement"])
    assert st.sha256 == "cae6068f7ad8c4891cb3220702a88b0bc3df54013f45e65df11a9ced531bc869"
    assert st.magic == b"NHC1" and st.k == 1 and st.steps == 975_072
    assert st.start.height == 0 and st.start.hash_display == statement.GENESIS_HASH["mainnet"]
    assert st.tip.height == 975_072
    assert st.tip.hash_display == "000000000000000000013ec209c5510205d35f80f657c20ef1ea16f73f6ff792"
    assert st.tip.chainwork == 0x156C4C3C54AD473BAC5DAF261  # Core getblockheader at 975,072
    assert st.nova_vk_sha256.hex() == "6aa50d09397c51d0b89d78b3a918d3fe0962251225c8b6ca91e83199a4e6da1d"
    p = st.payment
    assert p.segments == 2 and p.block_height == 975_067 and p.confirmations == 6
    assert p.block_hash_display == "000000000000000000017809af97fdd5530149e411b2ab091db4f405e355fe22"
    assert p.outpoint == "a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045:0"
    assert p.value_sats == 940_000 and p.script_len == 22
    assert p.script_sha256.hex() == "58432f41ce2b63d9a8e65e9b5bed183cd2ed12a03fe2b6020cda00235c147283"


def test_refusals(real):
    raw = real["statement"]
    cases = {
        "no_payment_record": raw[: statement.CHAIN_BYTES],
        "statement_length": raw[:-1],
        "payment_record_magic": raw[: statement.CHAIN_BYTES] + b"PAY2" + raw[statement.CHAIN_BYTES + 4 :],
        # a nonzero byte above the height's u32 in zn
        "statement_state_encoding": raw[: 12 + statement.STATE_BYTES + 8] + b"\x01" + raw[12 + statement.STATE_BYTES + 9 :],
        # confirmations 7 under the same tip
        "statement_inconsistent": raw[: statement.CHAIN_BYTES + 44] + b"\x07" + raw[statement.CHAIN_BYTES + 45 :],
    }
    for reason, bad in cases.items():
        with pytest.raises(Refusal) as e:
            statement.parse(bad)
        assert e.value.reason == reason
