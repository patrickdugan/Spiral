from pathlib import Path
import sys


root = Path(sys.argv[1]) / "prover-ui"
edits = {
    "web/app.js": [
        (
            "A holder claimed a dedicated reserve while the mint was offline. The full policy still needs to make a normal Cashu redemption and a reserve payout consume the same claim.",
            "A regtest melt consumed the original Cashu proofs and funded a reserve for the holder. The mint must accept that initial melt. The full policy still needs a funded exit when the mint refuses before funding.",
        ),
        (
            "A shared consumption rule for normal melts and fallback spends remains open.",
            "That run used a separately funded reserve.",
        ),
        (
            "      {id:'ark-proof',label:'Ark Nova",
            """      {id:'melt-reserve-demo',label:'Fund the holder reserve by melting Cashu',
        status:'Verified regtest settlement',done:true,
        detail:'CDK consumed six Cashu proofs to fund a 24,000-sat reserve and rejected reusing them. Core paid 23,750 sats to the holder after six blocks with the mint offline.'},
      {id:'ark-proof',label:'Ark Nova""",
        ),
    ],
    "tests/eta_model.cjs": [
        (
            "  assert.equal(road.friday.find(item=>item.id==='refusal-demo').done,true);",
            """  assert.equal(road.friday.find(item=>item.id==='refusal-demo').done,true);
  assert.equal(road.friday.find(item=>item.id==='melt-reserve-demo').status,'Verified regtest settlement');""",
        ),
    ],
}
updates = {}
for name, replacements in edits.items():
    path = root / name
    encoded = path.read_bytes()
    newline = "\r\n" if b"\r\n" in encoded else "\n"
    source = encoded.decode("utf-8").replace("\r\n", "\n")
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError(f"unexpected source in {name}")
        source = source.replace(before, after)
    updates[path] = source.replace("\n", newline).encode("utf-8")
for path, data in updates.items():
    path.write_bytes(data)
