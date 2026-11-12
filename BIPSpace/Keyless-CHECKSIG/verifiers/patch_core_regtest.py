#!/usr/bin/env python3
"""Disposable Core v30.0 patch for isolated regtest block validation.

Apply after core/patch_core.py. The explicit -keylessresearch switch is read
only into RegTestOptions. Mainnet/testnet/signet consensus is unchanged.
No relay-policy changes are made. Never use this research build with funds.

All source anchors are checked before any file is written. --check performs
that preflight without writing. This is a pinned-source patcher, not a general
C++ parser, and deliberately rejects changed or already-patched inputs.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping


FLAGS_DEFINITION = (
    'static unsigned int GetBlockScriptFlags('
    'const CBlockIndex& block_index, const ChainstateManager& chainman)\n{'
)
RESEARCH_FLAGS = (
    'SCRIPT_VERIFY_RESEARCH_TXCOMMIT',
    'SCRIPT_VERIFY_RESEARCH_CAT',
    'SCRIPT_VERIFY_RESEARCH_P2MR',
)
SIMPLE_EDITS = (
    ('src/consensus/params.h', 'struct Params {\n',
     'struct Params {\n    bool keyless_research{false}; // Explicit regtest research only.\n'),
    ('src/kernel/chainparams.h', '    struct RegTestOptions {\n',
     '    struct RegTestOptions {\n        bool keyless_research{false};\n'),
    ('src/chainparams.cpp',
     'void ReadRegTestArgs(const ArgsManager& args, CChainParams::RegTestOptions& options)\n{',
     'void ReadRegTestArgs(const ArgsManager& args, CChainParams::RegTestOptions& options)\n{\n'
     '    options.keyless_research = args.GetBoolArg("-keylessresearch", false);'),
    ('src/kernel/chainparams.cpp',
     '        m_chain_type = ChainType::REGTEST;',
     '        m_chain_type = ChainType::REGTEST;\n'
     '        consensus.keyless_research = opts.keyless_research;'),
    ('src/init.cpp',
     'void SetupServerArgs(ArgsManager& argsman, bool can_listen_ipc)\n{',
     'void SetupServerArgs(ArgsManager& argsman, bool can_listen_ipc)\n{\n'
     '    argsman.AddArg("-keylessresearch", "Enable experimental CAT/TXCOMMIT/P2MR '
     'block rules on isolated regtest only", ArgsManager::ALLOW_ANY, OptionsCategory::DEBUG_TEST);'),
    # ConnectBlock normally initializes this cache with force=false. Compute
    # BIP341 message components for the experimental native witness-v2 input.
    # This adds cache work only; it does not activate a spending rule.
    ('src/script/interpreter.cpp',
     'm_spent_outputs[inpos].scriptPubKey[0] == OP_1) {',
     '(m_spent_outputs[inpos].scriptPubKey[0] == OP_1 || '
     'm_spent_outputs[inpos].scriptPubKey[0] == OP_2)) {'),
)
PATCH_PATHS = tuple(path for path, _, _ in SIMPLE_EDITS) + ('src/validation.cpp',)
HEADER_PATH = 'src/script/interpreter.h'


def replace_once(text: str, old: str, new: str, path: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'Expected one pinned source anchor in {path}, found {count}: {old[:80]}')
    return text.replace(old, new, 1)


def patch_script_flags(text: str) -> str:
    """Select the definition; Core also has an earlier forward declaration."""
    if text.count(FLAGS_DEFINITION) != 1:
        raise RuntimeError('Expected exactly one pinned GetBlockScriptFlags definition')
    start = text.index(FLAGS_DEFINITION)
    end = text.find('\n}\n', start + len(FLAGS_DEFINITION))
    if end == -1:
        raise RuntimeError('Unterminated pinned GetBlockScriptFlags definition')
    end += 3
    function = text[start:end]
    if '    const Consensus::Params& consensusparams = chainman.GetConsensus();' not in function:
        raise RuntimeError('Unexpected GetBlockScriptFlags consensus-parameter binding')
    if 'keyless_research' in function:
        raise RuntimeError('GetBlockScriptFlags already has research activation')
    function = replace_once(function, '    return flags;',
        '    if (consensusparams.keyless_research && '
        'chainman.GetParams().GetChainType() == ChainType::REGTEST) {\n'
        '        flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT | '
        'SCRIPT_VERIFY_RESEARCH_CAT | SCRIPT_VERIFY_RESEARCH_P2MR;\n'
        '    }\n'
        '    return flags;', 'src/validation.cpp:GetBlockScriptFlags')
    return text[:start] + function + text[end:]


def plan_patch(sources: Mapping[str, str]) -> dict[str, str]:
    """Return complete replacements after validating the entire source set."""
    missing = [path for path in (*PATCH_PATHS, HEADER_PATH) if path not in sources]
    if missing:
        raise RuntimeError('Missing required source files: ' + ', '.join(missing))
    if any(flag not in sources[HEADER_PATH] for flag in RESEARCH_FLAGS):
        raise RuntimeError('Apply core/patch_core.py before the regtest patch')
    # A previous interrupted patch must not silently add duplicate members,
    # options or activation. Start from a fresh pinned checkout in that case.
    if any('keyless_research' in sources[path] or '-keylessresearch' in sources[path]
           for path in PATCH_PATHS):
        raise RuntimeError('Regtest patch is already present or partially applied; use a fresh pinned checkout')
    edits = {}
    for path, old, new in SIMPLE_EDITS:
        edits[path] = replace_once(sources[path], old, new, path)
    edits['src/validation.cpp'] = patch_script_flags(sources['src/validation.cpp'])
    return edits


def apply_patch(root: Path, *, check_only: bool = False) -> tuple[str, ...]:
    paths = (*PATCH_PATHS, HEADER_PATH)
    sources = {path: (root / path).read_text(encoding='utf-8') for path in paths}
    edits = plan_patch(sources)
    # Check every file again before the first write, catching an intervening
    # source change. There is no claim of multi-file filesystem atomicity.
    if any((root / path).read_text(encoding='utf-8') != original
           for path, original in sources.items()):
        raise RuntimeError('Core source changed during patch preflight')
    if not check_only:
        for path, replacement in edits.items():
            (root / path).write_text(replacement, encoding='utf-8')
    return tuple(edits)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core_source', type=Path)
    parser.add_argument('--check', action='store_true', help='validate all anchors without writing')
    args = parser.parse_args()
    try:
        paths = apply_patch(args.core_source, check_only=args.check)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f'Regtest patch refused: {error}\n')
    action = 'Validated' if args.check else 'Applied'
    print(f'{action} {len(paths)} pinned Core file changes for explicit regtest-only activation.')


if __name__ == '__main__':
    main()
