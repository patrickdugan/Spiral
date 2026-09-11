# Response to the algebra review of the new reference ledger

The independent reviewer reproduced a float-direction failure against the first
resource_model.py draft. Python equates 1.0 with 1 in membership tests. The draft
accepted direction=1.0, then produced a float balance and raised its integer-state
validation error after changing state. The historical cross_examination.json
and report are retained unchanged; they describe the pre-fix code identified by
their source hash, not the revised version.

The coordinator added an exact integer type guard for direction in prepare and
seven rejection-without-mutation regression cases (floats, booleans, strings,
and out-of-domain integers). No change was made to the original paper's code.
The original six reference tests, including the 440-state finite enumeration,
also remain in place. The post-review guard does not establish distributed
atomicity; the declared model still assumes a well-formed ledger, no external
mutation between calls, and local atomic finish.

To reconstruct the one-line pre-fix reference for reviewing the historical
witness, remove `type(direction) is not int or ` from the first directional
validation conditional in prepare. Do not use that draft as the corrected
reference or replace the preserved historical result with a later rerun.

The reviewer also corrected a metadata counting error in the original testnet
receipt: 512 headers contain 511 internal parent links. The exported bytes,
hashes, encoded-target checks, and 3 direct D-drive spotchecks are unaffected.
The historical receipt retains its original wording to preserve byte identity;
the paper and final validation receipt use the correct count.
