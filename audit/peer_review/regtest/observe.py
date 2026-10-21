"""Read-only fixture collector. DB snapshot is consistent; RPCs are bracketed.
No wallet sync, signing, or broadcasts. Preimages are verified, never published.
"""
from bootstrap import docker, core
from launch import rpc, bark
from fund import cln
from attest import save, DEST
import hashlib
import json
import re
import sys
import time

QUERIES = {
    "subscriptions": "SELECT id,lightning_node_id,status,created_at,updated_at,lowest_incoming_htlc_expiry,accepted_at,payment_hash,invoice,final_amount_msat FROM lightning_htlc_subscription ORDER BY id",
    "subscription_vtxos": "SELECT vtxo_id,lightning_htlc_subscription_id FROM vtxo WHERE lightning_htlc_subscription_id IS NOT NULL ORDER BY vtxo_id",
    "vtxos": "SELECT id,vtxo_id,expiry,oor_spent_txid,spent_in_round,offboarded_in,vtxo_txid,exit_delta,policy_type,amount,anchor_point,spend_state,frontier_at,confirmed_height,onchain_spent_height,onchain_spent_txid FROM vtxo ORDER BY id",
    "pool": "SELECT id,vtxo_id,expiry_height,amount,created_at,spent_at FROM vtxo_pool ORDER BY id",
    "attempts": "SELECT id,payment_hash,amount_msat,final_amount_msat,status,user_fee_sat,lightning_htlc_subscription_id,block_height,created_at,updated_at FROM lightning_payment_attempt ORDER BY id",
    "settlements": "SELECT id,payment_hash,preimage,created_at FROM htlc_settlement ORDER BY id",
    "attempt_vtxos": "SELECT * FROM lightning_payment_attempt_htlc_vtxo ORDER BY lightning_payment_attempt_id,vtxo_id",
    "htlc_vtxos": "SELECT * FROM htlc_vtxo ORDER BY id",
    "rounds": "SELECT id,seq,funding_txid,expiry,swept_at,created_at FROM round ORDER BY id",
    "round_inputs": "SELECT participation_id,vtxo_id FROM round_part_input ORDER BY participation_id,vtxo_id",
    "round_participations": "SELECT id,round_id,created_at,forfeited_at,scheduled_height FROM round_participation ORDER BY id",
    "sweeps": "SELECT id,txid,confirmed_at,abandoned_at,created_at FROM sweep ORDER BY id",
    "nursery": "SELECT id,txid,confirm_target_height,confirmed_at_height,abandoned_at,kind FROM nursery_tx ORDER BY id",
    "virtual_transactions": "SELECT txid,is_funding,encode(signed_tx,'hex') AS signed_tx FROM virtual_transaction ORDER BY txid",
    "captaind_tip": "SELECT * FROM captaind_block ORDER BY height DESC LIMIT 1",
    "watchmand_tip": "SELECT * FROM watchmand_block ORDER BY height DESC LIMIT 1",
}


def database():
    fields = ["'snapshot',txid_current_snapshot()::text"]
    fields += [f"'{name}',(SELECT coalesce(json_agg(r),'[]'::json) FROM ({query}) r)" for name, query in QUERIES.items()]
    sql = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT json_build_object(" + ",".join(fields) + "); COMMIT;"
    raw = docker("exec", "spiral-postgres", "psql", "-h", "127.0.0.1", "-p", "15432", "-U", "postgres", "-d", "spiral_capital", "-Atq", "-v", "ON_ERROR_STOP=1", "-c", sql).stdout
    result = json.loads(raw)
    for row in result["settlements"]:
        actual = hashlib.sha256(bytes.fromhex(row.pop("preimage"))).hexdigest()
        if actual != row["payment_hash"]:
            raise RuntimeError("invalid settlement preimage")
        row["preimage_sha256_verified"] = actual
    return result


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in {"preimage", "payment_preimage"}}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def watchman_claims():
    result = docker('logs', 'spiral-watchmand')
    rows = []
    for line in (result.stdout + result.stderr).splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get('slog_id') in {'ClaimBroadcast', 'ClaimBroadcastFailure', 'PreparingVtxoClaim'}:
            rows.append({k: entry[k] for k in ['timestamp', 'slog_id', 'slog_data']})
    return rows


def transactions(ids):
    result = {}
    for txid in sorted(set(ids)):
        try:
            tx = core('getrawtransaction', txid, 'true')
            if tx.get('blockhash'):
                tx = core('getrawtransaction', txid, 'true', tx['blockhash'])
            previous = {}
            for vin in tx['vin']:
                if 'txid' in vin:
                    parent = core('getrawtransaction', vin['txid'], 'true')
                    previous[f"{vin['txid']}:{vin['vout']}"] = parent['vout'][vin['vout']]
            result[txid] = {'transaction': tx, 'previous_outputs': previous}
        except Exception as exc:
            result[txid] = {'unresolved': str(exc)}
    return result


def snapshot(label, include_client=True):
    if not re.fullmatch(r"[a-z0-9-]+", label):
        raise ValueError("invalid label")
    begin = time.monotonic_ns()
    before = core("getblockchaininfo")
    result = {"label": label, "evidence_class": "regtest-observation", "monotonic_start_ns": begin,
              "captured_unix_ns": time.time_ns(), "chain_before": before, "database": database(),
              "server_wallet": json.loads(rpc("wallet").stdout),
              "cln_funds": cln("server", "listfunds"), "channels": cln("server", "listpeerchannels"),
              "pays": redact(cln("server", "listpays")), "peer_invoices": redact(cln("peer", "listinvoices"))}
    if include_client:
        result.update(bark_balance=json.loads(bark("balance", "--no-sync").stdout),
                      bark_vtxos=json.loads(bark("vtxos", "--all", "--no-sync").stdout),
                      bark_utxos=json.loads(bark("onchain", "utxos", "--no-sync").stdout))
    else:
        result['client_read_gap'] = 'Concurrent Bark CLI reads omitted while send owns the wallet; no client state inferred from missing fields.'
    result['watchman_claims'] = watchman_claims()
    result['mempool'] = core('getrawmempool')
    ids = list(result['mempool'])
    ids += [x['slog_data']['txid'] for x in result['watchman_claims'] if x['slog_id'] == 'ClaimBroadcast']
    ids += [x['txid'] for x in result['database']['virtual_transactions'] if x['is_funding']]
    ids += [x['txid'] for x in result['database']['nursery']]
    ids += [x['funding_txid'] for x in result['channels']['channels']]
    for name in ['initial-funding.json', 'action-quarantine-free-reserve.json']:
        path = DEST / name
        if path.exists():
            record = json.loads(path.read_text())
            txid = record.get('txid') or record.get('result', {}).get('txid')
            if txid:
                ids.append(txid)
    result['transactions'] = transactions(ids)
    result['unspent_outputs'] = {}
    for txid, record in result['transactions'].items():
        if 'transaction' not in record:
            continue
        for output in record['transaction']['vout']:
            result['unspent_outputs'][f"{txid}:{output['n']}"] = core('gettxout', txid, str(output['n']), 'true')
    after = core("getblockchaininfo")
    result.update(chain_after=after, monotonic_end_ns=time.monotonic_ns(),
                  stable_chain_tip=before["bestblockhash"] == after["bestblockhash"])
    save(f"{label}.json", result)
    if not result["stable_chain_tip"]:
        raise RuntimeError("chain changed during collection; preserve record and recollect")
    print(json.dumps({"label": label, "height": after["blocks"], "vtxos": len(result["database"]["vtxos"]),
                      "settlements": len(result["database"]["settlements"])}))
    return result


if __name__ == "__main__":
    snapshot(sys.argv[1])
