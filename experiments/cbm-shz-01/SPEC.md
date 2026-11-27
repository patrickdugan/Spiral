# CBM-SHZ-01 registered experiment specification (operational, v1)

Registered in `paper/shz_clearing_rent.md` §6 (PR #21, 26cc5b6). This file fixes the
operational choices used for the run of 2026-11-25. It was written before the sweeps ran;
the base-cell smoke run (2-day horizon) was inspected first and led to three corrections
recorded in `LEDGER.md` (trade-size calibration, offline events per party-day, offline
obligations in gross/net totals).

## Demand and prices
- Source: public Lighter BTC trades (AWS public blockchain dataset), per-second cache from
  SatsHedgeZero `research/latency_value/trades_daily.py`, 2026-09-16..11-21 (67 days).
  `cbm/calibrate.py` commits per-day aggregates only (one-minute volatility and tails,
  288-bucket intensity profile, mean trade size, buy share); no price path.
- Regimes: calm / median / volatile = lowest / median / highest one-minute volatility day.
- Synthetic paths: Student-t one-minute returns with the regime's sigma and kurtosis
  (deterministic per seed). Empirical cell: local replay of the median-day week.
- Directions and identities are not in the data: 200 traders (Pareto activity), biases with
  common-sign share (1+rho)/2, persistence 0.6; 8 makers; 4 routers (mesh or star).

## Contracts
Fixed-maturity inverse BTC/USD, margin q/(L P0) per side, payoff clipped to [-m, m] (DLC
collateral bound); obligation debtor -> creditor at maturity. Offline: per (party, UTC day)
with probability `offline_frac`; offline settlements use the unilateral path
(to_self_delay 144 + 3 confirmations).

## Architectures
A bilateral LN-DLC (pair channels at peak concurrent margin); B router-local netting
(trader-router channels at peak margin + router directional stock = running max of the
trader's cumulative net receipts per channel); C UTXORef multilateral clearing (exact
margins, hourly rounds, restricted payout graph by max flow, release at round + 3 conf);
D = C + LP advances at maturity (scope all/payouts), reimbursement after proof latency 3 h +
challenge period + confirmations, operator bond 0.5 x peak advance, Nova-in-SP1 proof at
3 GPU-h x $1.50 per batch, 300 vB claim per batch, Assert+Disprove with p=0.01; E frictionless.
Portfolio-margin rows B_pm, C_pm, E_pm: |net|/(L P) + MTM loss, 5-min variation margin,
2% defaulting traders; impaired claims reported.

## Measures (per architecture)
Peak locked BTC, integrated BTC-days by owner and category with verification class,
capital duration K/V, reuse delay distribution, LP recovery delay, gross and net settlement
flow, chain vB, proof cost, customer cost, provider cost, fee ceiling vs A (bp and sat per
BTC-day saved), surplus, feasibility, unserved/deferred amounts, impaired claims.

## Sweeps (one at a time around base; base over seeds 1-3, others seed 1)
regime; imbalance_corr {0, .3, .7, 1}; leverage {2, 5, 10, 20}; maturity {1, 24, 168 h};
settlement period {0.25, 1, 6, 24 h}; topology {mesh, star}; payout edge density {1, .5, .25};
vault budget {1, .9, .7}; offline {0, .05, .2}; funding {0.25, 1, 5, 10 %}; fee rate
{2, 10, 50, 200 sat/vB}; proof batch {0.25, 1, 6, 24 h}; challenge {6, 36, 144, 1008 blocks};
advance scope {all, payouts}; volume {$1M, $20M, $100M/day}; routers {1, 4, 16}.

## Pass conditions (from §6 of the note)
Commercial hypothesis passes for an architecture when: positive net resource surplus vs A at
equal enforceable claims (impaired = 0), positive fee headroom after provider cost, and the
result holds on the volatile regime and the empirical replay. Portfolio-margin rows cannot
pass while they impair claims. Every release is SIMULATED; a row is "verified" only when the
named mechanism has been observed on Testnet4.
