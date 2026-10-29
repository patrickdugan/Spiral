# Stage 3: algorithmic shortcut concentration

**Evidence:** exact finite probability calculation, conditional on independent
block winners and fixed mining resources. This is general PoW research.

An attacker with baseline resource fraction `a` and private solver speedup
`s` wins a fraction `p = a*s / (1-a+a*s)` of independent races. The
critical speedup at which p reaches one half is `(1-a)/a`. For an attacker
with 10% of the baseline resources, that threshold is 9x.

Under an explicitly simplified model of `n` independent block winners,
the probability of a *strict* majority of wins is

`sum_{k=floor(n/2)+1}^n choose(n,k)*p^k*(1-p)^(n-k)`.

The implementation computes this as exact rational arithmetic, retaining
ties as non-majorities. A separate finite oracle enumerates all length-n
sequences over four equiprobable outcomes up to n=8. Tests additionally check
boundary values, monotonicity and odd/even tie handling.

Run from this folder:

```sh
python -m unittest discover -s pow-research -p 'test_*.py' -v
python pow-research/miner_asymmetry.py --blocks 21
```

**Interpretation:** Winning more than half of a fixed interval is not
equivalent to executing a chain reorganization or double-spend. This experiment
omits selfish mining, network delay, miner admission, retarget policy, pooled
work, capital constraints and price changes. The speedup applies uniformly to
every attempted proof in one family. Cross-family operation counters remain
incomparable. No energy or dollar thermocap estimate follows from this model.

Next: run a preregistered measured-work campaign on actual hardware, with a
native Primecoin verifier and verifier-cost distributions. Derive any security
cost from explicit attacker budgets, equipment cost and network model.
