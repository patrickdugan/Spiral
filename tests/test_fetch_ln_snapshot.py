import pytest

from scripts.fetch_ln_snapshot import select_member


def test_select_latest_snapshot_member():
    names = ["snapshots/20190120.gml.geo", "snapshots/20230716.gml.geo"]
    assert select_member(names, "latest") == "snapshots/20230716.gml.geo"


def test_select_snapshot_by_basename():
    names = ["snapshots/20190120.gml.geo", "snapshots/20230716.gml.geo"]
    assert select_member(names, "20190120.gml.geo") == "snapshots/20190120.gml.geo"


def test_missing_snapshot_is_rejected():
    with pytest.raises(ValueError, match="not found"):
        select_member(["snapshots/20230716.gml.geo"], "20200101.gml.geo")
