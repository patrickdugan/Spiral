# State-linked validity verification with Keyless CHECKSIG

This construction runs a finite transparent verifier as a sequence of proof-authorized UTXO spends. The implementation is [verifiers/circle_chain.py](verifiers/circle_chain.py). The [Core workflow](../../.github/workflows/keyless-circle-chain.yml) generates a real Circle-STARK proof, compiles its verifier stages and checks the serialized transaction chain in Bitcoin Core's interpreter with opt-in research flags.

The current instance is the upstream **32-row Fibonacci PLONK example with eight query groups**. It has 72 verifier stages. Its application statement does not authenticate an In-and-Out-Burger payment or execute a Nova verifier. No production security level is claimed for this example profile.

## Contract state

Let V_i be the script for stage i, and L_i its tagged TapLeaf hash. Define a permanently unspendable data leaf:

    D(s) = TapLeaf(OP_RETURN PUSH32 s)
    R_i(s) = TapBranch(L_i, D(s))

The state-bearing coin has a proposed P2MR scriptPubKey OP_2 PUSH32 R_i(s). Its two-leaf tree contains the executable verifier and the unspendable state commitment. There is no key path in this proposed output type.

The first output commits to V_0 and the all-zero initial state. For intermediate stages the input state is the previous stage's 32-byte local-data-memory commitment. V_i checks its own stage of the proof and computes the next memory commitment s'.

Every intermediate spend must create exactly one successor:

    (a_i, R_i(s)) -> (a_i - fee, R_(i+1)(s'))

The terminal stage replaces the successor with the permitted payout. The research fixture starts with 10,000,000 sats and deducts a fixed 10,000-sat fee at each of 72 transitions, leaving 9,280,000 sats. These values are synthetic test inputs.

## Authenticating the old state

A proof fragment can supply a state commitment on its witness stack. That value must be tied to the actual spent output.

The wrapper computes D(s) from the state consumed by the verifier stage, then reconstructs the current P2MR root using a supplied self-leaf hash. It hashes the serialized spent scriptPubKey for the BIP341 sha_scriptpubkeys field. The self-leaf hash is also inserted into the Tapscript signature-message extension.

Keyless CHECKSIG compares the resulting digest against the actual transaction digest. Under SHA256 binding, acceptance therefore authenticates both the current verifier leaf and its state. A fresh, internally valid computation beginning from an unrelated old state cannot satisfy the same spent-output commitment.

The fixture fixes one input and its amount in the reconstructed hash message. It also fixes the sequence, transaction version and locktime. Appending a second input changes the actual input-vector hashes. The executing input index is zero.

## Authenticating the successor

V_i contains the constant L_(i+1). The scripts are compiled backwards, starting with the terminal policy. This gives a finite dependency chain and avoids a self-referential funding transaction ID.

After the real verifier stage computes s', the wrapper computes D(s'). It then derives the next P2MR root and serializes the exact permitted output. The transaction hash is reconstructed using that output hash.

The produced state is not copied from a host assertion or embedded as an expected constant in the wrapper. The expected states in exported fixtures are used to construct test transactions and compare results.

### Canonical TapBranch ordering

A witness-controlled ordering bit would allow someone to construct an unspendable successor with an incorrectly ordered branch hash. The successor therefore checks lexicographic order in Script.

The witness supplies the position of the first differing byte between D(s') and the constant L_(i+1), that raw byte, the suffix, and its numeric value. Script reconstructs the complete D(s') using the constant's shared prefix and checks equality against the hash computed from the verifier result. It requires a differing byte and validates the raw-byte/numeric encoding, including zero and bytes from 128 through 255. The comparison then determines the canonical order.

The compiler tests cover every first-difference position and the byte boundaries 0, 1, 127, 128, 254 and 255. Equal hashes fail closed. The two leaves have distinct encoded preimages, so equality would require a hash collision.

For the current input, the ordering bit is authenticated through the actual spent root: a wrong order changes sha_scriptpubkeys and fails the final digest comparison.

## Transaction context and bounds

The reconstructed TapSighash uses the proposed key_version 2, SIGHASH_DEFAULT, script-path ext_flag 1, input index zero and no CODESEPARATOR. The wrapper is compiled from bounded Script operations and uses the same research selector as the original proposal.

The fixed output amount and the computed output script cover the entire output vector. Each intermediate transaction has one input and one output. An amount change, successor-code substitution or state change alters the actual transaction commitment and is rejected.

The prototype uses seven context items above the upstream proof-stage witness for intermediate steps. It preserves them beneath the stage's temporary altstack before execution. The old state is preserved separately and authenticated after the stage computes its result. The 1,000-item stack limit and 520-byte element limit remain in force.

A simple concatenation of all stages would need more than 27,000 hint items at entry. The state-linked construction instead gives each transaction its own bounded witness and authenticates the boundary between transactions.

## Terminal policy

The terminal script permits one of two fixed P2TR recipient keys. A witness selector chooses the recipient after funding. The transaction digest binds that selected output and the final amount.

This demonstrates dynamic selection under a committed policy. An IOB deployment needs a proved relation authenticating the inbound payment, derived payout key, amount and claim-history update. The Fibonacci proof and its two-recipient fixture do not provide those application guarantees.

Recipients retain ordinary control of their payout keys. The reserve's 72 verification transitions require no reserve-signing key, presigning ceremony or key deletion.

## Conditional safety argument

Assume the fixed verifier stages implement a sound proof relation, the source compiler and wrappers are correct, and the relevant SHA256 commitments are binding. Start with the reviewed V_0 root and its required initial state.

A valid spend authenticates its executing leaf and old state through the actual spent scriptPubKey. Its permitted output commits the computed new state together with the next program hash fixed by that leaf. Induction therefore carries the reserve through the specified verifier sequence. The final payout is reachable through the terminal program after the required preceding transitions.

The independent Core harness also checks consecutive outpoints, equality of each spent output with the previous transaction's output, and the fixed value decrement. These checks prevent a collection of unrelated successful stage fixtures from being reported as a linked chain.

This argument is conditional. Passing test cases does not establish cryptographic soundness, compiler correctness for all inputs, or a production security estimate for the pinned STWO profile.

## Scope of the implementation

The Core patch uses isolated opt-in interpreter flags for CAT, TXCOMMIT and a restricted positive-depth P2MR script path. Default Bitcoin consensus flags are unchanged. The harness provides a synthetic initial UTXO, then validates serialized linked spends and malicious variants. It runs no daemon and broadcasts or mines no funds.

The test matrix includes changed amounts and successor commitments at every real stage. Separate small SHA256 controls construct a valid computation from the wrong old state, and attempt to use a different next program or false output state. Those controls isolate the wrapper's state-binding obligation from the STARK's internal constraints.

The linked sequence still needs block-level and relay-policy testing. A byte total below 4,000,000 weight units does not establish package relay, fee-bumping behavior, or mined-block acceptance. The eight-query Fibonacci instance also leaves production proof parameters, general application support and independent review outstanding.

Sequential verification introduces an availability obligation: later proof fragments must remain obtainable after an intermediate spend. Recovery rules and fee adjustments require a separate design. The current fixed-fee fixture contains no recovery branch.

## Nova track

The native adapter has verified the pinned Nova 0.76 Pallas/Vesta Spartan+IPA fixture. Its recorded result is in [results/native-core-nova-2026-11-12.json](results/native-core-nova-2026-11-12.json). It verifies header-chain statements off chain.

Executing that Nova verifier as the statement of a transparent proof, then running the corresponding transparent verifier through this state-linked construction, is a separate integration. The current Circle-STARK circuit is the Fibonacci example. The standalone Python IPA and folding tests remain research components and must not be substituted for the real Nova verifier.

## Provenance

- Circle-STARK implementation: Bitcoin-Wildlife-Sanctuary/bitcoin-circle-stark at 9540164f243b23e4ca995c153f70ec64744df28a.
- Script compiler: Bitcoin-Wildlife-Sanctuary/dsl 0.2.0 at e6f986abd27aebfe76617e4017eb3a390a7fc984.
- Bitcoin Core: v30.0 at d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3.
- The upstream implementation already includes a covenant-based staged verifier. This work reuses its proof and compiled stages, with an explicit P2MR state commitment and Keyless CHECKSIG binding, and adds independent Core transaction tests.
