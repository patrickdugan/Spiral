# In-and-Out-Burger

A payment goes **in** to a pre-programmed Bitcoin address. A zero-knowledge proof shows it
confirmed. Sats come **out** to whoever sent it, in an amount set by the size of the payment.

The proof is the nova-bitvm3 **M16** final proof (garbled-snark-verifier `nova-bitvm3/m16`): a
Nova proof of the whole header chain from genesis, verified inside SP1, plus an SPV payment
under its tip, wrapped under BLAKE3 (`m13`). The burger never runs Nova. It checks the final
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
  to the proven block.
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
5. **The sender is resolved**, with the witness bound to the proven block when the rule needs it.
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
regtest payout only (`unproven_needs_regtest` otherwise). That flag exists for the replay below,
because no M16 final proof exists yet.

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

The replay menu pre-programs that address. The desk pays the sender's script on a private
regtest chain: scripts do not depend on the network, so the payout is spendable by the same key,
and no real sats move.

The sender is input 0's P2WPKH key `0254bb09…7b3b`, giving `bc1qcfgpeswyzk9sh9qxxa53lqrnd92whjy2gl8awg`.
mempool.space reports the same address for the spent output (`862239f7…876e:1`, 950,000 sats).

Fixtures ([`fixtures/m16-mainnet`](fixtures/m16-mainnet)) come from the M16 inputs:

| File | Source |
| --- | --- |
| `statement.bin` | WSL `/root/m16-main/public.bin`, SHA-256 `cae6068f…c869` |
| `payment-tx.hex` | `python -m iob tx`, run on `block.bin` (block 975,067 from mempool.space, SHA-256 `41600bb8…aae8`; its header matches Core's) |
| `sender-proof.json` | `python -m iob sender-proof`, run on the same block |

### Results (2026-11-10)

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

Unit tests (`tests/`, 46) run against the real statement, the real transaction and the real
sender proof, with each binding tampered in turn, and against synthetic blocks for the other
sender rules (P2PKH, P2SH-P2WPKH, P2SH-P2WSH, P2WSH, declared return, Taproot refusals).

**Not yet run:** a *proven* order. The M16 mainnet GPU proof is running
(`/root/nb3-runs/m16-mainnet-t27`), and its BLAKE3 v2 wrap does not exist yet. When it does:

```sh
python3 scripts/regtest_replay.py --proof <m16-wrap-blake3-v2.bin> --out results/regtest-replay-proven.json
```

That run serves the order with `proof: verified` and no `--allow-unproven`.

## Commands

```sh
python -m pytest -q tests                                  # unit tests, any OS, standard library only
python3 scripts/regtest_replay.py --out results/x.json     # WSL: needs bitcoind and kan-payment-gate
python -m iob inspect --statement S                        # decode an M16 statement
python -m iob policy --menu M                              # the kan-payment-gate policy a menu implies
python -m iob tx --block BLOCK.bin --txid T                # the payment tx, with witness, from a raw block
python -m iob sender-proof --block BLOCK.bin --txid T      # the sender proof for it
python -m iob order --menu M --statement S --tx T.hex [--sender-proof SP.json] --proof P \
    --ledger served.jsonl [--pay --rpc-url URL --rpc-cookie COOKIE --wallet burger]
```

`order` prints one JSON line. It exits 0 when the order is accepted or served and 1 when it is
refused. The menu's `gate.argv` is the gate command line; set `"paths": "wsl"` to call the
Linux gate from Windows through `wsl.exe`.

## A live order

1. Write a menu with your address as `in.address` (`mainnet`, or `testnet4`, which M16 and the
   gate are also pinned for). Take `min_tip_chainwork` from your own node's `getblockheader`.
   Set `out.network` to the payout chain.
2. The customer pays the address. To name the payout script explicitly, which a Taproot
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

## What is missing for a trustless BitVM3 refill

In this design the desk fronts every payout from its own float: once the proof checks out, the
operator pays. That is also how a BitVM bridge pays out. Presigned BitVM transactions fix their
outputs when they are signed, so a vault cannot pay a recipient chosen later. The operator pays
first and claims afterwards. Refilling the float from a BitVM3 vault without trusting the
operator still needs three things:

1. **The claim transaction graph.** Claim, challenge and disprove transactions in which a
   challenger evaluates the M14 circuit on the operator's committed proof, and a reject label
   unlocks the disprove. nova-bitvm3 has the circuit (785,442,492 gates, garbled and evaluated
   on real proofs) but not these transactions.
2. **A statement covering both legs.** The in-payment to the menu address, and the payout to
   the script that the in-payment's input reveals, linked by IOBP. M16 proves one payment and
   does not apply the sender rule, so this needs a new guest that runs M16's check twice, plus
   the sender rule with its witness-commitment check.
3. **Latency the vault can tolerate.** About 5 GPU hours per mainnet proof, plus the challenge
   window.

## Layout

- `iob/btc.py`: hashes (including RIPEMD-160, which OpenSSL 3 may lack), transactions, Merkle
  branches, scripts, addresses.
- `iob/statement.py`: the M16 statement.
- `iob/policy.py`: the gate's policy rules.
- `iob/sender.py`: the sender rules and the sender proof.
- `iob/menu.py`: the menu and pricing.
- `iob/gate.py`: running `kan-payment-gate`.
- `iob/ledger.py`: the served-outpoint journal.
- `iob/rpc.py`: Core RPC.
- `iob/desk.py`: the order pipeline and payer.
- `iob/__main__.py`: the CLI.
- `menus/`, `fixtures/`, `scripts/regtest_replay.py`, `results/`, `tests/`.

Standard library only (Python 3.10 or later). The gate is GPL-3.0-only because it links
`m13-verify`, so it runs as a separate process.
