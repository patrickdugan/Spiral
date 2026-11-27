# CBM-SHZ-01: settlement capital under decentralized SHZ execution

Registered in `paper/shz_clearing_rent.md` §6; operational spec `SPEC.md`; ledger `LEDGER.md`; paper section `paper/tex/rent.tex`.

```
python -m pip install -r requirements.txt
python cbm/calibrate.py --cache <SHZ_LV cache> --output data/lighter_regimes.json   # needs the local Lighter trade cache
python run.py                      # synthetic cells (deterministic); add --empirical with SHZ_LV_CACHE set
python commercial.py               # duals, pooling, fragmentation, services
python figures.py                  # paper/tex/figs_rent/*.pdf
python -m pytest -q tests && python verify.py
python regtest/clearing_release_regtest.py --bitcoind <bitcoind>     # clearing release, reuse, CSV exit
python dlc/run_regtest.py --bitcoind <bitcoind>                      # oracle-attested DLC release + LP reimbursement
python dlc/oracle_dlc.py --chain testnet4 ...                        # same flow on Testnet4 (broadcasts; approved campaign cbm-shz01-dlc01)
```

The simulator uses no network or wallet; its capital releases are simulated and tagged with the mechanism that would verify them. The regtest harnesses run an isolated Bitcoin Core node. Only `dlc/oracle_dlc.py --chain testnet4` broadcasts, on Testnet4, under the approved campaign ID; oracle and leaf secrets stay in its local run directory and are never committed.
