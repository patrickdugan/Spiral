# CBM-SHZ-01: settlement capital under decentralized SHZ execution

Registered in `paper/shz_clearing_rent.md` §6; operational spec `SPEC.md`; ledger `LEDGER.md`; paper section `paper/tex/rent.tex`.

```
python -m pip install -r requirements.txt
python cbm/calibrate.py --cache <SHZ_LV cache> --output data/lighter_regimes.json   # needs the local Lighter trade cache
python run.py                      # synthetic cells (deterministic); add --empirical with SHZ_LV_CACHE set
python commercial.py               # duals, pooling, fragmentation, services
python figures.py                  # paper/tex/figs_rent/*.pdf
python -m pytest -q tests && python verify.py
```

No network, wallet or live order is used. All capital releases are simulated and tagged with the mechanism that would verify them.
