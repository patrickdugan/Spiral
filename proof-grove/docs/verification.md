# Verification record

Checked locally on November 15, 2026. Commands and reproducible test scripts are in the repository.

## Static Pages export, November 16, 2026 (Singapore time)

The public exporter packages only its listed assets, precomputed Python fixture
cases and the two public withdrawal/exit reports. The hosted browser check passed
at the actual `/Spiral/proof-grove/` project subpath at 1440 and 390 px: eight
cases, recovery slider, receipt dialog, exact archive hash/CID, result links and
no JavaScript errors, horizontal overflow or `/api/` requests. Native wallet and
signing controls are hidden in this hosted build. See
[browser result](hosted-browser-check.json) and [hosting guide](hosting.md).
Python regression checks: 76 passed, including export allowlisting, subpath
assets and refusal to mix existing files into a public bundle. Both browser
scripts passed JavaScript syntax checks.

## Combined Cashu withdrawal and offline Ark exit, November 16, 2026 (Singapore time)

The [combined result](cashu-ark-integration.json) covers a fresh Core 31 / CDK
0.18.3 / Bark 0.8.1 stack using actual Cashu cryptography and valueless regtest
coins. A 25,000 sat BDK deposit passed Core admission and issued verified proofs.
The wallet redeemed 10,000 sats through the ported custom `arkoor` processor. A
proxy dropped the successful HTTP 200 response. New wallet processes recovered
15,000 sats of DLEQ-verified, unspent change with exactly one melt POST and one
NUT-09 restore. The native test caught the SDK's NUT-19 automatic retry behavior;
the wallet now uses an explicit single-attempt transport.

The receiving Bark wallet independently validated the new VTXOs and matched its
fresh address and exact amount. A delegated refresh produced a 9,810 sat
successor, with a 190 sat fee and a Core-confirmed anchor. The mint and its
processor were then stopped. The [linked exit result](cashu-ark-exit-integration.json)
binds its input to this exact successor. With the Ark server also stopped and
the owner wallet paused, an independent Core-only watcher advanced two saved
transaction waves and recovered a lost submission response. It rejected an
altered witness, handled an already-confirmed parent with a missing child, and
detected a funding reorg. The owner resumed and claimed 9,165 sats at the selected
on-chain destination, with a separate 645 sat claim fee, while both services
remained offline.

User deposit accounting is `15,000 Cashu change + 9,165 owner claim + 190 refresh
fee + 645 claim fee = 25,000 sats`. The 3,180 sat CPFP fee came from an additional
40,000 sat valueless fixture funding output, separate from the deposit. Mint Ark
liquidity was separately prefunded; the test proves neither reserve backing nor
solvency. Bark validates Ark signatures and ownership; this Python desk checks
Core observations. No new M16 proof or funded BitVM bridge was generated.

- Python regression suite: 74 passed.
- Wallet tests: 11 passed, including durable reservations, no uncertain resend,
  NUT-19 single-attempt behavior, redirect refusal and sanitized provider errors.
- Processor tests: 33 library and 3 transport configuration tests passed.
- Rust all-target type check, formatting, Python compilation and Git whitespace
  checks passed.
- Fixture dashboard checks passed at 1440 and 390 px with no JavaScript errors
  or horizontal overflow.

The supervisor's `--test-cashu-exit` mode reproduces this flow on new state and
cleans up only its labelled resources. See the [withdrawal guide](cashu-ark-withdrawal.md).
The native M16 verification below remains a separate historical proof check.

## Offline Ark exit recovery, November 16, 2026 (Singapore time)

The [native exit result](ark-exit-integration.json) covers a real Bark/Core recovery package with two transaction waves and 3,180 sats of saved CPFP fees. The Ark server was stopped and the owner wallet paused during independent broadcast. Core rejected an altered witness without admitting its zero-fee parent. The authentic package was exported/imported into a separate database with no Bark configuration, and a lost successful submission reply was recovered by new CLI processes. Confirmation/reorg checks and the owner claim are separate evidence stages.

The owner resumed and signed its final claim while the Ark server remained offline. Core confirmed 496,607 sats at the preselected destination and a separate 645 sat claim fee. These figures describe this pinned, valueless regtest fixture, not a production fee estimate. The saved CPFP budget does not include the final claim.

The recovery test also mines a valid parent without its fee-paying child, then verifies that the broadcaster submits only the missing child. The second wave exercises combined parent/child submission. The owner wallet remains paused throughout both paths; the test does not establish safety under concurrent off-chain spending by another wallet process.

The supervisor's `--test-exits` path runs refresh followed by this recovery test on fresh state. See [recovery guide](ark-recovery.md). Earlier Cashu issuance and M16 tests below remain separate; no combined Cashu-to-Ark transfer is implied.

- Python regression checks: 74 passed, including fee budgets, altered metadata, restart recovery, wave ordering, timelocks, conflicting reservations, a preconfirmed parent with a missing child, orphan/mempool distinction and sanitized Core errors.
- A targeted real Core check confirmed that an unknown transaction and a known orphan absent from the mempool are not treated as pending admission. Reconsidering the block restored its confirmed observation.
- The [Core-only browser check](ark-exit-browser-check.json) passed at 1440 and 390 px, including an exact-hash private download and a fresh check of the already-spent exit output. No JavaScript errors or page overflow were observed.

## Ark integration, November 16, 2026 (Singapore time)

Real Bark/captaind 0.8.1 and Bitcoin Core 31.0 ran on a fresh, isolated regtest stack. A 500,000 sat board produced a 499,400 sat VTXO. The caretaker delegated its refresh, a proxy discarded the successful reply, and the desk reopened its SQLite database. Reconciliation recovered the operation with exactly one refresh POST, confirmed a 497,252 sat successor with a 16-block expiry extension, and recorded a 2,148 sat refresh fee. Invalidating the successor's funding block changed the desk observation to `chain_unconfirmed`; reconsidering it restored `confirmed`.

The packaged foreground supervisor reproduced the full test with fresh server/Core/wallet state. This tests actual Ark signing through Bark and independent Core anchor observations, with valueless regtest coins. It does not independently verify Ark scripts in Python, execute an exit or bridge Cashu into Ark. Production dispatch remains disabled because the upstream REST API has no signer-enforced fee cap.

- Python regression checks: 63 passed, including durable Ark recovery, request/wallet changes, fee discrepancies, reorgs and unconfigured HTTP refusal.
- Default fixture browser checks: desktop and phone layouts passed.
- Actual Ark browser checks cover real VTXOs, Core anchors and the persisted refresh record at 1440 and 390 px; results are in [the browser report](ark-browser-check.json).

See [native result](ark-integration.json), [caretaker guide](ark-caretaker.md), `tests/run-ark-stack.py`, and `tests/ark-regtest-integration.py`. Earlier Cashu and M16 results below are separate tests; they do not establish one combined mainnet-to-Cashu-to-Ark flow.

## Cashu integration, November 16, 2026 (Singapore time)

Real CDK 0.18.3 with its BDK/Core backend received a 25,000 sat regtest deposit with two confirmations. The desk rejected issuance before admission. After admission, a proxy discarded the successful mint reply; a new wallet process restored the original six outputs, verified their DLEQ signatures and unspent states, and decoded the token with loaded mint keysets. There was exactly one mint request and one restoration request. No bearer token or wallet key is in the report.

The isolated foreground stack supervisor also reproduced the issuance/recovery test with fresh Core/CDK state on WSL. This test uses actual Cashu cryptography and valueless regtest coins. It uses `core-regtest` admission, not M16/ZK, and does not establish mainnet issuance, Ark transfer or rollover.

- Python regression tests: 55 passed after quote-owner authorization and late-proof admission tests were added.
- Node wallet tests: 4 passed, covering encrypted restart recovery, process leases, complete-request authorization and receiving-address/amount binding.
- Connected desktop and phone checks: 1440 px and 390 px passed actual regtest admission, issuance-state inspection and archive download, with no JavaScript errors or page overflow.
- JavaScript syntax check: passed.
- The historical M16 proof also passed with an intent-style script identifier and an exact 940,000 sat policy floor, exercising the new per-intent policy shape without reserving a payment.

See [CDK result](cdk-integration.json), [connected browser result](connected-browser-check.json), and [wallet guide](cashu-wallet.md). The older fixture-browser report below covers the default demo separately.

## Historical M16 and initial dashboard checks

- Python policy, persistence, HTTP, parser and adapter tests: **39 passed**. Core, Cashu and Bark provider responses in these tests are mocked; no live provider integration is claimed.
- Real native M16 verification: the historical mainnet payment statement passed against the existing `kan-payment-gate` binary. A flipped proof byte, a truncated proof, and a modified PAY1 payment amount were each rejected by the actual verifier.
- JavaScript syntax check: passed.
- Desktop and phone browser checks use the real local HTTP service, with fixture data; results are recorded separately in `browser-check.json`.

| Native artifact | SHA-256 |
| --- | --- |
| Gate executable | `2344753bc291b611bcffb74e04bcabd0e9b92a3832e7a95132641ef752602f56` |
| Public statement | `cae6068f7ad8c4891cb3220702a88b0bc3df54013f45e65df11a9ced531bc869` |
| Historical final proof, not bundled | `97871e86cd0809e4b21d744343c43737cb56073f65e671da727e9db6051326e3` |

Native verification took approximately 0.8–1.3 seconds per case inside WSL after startup. This is verification latency for these artifacts, not proving time or an app performance guarantee. Windows-to-WSL startup can be much slower; the executable hash check allows 120 seconds.

The historical proof establishes the payment statement under its pinned program and policy. This check did not refresh its current active-chain context, claim the deposit for this application, issue tokens, send funds, create a Filecoin deal, or run a funded BitVM challenge. The default dashboard remains a fixture demonstration.
