#!/usr/bin/env python3
"""R-VER-1: oracle-attested DLC margin release with an LP reimbursement, on regtest or Testnet4.

Contract: an inverse BTC/USD position between A (long) and B (short), margin m sat each,
leverage L, entry price P0. Outcomes: down / flat / up, decided by the price the oracle
attests at maturity against thresholds of +/-1 percent; each CET pays the clipped inverse
payoff at the representative price P0(1 -/+ 2 percent).

Funding: one dual-funded taproot output whose internal key is unspendable (NUMS) and whose
leaves are
    outcome j:  multi_a(3, A_j, B_j, S_j)        j in {down, flat, up}
    refund:     and_v(v:multi_a(2, A_r, B_r), older(REFUND_BLOCKS))
S_j = R + e_j P is the oracle's BIP340-style attestation point for outcome j (P the oracle
key, R its announced nonce point, e_j the BIP340 challenge of the outcome message). The
attestation for the realised outcome is the scalar s_j with s_j G = S_j, which completes the
third signature of exactly one CET. A and B use a different key per leaf and sign each CET in
a wallet that holds only that leaf's private key, so a CET can never be completed through
another outcome's leaf. All CETs and the refund are signed BEFORE the funding transaction is
broadcast.

LP reimbursement (architecture D without the BitVM3 game): B's output in every CET pays the
LP. At maturity, after the attestation and before the CET confirms, the LP pays B its
outcome value from its own wallet; the CET then reimburses the LP. Released outputs are
spent again (reuse) and returned to the campaign payer.

Phases are resumable: state lives in <run>/state.json; evidence in <run>/*.json.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

# ----------------------------------------------------------------------------- secp256k1
p_ = 2 ** 256 - 2 ** 32 - 977
n_ = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def padd(P, Q):
    if P is None:
        return Q
    if Q is None:
        return P
    if P[0] == Q[0] and (P[1] + Q[1]) % p_ == 0:
        return None
    if P == Q:
        lam = 3 * P[0] * P[0] * pow(2 * P[1], p_ - 2, p_) % p_
    else:
        lam = (Q[1] - P[1]) * pow(Q[0] - P[0], p_ - 2, p_) % p_
    x = (lam * lam - P[0] - Q[0]) % p_
    return x, (lam * (P[0] - x) - P[1]) % p_


def pmul(k, P=G):
    R = None
    while k:
        if k & 1:
            R = padd(R, P)
        P = padd(P, P)
        k >>= 1
    return R


def xonly(P):
    return P[0].to_bytes(32, "big")


def tagged(tag, msg):
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + msg).digest()


def even_secret(sk):
    """Return (sk', P) with P = sk' G having even y (BIP340 convention)."""
    P = pmul(sk)
    return (sk, P) if P[1] % 2 == 0 else (n_ - sk, pmul(n_ - sk))


def challenge(R, P, msg: bytes):
    return int.from_bytes(tagged("BIP0340/challenge", xonly(R) + xonly(P) + hashlib.sha256(msg).digest()), "big") % n_


def wif(sk: int, testnet=True):
    payload = (b"\xef" if testnet else b"\x80") + sk.to_bytes(32, "big") + b"\x01"
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    num, out = int.from_bytes(raw, "big"), ""
    alpha = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    while num:
        num, r = divmod(num, 58)
        out = alpha[r] + out
    return out


# ----------------------------------------------------------------------------------- PSBT
def _ser_compact(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    return b"\xfe" + n.to_bytes(4, "little")


def _read_compact(b, i):
    x = b[i]
    if x < 0xFD:
        return x, i + 1
    if x == 0xFD:
        return int.from_bytes(b[i + 1:i + 3], "little"), i + 3
    if x == 0xFE:
        return int.from_bytes(b[i + 1:i + 5], "little"), i + 5
    return int.from_bytes(b[i + 1:i + 9], "little"), i + 9


def _read_map(b, i):
    items = []
    while True:
        kl, i = _read_compact(b, i)
        if kl == 0:
            return items, i
        k = b[i:i + kl]; i += kl
        vl, i = _read_compact(b, i)
        v = b[i:i + vl]; i += vl
        items.append((k, v))


def psbt_set_witness_utxo(psbt_b64: str, index: int, amount_sat: int, spk_hex: str) -> str:
    """Insert PSBT_IN_WITNESS_UTXO for an input whose previous transaction the wallets do not
    know yet (the funding transaction is signed but deliberately not broadcast)."""
    b = base64.b64decode(psbt_b64)
    assert b[:5] == b"psbt\xff"
    i = 5
    glob, i = _read_map(b, i)
    unsigned = dict(glob)[b"\x00"]
    # count inputs/outputs of the unsigned tx
    j = 4
    n_in, j = _read_compact(unsigned, j)
    for _ in range(n_in):
        j += 36
        sl, j = _read_compact(unsigned, j)
        j += sl + 4
    n_out, j = _read_compact(unsigned, j)
    ins, outs = [], []
    for _ in range(n_in):
        m, i = _read_map(b, i)
        ins.append(m)
    for _ in range(n_out):
        m, i = _read_map(b, i)
        outs.append(m)
    spk = bytes.fromhex(spk_hex)
    txout = amount_sat.to_bytes(8, "little") + _ser_compact(len(spk)) + spk
    ins[index] = [(k, v) for k, v in ins[index] if k != b"\x01"] + [(b"\x01", txout)]

    def ser(m):
        out = b""
        for k, v in m:
            out += _ser_compact(len(k)) + k + _ser_compact(len(v)) + v
        return out + b"\x00"
    return base64.b64encode(b"psbt\xff" + ser(glob) + b"".join(ser(m) for m in ins) + b"".join(ser(m) for m in outs)).decode()


# ------------------------------------------------------------------------------------ RPC
class Node:
    def __init__(self, cookie: Path, port: int):
        self.cookie, self.port = cookie, port

    def __call__(self, method, params=None, wallet=None):
        auth = self.cookie.read_bytes().strip()
        suffix = "/wallet/" + urllib.parse.quote(wallet, safe="") if wallet else "/"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{suffix}",
                                     data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode(),
                                     headers={"Authorization": "Basic " + base64.b64encode(auth).decode()})
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            resp = e
        with resp:
            out = json.loads(resp.read(), parse_float=Decimal)
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out["result"]


def btc(sat):
    return f"{sat // 100_000_000}.{sat % 100_000_000:08d}"


def sats(v):
    return int(Decimal(str(v)) * 100_000_000)


NUMS = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
OUTCOMES = ("down", "flat", "up")
LEAF_PATH = {"down": 1, "flat": 2, "up": 3, "refund": 9}


# ---------------------------------------------------------------------------- campaign
class Campaign:
    def __init__(self, rpc: Node, run: Path, prefix: str, testnet: bool, mine=None):
        self.rpc, self.run, self.prefix, self.testnet, self.mine = rpc, run, prefix, testnet, mine
        self.state_path = run / "state.json"
        self.extra_wallets = []
        self.s = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}

    def save(self):
        self.run.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.s, indent=1, default=str) + "\n")

    def w(self, name):
        return f"{self.prefix}-{name}"

    def ensure_wallet(self, name, blank=False):
        full = self.w(name)
        if full in self.rpc("listwallets"):
            return full
        try:
            self.rpc("loadwallet", [full])
        except RuntimeError:
            self.rpc("createwallet", [full, False, blank, "", False, True, True])
        return full

    def root(self, wallet):
        rows = self.rpc("listdescriptors", [True], wallet=wallet)["descriptors"]
        (row,) = [r for r in rows if not r["internal"] and r["desc"].startswith("tr(")]
        root = row["desc"].split("(", 1)[1].split("#")[0].split("/", 1)[0]
        if root.startswith("["):
            root = root.split("]", 1)[1]
        pub = self.rpc("getdescriptorinfo", [f"pk({root})"])["descriptor"].split("(", 1)[1].split(")", 1)[0]
        return root, pub

    def chk(self, desc):
        return desc + "#" + self.rpc("getdescriptorinfo", [desc])["checksum"]

    # The funding descriptor with private keys only where `priv` says (party, leaf) -> True.
    # Every (party, leaf) key is an INDEPENDENT secret: a wallet holding an xprv derives the
    # private key of every path under it, so per-path keys from one root would let one signer
    # wallet sign every leaf (observed on regtest, see LEDGER R-VER-1 negative finding).
    def descriptor(self, priv=(), oracle_wif=None):
        def k(party, leaf):
            ent = self.s["leaf_keys"][party][leaf]
            return ent["wif"] if (party, leaf) in priv else ent["pub"]
        leaves = []
        for o in OUTCOMES:
            S = oracle_wif if (oracle_wif and o == self.s.get("outcome")) else self.s["oracle"]["S"][o]
            leaves.append(f"multi_a(3,{k('A', o)},{k('B', o)},{S})")
        refund = f"and_v(v:multi_a(2,{k('A', 'refund')},{k('B', 'refund')}),older({self.s['refund_blocks']}))"
        return f"tr({NUMS},{{{{{leaves[0]},{leaves[1]}}},{{{leaves[2]},{refund}}}}})"

    def import_signer(self, name, priv, oracle_wif=None):
        wallet = self.ensure_wallet(name, blank=True)
        d = self.chk(self.descriptor(priv, oracle_wif))
        res = self.rpc("importdescriptors", [[{"desc": d, "timestamp": "now", "active": False}]], wallet=wallet)
        assert all(r["success"] for r in res), res
        return wallet

    def wait_blocks(self, n, label):
        start = self.rpc("getblockcount")
        if self.mine:
            self.mine(n)
            return
        print(f"[{label}] waiting for {n} block(s) from {start}", flush=True)
        while self.rpc("getblockcount") < start + n:
            time.sleep(30)

    def wait_conf(self, txid, k, label):
        if self.mine:
            self.mine(k)
            return
        print(f"[{label}] waiting for {k} confirmation(s) of {txid}", flush=True)
        while True:
            c = self.txinfo(txid)[1]
            if c >= k:
                return
            time.sleep(30)

    def txinfo(self, txid):
        """(decoded tx, confirmations, blockheight) via mempool or any campaign wallet.
        The Testnet4 campaign node is pruned without txindex, so getrawtransaction cannot
        find a confirmed transaction; every campaign transaction touches a campaign wallet."""
        for w in [x for x in self.rpc("listwallets") if x.startswith(self.prefix)] + self.extra_wallets:
            try:
                t = self.rpc("gettransaction", [txid, True, True], wallet=w)
                return t["decoded"], t.get("confirmations", 0), t.get("blockheight")
            except RuntimeError:
                continue
        try:
            d = self.rpc("getrawtransaction", [txid, True])
            return d, d.get("confirmations", 0), None
        except RuntimeError:
            return None, 0, None

    # -------------------------------------------------------------------- phase: setup
    def setup(self, payer, margin, lp_float, price0, leverage, refund_blocks, oracle_seed: bytes):
        if self.s.get("phase_done", {}).get("setup"):
            return
        if self.s.get("setup_txid"):          # resume: never pay the setup twice
            for x in ("a", "b", "lp"):
                self.ensure_wallet(x)
            self.wait_conf(self.s["setup_txid"], 1, "setup")
            self.s.setdefault("phase_done", {})["setup"] = True
            self.save()
            return
        a, b, lp = (self.ensure_wallet(x) for x in ("a", "b", "lp"))
        leaf_keys = {}
        for party in ("A", "B"):
            leaf_keys[party] = {}
            for leaf in OUTCOMES + ("refund",):
                sk, Pk = even_secret(int.from_bytes(tagged("cbm/leaf-key", oracle_seed + f"{party}/{leaf}".encode()), "big") % n_)
                leaf_keys[party][leaf] = dict(wif=wif(sk, True), pub=xonly(Pk).hex())
        self.s.update(margin=margin, price0=price0, leverage=leverage, refund_blocks=refund_blocks, leaf_keys=leaf_keys)
        # Oracle: key x, nonce k; announcement (P, R) and outcome points S_j = R + e_j P.
        x, P = even_secret(int.from_bytes(tagged("cbm/oracle-key", oracle_seed), "big") % n_)
        k, R = even_secret(int.from_bytes(tagged("cbm/oracle-nonce", oracle_seed), "big") % n_)
        S = {}
        for o in OUTCOMES:
            e = challenge(R, P, self.msg(o))
            S[o] = xonly(padd(R, pmul(e, P))).hex()
        self.s["oracle"] = dict(P=xonly(P).hex(), R=xonly(R).hex(), S=S, event=self.event_id())
        (self.run / "oracle_secret.json").write_text(json.dumps({"x": hex(x), "k": hex(k)}))  # never committed
        # Payer funds A, B (margin + fee share) and the LP float in one transaction.
        fee_share = 600
        outs = {self.rpc("getnewaddress", ["", "bech32m"], wallet=a): btc(margin + fee_share),
                self.rpc("getnewaddress", ["", "bech32m"], wallet=b): btc(margin + fee_share),
                self.rpc("getnewaddress", ["", "bech32m"], wallet=lp): btc(lp_float)}
        txid = self.rpc("sendmany", ["", outs, 1, "cbm-shz01 dlc setup", [], True, None, "unset", 2], wallet=payer)
        self.s["setup_txid"] = txid
        self.s["t_setup"] = time.time()
        self.save()
        self.wait_conf(txid, 1, "setup")
        self.s.setdefault("phase_done", {})["setup"] = True
        self.save()

    def event_id(self):
        return f"{self.prefix}/btcusd-bucket"

    def msg(self, outcome):
        return f"{self.event_id()}/{outcome}".encode()

    def payouts(self, outcome):
        """Clipped inverse payoff at the representative price; returns (A_sat, B_sat) before fee."""
        m, P0, L = self.s["margin"], self.s["price0"], self.s["leverage"]
        q_usd = L * m / 1e8 * P0                       # notional so that m = q / (L P0)
        P1 = P0 * {"down": 0.98, "flat": 1.0, "up": 1.02}[outcome]
        pnl_long = q_usd * (1 / P0 - 1 / P1) * 1e8
        pnl = int(round(max(-m, min(m, pnl_long))))
        return m + pnl, m - pnl

    # --------------------------------------------------------- phase: presign + fund
    def presign_and_fund(self, cet_fee=600, fund_fee=600):
        if self.s.get("phase_done", {}).get("fund"):
            return
        a, b, lp = self.w("a"), self.w("b"), self.w("lp")
        funding_addr = self.rpc("deriveaddresses", [self.chk(self.descriptor())])[0]
        spk = self.rpc("getaddressinfo", [funding_addr], wallet=a)["scriptPubKey"]
        amt = 2 * self.s["margin"]
        ua = [u for u in self.rpc("listunspent", [1], wallet=a)]
        ub = [u for u in self.rpc("listunspent", [1], wallet=b)]
        ia, ib = max(ua, key=lambda u: u["amount"]), max(ub, key=lambda u: u["amount"])
        change_a = sats(ia["amount"]) - self.s["margin"] - fund_fee // 2
        change_b = sats(ib["amount"]) - self.s["margin"] - fund_fee // 2
        outs = [{funding_addr: btc(amt)}]
        if change_a > 330:
            outs.append({self.rpc("getnewaddress", ["", "bech32m"], wallet=a): btc(change_a)})
        if change_b > 330:
            outs.append({self.rpc("getnewaddress", ["", "bech32m"], wallet=b): btc(change_b)})
        fpsbt = self.rpc("createpsbt", [[{"txid": ia["txid"], "vout": ia["vout"]}, {"txid": ib["txid"], "vout": ib["vout"]}], outs, 0, True])
        parts = [self.rpc("walletprocesspsbt", [fpsbt, True, "ALL", True, False], wallet=w)["psbt"] for w in (a, b)]
        fin = self.rpc("finalizepsbt", [self.rpc("combinepsbt", [parts])])
        assert fin["complete"], "funding not fully signed"
        fraw = fin["hex"]
        dec = self.rpc("decoderawtransaction", [fraw])
        ftxid = dec["txid"]
        vout = next(o["n"] for o in dec["vout"] if o["scriptPubKey"].get("address") == funding_addr)
        self.s.update(funding=dict(txid=ftxid, vout=vout, amount=amt, address=funding_addr, spk=spk, vsize=dec["vsize"]))
        # CETs: B's output pays the LP (reimbursement of the advance).
        cets = {}
        for o in OUTCOMES:
            pa, pb = self.payouts(o)
            pa -= cet_fee // 2
            pb -= cet_fee // 2
            outs = []
            if pa > 330:
                outs.append({self.rpc("getnewaddress", ["", "bech32m"], wallet=a): btc(pa)})
            if pb > 330:
                outs.append({self.rpc("getnewaddress", ["", "bech32m"], wallet=lp): btc(pb)})
            ps = self.rpc("createpsbt", [[{"txid": ftxid, "vout": vout, "sequence": 0xFFFFFFFD}], outs, 0, True])
            ps = psbt_set_witness_utxo(ps, 0, amt, spk)
            sig_a = self.import_signer(f"cet-{o}-a", {("A", o)})
            sig_b = self.import_signer(f"cet-{o}-b", {("B", o)})
            parts = [self.rpc("walletprocesspsbt", [ps, True, "ALL", True, False], wallet=w)["psbt"] for w in (sig_a, sig_b)]
            comb = self.rpc("combinepsbt", [parts])
            pre = self.rpc("finalizepsbt", [comb, False])
            assert not pre["complete"], "a CET must not be complete before the attestation"
            info = self.rpc("decodepsbt", [comb])["inputs"][0]
            nsig = len(info.get("taproot_script_path_sigs", []))
            cets[o] = dict(psbt=comb, a_sat=pa, lp_sat=pb, presigned_sigs=nsig)
        # Refund: both parties, relative timelock.
        r_outs = [{self.rpc("getnewaddress", ["", "bech32m"], wallet=a): btc(self.s["margin"] - cet_fee // 2)},
                  {self.rpc("getnewaddress", ["", "bech32m"], wallet=b): btc(self.s["margin"] - cet_fee // 2)}]
        rps = self.rpc("createpsbt", [[{"txid": ftxid, "vout": vout, "sequence": self.s["refund_blocks"]}], r_outs, 0, True])
        rps = psbt_set_witness_utxo(rps, 0, amt, spk)
        ra = self.import_signer("refund-a", {("A", "refund")})
        rb = self.import_signer("refund-b", {("B", "refund")})
        parts = [self.rpc("walletprocesspsbt", [rps, True, "ALL", True, False], wallet=w)["psbt"] for w in (ra, rb)]
        rfin = self.rpc("finalizepsbt", [self.rpc("combinepsbt", [parts])])
        assert rfin["complete"], "refund must be complete before funding"
        self.s.update(cets=cets, refund_hex=rfin["hex"])
        self.s["presigned_before_funding_broadcast"] = True
        self.save()
        # Only now broadcast the funding transaction.
        assert self.rpc("testmempoolaccept", [[fraw]])[0]["allowed"]
        self.rpc("sendrawtransaction", [fraw])
        self.s["t_fund_broadcast"] = time.time()
        self.save()
        self.wait_conf(ftxid, 1, "funding")
        self.s["fund_height"] = self.txinfo(ftxid)[2]
        self.s.setdefault("phase_done", {})["fund"] = True
        self.save()
        # The refund must be rejected before its timelock.
        early = self.rpc("testmempoolaccept", [[self.s["refund_hex"]]])[0]
        self.s["refund_early_reject"] = early.get("reject-reason")
        self.save()

    # ----------------------------------------------------- phase: maturity and close
    def close(self, price1, price_source, maturity_blocks):
        if self.s.get("phase_done", {}).get("close"):
            return
        a, b, lp = self.w("a"), self.w("b"), self.w("lp")
        if "maturity_height" not in self.s:
            self.s["maturity_height"] = self.s["fund_height"] + maturity_blocks
            self.save()
        while self.rpc("getblockcount") < self.s["maturity_height"]:
            self.wait_blocks(1, "maturity")
        P0 = self.s["price0"]
        outcome = "down" if price1 < P0 * 0.99 else "up" if price1 > P0 * 1.01 else "flat"
        sec = json.loads((self.run / "oracle_secret.json").read_text())
        x, k = int(sec["x"], 16), int(sec["k"], 16)
        Pt, Rt = pmul(x), pmul(k)
        e = challenge(Rt, Pt, self.msg(outcome))
        s = (k + e * x) % n_
        assert xonly(pmul(s)).hex() == self.s["oracle"]["S"][outcome], "attestation does not match the announced point"
        self.s.update(outcome=outcome, price1=price1, price_source=price_source,
                      attestation=dict(s=hex(s), outcome=outcome, R=self.s["oracle"]["R"]), t_attest=time.time(),
                      attest_height=self.rpc("getblockcount"))
        self.save()
        # LP advance: pay B its outcome value now, before the CET confirms.
        cet = self.s["cets"][outcome]
        adv_txid = None
        if cet["lp_sat"] > 330:
            b_addr = self.rpc("getnewaddress", ["", "bech32m"], wallet=b)
            adv_txid = self.rpc("sendtoaddress", [b_addr, btc(cet["lp_sat"]), "", "", False, True, None, "unset", False, 2], wallet=lp)
        self.s["lp_advance_txid"] = adv_txid
        self.s["t_advance"] = time.time()
        self.save()
        # Close: any holder of s completes the outcome CET.
        closer = self.import_signer(f"close-{outcome}", set(), oracle_wif=wif(s if pmul(s)[1] % 2 == 0 else s, True))
        done = self.rpc("walletprocesspsbt", [cet["psbt"], True, "ALL", True, False], wallet=closer)["psbt"]
        fin = self.rpc("finalizepsbt", [done])
        assert fin["complete"], "CET did not complete with the attestation"
        verdict = self.rpc("testmempoolaccept", [[fin["hex"]]])[0]
        assert verdict["allowed"], verdict
        cet_txid = self.rpc("sendrawtransaction", [fin["hex"]])
        self.s.update(cet_txid=cet_txid, t_cet_broadcast=time.time())
        self.save()
        # Wrong-outcome CETs must stay incomplete even with the realised attestation.
        others = {}
        for o in OUTCOMES:
            if o == outcome:
                continue
            try_ = self.rpc("walletprocesspsbt", [self.s["cets"][o]["psbt"], True, "ALL", True, False], wallet=closer)["psbt"]
            others[o] = self.rpc("finalizepsbt", [try_])["complete"]
        self.s["other_cets_completed_with_attestation"] = others
        self.save()
        self.wait_conf(cet_txid, 1, "cet")
        if adv_txid:
            self.wait_conf(adv_txid, 1, "advance")
        self.s["t_cet_confirmed"] = time.time()
        self.s["cet_height"] = self.rpc("getblockcount")
        self.s.setdefault("phase_done", {})["close"] = True
        self.save()

    # ------------------------------------------------------------------ phase: reuse
    def reuse(self, return_to_wallet):
        if self.s.get("phase_done", {}).get("reuse"):
            return
        back = self.rpc("getnewaddress", ["", "bech32m"], wallet=return_to_wallet)
        spent = {}
        for name in ("a", "b", "lp"):
            w = self.w(name)
            bal = sats(self.rpc("getbalances", wallet=w)["mine"]["trusted"])
            if bal > 1_000:
                spent[name] = self.rpc("sendtoaddress", [back, btc(bal), "", "", True, True, None, "unset", False, 2], wallet=w)
        self.s["reuse"] = spent
        self.save()
        for t in spent.values():
            self.wait_conf(t, 1, "reuse")
        self.s["t_reuse_confirmed"] = time.time()
        self.s.setdefault("phase_done", {})["reuse"] = True
        self.save()

    def report(self):
        s = self.s
        cet, cet_conf, _ = self.txinfo(s["cet_txid"])
        cet["confirmations"] = cet_conf
        fund = self.txinfo(s["funding"]["txid"])[0]
        rep = dict(
            schema="cbm-shz-01/oracle-dlc-release/v1", prefix=self.prefix, chain=self.rpc("getblockchaininfo")["chain"],
            core_version=self.rpc("getnetworkinfo")["subversion"],
            contract=dict(margin_sat=s["margin"], leverage=s["leverage"], price0=s["price0"], price1=s["price1"],
                          price_source=s["price_source"], outcome=s["outcome"], refund_blocks=s["refund_blocks"]),
            oracle=dict(P=s["oracle"]["P"], R=s["oracle"]["R"], S=s["oracle"]["S"], attestation_s=s["attestation"]["s"],
                        event=s["oracle"]["event"]),
            funding=dict(txid=s["funding"]["txid"], vsize=fund["vsize"], amount_sat=s["funding"]["amount"],
                         height=s.get("fund_height")),
            cet=dict(txid=s["cet_txid"], vsize=cet["vsize"], witness_items=len(cet["vin"][0]["txinwitness"]),
                     outputs={o["scriptPubKey"]["address"]: sats(o["value"]) for o in cet["vout"]},
                     a_sat=s["cets"][s["outcome"]]["a_sat"], lp_sat=s["cets"][s["outcome"]]["lp_sat"]),
            presigned_sigs_per_cet={o: c["presigned_sigs"] for o, c in s["cets"].items()},
            lp_advance_txid=s.get("lp_advance_txid"), reuse=s.get("reuse"),
            checks=dict(
                cets_and_refund_signed_before_funding=bool(s.get("presigned_before_funding_broadcast")),
                cets_incomplete_before_attestation=all(c["presigned_sigs"] == 2 for c in s["cets"].values()),
                cets_presigned_only_on_own_leaf=all(c["presigned_sigs"] == 2 for c in s["cets"].values()),
                refund_rejected_before_timelock=s.get("refund_early_reject") in ("non-BIP68-final",),
                attestation_matches_announced_point=True,
                wrong_outcome_cets_stay_incomplete=not any(s["other_cets_completed_with_attestation"].values()),
                cet_confirmed=cet.get("confirmations", 0) >= 1,
                lp_reimbursed_by_cet=s["cets"][s["outcome"]]["lp_sat"] in [sats(o["value"]) for o in cet["vout"]] or s["cets"][s["outcome"]]["lp_sat"] <= 330,
                released_outputs_reused=bool(s.get("reuse"))),
            timings_s=dict(attestation_to_cet_confirmed=s["t_cet_confirmed"] - s["t_attest"],
                           lp_advance_to_reimbursement_confirmed=s["t_cet_confirmed"] - s["t_advance"],
                           cet_confirmed_to_reuse_confirmed=s["t_reuse_confirmed"] - s["t_cet_confirmed"],
                           funding_broadcast_to_reuse_confirmed=s["t_reuse_confirmed"] - s["t_fund_broadcast"]),
            heights=dict(funding=s.get("fund_height"), maturity=s.get("maturity_height"), attestation=s.get("attest_height"),
                         cet=s.get("cet_height")))
        rep["passed"] = all(rep["checks"].values())
        (self.run / "report.json").write_text(json.dumps(rep, indent=1, default=str) + "\n")
        return rep


def spot_price():
    url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-client/1"}), timeout=30).read()
    return float(json.loads(raw)["data"]["amount"]), dict(url=url, sha256=hashlib.sha256(raw).hexdigest(), fetched_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datadir", type=Path, required=True)
    ap.add_argument("--chain", choices=["regtest", "testnet4"], required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--payer", required=True)
    ap.add_argument("--margin", type=int, default=20_000)
    ap.add_argument("--lp-float", type=int, default=30_000)
    ap.add_argument("--maturity-blocks", type=int, default=2)
    ap.add_argument("--refund-blocks", type=int, default=144)
    ap.add_argument("--synthetic-price1", type=float)
    a = ap.parse_args()
    cookie = a.datadir / (a.chain if a.chain != "regtest" else "regtest") / ".cookie"
    rpc = Node(cookie, a.port)
    mine = None
    if a.chain == "regtest":
        miner = rpc("getnewaddress", wallet=a.payer)
        mine = lambda k: rpc("generatetoaddress", [k, miner])
    c = Campaign(rpc, a.run, a.prefix, testnet=True, mine=mine)
    c.extra_wallets = [a.payer]
    if "price0" not in c.s:
        p0, src0 = (100_000.0, {"synthetic": True}) if a.synthetic_price1 else spot_price()
        c.s["price0_source"] = src0
        seed = secrets.token_bytes(32)
        c.run.mkdir(parents=True, exist_ok=True)
        (c.run / "oracle_seed.hex").write_text(seed.hex())
        c.s["price0_pending"] = p0
        c.save()
    seed = bytes.fromhex((c.run / "oracle_seed.hex").read_text())
    c.setup(a.payer, a.margin, a.lp_float, c.s.get("price0", c.s["price0_pending"]), 10, a.refund_blocks, seed)
    c.presign_and_fund()
    if a.synthetic_price1:
        p1, src1 = a.synthetic_price1, {"synthetic": True}
    elif "price1" in c.s:
        p1, src1 = c.s["price1"], c.s["price_source"]
    else:
        # wait for maturity first, then fetch the price at attestation time
        while rpc("getblockcount") < c.s["fund_height"] + a.maturity_blocks:
            c.wait_blocks(1, "maturity")
        p1, src1 = spot_price()
    c.close(p1, src1, a.maturity_blocks)
    c.reuse(a.payer)
    rep = c.report()
    print(json.dumps({k: rep[k] for k in ("passed", "checks", "timings_s", "contract", "cet", "heights")}, indent=1, default=str))


if __name__ == "__main__":
    main()
