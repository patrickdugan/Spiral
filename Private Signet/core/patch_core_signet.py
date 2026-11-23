#!/usr/bin/env python3
"""Extend the Keyless research activation from regtest to a CUSTOM Signet.

Apply to Bitcoin Core d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3 after
BIPSpace/Keyless-CHECKSIG/core/patch_core.py and
BIPSpace/Keyless-CHECKSIG/verifiers/patch_core_regtest.py.

- `-keylessresearch` is read into SigNetOptions as well as RegTestOptions.
- It is refused unless `-signetchallenge` is also given, so the default public
  Signet can never run with the research rules.
- GetBlockScriptFlags enables TXCOMMIT/CAT/P2MR on REGTEST or SIGNET when the
  chain's consensus.keyless_research is set. Mainnet and testnets are unchanged.

Every anchor is checked before any file is written (--check only checks).
Relay policy is not changed: the research spends stay non-standard and reach
blocks only through the Signet block signer.
"""
from __future__ import annotations

import argparse
from pathlib import Path

EDITS = (
    ("src/kernel/chainparams.h",
     "    struct SigNetOptions {\n        std::optional<std::vector<uint8_t>> challenge{};\n",
     "    struct SigNetOptions {\n        std::optional<std::vector<uint8_t>> challenge{};\n"
     "        bool keyless_research{false};\n"),
    ("src/chainparams.cpp",
     "        options.challenge.emplace(*val);\n    }\n}\n",
     "        options.challenge.emplace(*val);\n    }\n"
     "    options.keyless_research = args.GetBoolArg(\"-keylessresearch\", false);\n"
     "    if (options.keyless_research && !options.challenge) {\n"
     "        throw std::runtime_error(\"-keylessresearch on signet requires a custom -signetchallenge\");\n"
     "    }\n}\n"),
    ("src/kernel/chainparams.cpp",
     "        m_chain_type = ChainType::SIGNET;\n        consensus.signet_blocks = true;\n",
     "        m_chain_type = ChainType::SIGNET;\n        consensus.signet_blocks = true;\n"
     "        consensus.keyless_research = options.keyless_research && options.challenge.has_value();\n"),
    ("src/validation.cpp",
     "    if (consensusparams.keyless_research && chainman.GetParams().GetChainType() == ChainType::REGTEST) {",
     "    if (consensusparams.keyless_research &&\n"
     "        (chainman.GetParams().GetChainType() == ChainType::REGTEST ||\n"
     "         chainman.GetParams().GetChainType() == ChainType::SIGNET)) {"),
    ("src/init.cpp",
     "\"Enable experimental CAT/TXCOMMIT/P2MR block rules on isolated regtest only\"",
     "\"Enable experimental CAT/TXCOMMIT/P2MR block rules on isolated regtest or a custom -signetchallenge signet only\""),
)


def plan(sources: dict[str, str]) -> dict[str, str]:
    out = {}
    for path, old, new in EDITS:
        text = out.get(path, sources[path])
        if text.count(old) != 1:
            raise RuntimeError(f"expected one anchor in {path}, found {text.count(old)}: {old[:70]!r}")
        if "keyless_research{false};\n" in text and path.endswith("chainparams.h") and \
                text.count("keyless_research{false}") > 1:
            raise RuntimeError("signet patch already applied")
        out[path] = text.replace(old, new, 1)
    if "keyless_research" not in sources["src/validation.cpp"]:
        raise RuntimeError("apply patch_core_regtest.py first")
    return out


def apply(root: Path, check_only: bool = False) -> list[str]:
    paths = sorted({p for p, _, _ in EDITS})
    sources = {p: (root / p).read_text(encoding="utf-8") for p in paths}
    edits = plan(sources)
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
        ap.exit(1, f"Signet patch refused: {exc}\n")
    print(f"{'Validated' if args.check else 'Applied'} custom-Signet keyless activation in {len(files)} files.")


if __name__ == "__main__":
    main()
