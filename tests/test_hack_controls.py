import json
from pathlib import Path

from spiral_ln import hack_controls

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "configs" / "crypto_hack_corpus.json"
CATALOG = ROOT / "configs" / "software_catalog.json"


def _payload(tmp_path):
    return hack_controls.run(CORPUS, CATALOG, tmp_path, seed=1)


def test_every_chain_is_broken_by_at_least_one_control(tmp_path):
    payload = _payload(tmp_path)
    rows = payload["rows"]
    assert len(rows) == 9
    for r in rows:
        assert r["baseline_success"] is True
        assert r["broken_by"], f"{r['id']} broken by nothing"


def test_clear_signing_breaks_blind_signing_but_not_pure_credential_theft(tmp_path):
    rows = {r["id"]: r for r in _payload(tmp_path)["rows"]}
    # the signer-manipulation (blind-signing) cluster is broken by clear-signing
    for hid in ("bybit", "wazirx", "radiant", "dmm", "ledger_connectkit", "bitpay"):
        assert rows[hid]["broke_chain"]["clear_signing"] is True
    # pure credential-theft chains have no signer to clear-sign
    for hid in ("ronin", "coincheck", "twitter_2020"):
        assert rows[hid]["broke_chain"]["clear_signing"] is False


def test_device_integrity_breaks_device_deception_not_social(tmp_path):
    rows = {r["id"]: r for r in _payload(tmp_path)["rows"]}
    assert rows["bybit"]["broke_chain"]["device_integrity_patch"] is True      # tampered front-end
    assert rows["bitpay"]["broke_chain"]["device_integrity_patch"] is False    # impersonation email, no device


def test_anti_phishing_breaks_the_whole_sample(tmp_path):
    payload = _payload(tmp_path)
    eff = payload["summary"]["control_effect"]["phishing_resistant_entry"]
    assert eff["chains_broken"] == payload["summary"]["chains"] == 9


def test_sweep_is_deterministic_and_reported(tmp_path):
    a = hack_controls.run(CORPUS, CATALOG, tmp_path / "a")
    b = hack_controls.run(CORPUS, CATALOG, tmp_path / "b")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    report = (tmp_path / "a" / "report.md").read_text(encoding="utf-8")
    assert "defensive ROI" in report and "clear-signing" in report
