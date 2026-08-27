import pytest

from spiral_ln.public_topology_analysis import cluster_interval


def test_cluster_interval_uses_topologies_not_atomic_rows():
    values = [
        ("first", "A", 0.01),
        ("first", "A", 0.03),
        ("first", "B", 0.05),
        ("first", "B", 0.07),
    ]
    interval = cluster_interval(values)
    assert interval["cluster_n"] == 2
    assert interval["atomic_n"] == 4
    assert interval["cluster_means"] == pytest.approx([0.02, 0.06])
    assert interval["mean"] == pytest.approx(0.04)
