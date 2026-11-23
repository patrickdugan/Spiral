#!/usr/bin/env python3
"""Research OP_CHECKSIGFROMSTACK (opcode 0xcc, Tapscript) for the Keyless lab.

Apply to Bitcoin Core d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3 after
patch_core.py, patch_core_regtest.py and patch_core_signet.py. The opcode is
enabled together with TXCOMMIT/CAT/P2MR by -keylessresearch (regtest or a
custom-challenge Signet only).

Semantics follow BIP348 with one restriction:
  (sig msg pubkey -- bool)
  - fewer than 3 items: INVALID_STACK_OPERATION
  - empty pubkey: PUBKEYTYPE
  - non-empty sig: charges 50 against the BIP342 validation budget
  - 32-byte pubkey and non-empty sig: the sig must be 64 bytes and a valid
    BIP340 signature, otherwise the script fails (no false on bad signature)
  - other pubkey sizes: success = sig non-empty (upgradable key types)
  - empty sig: pushes false
  - RESTRICTION: the message must be exactly 32 bytes. BIP348 allows any
    length; Core d0f6d995's XOnlyPubKey::VerifySchnorr takes a uint256, and
    every message in this lab is a 32-byte hash.
Without the flag, 0xcc stays OP_SUCCESS204 (old rules).
"""
from __future__ import annotations

import argparse
from pathlib import Path

CSFS_CASE = '''                case static_cast<opcodetype>(0xcc): // research OP_CHECKSIGFROMSTACK (BIP348, 32-byte msg)
                {
                    if (sigversion != SigVersion::TAPSCRIPT || !(flags & SCRIPT_VERIFY_RESEARCH_CSFS)) return set_error(serror, SCRIPT_ERR_BAD_OPCODE);
                    if (stack.size() < 3) return set_error(serror, SCRIPT_ERR_INVALID_STACK_OPERATION);
                    const valtype& sig = stacktop(-3);
                    const valtype& msg = stacktop(-2);
                    const valtype& pubkey = stacktop(-1);
                    if (pubkey.size() == 0) return set_error(serror, SCRIPT_ERR_PUBKEYTYPE);
                    const bool success = !sig.empty();
                    if (success) {
                        assert(execdata.m_validation_weight_left_init);
                        execdata.m_validation_weight_left -= VALIDATION_WEIGHT_PER_SIGOP_PASSED;
                        if (execdata.m_validation_weight_left < 0) return set_error(serror, SCRIPT_ERR_TAPSCRIPT_VALIDATION_WEIGHT);
                        if (pubkey.size() == 32) {
                            if (sig.size() != 64) return set_error(serror, SCRIPT_ERR_SCHNORR_SIG_SIZE);
                            if (msg.size() != 32) return set_error(serror, SCRIPT_ERR_SCHNORR_SIG);
                            if (!XOnlyPubKey{std::span<const unsigned char>{pubkey}}.VerifySchnorr(uint256{std::span<const unsigned char>{msg}}, sig)) {
                                return set_error(serror, SCRIPT_ERR_SCHNORR_SIG);
                            }
                        }
                    }
                    popstack(stack);
                    popstack(stack);
                    popstack(stack);
                    stack.push_back(success ? vchTrue : vchFalse);
                }
                break;

'''

EDITS = (
    ("src/script/interpreter.h",
     "    SCRIPT_VERIFY_RESEARCH_P2MR = (1U << 23),\n",
     "    SCRIPT_VERIFY_RESEARCH_P2MR = (1U << 23),\n    SCRIPT_VERIFY_RESEARCH_CSFS = (1U << 24),\n"),
    ("src/script/interpreter.cpp",
     "            if (IsOpSuccess(opcode) && !(opcode == OP_CAT && (flags & SCRIPT_VERIFY_RESEARCH_CAT))) {",
     "            if (IsOpSuccess(opcode) && !(opcode == OP_CAT && (flags & SCRIPT_VERIFY_RESEARCH_CAT)) &&\n"
     "                !(opcode == 0xcc && (flags & SCRIPT_VERIFY_RESEARCH_CSFS))) {"),
    ("src/script/interpreter.cpp",
     "                case OP_CHECKMULTISIG:\n                case OP_CHECKMULTISIGVERIFY:\n",
     CSFS_CASE + "                case OP_CHECKMULTISIG:\n                case OP_CHECKMULTISIGVERIFY:\n"),
    ("src/validation.cpp",
     "        flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT | SCRIPT_VERIFY_RESEARCH_CAT | SCRIPT_VERIFY_RESEARCH_P2MR;",
     "        flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT | SCRIPT_VERIFY_RESEARCH_CAT | SCRIPT_VERIFY_RESEARCH_P2MR |\n"
     "                 SCRIPT_VERIFY_RESEARCH_CSFS;"),
)


def plan(sources: dict[str, str]) -> dict[str, str]:
    if "SCRIPT_VERIFY_RESEARCH_P2MR" not in sources["src/script/interpreter.h"]:
        raise RuntimeError("apply patch_core.py first")
    if "SCRIPT_VERIFY_RESEARCH_CSFS" in sources["src/script/interpreter.h"]:
        raise RuntimeError("CSFS patch already applied")
    out = dict(sources)
    for path, old, new in EDITS:
        if out[path].count(old) != 1:
            raise RuntimeError(f"expected one anchor in {path}, found {out[path].count(old)}: {old[:70]!r}")
        out[path] = out[path].replace(old, new, 1)
    return {p: out[p] for p in {e[0] for e in EDITS}}


def apply(root: Path, check_only: bool = False) -> list[str]:
    paths = sorted({p for p, _, _ in EDITS})
    edits = plan({p: (root / p).read_text(encoding="utf-8") for p in paths})
    if not check_only:
        for p, text in edits.items():
            (root / p).write_text(text, encoding="utf-8")
    return sorted(edits)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("core_source", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        files = apply(args.core_source, args.check)
    except (OSError, RuntimeError) as exc:
        ap.exit(1, f"CSFS patch refused: {exc}\n")
    print(f"{'Validated' if args.check else 'Applied'} research OP_CHECKSIGFROMSTACK in {len(files)} files.")


if __name__ == "__main__":
    main()
