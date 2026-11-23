# Private Signet: Keyless-CHECKSIG / BitVM experiment

This is a **local, self-mined Bitcoin Core custom Signet** with an authorized
block-signing key, a miner and a separate validation peer. The Python harness
generates a fresh signer key through an isolated temporary Signet wallet,
creates a unique P2PK OP_CHECKSIG challenge, imports the secret descriptors
into the final Signet signer, and starts both nodes on loopback.

**Status:** infrastructure scaffold, static tests only. The Keyless-CHECKSIG
research BIP is *not* a Bitcoin Core consensus implementation. This lab has
not yet produced a signed block in CI or on a local Bitcoin Core installation.

The working spec is
[BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md](../BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md).
It describes an unallocated Tapscript unknown-key type, proposed TXCOMMIT
digest comparison, and an illustrative Script that also depends on separately
proposed OP_CAT/P2MR semantics. **Funding a TXCOMMIT-only script on Bitcoin's
existing rules could be anyone-can-spend.** All funds here must be valueless
test coins and fresh test-only keys.

## Requirements

- Linux, macOS, or WSL2 shell with Python 3.10+ (Python standard library only).
- Bitcoin Core bitcoind, bitcoin-cli and bitcoin-util on PATH, or provide
  BITCOIND, BITCOIN_CLI, BITCOIN_UTIL as absolute executable paths.
- A matching Bitcoin Core source checkout with its official
  contrib/signet/miner script and test/functional/test_framework module.
- Bitcoin Core descriptor wallet support. Use a coherent Core source/binary
  version rather than mixing a recent Signet miner with old RPCs.

The harness keeps node data under
~/.local/share/spiral-private-signet/ by default. Set
SPIRAL_SIGNET_HOME to another **empty, private directory** if desired.
Never point it at existing Bitcoin Core data. Neither production wallets
nor mainnet/Testnet4 nodes are opened.

Example paths, from the Spiral repository root:

~~~bash
export SIGNET_MINER="$HOME/src/bitcoin/contrib/signet/miner"
python3 "Private Signet/lab.py" init
python3 "Private Signet/lab.py" status
python3 "Private Signet/lab.py" mine --blocks 101
python3 "Private Signet/lab.py" status
python3 "Private Signet/lab.py" stop
~~~

Init starts a local-only temporary OP_TRUE Signet *solely* to generate
the signer key. It stops that temporary node and starts the real custom
Signet using a script of the form PUSH33 <compressed-pubkey> OP_CHECKSIG.
The challenge is unique to this laboratory and can only be satisfied by the
generated signing key, assuming that key stays private.

Mine uses Bitcoin Core's **official Signet miner**. The 101-block example
is meant to generate a spendable coinbase balance, with the first 100 blocks
required for maturity. The --min-nbits option requests Signet's minimum
difficulty. There is no GPU mining. Bitcoin Core's Signet miner requires a signet
signature as well as a valid proof-of-work header.

The raw private extended-key descriptors are retained in
PRIVATE-descriptor-backup.json under the local lab home, with mode 0600.
That file and the node wallets **must never be committed, shared, or copied
into public CI**. State.json holds a public challenge, genesis hash,
reward address, and chosen ports. Restarting init against existing data
is intentionally blocked.

## What is running?

| Node | RPC on localhost | P2P on localhost | Purpose |
|---|---:|---:|---|
| Bootstrap (stopped after init) | 39432 | 39433 | Generate signer key in an isolated temporary Signet |
| Miner | 39442 | 39443 | Hold signing wallet and issue signed blocks |
| Observer | 39452 | 39453 | Independent Bitcoin Core validation and mempool behavior |

The observer connects only to the miner. Both share the challenge and
genesis hash. The signer RPC and P2P listeners remain on loopback. The
default miner does not connect to public Signet seeds.

### Probe a real raw transaction

~~~bash
# File contains exactly one fully serialized, signed transaction in hex.
python3 "Private Signet/lab.py" probe --txhex-file /tmp/signet-spend.hex
~~~

This calls testmempoolaccept independently on miner and observer and
writes the raw RPC observations to the local receipts/ directory.
It leaves the mempool unchanged.

For a deliberately broadcast experiment, after inspecting the transaction:

~~~bash
python3 "Private Signet/lab.py" probe \
  --txhex-file /tmp/signet-spend.hex --broadcast
python3 "Private Signet/lab.py" mine --blocks 1
~~~

Broadcast is sent only to the isolated miner node. Both nodes presently
enforce the **same stock Bitcoin Core consensus rules**. Peer-to-peer relay
is not the same as inclusion in a valid block, and testmempoolaccept
includes mempool policy constraints. Inspect reject-reason and use
independent block validation to resolve policy-versus-consensus disputes.

The receipts include block heights, hashes, Core versions, elapsed mining
time, RPC responses and errors. All receipts are local, with no token or
private-key material. Inspect them before publishing.

## Adding a real consensus experiment

There are two deliberately separate research lanes.

**A. Stock-core lane:** demonstrate a vanilla BitVM/DLC settlement on this
self-mined Signet. This answers questions about transaction construction,
policy, relay and independent acceptance on existing consensus.

**B. Modified-core lane:** write or import a reviewed Bitcoin Core patch
that recognizes the draft Keyless-CHECKSIG selector, computes the actual
BIP341 Tapscript digest and aborts on mismatch. OP_CAT and P2MR are separate
consensus changes. Pin each patch and activation height in a run manifest.
First test on disposable **regtest** data directories under explicit
activation, then set up a separately identified *patched custom Signet*.
Both miners and validators must enforce the same candidate rules when
asserting a valid upgraded chain.

Never infer successful TXCOMMIT enforcement from acceptance on stock Core:
the unknown-key path currently accepts nonempty candidates without this
digest comparison. Do not use a stock chain to claim a secure keyless vault.

See [AB_TEST_PLAN.md](AB_TEST_PLAN.md) for falsifiable controls and
requirements for evidence that can be shown to reviewers.

## Static validation

~~~bash
python3 -m unittest discover -s "Private Signet" -p 'test_lab.py' -v
python3 -m py_compile "Private Signet/lab.py"
~~~

These tests run without Bitcoin Core and cover challenge serialization,
descriptor-import request construction and input validation. Full
end-to-end tests require local Core binaries and the upstream miner.

## References

- [BIP325, Signet](https://bips.dev/325/)
- [Bitcoin Core's official Signet miner instructions](https://github.com/bitcoin/bitcoin/blob/master/contrib/signet/README.md)
- [Bitcoin Core Signet miner](https://github.com/bitcoin/bitcoin/blob/master/contrib/signet/miner)
- [Bitcoin Core data-directory conventions](https://github.com/bitcoin/bitcoin/blob/master/doc/files.md)
- [Keyless-CHECKSIG research BIP](../BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md)
