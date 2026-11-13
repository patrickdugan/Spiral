# Reproducing the research

Both programs use the Python standard library. Run the commands from the
Spiral repository root with Python 3.11 or later.

## Historical frame

Obtain a bitcoin/bips checkout at
b34d9f751791d4feb22feff4f2ed00bcac83961b, then run:

    python BIPSpace/The-BIP-Sieve/research/extract_historical_frame.py \
      --bips-root /path/to/bitcoin-bips \
      --verify-against BIPSpace/The-BIP-Sieve/historical-frame.json \
      --output reproduced-frame.json

The verifier checks the index and all 63 consensus-labelled source documents
against the Git blob hashes recorded in the frame. It compares each index row
with its document header and applies the inclusive assignment-date interval
2011-01-01 through 2017-12-31.

The result has 39 included rows and 24 date exclusions. Every source file used
for this revision matched the official repository blob, and a second run
reproduced the JSON exactly. An independent parser confirmed the included
document set.

The selection rule was introduced after the purposive first draft. Its scope
is a retrospective coverage audit of current metadata. Closure causes and
network outcomes remain separate historical work.

## One-shot claim comparison

    python BIPSpace/The-BIP-Sieve/benchmarks/sibling_vs_merged.py \
      --output reproduced-sibling-comparison.json

The harness verifies its vendored paired model and official vector fixture
against pinned Git blob hashes. It compares the unchanged paired validator
with a separately implemented merged-output model and an abstract claim
predicate. The result file includes exact parameter grids, mutation cases,
the serialized envelope and unmeasured properties.

Compare the output with
[benchmarks/results.json](../benchmarks/results.json). The deterministic seed
is 20261113. Results are independent of wall-clock timing and hardware.

The [benchmark report](../benchmarks/REPORT.md) explains the 84-base-byte
increment and the witness assumptions behind the 467-WU payout difference.
Its synthetic reconfirmation cases manipulate model state; full node
reorganizations require a separate execution receipt.

## Evidence boundaries

The native MULADDMOD, Keyless and CPA counts in the paper come from existing
pinned receipts and inspected workflow logs. This research extension
reproduces its new graph experiment and historical extraction. Each kind of
evidence remains labelled in
[portfolio-evidence.json](../portfolio-evidence.json).
