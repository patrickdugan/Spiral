#!/usr/bin/env python3
"""Extend the isolated Core v30 interpreter patch to a dedicated regtest build.

Run patch_core.py first. Defining KEYLESS_RESEARCH_REGTEST=1 at compilation
then enables its CAT/TXCOMMIT/restricted-P2MR rules for regtest block validation.
Without that build define, this patch changes no network's validation flags.
Even with it, mainnet, signet and both testnets retain their original flags.
The experimental build also precomputes BIP341 data for witness-v2 inputs.
This is a research activation mechanism, not a proposed deployment scheme.
"""
from pathlib import Path
import argparse
import subprocess

CORE_REV = 'd0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3'
MARKER = 'KEYLESS_RESEARCH_REGTEST'


def apply(root: Path) -> None:
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != CORE_REV:
        raise ValueError(f'Expected pinned Core {CORE_REV}, got {head}')
    header = (root / 'src/script/interpreter.h').read_text()
    names = ('SCRIPT_VERIFY_RESEARCH_TXCOMMIT', 'SCRIPT_VERIFY_RESEARCH_CAT', 'SCRIPT_VERIFY_RESEARCH_P2MR')
    if not all(name in header for name in names):
        raise ValueError('Run the isolated patch_core.py interpreter patch first')
    path = root / 'src/validation.cpp'
    text = path.read_text()
    if MARKER in text:
        raise ValueError('Regtest validation patch already applied')
    begin = text.index('static unsigned int GetBlockScriptFlags(')
    end = text.index('bool Chainstate::ConnectBlock(', begin)
    section = text[begin:end]
    old = '    return flags;\n'
    if section.count(old) != 1:
        raise ValueError('Unexpected GetBlockScriptFlags layout')
    addition = '''#if defined(KEYLESS_RESEARCH_REGTEST) && KEYLESS_RESEARCH_REGTEST
    // Explicit experimental build AND regtest network are both required.
    // Do not deploy this binary on a public network. This is not BIP activation.
    if (chainman.GetParams().GetChainType() == ChainType::REGTEST) {
        flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT |
                 SCRIPT_VERIFY_RESEARCH_CAT |
                 SCRIPT_VERIFY_RESEARCH_P2MR;
    }
#endif
    return flags;
'''
    validation = text[:begin] + section.replace(old, addition, 1) + text[end:]
    interpreter_path = root / 'src/script/interpreter.cpp'
    interpreter = interpreter_path.read_text()
    cache_anchor = 'm_spent_outputs[inpos].scriptPubKey[0] == OP_1) {'
    if interpreter.count(cache_anchor) != 1:
        raise ValueError('Unexpected sighash precomputation layout')
    cache_replacement = '''(m_spent_outputs[inpos].scriptPubKey[0] == OP_1
#if defined(KEYLESS_RESEARCH_REGTEST) && KEYLESS_RESEARCH_REGTEST
                // Research P2MR needs the same transaction-wide hash caches.
                || (m_spent_outputs[inpos].scriptPubKey[0] == OP_2 &&
                    m_spent_outputs[inpos].scriptPubKey[1] == 0x20)
#endif
                )) {'''
    interpreter = interpreter.replace(cache_anchor, cache_replacement, 1)
    path.write_text(validation)
    interpreter_path.write_text(interpreter)
    print('Installed regtest-only validation flags and research P2MR sighash cache detection.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    apply(parser.parse_args().core)
