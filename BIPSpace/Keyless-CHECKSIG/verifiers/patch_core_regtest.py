#!/usr/bin/env python3
"""Disposable Core v30.0 patch for isolated regtest block validation.

Apply after core/patch_core.py. The explicit -keylessresearch switch is read
only into RegTestOptions. Mainnet/testnet/signet consensus is unchanged.
No relay-policy changes are made. Never use this research build with funds.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])


def replace(path: str, old: str, new: str) -> None:
    file = root / path
    text = file.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one pinned source anchor in {path}: {old[:80]}')
    file.write_text(text.replace(old, new, 1))


replace('src/consensus/params.h', 'struct Params {\n',
        'struct Params {\n    bool keyless_research{false}; // Explicit regtest research only.\n')
replace('src/kernel/chainparams.h', '    struct RegTestOptions {\n',
        '    struct RegTestOptions {\n        bool keyless_research{false};\n')
replace('src/chainparams.cpp',
        'void ReadRegTestArgs(const ArgsManager& args, CChainParams::RegTestOptions& options)\n{',
        'void ReadRegTestArgs(const ArgsManager& args, CChainParams::RegTestOptions& options)\n{\n    options.keyless_research = args.GetBoolArg("-keylessresearch", false);')
replace('src/kernel/chainparams.cpp',
        '        m_chain_type = ChainType::REGTEST;',
        '        m_chain_type = ChainType::REGTEST;\n        consensus.keyless_research = opts.keyless_research;')
replace('src/init.cpp',
        'void SetupServerArgs(ArgsManager& argsman, bool can_listen_ipc)\n{',
        '''void SetupServerArgs(ArgsManager& argsman, bool can_listen_ipc)
{
    argsman.AddArg("-keylessresearch", "Enable experimental CAT/TXCOMMIT/P2MR block rules on isolated regtest only", ArgsManager::ALLOW_ANY, OptionsCategory::DEBUG_TEST);''')
path = root / 'src/validation.cpp'
text = path.read_text()
start = text.index('static unsigned int GetBlockScriptFlags(')
end = text.index('\n}\n', start) + 3
block = text[start:end]
if block.count('    return flags;') != 1:
    raise RuntimeError('Unexpected block-script-flags function')
block = block.replace('    return flags;', '''    if (consensusparams.keyless_research && chainman.GetParams().GetChainType() == ChainType::REGTEST) {
        flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT | SCRIPT_VERIFY_RESEARCH_CAT | SCRIPT_VERIFY_RESEARCH_P2MR;
    }
    return flags;''')
path.write_text(text[:start] + block + text[end:])
# Actual ConnectBlock normally calls Init with force=false. Populate BIP341
# hashes for research P2MR inputs too; this only adds cache computation when
# research validation is disabled and does not change acceptance rules.
replace('src/script/interpreter.cpp',
        'm_spent_outputs[inpos].scriptPubKey[0] == OP_1) {',
        '(m_spent_outputs[inpos].scriptPubKey[0] == OP_1 || m_spent_outputs[inpos].scriptPubKey[0] == OP_2)) {')
print('Added explicit regtest-only block activation and witness-v2 sighash precomputation.')
