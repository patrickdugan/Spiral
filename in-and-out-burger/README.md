# In-and-Out-Burger

A payment goes **in** to a pre-programmed Bitcoin address. A zero-knowledge proof shows it
confirmed. Sats come **out** to whoever sent it, in an amount set by the size of the payment.

The proof is the nova-bitvm3 **M16** final proof (garbled-snark-verifier `nova-bitvm3/m16`): a
Nova proof of the header chain from a pinned starting state, verified inside SP1, plus an SPV
payment under its tip, wrapped under BLAKE3 (`m13`). The default desk policy pins genesis; the
testnet4 bonded-payout demonstration below pins checkpoint 160,000. The burger never runs Nova. It checks the final
proof with `kan-payment-gate` (UTXO-Ref `key-agent-net/distributed/payment-gate`, which links
`m13-verify`), then reads the proven statement. In a BitVM3 setting, the same final verifier is
the M14 garbled circuit.

## Is it possible?

Yes, as an operator-run desk, and that is what this folder builds and tests. A payout from a
BitVM3 vault with no operator trust is not built yet; [What is missing](#what-is-missing-for-a-trustless-bitvm3-refill)
lists what it needs.

- **Pre-programmed address.** The menu fixes one address. M16 commits SHA-256 of the paid
  output's script, and the desk requires that hash and the script bytes to match.
- **ZK proof of the payment.** M16 proves the output exists, with `confirmations` blocks under a
  proof-of-work chain from genesis. The desk also needs a chainwork floor: a valid chain is not
  necessarily the heaviest one.
- **Send sats to the sender.** Bitcoin has no sender field. The desk reads the sender from the
  payment transaction (see [Who is the sender](#who-is-the-sender)) and binds every byte it reads
  to the proven block. It pays a fresh key derived from the sender's, not the address they
  paid from.
- **Dynamic amount.** The payout follows a price list: a rate per tier of payment size, a flat
  fee, a cap, and Core's dust limits.

## What an order is

| Part | Size | What it is |
| --- | --- | --- |
| statement | 1,292 bytes | the M16 guest's committed public values: guest A's chain record plus the `PAY1` payment record |
| final proof | ~1.1 MB | the M16 proof, wrapped under BLAKE3 v2 (`m13 wrap-only-v2`); it commits SHA-256 of the statement |
| payment tx | hex | with or without its witness |
| sender proof | ~4.5 KB JSON | only for a witness spend: header B, the coinbase with its branch, the payment's txid and wtxid branches |

The desk checks them in this order. Each refusal has its own reason code:

1. **The statement parses.** This mirrors `kan-payment-gate`'s `statement.rs`; the desk compares
   its parse with the gate's whenever the gate is available.
2. **The proof verifies.** `kan-payment-gate check` verifies it in `m13_verify::verify_final`'s
   order: wrap key, BLAKE3 STARK, exit code, M16 program key, recursion root, statement digest.
   The policy it checks is derived from the menu.
3. **The menu's policy holds** (`iob/policy.py`, the same rules as the gate's): network,
   k = 1, genesis z0 pin and genesis hash, Nova key, chainwork floor, confirmations, the
   pre-programmed script, minimum value.
4. **The transaction matches the proof.** It hashes to the proven txid, and output `vout` is the
   proven script and value.
5. **The sender is resolved**, with the witness bound to the proven block when the rule needs it,
   and for a one-key sender the payout key is derived from theirs ([The payout key](#the-payout-key)).
6. **The order is priced.**
7. **The journal is checked.** An outpoint is served once (`iob/ledger.py`, fsync'ed JSON lines,
   with reserved, paid and released states).
8. **The desk pays.** It reserves the outpoint, then Core funds and signs the payout. The desk
   checks that the transaction pays the priced amount exactly once, runs `testmempoolaccept`,
   and broadcasts. A mainnet payout is broadcast only with `--allow-mainnet`; without it the
   desk stops at a signed transaction.

The payout carries `OP_RETURN "IOBP" || in-txid || vout`, so each payout names the payment it
answers and is itself provable by M16.

An order without a proof is refused (`proof_required`). `--allow-unproven` admits one for a
regtest payout only (`unproven_needs_regtest` otherwise). The unproven replay below uses it; the
proven replay does not.

## Who is the sender

The desk tries two rules, in this order:

1. **Declared return script.** An output `OP_RETURN "IOB1" || scriptPubKey` names the payout
   script. The txid covers it, so it needs no sender proof. Exactly one such output is allowed.
   A Taproot spender must use this rule.
2. **The script that input 0 spent**, rebuilt from what the spend reveals:
   - P2PKH: the key in scriptSig;
   - P2SH: the redeem script;
   - P2WPKH, P2WSH, and both wrapped in P2SH: the witness. For the wrapped forms, the
     witness must also match the program in scriptSig.

   Taproot key-path spends reveal no key, and script-path spends are not implemented; both are
   refused. Bare P2PK and bare multisig spends are refused too, since they do not reveal the
   script.

The txid does not cover a witness. For a witness spend the sender proof binds it, and the desk
checks four things:
- header B hashes to the proven block hash;
- the coinbase and the payment are both in that block, with equal branch depths and no 64-byte
  transactions;
- the coinbase carries the BIP141 witness reserved value;
- the payment's wtxid is under the block's witness commitment.

A spender who builds an unusual script, such as a P2WSH whose witness script looks like a key,
can make rule 2 name a script they did not spend. That only redirects their own payout. Nobody
else can change a confirmed transaction or its committed witness.

### The payout key

Under rule 2 the desk does not pay the sender's old address again. When input 0 revealed one
key P (P2PKH, P2WPKH, or P2WPKH in P2SH), it pays the same script type over a key derived from
P and the payment ([`iob/payout_key.py`](iob/payout_key.py)):

```
P' = P + t·G,   t = int(tagged_hash("IOB/payout-key", in_txid || in_vout || P)) mod n
```

`in_txid` is in internal byte order, `in_vout` is a little-endian u32, and P is serialized as
the spend revealed it (33 or 65 bytes). The payer's key for P' is p + t mod n.

- The payer puts nothing extra in the payment and receives at a fresh address for every
  payment.
- Every input to t is public and bound by the proof, so anyone can recompute P' from the
  chain, including a later proof of the payout leg.
- The payer recovers the key with
  `python -m iob payout-key --in-outpoint TXID:VOUT --type p2wpkh --network mainnet --wif-stdin`,
  which reads the WIF of the key they paid from on stdin and prints the derived WIF and a
  descriptor (`wpkh(…)`, `sh(wpkh(…))` or `pkh(…)`) to import into Core or any wallet that
  takes one. No wallet finds P' on its own.

A declared return script (rule 1) is paid as declared. A sender that revealed a script rather
than one key (P2SH, P2WSH, P2SH-P2WSH) is paid at that script; such a sender avoids reuse with
`IOB1`. A revealed key that is not on secp256k1 is refused (`sender_key_invalid`). Menu
`out.payout_key` is `derived` (the default) or `spent`, which pays the old script as before.

## Pricing

Menu `out` section: `tiers` (`min_value_sats`, `rate_ppm`), `fee_sats`, `max_payout_sats`.

```
payout = min(value × rate_ppm(highest tier reached) / 10^6 − fee_sats, max_payout_sats)
```

An order below `in.min_value_sats` is refused, and so is a payout below the dust limit for the
sender's script type.

The replay menu ([`menus/m16-mainnet-replay.json`](menus/m16-mainnet-replay.json)) pays 1:1
from 10,000 sats and 1.01:1 from 500,000 sats, less 1,000 sats, capped at 2,000,000. The proven
940,000-sat payment earns 948,400 sats.

## The test: replaying the M16 mainnet payment

The M16 mainnet run proves this payment:
- `a652ab0c…0045:0`: 940,000 sats to `bc1q3czxrv2eptks5u37yxkpdayrzlxm965ktma3cu`, in block
  975,067, 6 confirmations under tip 975,072;
- statement `cae6068f…c869`, from the CPU execution (34,055,622,753 instructions).

The replay menu pre-programs that address. The desk pays the sender on a private regtest
chain: scripts do not depend on the network, so the payout is spendable by the same key, and no
real sats move.

The sender is input 0's P2WPKH key `0254bb09…7b3b`, which spent `bc1qcfgpeswyzk9sh9qxxa53lqrnd92whjy2gl8awg`.
mempool.space reports the same address for the spent output (`862239f7…876e:1`, 950,000 sats).
The desk pays the derived key `02af01bc…501f` (t = `51de31df…fc7d`) instead: `bc1qf33qwl5845afqf28e9jedrvjfajtgg0g8lal8q`
on mainnet, `bcrt1qf33qwl5845afqf28e9jedrvjfajtgg0g0slpt6` on regtest.

Fixtures ([`fixtures/m16-mainnet`](fixtures/m16-mainnet)) come from the M16 inputs:

| File | Source |
| --- | --- |
| `statement.bin` | WSL `/root/m16-main/public.bin`, SHA-256 `cae6068f…c869` |
| `payment-tx.hex` | `python -m iob tx`, run on `block.bin` (block 975,067 from mempool.space, SHA-256 `41600bb8…aae8`; its header matches Core's) |
| `sender-proof.json` | `python -m iob sender-proof`, run on the same block |

### Proven order (2026-11-11)

The final proof is the M16 mainnet run's BLAKE3 v2 wrap, proved on the laptop GPU on
2026-11-11:

| | |
| --- | --- |
| file | `m16-wrap-blake3-v2.bin`, 1,099,173 bytes, SHA-256 `97871e86cd0809e4b21d744343c43737cb56073f65e671da727e9db6051326e3` |
| where | garbled-snark-verifier `nova-bitvm3/m13/fixtures/`; public in patrickdugan/zk-rusto-no-bitcoino at `integrations/bitvm3-nova/m13/fixtures/` (c85ee60, same SHA-256) |
| commits | statement `cae6068f…c869` (equal to `fixtures/m16-mainnet/statement.bin`), program key `dfc68a5d…cb60`, recursion root `7487c217…f257`, wrap key `d42c63e3…b0d7` |
| gate | `kan-payment-gate` from UTXO-Ref fc69bba, binary SHA-256 `2344753b…2f56` |

```sh
python3 scripts/regtest_replay.py --proof /root/m16-main/m16-wrap-blake3-v2.bin --out results/regtest-replay-proven.json
```

Run in WSL with Bitcoin Core 31.1 regtest and `payout_key: derived`: 16 of 16 steps passed in
40.4 s, with no `--allow-unproven`. The record is [`results/regtest-replay-proven.json`](results/regtest-replay-proven.json).

| Step | Result | Time |
| --- | --- | --- |
| serve the M16 order with the real wrap (`kan-payment-gate check`, then the desk's checks) | served, `proof: verified`: 948,400 sats to the derived key, `bcrt1qf33qwl…slpt6`, 192 vB, 384 sats fee | 0.591 s |
| the chain after one block | the derived script holds exactly 948,400 sats and the script the payer spent from holds 0 (`scantxoutset`); the payout carries the IOBP link | |
| the same order again | `already_served` | 0.361 s |
| the same order under a `payout_key: spent` menu | accepted, priced to the old script `bcrt1qcfgp…qs9rzj` | 0.404 s |
| a fresh key of each one-key type (P2WPKH, P2SH-P2WPKH, compressed and uncompressed P2PKH), derived with the real in-outpoint | for all four, Core's `deriveaddresses` on the derived WIF gives the desk's address; the desk pays 50,000 sats to each; a Core wallet that imported only the four derived WIFs sweeps all four in one transaction, confirmed | 6.199 s |
| a forged witness with the same txid | `sender_proof_witness` | 0.310 s |
| a menu pre-programmed with another address | `script_not_registered` (from the gate's policy) | 0.249 s |
| a chainwork floor one above the proven tip | `chainwork_below_floor` (from the gate's policy) | 0.254 s |
| no proof and no `--allow-unproven` | `proof_required` | 0.000 s |
| guest A's real final proof offered for the M16 statement | `proof_wrong_program` | 0.370 s |
| the wrap with one bit flipped at its middle byte | `proof_rejected` (PCS root mismatch) | 0.292 s |
| the wrap's committed digest re-pointed at a statement claiming 1,880,000 sats, offered with that statement | `proof_rejected` (`GkrVerificationFailed(Pow)`) | 0.071 s |
| the wrap with its last byte cut | `proof_malformed` | 0.060 s |
| the real wrap with the statement's value doubled to 1,880,000 sats | `statement_digest_mismatch` | 0.411 s |
| the real wrap with another real M16 statement (block 170 run, `67a9deb9…`) | `statement_digest_mismatch` | 0.257 s |

The 16 steps are the 15 rows above plus a check that the order's proof state is `verified`.

The first proven run (00bae56, `payout_key` before it existed, so the old script was paid)
passed 14 of 14 in 8.8 s, with each gate step at 0.03 s. Run alone under `/usr/bin/time`, the
gate verifies the 1.1 MB wrap in 0.03 s with 5.5 MB peak RSS. The 2026-11-11 derived run's steps
took about ten times as long, with the laptop shared with other jobs (WSL load average 4.35 on
20 threads when it finished). The committed digest sits at byte 240 of the wrap, one byte per
little-endian u32; the replay checks that before it re-points it.

### Unproven replay (2026-11-10)

`scripts/regtest_replay.py`, run in WSL with Bitcoin Core 31.1 regtest and the
`kan-payment-gate` binary built from UTXO-Ref fc69bba: 8 of 8 steps passed in 12 s.
The record is [`results/regtest-replay.json`](results/regtest-replay.json).

| Step | Result |
| --- | --- |
| serve the M16 order (unproven; statement cross-checked with `kan-payment-gate inspect`) | served: 948,400 sats to `bcrt1qcfgp…qs9rzj`, 192 vB, 384 sats fee |
| the chain after one block | the sender's script holds exactly 948,400 sats (`scantxoutset`); the payout carries the IOBP link |
| the same order again | `already_served` |
| a forged witness with the same txid | `sender_proof_witness` |
| a menu pre-programmed with another address | `script_not_registered` |
| a chainwork floor one above the proven tip | `chainwork_below_floor` |
| no proof and no `--allow-unproven` | `proof_required` |
| guest A's real final proof offered for the M16 statement (`kan-payment-gate check`) | `proof_wrong_program` |

Unit tests (`tests/`, 61) run against the real statement, the real transaction and the real
sender proof, with each binding tampered in turn, and against synthetic blocks for the other
sender rules (P2PKH, P2SH-P2WPKH, P2SH-P2WSH, P2WSH, declared return, Taproot refusals), each
paid at its derived key or, for a script sender, at its script. `test_payout_key.py` covers the curve (generator multiples, negation, point
encodings, off-curve refusals), WIF vectors, the tweak's binding to txid, vout and key encoding,
p + t against P + t·G for compressed and uncompressed keys, and the `payout-key` command.
On 2026-11-11: 61 passed in 13.5 s (Python 3.12, Windows), 9.4 s of it the pure-Python
RIPEMD-160 vectors. The unproven replay with the 2026-11-11 script passed 11 of 11; the new steps
are the `proof: absent` check, the spent-key menu and the sweep.

## Commands

```sh
python -m pytest -q tests                                  # unit tests, any OS, standard library only
python3 scripts/regtest_replay.py --out results/x.json     # WSL: needs bitcoind and kan-payment-gate
python3 scripts/regtest_replay.py --proof WRAP.bin --out results/x.json   # proven, plus tamper refusals
python -m iob inspect --statement S                        # decode an M16 statement
python -m iob policy --menu M                              # the kan-payment-gate policy a menu implies
python -m iob tx --block BLOCK.bin --txid T                # the payment tx, with witness, from a raw block
python -m iob sender-proof --block BLOCK.bin --txid T      # the sender proof for it
python -m iob order --menu M --statement S --tx T.hex [--sender-proof SP.json] --proof P \
    --ledger served.jsonl [--pay --rpc-url URL --rpc-cookie COOKIE --wallet burger]
python -m iob payout-key --in-outpoint TXID:VOUT --type p2wpkh --network N --pubkey HEX
                                                           # the derived payout address for a payment
python -m iob payout-key --in-outpoint TXID:VOUT --type p2wpkh --network N --wif-stdin < key.wif
                                                           # the payer's derived WIF and descriptor
```

`order` prints one JSON line. It exits 0 when the order is accepted or served and 1 when it is
refused. The menu's `gate.argv` is the gate command line; set `"paths": "wsl"` to call the
Linux gate from Windows through `wsl.exe`.

## A live order

1. Write a menu with your address as `in.address` (`mainnet`, or `testnet4`, which M16 and the
   gate are also pinned for). Take `min_tip_chainwork` from your own node's `getblockheader`.
   Set `out.network` to the payout chain.
2. The customer pays the address. A one-key spender is paid at the derived key and recovers it
   with `iob payout-key --wif-stdin`. To name the payout script explicitly, which a Taproot
   spender must do, the payment includes `OP_RETURN "IOB1" || scriptPubKey`.
3. Prove it:
   - extend the Nova chain past the payment block plus the confirmations you require
     (`nova-chain resume`);
   - build the payment input (`m16/fetch_mainnet.py`);
   - run M16 on the GPU (about 5 GPU hours for a two-segment mainnet proof on the laptop);
   - wrap it (`m13 wrap-only-v2`).
4. `iob sender-proof` on the payment's block, then `iob order … --proof … --pay`, with the float
   in a Core wallet on the payout chain.

Orders settle in hours, not minutes, because the proof dominates.

## Demo page

https://patrickdugan.github.io/Spiral/in-and-out-burger/ shows the testnet4 order end to end:
- the payment to the burger address;
- the three bonded vaults: an honest claim, a tampered proof and a wrong statement;
- the Nova checkpoint segment and the M16 statement;
- the garbled M14 verdict for each claim;
- the payout to P′.

The page reads `site/data/demo.json` and asks mempool.space for live testnet4 confirmations, so
claims and payouts show up as they confirm. It recomputes t, P′ and the payout address in the
browser with its own secp256k1, SHA-256 and RIPEMD-160 code, and lists the counterexamples Bitcoin
Core refused. It runs on the trusted BitVM setup described below.

Refresh the data after the run writes new state, then push to main;
`.github/workflows/iob-pages.yml` copies `site/` to the `gh-pages` branch under
`in-and-out-burger/`:

```
python scripts/build_site_data.py --state results/testnet4-bitvm3
```

The builder reads only public state files: never `keys.json` or `m14-seeds.json`.
The completed page lists all seven claim/disprove/payout/sweep explorer links, the final checks,
and the derived-key spend. It uses the committed confirmation record when live explorer lookups
are unavailable, labels those counts as recorded, and gives live status priority when available.
For an in-progress run, pass its state directory instead of the completed public record.

## Testnet4 BitVM3 bonded payout (2026-11-14)

The public testnet4 demonstration is complete. M16 proves the header chain **from checkpoint
160,000 to tip 161,016**, plus the 11,600-sat burger payment in block 161,011. This is a
checkpoint-anchored proof, not a proof from genesis. The desk pins the checkpoint hash and
chainwork to its own node before presigning a graph for this order.

The proof's public-values SHA-256 is
`220205b4e5826bc0f3423abf39feb52c66bd4c081a1b617b85ce909c5719fc43`; its M16 program key is
`dfc68a5d579b86244a60ba0baee7852348cf0d2a3bb13910ebb95a3e625fcb60`.
The final BLAKE3 v2 wrap is included in [the public record](results/testnet4-bitvm3/), with
SHA-256 `f5123369c8795d698510955d33b22e9118f7206ef8622e2e679dab3833a24faa`. The native final verifier accepts it against the pinned statement.

| Instance | M14 verdict | Claim transaction | Outcome |
| --- | --- | --- | --- |
| honest | accept | `d61ddbb16944af5e090ed1994143e75a7777b0977efe6451ea53ce5d8a2a9056` | Payout after the window |
| tampered-proof | reject | `580c7d010b3e95f4e46bd4c5b92b5a29b30c5d2265078cc06ce4c85cd195dcce` | Disprove `b164f36bb5d61bf59ec6463a03f0f58af0dcded6c5749a57432d025606b1c0ee` |
| wrong-statement | reject | `1eefeeb8e67f2f15caef5ea93c895a46adcea707ad2e599b118850684683cd49` | Disprove `88676a6ddd796e4be09aa4caf24e5c32815beb71b6c403393943f2eb6f99d14c` |

Payment: `11c18d7c51cb6c20ece374bd3b70a09aa965d31dbb1ef3e3cd504277b301aa0e`. The honest vault paid **24,328 sats** to P′ at
`mwYxG4Qpth2KEEgFgwovHGGXvDbyD9xcJ2` in transaction `a2de74eacb4a1b52aac17a6e112df219da1fed043ca06cea8b03bc7b1cdbf9ac`.
The payer then spent that output using p′ = p + t in transaction `0fa328ab2447db50fe5eab0b479f78857846c9ee9f1d94ccb5f74bb898a9966e`.
Every broadcast in the record was confirmed when the final checks ran.

The tampered-proof instance flips one garbled input bit of the testnet4 proof; the wrong-statement
instance supplies the valid M16 mainnet proof to the testnet4 statement. Both evaluate to the
committed reject label and are disproved on chain. Bitcoin also refuses an early payout,
redirects to the old payer address or claimant, and disproves using the accept label or a random
label. Rejected counterexample transactions were probed with `testmempoolaccept`.

Checks: 78 Python unit tests; 11/11 isolated regtest graph checks; 14/14 statement checks;
11 guest mutations refused; 63/63 final testnet4 checks.
Each M14 setup, garbler and evaluator agrees on its ciphertext commitment and output-label hashes.
See [checks.json](results/testnet4-bitvm3/checks.json),
[summary.json](results/testnet4-bitvm3/summary.json), and
[the regtest record](results/bitvm3-regtest.json).

The demonstration retains FC03's T1 (garbling correctness without cut-and-choose), T2 (off-chain
input-label delivery), and T3 (a presigned graph, with the desk as committee of one). It signs
after the payment to fix P′ and does not demonstrate committee key deletion or trustless float
reimbursement. Private keys and garbling seeds are excluded from the public record.

## What is missing for a trustless BitVM3 refill

In this design the desk fronts every payout from its own float: once the proof checks out, the
operator pays. That is also how a BitVM bridge pays out. Presigned BitVM transactions fix their
outputs and amounts when the committee signs them, and the committee then deletes its keys, so
a vault cannot pay a recipient chosen later. The customer's address therefore never enters the
vault: the operator pays the customer, and the vault reimburses the operator.

The one address a graph fixes is the operator's reimbursement address, and it need not repeat:
derive graph i's key from an operator xpub at non-hardened index i, and have every committee
member re-derive it before signing. Choosing the payout inside the graph after setup would need a
covenant opcode (CTV with a template hash taken from the witness and fixed by a Winternitz
commitment the fraud proof checks; or CSFS, OP_CAT, OP_CHECKCONTRACTVERIFY). None is active on
mainnet.

Refilling the float from a BitVM3 vault without trusting the operator still needs three things:

The experimental graph here instead signs separately after the payment, fixes P′ at that
point, and pays P′ directly from the bonded vault. It demonstrates the claim/disprove/payout
mechanism; the general float-refill design above still requires the following work.

1. **Removing the demo's trust assumptions.** The claim graph is implemented in
   `iob/bitvm3.py`, exercised against Bitcoin Core by `scripts/bitvm3_regtest.py`, and driven
   on testnet4 by `scripts/bitvm3_testnet4.py`. It commits to one M14 instance and its statement;
   a reject label unlocks a disprove, while a presigned payout to P′ matures after six blocks.
   This demonstration retains FC03's T1 (correct garbling, without cut-and-choose), T2 (input
   labels handed over off-chain), and T3 (a presigned graph with the desk as a committee of
   one). Keys remain available in this demo; it does not demonstrate committee key deletion.
2. **A statement covering both legs.** The in-payment to the menu address, and the operator's
   payout to the sender, linked by IOBP. M16 proves one payment and does not apply the sender
   rule, so this needs a new guest that runs M16's check twice, plus the sender rule with its
   witness-commitment check and the payout key (one tagged hash and one secp256k1 multiply and
   add). A graph reimburses a fixed amount, so the vault is split into fixed-size UTXOs and the
   statement proves that the operator's payouts add up to at least the UTXO it claims.
3. **Latency the vault can tolerate.** About 5 GPU hours per mainnet proof, plus the challenge
   window.

### Who holds the committee keys

The graph is presigned by an n-of-n MuSig2 committee that then deletes its keys. Once every
member has signed, the graph can only be changed with all n keys, so one member who really
deleted is enough. The multiparty signing and key-deletion flow below is
not implemented by the committee-of-one demonstration.

- **The graph is a pure function.** Its inputs are the vault UTXO, the operator's xpub index, the
  M14 circuit hash, the timelocks and the fees. Each member rebuilds the graph and computes every
  sighash itself, and signs only those. A coordinator then cannot slip in a transaction the graph
  does not contain. Signing a sighash the coordinator hands over amounts to signing a theft.
- **Keys and nonces are fresh randomness, held only in RAM.** A key derived from a seed cannot be
  deleted, because the seed derives it again. MuSig2 key aggregation stops rogue-key attacks, so
  key generation only needs each member's own randomness to be sound. Every transaction in the
  graph is its own signing session and needs its own random nonce pair. Using a secret nonce
  twice leaks the key, and BIP327's deterministic signing is safe only for the last signer.
- **Funding comes last.** Each member checks the aggregated signatures on the whole graph before
  deleting. The depositor checks them before signing the deposit, so funds never sit behind a
  graph that is only partly signed.
- **Deletion cannot be proven, only made believable.** Three ways to back it:
  - the depositor or LP joins the committee and then trusts only itself;
  - a member runs an amnesic air-gapped signer that boots read-only, keeps keys in RAM and is
    powered off afterwards (airsign). Two MuSig2 rounds per transaction over QR codes is many
    scans for a graph with tens to hundreds of transactions;
  - members run attested TEEs from different vendors.
- **The damage has a bound.** Use a fresh committee for each graph and fixed-size vault UTXOs. A
  committee that colludes, or whose keys all leak, then opens one UTXO, not the vault.

Removing the committee needs a covenant that checks inputs as well as outputs. CTV fixes outputs
but not which other inputs a transaction spends, so it cannot hold the connector outputs the
disprove path depends on. BIP 448 (OP_TEMPLATEHASH from BIP 446 with OP_CHECKSIGFROMSTACK and
OP_INTERNALKEY, a draft) leaves out prevouts and amounts in the same way. With it, edges that only
fix outputs would need no presigned signatures, which cuts the number of MuSig2 sessions and
nonces. The committee would still sign every transaction that spends a connector. TXHASH or
OP_CHECKCONTRACTVERIFY could hold the connectors. None of these is active on mainnet.

## Layout

- `iob/btc.py`: hashes (including RIPEMD-160, which OpenSSL 3 may lack), transactions, Merkle
  branches, scripts, addresses.
- `iob/statement.py`: the M16 statement.
- `iob/policy.py`: the gate's policy rules.
- `iob/sender.py`: the sender rules and the sender proof.
- `iob/ec.py`: secp256k1 point arithmetic for the payout key.
- `iob/payout_key.py`: the derived payout key, WIF, and the payer's side.
- `iob/taproot.py`: BIP340 signatures, BIP341 script-path spends, and P2PKH signing.
- `iob/bitvm3.py`: the presigned vault, claim, disprove, and payout graph.
- `scripts/bitvm3_testnet4.py`: checkpoint/payment checks, M14 claim instances, counterexamples,
  payouts, payer sweeps, and public result recording; mainnet is refused.
- `scripts/bitvm3_regtest.py`: the isolated Bitcoin Core rehearsal of that graph.
- `scripts/fetch_testnet4.py`: header and payment inputs for the testnet4 proof.
- `site/` (`index.html`, `style.css`, `app.js`, `data/demo.json`): the demo page;
  `scripts/build_site_data.py` writes its data. `results/m14-claim-selftest.json`: `m14-claim`
  on the M16 mainnet proof.
- `iob/menu.py`: the menu and pricing.
- `iob/gate.py`: running `kan-payment-gate`.
- `iob/ledger.py`: the served-outpoint journal.
- `iob/rpc.py`: Core RPC.
- `iob/desk.py`: the order pipeline and payer.
- `iob/__main__.py`: the CLI.
- `menus/`, `fixtures/`, `scripts/regtest_replay.py`, `results/`, `tests/`.

Standard library only (Python 3.10 or later). The gate is GPL-3.0-only because it links
`m13-verify`, so it runs as a separate process.
## Experimental sibling-covenant proposal

The research-only [OP_CHECKSIBLINGVERIFY draft and executable adversarial model](research/checksiblingverify/README.md) explore replacing presigned connector-spending edges with a same-parent input check and fixed output templates. The design is unactivated, its crypto/setup predicates are idealized, and the funding and challenge assumptions are documented in the draft.
