from copy import deepcopy
from itertools import product

import pytest

from resource_model import ResourceChannel, ResourceLedger, fee_vector


def test_fee_vector_telescopes():
    amounts = fee_vector(100_000, [(1000, 1000), (2000, 2000)])
    assert amounts == [103302, 102200, 100000]
    assert amounts[0] - amounts[-1] == sum(a-b for a,b in zip(amounts, amounts[1:]))


@pytest.mark.parametrize("direction", [1.0, -1.0, True, False, "1", 0, 2])
def test_direction_type_and_domain_reject_unchanged(direction):
    ledger = ResourceLedger({"channel": ResourceChannel(100, 80)})
    before = deepcopy(ledger)
    with pytest.raises(ValueError):
        ledger.prepare("invalid", [("channel", direction, 10)])
    assert ledger == before


def test_repeated_resource_rejects_without_mutation():
    ledger = ResourceLedger({"channel": ResourceChannel(100, 100)})
    before = deepcopy(ledger)
    with pytest.raises(ValueError):
        ledger.prepare("op", [("channel", 1, 60), ("channel", 1, 60)])
    assert ledger == before


def test_net_zero_is_not_gross_feasible():
    ledger = ResourceLedger({"channel": ResourceChannel(100, 100)})
    before = deepcopy(ledger)
    with pytest.raises(ValueError):
        ledger.prepare("op", [("channel", 1, 60), ("channel", -1, 60)])
    assert ledger == before


def test_concurrent_double_use_rejected_and_abort_releases():
    ledger = ResourceLedger({"channel": ResourceChannel(100, 80)})
    ledger.prepare("first", [("channel", 1, 60)])
    before = deepcopy(ledger)
    with pytest.raises(ValueError):
        ledger.prepare("second", [("channel", 1, 30)])
    assert ledger == before
    ledger.finish("first", False)
    ledger.prepare("second", [("channel", 1, 30)])
    ledger.finish("second", True)
    assert ledger.channels["channel"].left == 50
    with pytest.raises(ValueError):
        ledger.prepare("first", [("channel", 1, 1)])


def test_parallel_channels_are_distinct():
    ledger = ResourceLedger({"one": ResourceChannel(100, 70), "two": ResourceChannel(100, 30)})
    ledger.prepare("op", [("one", 1, 60)])
    ledger.finish("op", True)
    assert ledger.channels["one"].left == 10
    assert ledger.channels["two"].left == 30


def test_exhaustive_small_concurrent_ledgers():
    # 11 balances * 10 amounts * 4 direction pairs = 440 states.
    for left, amount, first, second in product(range(11), range(1, 11), (-1, 1), (-1, 1)):
        ledger = ResourceLedger({"c": ResourceChannel(10, left)})
        for index, direction in enumerate((first, second)):
            before = deepcopy(ledger)
            try:
                ledger.prepare(str(index), [("c", direction, amount)])
            except ValueError:
                assert ledger == before
        for operation in list(ledger.pending):
            ledger.finish(operation, True)
        ledger.channels["c"].validate()
