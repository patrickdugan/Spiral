# Public topology input

This directory holds one locally extracted GML snapshot from the Harvard Dataverse dataset *Geolocated Lightning Network topology snapshots: a dataset covering 2019-2023* (DOI `10.7910/DVN/2OAVO6`, datafile `12510549`). The dataset contains 336 reconstructed public-gossip snapshots derived from the `lnresearch/topology` archive.

The full ZIP is 562,027,011 bytes. To avoid an unnecessary full download, the repository fetcher opens the remote ZIP with HTTP byte ranges and extracts only the selected member:

```powershell
python scripts/fetch_ln_snapshot.py --list
python scripts/fetch_ln_snapshot.py --member latest --output-dir data/topology
```

Raw `.gml.geo` files are ignored by Git. `snapshot_provenance.json` records the dataset DOI, Dataverse file ID, archive metadata, ZIP CRC, member size, and local SHA-256.

Public gossip describes topology and channel policy, not private directional balances. Experiments using this input must sample hidden balance ensembles and must not call the snapshot a complete view of the Lightning Network.
