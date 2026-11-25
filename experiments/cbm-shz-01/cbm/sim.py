"""CBM-SHZ-01 reference simulator: settlement capital under five SHZ architectures.

One demand trace (trades -> fixed-maturity inverse BTC/USD contracts, each a bilateral
DLC-equivalent claim between a taker and a maker) is replayed under:

  A  independent bilateral LN-DLC settlement (taker-maker channels)
  B  router-local netting (trader-router channels, settlement netted per router batch)
  C  UTXORef multilateral clearing (on-chain clearing rounds, restricted payout graph)
  D  C plus LP-funded advances, Nova-verified clearing statements and BitVM3 settlement
  E  unrestricted frictionless clearing (theoretical upper control)

and, as separate rows, pre-maturity portfolio margin (B_pm, C_pm, E_pm), which changes the
collateral rule and is checked for impaired claims.

Every architecture inventories distinct capital objects (amount, owner, category,
lock/release time, release verification class) on a one-minute grid. Integrals are in
BTC-days. Nothing here touches a network or a wallet: every release is SIMULATED; the
`verification` field names the mechanism that would have to be observed to verify it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

SEC_PER_BLOCK = 600
DAY = 86_400
SAT = 1e8


@dataclass
class Scenario:
    name: str = "base"
    seed: int = 1
    horizon_days: float = 7.0
    regime: str = "median"              # calm | median | volatile | synthetic-gbm
    price_mode: str = "synthetic"       # synthetic (calibrated t-returns) | empirical (local replay)
    daily_volume_usd: float = 20e6
    n_traders: int = 200
    n_makers: int = 8
    n_routers: int = 4
    topology: str = "mesh"              # mesh: makers quote on every router; star: one router each
    leverage: float = 10.0
    maturity_h: float = 24.0
    imbalance_corr: float = 0.3         # rho: share of trader biases aligned with a common sign
    persistence: float = 0.6            # P(trade side = trader bias)
    offline_frac: float = 0.05          # P(a counterparty is offline at a given settlement)
    settle_period_h: float = 1.0        # clearing round period for C/D
    confirmations: int = 3              # blocks before an on-chain release counts
    to_self_delay_blocks: int = 144     # unilateral exit delay for channels and vault fallbacks
    challenge_blocks: int = 144         # BitVM3 challenge period Delta for D
    proof_latency_h: float = 3.0        # Nova fold + SP1 guest-A proof per batch
    proof_batch_h: float = 1.0          # D: one proof per this many hours of settlements
    vault_edge_density: float = 1.0     # C/D restricted payout graph: share of vault->creditor edges present
    vault_budget_frac: float = 1.0      # C/D: share of due debtor collateral usable in-round
    funding_rate: float = 0.05          # trader BTC funding rate, simple annual
    lp_rate: float = 0.05               # LP / operator BTC funding rate
    feerate: float = 10.0               # sat/vB
    fee_reserve_multiple: float = 3.0   # exit reserve = exit vB x feerate x this
    btc_usd: float = 100_000.0          # for USD-denominated proof costs (synthetic mode)
    gpu_usd_per_h: float = 1.5
    guest_a_gpu_h: float = 3.0          # SP1 guest A (Nova verifier, ~21B instr) per proof batch
    bond_ratio: float = 0.5             # D operator bond / peak LP advance in flight
    advance_scope: str = "all"          # D: LP advances payouts and margin returns ("all") or payouts only
    challenge_prob: float = 0.01        # D: probability a batch is challenged (Assert + Disprove on chain)
    default_prob: float = 0.02          # PM rows: P(trader stops meeting margin calls)
    remargin_min: float = 5.0           # PM rows: variation margin interval (minutes)
    pm_buffer: float = 0.0              # PM rows: extra margin as a share of gross notional / leverage


# ----------------------------------------------------------------------------------- demand

def load_regimes(path: Path) -> dict:
    return json.loads(path.read_text())


def price_path(s: Scenario, reg: dict, rng: np.random.Generator, minutes: int, cache: Path | None):
    """Per-minute BTC/USD path of length minutes+1 (index = minute)."""
    day = reg["regimes"].get(s.regime, reg["regimes"]["median"])
    d = next(x for x in reg["days"] if x["day"] == day)
    if s.price_mode == "empirical":
        if cache is None:
            raise ValueError("empirical mode needs the local trades cache")
        days = sorted(p for p in cache.glob("trades_BTC_*.npz") if p.stem.split("_")[-1] >= day)
        px = []
        for p in days:
            z = np.load(p)["last_px"].astype(float)
            px.append(z)
            if sum(len(x) for x in px) >= (minutes + 1) * 60:
                break
        px = np.concatenate(px)
        ok = ~np.isnan(px)
        idx = np.where(ok, np.arange(len(px)), -1)
        np.maximum.accumulate(idx, out=idx)
        px = np.where(idx >= 0, px[np.maximum(idx, 0)], np.nan)
        out = px[::60][: minutes + 1]
        if len(out) < minutes + 1 or np.isnan(out).any():
            raise ValueError("local cache too short for the horizon")
        return out, d
    sig = d["sigma_1m"]
    k = max(d["kurtosis_1m"], 3.5)
    nu = max(4.0 + 6.0 / (k - 3.0), 4.1)  # Student-t df matching excess kurtosis
    t = rng.standard_t(nu, minutes) * sig * math.sqrt((nu - 2) / nu)
    return s.btc_usd * np.exp(np.concatenate([[0.0], np.cumsum(t)])), d


def trades(s: Scenario, d: dict, rng: np.random.Generator, minutes: int):
    prof = np.array(d["intensity_profile_288"])
    q = np.array(d["mean_trade_usd_q"])
    sig_ln = max((math.log(q[4]) - math.log(q[0])) / 2.563, 0.3)
    mean_size = d["daily_volume_usd"] / d["trades"]          # day's mean trade, not the per-second median
    med = mean_size / math.exp(sig_ln ** 2 / 2)
    per_day = s.daily_volume_usd / mean_size
    lam = np.tile(np.repeat(prof, 5) * per_day, int(math.ceil(minutes / 1440)))[:minutes]
    n = rng.poisson(lam)
    t_min = np.repeat(np.arange(minutes), n)
    t_sec = t_min * 60 + rng.integers(0, 60, len(t_min))
    size = np.exp(rng.normal(math.log(med), sig_ln, len(t_min)))
    # Trader population: Pareto activity, biases with common-sign share (1+rho)/2.
    act = rng.pareto(1.5, s.n_traders) + 1
    act /= act.sum()
    common = 1 if rng.random() < 0.5 else -1
    bias = np.where(rng.random(s.n_traders) < (1 + s.imbalance_corr) / 2, common, -common)
    taker = rng.choice(s.n_traders, len(t_min), p=act)
    side = np.where(rng.random(len(t_min)) < s.persistence, bias[taker], -bias[taker])
    home = np.arange(s.n_traders) % s.n_routers
    router = home[taker]
    if s.topology == "mesh":
        maker = rng.integers(0, s.n_makers, len(t_min))
    else:  # star: maker j quotes only on router j mod R
        per = max(s.n_makers // s.n_routers, 1)
        maker = (router + s.n_routers * rng.integers(0, per, len(t_min))) % s.n_makers
    return dict(t=t_sec.astype(np.int64), q=size, side=side.astype(np.int8), taker=taker, maker=maker + s.n_traders,
                router=router, n_parties=s.n_traders + s.n_makers)


# ------------------------------------------------------------------------------- contracts

def contracts(s: Scenario, tr: dict, px: np.ndarray, rng: np.random.Generator):
    """Fixed-maturity inverse contracts. Long side = taker if side=+1 else maker."""
    T = int(s.maturity_h * 3600)
    t0 = tr["t"]
    t1 = t0 + T
    keep = np.ones(len(t0), bool)  # every contract opened in the trading window lives to maturity
    t0, t1 = t0[keep], t1[keep]
    q = tr["q"][keep]
    long_ = np.where(tr["side"][keep] > 0, tr["taker"][keep], tr["maker"][keep])
    short = np.where(tr["side"][keep] > 0, tr["maker"][keep], tr["taker"][keep])
    P0 = px[t0 // 60]
    P1 = px[t1 // 60]
    m = q / (s.leverage * P0)                         # BTC margin per side
    pnl_long = q * (1 / P0 - 1 / P1)                  # BTC, inverse contract
    clipped = np.clip(pnl_long, -m, m)                # DLC payout bounded by posted collateral
    shortfall = np.abs(pnl_long) - np.abs(clipped)    # unenforceable beyond collateral (same in every arm)
    debtor = np.where(clipped < 0, long_, short)
    creditor = np.where(clipped < 0, short, long_)
    owed = np.abs(clipped)
    # Offline status is per (party, UTC day): an offline party misses every settlement that day.
    dday = t1 // DAY
    off_pd = rng.random((tr["n_parties"], int(dday.max()) + 1)) < s.offline_frac
    off_d = off_pd[debtor, dday]
    off_c = off_pd[creditor, dday]
    return dict(t0=t0, t1=t1, q=q, m=m, long=long_, short=short, debtor=debtor, creditor=creditor, owed=owed, day=dday,
                shortfall=shortfall, router=tr["router"][keep], taker=tr["taker"][keep], maker=tr["maker"][keep],
                offline=off_d | off_c, P0=P0, V_btc=float((q / P0).sum()), n=int(keep.sum()), n_parties=tr["n_parties"])


# ---------------------------------------------------------------------------- accounting

class Ledger:
    """Distinct capital objects on a one-minute grid, integrated by owner and category."""

    def __init__(self, minutes: int):
        self.minutes = minutes
        self.k = {}     # (owner, category) -> np.ndarray of BTC per minute (difference array)
        self.verif = {}
        self.objects = 0

    def lock(self, owner, cat, amount, t_lock, t_release, verification):
        amount = np.asarray(amount, float)
        a = np.clip(np.asarray(t_lock) // 60, 0, self.minutes)
        b = np.clip(np.ceil(np.asarray(t_release) / 60).astype(np.int64), 0, self.minutes)
        key = (owner, cat)
        if key not in self.k:
            self.k[key] = np.zeros(self.minutes + 1)
        np.add.at(self.k[key], np.broadcast_to(a, amount.shape), amount)
        np.add.at(self.k[key], np.broadcast_to(b, amount.shape), -amount)
        self.verif[key] = verification
        self.objects += int(amount.size)

    def flat(self, owner, cat, amount, verification, t_from=0, t_to=None):
        """A provisioned stock held from t_from to t_to (seconds); default: whole window."""
        t_to = self.minutes * 60 if t_to is None else t_to
        self.lock(owner, cat, np.array([float(amount)]), np.array([int(t_from)]), np.array([int(t_to)]), verification)

    def series(self):
        return {k: np.cumsum(v)[:-1] for k, v in self.k.items()}

    def summary(self):
        ser = self.series()
        tot = sum(ser.values()) if ser else np.zeros(self.minutes)
        by = {}
        for (o, c), x in ser.items():
            by.setdefault(o, {})[c] = dict(btc_days=float(x.sum() / 1440), peak_btc=float(x.max()), verification=self.verif[(o, c)])
        return dict(peak_btc=float(tot.max()), btc_days=float(tot.sum() / 1440), by_owner=by, objects=self.objects,
                    series_total_hourly=tot[::60].round(6).tolist())


def round_up(t, period):
    return (np.floor_divide(t, period) + 1) * period


def chain_release(t, s: Scenario):
    return t + s.confirmations * SEC_PER_BLOCK


def offline_delay(s: Scenario):
    return (s.to_self_delay_blocks + s.confirmations) * SEC_PER_BLOCK


def pair_peaks(keys, t_on, t_off, amt):
    """Peak concurrent amount per key (oracle channel provisioning)."""
    order = np.lexsort((np.concatenate([np.zeros(len(t_on)), np.ones(len(t_off))]),
                        np.concatenate([t_on, t_off]), np.concatenate([keys, keys])))
    k = np.concatenate([keys, keys])[order]
    v = np.concatenate([amt, -amt])[order]
    out = {}
    cur = {}
    for kk, vv in zip(k.tolist(), v.tolist()):
        c = cur.get(kk, 0.0) + vv
        cur[kk] = c
        if c > out.get(kk, 0.0):
            out[kk] = c
    return out


# --------------------------------------------------------------------------- architectures

EXIT_VB = dict(channel=600, vault=200)  # unilateral exit bytes: force close (commit+CET+sweep), vault path


def offline_events(keys, day, mask):
    """Distinct (key, day) pairs among offline settlements: one unilateral exit each."""
    if not mask.any():
        return 0
    return int(len(np.unique(np.stack([np.asarray(keys)[mask], day[mask]], 1), axis=0)))


def arch_A(s, c, minutes):
    """Bilateral LN-DLC: taker-maker channels provisioned at their peak concurrent margin."""
    L = Ledger(minutes)
    rel = c["t1"] + np.where(c["offline"], offline_delay(s), 0)
    pair = c["taker"].astype(np.int64) * 100_000 + c["maker"]
    peaks = pair_peaks(pair, c["t0"], rel, 2 * c["m"])
    # Channel stock: held for the horizon at the provisioned peak (both sides' margin).
    L.flat("traders", "channel_stock", sum(peaks.values()), "ln_channel_state", 0, rel.max())
    n_ch = len(peaks)
    chain_vb = n_ch * (154 + 200) + offline_events(pair, c["day"], c["offline"]) * (EXIT_VB["channel"] + 154)
    L.flat("traders", "exit_fee_reserve", n_ch * 2 * EXIT_VB["channel"] * s.feerate * s.fee_reserve_multiple / SAT, "onchain_utxo", 0, rel.max())
    return L, dict(chain_vb=chain_vb, channels=n_ch, release=rel, verification="ln_channel_state (cooperative) / onchain_confirmed (offline)",
                   provider_cost_btc=0.0, gross_settlement_btc=float(c["owed"].sum()), net_settlement_btc=float(c["owed"].sum()),
                   unserved_btc=0.0)


def settle_batches(c, period, key):
    """Net payables per (batch, key, party): returns gross, net flows."""
    b = c["t1"] // period
    g = float(c["owed"].sum())
    deb = np.stack([b, key, c["debtor"]], 1)
    cre = np.stack([b, key, c["creditor"]], 1)
    allk = np.concatenate([deb, cre])
    amt = np.concatenate([-c["owed"], c["owed"]])
    uniq, inv = np.unique(allk, axis=0, return_inverse=True)
    net = np.bincount(inv.ravel(), weights=amt)
    return g, float(net[net > 0].sum()), uniq, net


def arch_B(s, c, minutes, pm=False):
    """Router-local netting over trader-router channels.

    Trader side of each channel: peak margin the trader posts at that router (oracle).
    Router side: peak cumulative net receipts the trader collects at that router (prefix cut
    bound, unpooled per channel), provisioned by the router operator.
    """
    L = Ledger(minutes)
    period = int(s.settle_period_h * 3600)
    rel = round_up(c["t1"], period) + np.where(c["offline"], offline_delay(s), 0)
    keys = []
    for side in ("long", "short"):
        keys.append(c[side].astype(np.int64) * 100 + c["router"])
    k = np.concatenate(keys)
    if pm:
        ser, impaired = portfolio_margin(s, c, by_router=True, minutes=minutes, series=True)
        # Channels must carry the peak portfolio requirement (oracle provisioning).
        L.flat("traders", "channel_stock_pm", float(ser.max()), "ln_channel_state", 0, rel.max())
    else:
        peaks = pair_peaks(k, np.concatenate([c["t0"], c["t0"]]), np.concatenate([rel, rel]), np.concatenate([c["m"], c["m"]]))
        L.flat("traders", "channel_stock", sum(peaks.values()), "ln_channel_state", 0, rel.max())
        impaired = 0.0
    # Router directional stock: per trader-router edge, running max of cumulative net receipts.
    order = np.argsort(c["t1"], kind="stable")
    cre = (c["creditor"].astype(np.int64) * 100 + c["router"])[order]
    deb = (c["debtor"].astype(np.int64) * 100 + c["router"])[order]
    owed = c["owed"][order]
    cum, peak = {}, {}
    for cr, db, o in zip(cre.tolist(), deb.tolist(), owed.tolist()):
        cum[cr] = cum.get(cr, 0.0) + o
        if cum[cr] > peak.get(cr, 0.0):
            peak[cr] = cum[cr]
        cum[db] = cum.get(db, 0.0) - o
    L.flat("router_operators", "directional_stock", sum(peak.values()), "ln_channel_state", 0, rel.max())
    n_ch = len(set(k.tolist()))
    L.flat("traders", "exit_fee_reserve", n_ch * EXIT_VB["channel"] * s.feerate * s.fee_reserve_multiple / SAT, "onchain_utxo", 0, rel.max())
    g, n, _, _ = settle_batches(c, period, c["router"])
    off_keys = np.concatenate([c["debtor"].astype(np.int64) * 100 + c["router"], c["creditor"].astype(np.int64) * 100 + c["router"]])
    chain_vb = n_ch * (154 + 200) + offline_events(off_keys, np.concatenate([c["day"], c["day"]]),
                                                   np.concatenate([c["offline"], c["offline"]])) * (EXIT_VB["channel"] + 154)
    rd = sum(peak.values())
    return L, dict(chain_vb=chain_vb, channels=n_ch, release=rel, gross_settlement_btc=g, net_settlement_btc=n,
                   provider_capital_btc_days=rd * s.horizon_days, impaired_claims_btc=impaired, unserved_btc=0.0,
                   verification="ln_channel_state / onchain_confirmed (offline)")


def clearing_rounds(s, c, restricted=True, collect=None):
    """Per clearing round: multilateral net positions, restricted payout delivery.

    Debtors' due collateral forms vault budgets (one vault per debtor's router); creditors are
    reachable from a vault only along present edges (density vault_edge_density). Delivery is
    the max flow of the source->vault->creditor->sink network; the deficit rolls to the next
    round. Returns per-round records.
    """
    from .flow import bipartite_maxflow
    period = int(s.settle_period_h * 3600)
    b = c["t1"] // period
    rounds = []
    carry = {}
    edge_rng = np.random.default_rng(s.seed + 99)
    present = edge_rng.random((s.n_routers, s.n_traders + s.n_makers)) < s.vault_edge_density
    for rb in np.unique(b):
        sel = (b == rb) & ~c["offline"]
        net = np.zeros(c["n_parties"])
        np.add.at(net, c["creditor"][sel], c["owed"][sel])
        np.add.at(net, c["debtor"][sel], -c["owed"][sel])
        for p, v in carry.items():
            net[p] += v
        carry = {}
        cred = np.flatnonzero(net > 1e-15)
        debt = np.flatnonzero(net < -1e-15)
        demand = net[cred]
        if not restricted or len(cred) == 0:
            delivered = demand.copy()
        else:
            home = np.where(np.arange(c["n_parties"]) < s.n_traders, np.arange(c["n_parties"]) % s.n_routers, -1)
            vb = np.zeros(s.n_routers)
            for p in debt:
                r = home[p] if home[p] >= 0 else p % s.n_routers
                vb[r] += -net[p] * s.vault_budget_frac
            cap = present[:, cred].astype(float) * 1e9
            delivered = bipartite_maxflow(vb, cap, demand)
            if collect is not None:
                collect.append((vb.copy(), present[:, cred].copy(), demand.copy()))
        deficit = demand - delivered
        for p, dv in zip(cred.tolist(), deficit.tolist()):
            if dv > 1e-15:
                carry[p] = dv
        rounds.append(dict(t=(int(rb) + 1) * period, gross=float(c["owed"][sel].sum()), net=float(demand.sum()),
                           delivered=float(delivered.sum()), deficit=float(deficit.sum()), n_in=int(len(debt)), n_out=int(len(cred))))
    return rounds


def vault_offline_events(c):
    parties = np.concatenate([c["debtor"], c["creditor"]])
    return offline_events(parties, np.concatenate([c["day"], c["day"]]), np.concatenate([c["offline"], c["offline"]]))


def arch_C(s, c, minutes, pm=False, frictionless=False):
    L = Ledger(minutes)
    period = int(s.settle_period_h * 3600)
    if frictionless:
        rel = c["t1"].copy()
        verif = "none (theoretical control)"
    else:
        rel = chain_release(round_up(c["t1"], period), s) + np.where(c["offline"], offline_delay(s), 0)
        verif = "onchain_confirmed (clearing tx)"
    impaired = 0.0
    if pm:
        stock_series, impaired = portfolio_margin(s, c, by_router=False, minutes=minutes, series=True)
        L.k[("traders", "margin_pm")] = np.concatenate([[stock_series[0]], np.diff(stock_series), [-stock_series[-1]]])
        L.verif[("traders", "margin_pm")] = verif
    else:
        L.lock("traders", "margin", np.concatenate([c["m"], c["m"]]), np.concatenate([c["t0"], c["t0"]]),
               np.concatenate([rel, rel]), verif)
    rounds = clearing_rounds(s, c, restricted=not frictionless)
    chain_vb = 0
    if not frictionless:
        chain_vb = sum(11 + 57.5 * r["n_in"] + 43 * r["n_out"] for r in rounds if r["n_out"])
        chain_vb += vault_offline_events(c) * EXIT_VB["vault"]
        chain_vb += (s.n_traders + s.n_makers) * 154 * s.horizon_days  # one vault top-up per party per day
        L.flat("traders", "exit_fee_reserve", (s.n_traders + s.n_makers) * EXIT_VB["vault"] * s.feerate * s.fee_reserve_multiple / SAT, "onchain_utxo", 0, rel.max())
        # Deficit carried to the next round keeps the creditor's claim locked one more period.
        for r in rounds:
            if r["deficit"] > 0:
                L.lock("traders", "deferred_claims", np.array([r["deficit"]]), np.array([r["t"]]), np.array([r["t"] + period]), verif)
    off_gross = float(c["owed"][c["offline"]].sum())     # offline obligations settle bilaterally, unnetted
    g = float(c["owed"].sum())
    n = sum(r["net"] for r in rounds) + off_gross
    return L, dict(chain_vb=int(chain_vb), release=rel, gross_settlement_btc=g, net_settlement_btc=n,
                   unserved_btc=float(sum(r["deficit"] for r in rounds[-1:])), deferred_btc=float(sum(r["deficit"] for r in rounds)),
                   rounds=len(rounds), impaired_claims_btc=impaired, verification=verif)


def arch_D(s, c, minutes):
    """C plus LP advances at maturity, Nova-verified clearing statements, BitVM3 settlement.

    Customers are paid (and, with advance_scope=all, get their margin back) at maturity by an
    LP over Lightning. The LP is reimbursed from the clearing vaults once the batch's Nova
    statement is proven and the BitVM3 challenge period has passed. Offline debtors' vaults are
    recovered through the unilateral path, extending the LP's lock.
    """
    L = Ledger(minutes)
    period = int(s.settle_period_h * 3600)
    batch = int(s.proof_batch_h * 3600)
    lp_release = (round_up(c["t1"], max(batch, period)) + int(s.proof_latency_h * 3600)
                  + (s.challenge_blocks + s.confirmations) * SEC_PER_BLOCK + np.where(c["offline"], offline_delay(s), 0))
    # Customer margin: released at maturity when advanced; otherwise as in C.
    cust_rel = c["t1"] if s.advance_scope == "all" else chain_release(round_up(c["t1"], period), s)
    L.lock("traders", "margin", np.concatenate([c["m"], c["m"]]), np.concatenate([c["t0"], c["t0"]]),
           np.concatenate([cust_rel, cust_rel]), "ln_settled (LP advance) - SIMULATED")
    adv = c["owed"] + (2 * c["m"] - c["owed"] if s.advance_scope == "all" else 0)
    L.lock("lp", "advance_in_flight", adv, c["t1"], lp_release, "simulated: needs proof + challenge expiry + vault spend")
    ser = L.series()[("lp", "advance_in_flight")]
    peak_adv = float(ser.max())
    L.flat("operator", "bitvm3_bond", s.bond_ratio * peak_adv, "onchain_utxo (bond escrow)", int(c["t1"].min()), int(lp_release.max()))
    L.flat("traders", "exit_fee_reserve", (s.n_traders + s.n_makers) * EXIT_VB["vault"] * s.feerate * s.fee_reserve_multiple / SAT, "onchain_utxo", 0, int(lp_release.max()))
    rounds = clearing_rounds(s, c, restricted=True)
    n_batches = int(math.ceil(s.horizon_days * 24 / max(s.proof_batch_h, s.settle_period_h)))
    chain_vb = sum(11 + 57.5 * r["n_in"] + 43 * r["n_out"] for r in rounds if r["n_out"])
    chain_vb += n_batches * 300 + n_batches * s.challenge_prob * (2400 + 93)
    chain_vb += vault_offline_events(c) * EXIT_VB["vault"] + (s.n_traders + s.n_makers) * 154 * s.horizon_days
    proof_usd = n_batches * s.guest_a_gpu_h * s.gpu_usd_per_h
    proof_btc = proof_usd / s.btc_usd
    return L, dict(chain_vb=int(chain_vb), release=cust_rel, lp_release=lp_release, gross_settlement_btc=float(c["owed"].sum()),
                   net_settlement_btc=sum(r["net"] for r in rounds) + float(c["owed"][c["offline"]].sum()), unserved_btc=0.0, deferred_btc=float(sum(r["deficit"] for r in rounds)),
                   proof_batches=n_batches, proof_cost_btc=proof_btc, peak_lp_advance_btc=peak_adv,
                   verification="customer: ln_settled (simulated); LP: proof+challenge (simulated)")


def portfolio_margin(s, c, by_router, minutes, series=False):
    """Pre-maturity portfolio margin with variation margin every remargin_min minutes.

    Collateral per trader (per router if by_router) = |net notional|/(L P) + mark-to-market
    loss + buffer. A defaulting trader stops meeting calls at a random time; claims due from it
    later are paid only from collateral held at default. Returns (stock BTC-days or series,
    impaired claims BTC). Impaired claims are payouts enforceable under per-contract margin and
    not under this rule.
    """
    rng = np.random.default_rng(s.seed + 7)
    grid = np.arange(0, minutes, s.remargin_min, dtype=np.int64)
    P = c["P_path"][grid]
    key = (lambda p: p * 100 + c["router"]) if by_router else (lambda p: p)
    rows = np.concatenate([key(c["long"]), key(c["short"])])
    sgn = np.concatenate([np.ones(c["n"]), -np.ones(c["n"])])
    q = np.concatenate([c["q"], c["q"]])
    P0 = np.concatenate([c["P0"], c["P0"]])
    a = np.searchsorted(grid * 60, np.concatenate([c["t0"], c["t0"]]), side="left")
    b = np.searchsorted(grid * 60, np.concatenate([c["t1"], c["t1"]]), side="left")
    ukeys, ridx = np.unique(rows, return_inverse=True)
    G = len(grid)
    net = np.zeros((len(ukeys), G + 1))
    np.add.at(net, (ridx, a), sgn * q)
    np.add.at(net, (ridx, b), -sgn * q)
    net = np.cumsum(net, 1)[:, :G]
    inv0 = np.zeros((len(ukeys), G + 1))           # sum sgn*q/P0 of open contracts (inverse MTM)
    np.add.at(inv0, (ridx, a), sgn * q / P0)
    np.add.at(inv0, (ridx, b), -sgn * q / P0)
    inv0 = np.cumsum(inv0, 1)[:, :G]
    gross = np.zeros((len(ukeys), G + 1))
    np.add.at(gross, (ridx, a), q)
    np.add.at(gross, (ridx, b), -q)
    gross = np.cumsum(gross, 1)[:, :G]
    mtm = inv0 - net / P                           # BTC P&L of open book at current price
    req = np.abs(net) / (s.leverage * P) + np.maximum(-mtm, 0) + s.pm_buffer * gross / (s.leverage * P)
    stock = req.sum(0)
    # Default: collateral frozen at the last call before default; later losses beyond it impaired.
    dflt = rng.random(len(ukeys)) < s.default_prob
    t_def = rng.integers(0, G, len(ukeys))
    impaired = 0.0
    for i in np.flatnonzero(dflt):
        held = req[i, t_def[i]]
        loss_need = np.maximum(-mtm[i, t_def[i]:], 0)
        impaired += float(max(loss_need.max() - held, 0.0))
    if series:
        full = np.repeat(stock, int(s.remargin_min))[:minutes]
        return full, impaired
    return float(stock.mean() * s.horizon_days), impaired


# ---------------------------------------------------------------------------------- driver

def run(s: Scenario, regimes: dict, cache: Path | None = None) -> dict:
    rng = np.random.default_rng(s.seed)
    trade_minutes = int(s.horizon_days * 1440)
    # Accounting window: every contract's whole life plus the longest release delay.
    slack_blocks = s.to_self_delay_blocks + s.challenge_blocks + 2 * s.confirmations
    minutes = trade_minutes + int(s.maturity_h * 60) + int(max(s.settle_period_h, s.proof_batch_h) * 60 + s.proof_latency_h * 60) \
        + slack_blocks * SEC_PER_BLOCK // 60 + 60
    px, d = price_path(s, regimes, rng, minutes, cache)
    tr = trades(s, d, rng, trade_minutes)
    c = contracts(s, tr, px, rng)
    c["P_path"] = px
    if s.price_mode == "empirical":
        s.btc_usd = float(np.median(px))
    out = dict(scenario=asdict(s), contracts=c["n"], matched_btc=c["V_btc"], gross_obligation_btc=float(c["owed"].sum()),
               unenforceable_shortfall_btc=float(c["shortfall"].sum()), arch={})
    arms = {
        "A": lambda: arch_A(s, c, minutes),
        "B": lambda: arch_B(s, c, minutes),
        "B_pm": lambda: arch_B(s, c, minutes, pm=True),
        "C": lambda: arch_C(s, c, minutes),
        "C_pm": lambda: arch_C(s, c, minutes, pm=True),
        "D": lambda: arch_D(s, c, minutes),
        "E": lambda: arch_C(s, c, minutes, frictionless=True),
        "E_pm": lambda: arch_C(s, c, minutes, pm=True, frictionless=True),
    }
    for name, f in arms.items():
        L, meta = f()
        summ = L.summary()
        rel = meta.pop("release")
        lp_rel = meta.pop("lp_release", None)
        reuse = (rel - c["t1"]) / 3600
        w = 2 * c["m"]
        meta["reuse_delay_h"] = dict(mean_weighted=float((reuse * w).sum() / w.sum()), p50=float(np.median(reuse)),
                                     p99=float(np.quantile(reuse, 0.99)), max=float(reuse.max()))
        if lp_rel is not None:
            lr = (lp_rel - c["t1"]) / 3600
            meta["lp_recovery_delay_h"] = dict(p50=float(np.median(lr)), p99=float(np.quantile(lr, 0.99)))
        out["arch"][name] = dict(**summ, **meta)
    economics(s, out)
    return out


def economics(s: Scenario, out: dict):
    """Customer and provider cost decomposition, fee ceiling vs baseline A (Section 3 of the note)."""
    V = out["matched_btc"]
    days = s.horizon_days
    for name, a in out["arch"].items():
        by = a["by_owner"]
        cap = {o: sum(x["btc_days"] for x in cats.values()) for o, cats in by.items()}
        rate = {"traders": s.funding_rate, "lp": s.lp_rate, "operator": s.lp_rate, "router_operators": s.lp_rate}
        fund = {o: rate.get(o, s.lp_rate) * v / 365 for o, v in cap.items()}
        chain_btc = a["chain_vb"] * s.feerate / SAT
        cust_chain = chain_btc if name in ("A", "B", "B_pm") else 0.0   # channel opens/closes borne by users
        prov_chain = chain_btc - cust_chain
        a["capital_btc_days_by_owner"] = cap
        a["funding_cost_btc"] = fund
        a["customer_cost_btc"] = fund.get("traders", 0.0) + cust_chain
        a["provider_cost_btc"] = (sum(v for o, v in fund.items() if o != "traders") + prov_chain + a.get("proof_cost_btc", 0.0))
        a["system_cost_btc"] = a["customer_cost_btc"] + a["provider_cost_btc"]
        a["capital_duration_days"] = a["btc_days"] / V
        a["system_cost_bps"] = 1e4 * a["system_cost_btc"] / V
    base = out["arch"]["A"]
    for name, a in out["arch"].items():
        headroom = base["customer_cost_btc"] - a["customer_cost_btc"]
        a["fee_ceiling_bps_vs_A"] = 1e4 * headroom / V
        a["provider_cost_bps"] = 1e4 * a["provider_cost_btc"] / V
        a["fee_feasible_vs_A"] = headroom >= a["provider_cost_btc"]
        a["surplus_bps_vs_A"] = 1e4 * (base["system_cost_btc"] - a["system_cost_btc"]) / V
        saved = base["btc_days"] - a["btc_days"]
        a["capital_btc_days_saved_vs_A"] = saved
        a["fee_ceiling_sat_per_btc_day_saved"] = (headroom * SAT / saved) if saved > 0 else None
