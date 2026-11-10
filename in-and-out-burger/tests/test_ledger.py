import pytest

from iob.errors import Refusal
from iob.ledger import Ledger


def test_states_survive_restart(tmp_path):
    path = str(tmp_path / "j.jsonl")
    led = Ledger(path)
    led.check_free("a:0")
    led.reserve("a:0", 1000, "0014")
    led.reserve("b:1", 2000, "0014")
    led.paid("a:0", "ff" * 32)
    led.release("b:1", "wallet empty")
    led.reserve("c:2", 3000, "0014")

    again = Ledger(path)
    with pytest.raises(Refusal) as e:
        again.check_free("a:0")
    assert e.value.reason == "already_served"
    again.check_free("b:1")  # released: may be served again
    with pytest.raises(Refusal) as e:
        again.check_free("c:2")
    assert e.value.reason == "order_in_flight"
    with pytest.raises(Refusal):
        again.reserve("c:2", 3000, "0014")
