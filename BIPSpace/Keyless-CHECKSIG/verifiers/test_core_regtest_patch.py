"""Source-patching regression tests for the disposable Core v30 experiment.

The C++ test compiles the retrieved GetBlockScriptFlags body with mock Core
interfaces to test the opt-in/network guard. It does not compile bitcoind or
establish block acceptance. Source anchors target Bitcoin Core d0f6d995.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import patch_core_regtest as P


DECLARATION = ('static unsigned int GetBlockScriptFlags('
               'const CBlockIndex& block_index, const ChainstateManager& chainman);\n')
# The body is transcribed from bitcoin/bitcoin d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3,
# src/validation.cpp. Comments are omitted; the executable statements are retained.
# Bitcoin Core source is MIT licensed.
BODY = P.FLAGS_DEFINITION + '''
    const Consensus::Params& consensusparams = chainman.GetConsensus();
    uint32_t flags{SCRIPT_VERIFY_P2SH | SCRIPT_VERIFY_WITNESS | SCRIPT_VERIFY_TAPROOT};
    const auto it{consensusparams.script_flag_exceptions.find(*Assert(block_index.phashBlock))};
    if (it != consensusparams.script_flag_exceptions.end()) {
        flags = it->second;
    }
    if (DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_DERSIG)) {
        flags |= SCRIPT_VERIFY_DERSIG;
    }
    if (DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_CLTV)) {
        flags |= SCRIPT_VERIFY_CHECKLOCKTIMEVERIFY;
    }
    if (DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_CSV)) {
        flags |= SCRIPT_VERIFY_CHECKSEQUENCEVERIFY;
    }
    if (DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_SEGWIT)) {
        flags |= SCRIPT_VERIFY_NULLDUMMY;
    }
    return flags;
}
'''
PRELUDE = DECLARATION + '''
static int UnrelatedFunction()
{
    return 7;
}

'''
SUFFIX = '''
static unsigned int AnotherFunction()
{
    unsigned int flags = 0;
    return flags;
}
'''


def source_fixture() -> dict[str, str]:
    result = {path: '// Pinned-source patch anchor fixture.\n' + old + '\n'
              for path, old, _ in P.SIMPLE_EDITS}
    result['src/validation.cpp'] = PRELUDE + BODY + SUFFIX
    result[P.HEADER_PATH] = '\n'.join(P.RESEARCH_FLAGS) + '\n'
    return result


def save_fixture(root: Path, sources: dict[str, str]) -> None:
    for name, contents in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')


class DefinitionSelectionTests(unittest.TestCase):
    def test_reproduce_legacy_forward_declaration_failure(self):
        text = PRELUDE + BODY + SUFFIX
        start = text.index('static unsigned int GetBlockScriptFlags(')
        end = text.index('\n}\n', start) + 3
        self.assertEqual(text[start:end].count('    return flags;'), 0)
        self.assertIn('UnrelatedFunction', text[start:end])

    def test_patch_body_and_preserve_forward_declaration(self):
        result = P.patch_script_flags(PRELUDE + BODY + SUFFIX)
        self.assertTrue(result.startswith(PRELUDE))
        self.assertTrue(result.endswith(SUFFIX))
        self.assertEqual(result.count('flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT'), 1)

    def test_declaration_without_definition_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'definition'):
            P.patch_script_flags(PRELUDE)

    def test_duplicate_definition_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'definition'):
            P.patch_script_flags(BODY + BODY)

    def test_missing_return_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'anchor'):
            P.patch_script_flags(BODY.replace('    return flags;', '    return 0;'))

    def test_duplicate_return_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'anchor'):
            P.patch_script_flags(BODY.replace('    return flags;', '    return flags;\n    return flags;'))

    def test_unterminated_definition_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unterminated'):
            P.patch_script_flags(BODY.rsplit('\n}\n', 1)[0])

    def test_changed_consensus_binding_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'consensus-parameter'):
            P.patch_script_flags(BODY.replace('chainman.GetConsensus();', 'other.GetConsensus();'))

    def test_reapplying_definition_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'already'):
            P.patch_script_flags(P.patch_script_flags(BODY))

    def test_unrelated_braces_before_definition_do_not_change_selection(self):
        for count in range(65):
            text = PRELUDE + ('int Other%d()\n{\n    return 0;\n}\n' % count) * count
            result = P.patch_script_flags(text + BODY + SUFFIX)
            self.assertTrue(result.startswith(text))
            self.assertTrue(result.endswith(SUFFIX))


class PreflightTests(unittest.TestCase):
    def test_plan_edits_exactly_seven_files_without_mutating_input(self):
        sources = source_fixture()
        before = deepcopy(sources)
        edits = P.plan_patch(sources)
        self.assertEqual(len(edits), 7)
        self.assertEqual(set(edits), set(P.PATCH_PATHS))
        self.assertEqual(sources, before)

    def test_missing_file_rejected(self):
        for path in (*P.PATCH_PATHS, P.HEADER_PATH):
            with self.subTest(path=path):
                sources = source_fixture()
                del sources[path]
                with self.assertRaisesRegex(RuntimeError, 'Missing'):
                    P.plan_patch(sources)

    def test_missing_base_research_flags_rejected(self):
        for flag in P.RESEARCH_FLAGS:
            with self.subTest(flag=flag):
                sources = source_fixture()
                sources[P.HEADER_PATH] = sources[P.HEADER_PATH].replace(flag, '')
                with self.assertRaisesRegex(RuntimeError, 'core/patch_core.py'):
                    P.plan_patch(sources)

    def test_source_anchor_changes_rejected(self):
        for path, anchor, _ in P.SIMPLE_EDITS:
            with self.subTest(path=path):
                sources = source_fixture()
                sources[path] = sources[path].replace(anchor, 'CHANGED_SOURCE')
                with self.assertRaisesRegex(RuntimeError, 'anchor'):
                    P.plan_patch(sources)

    def test_duplicate_source_anchors_rejected(self):
        for path, anchor, _ in P.SIMPLE_EDITS:
            with self.subTest(path=path):
                sources = source_fixture()
                sources[path] += anchor
                with self.assertRaisesRegex(RuntimeError, 'found 2'):
                    P.plan_patch(sources)

    def test_partial_previous_patch_rejected(self):
        for path, _, replacement in P.SIMPLE_EDITS[:5]:
            with self.subTest(path=path):
                sources = source_fixture()
                sources[path] = replacement
                with self.assertRaisesRegex(RuntimeError, 'partially applied'):
                    P.plan_patch(sources)

    def test_complete_previous_patch_rejected(self):
        sources = source_fixture()
        sources.update(P.plan_patch(sources))
        with self.assertRaisesRegex(RuntimeError, 'already present'):
            P.plan_patch(sources)

    def test_dry_run_preserves_every_file(self):
        sources = source_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_fixture(root, sources)
            self.assertEqual(len(P.apply_patch(root, check_only=True)), 7)
            self.assertEqual({p: (root/p).read_text() for p in sources}, sources)

    def test_bad_late_anchor_leaves_every_file_unchanged(self):
        sources = source_fixture()
        sources['src/validation.cpp'] = PRELUDE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_fixture(root, sources)
            with self.assertRaisesRegex(RuntimeError, 'definition'):
                P.apply_patch(root)
            self.assertEqual({p: (root/p).read_text() for p in sources}, sources)

    def test_apply_writes_all_planned_changes_and_preserves_header(self):
        sources = source_fixture()
        expected = {**sources, **P.plan_patch(sources)}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_fixture(root, sources)
            P.apply_patch(root)
            self.assertEqual({p: (root/p).read_text() for p in sources}, expected)

    def test_default_opt_in_remains_false(self):
        edits = P.plan_patch(source_fixture())
        self.assertIn('bool keyless_research{false}', edits['src/consensus/params.h'])
        self.assertIn('bool keyless_research{false}', edits['src/kernel/chainparams.h'])
        self.assertIn('GetBoolArg("-keylessresearch", false)', edits['src/chainparams.cpp'])

    def test_runtime_guard_requires_opt_in_and_regtest(self):
        edits = P.plan_patch(source_fixture())
        self.assertIn('consensusparams.keyless_research && '
                      'chainman.GetParams().GetChainType() == ChainType::REGTEST',
                      edits['src/validation.cpp'])

    def test_witness_v1_and_v2_precomputation(self):
        edits = P.plan_patch(source_fixture())
        self.assertIn('scriptPubKey[0] == OP_1 || ', edits['src/script/interpreter.cpp'])
        self.assertIn('scriptPubKey[0] == OP_2)', edits['src/script/interpreter.cpp'])

    def test_import_has_no_filesystem_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-B', '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); import patch_core_regtest',
                str(Path(P.__file__).resolve().parent)], cwd=tmp,
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_command_line_check_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = source_fixture()
            save_fixture(root, sources)
            cmd = [sys.executable, str(Path(P.__file__).resolve()), str(root)]
            check = subprocess.run(cmd + ['--check'], capture_output=True, text=True, timeout=10)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn('Validated 7', check.stdout)
            self.assertEqual({p: (root/p).read_text() for p in sources}, sources)
            apply = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn('Applied 7', apply.stdout)
            repeat = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertIn('already present', repeat.stderr)


class CompiledGuardTests(unittest.TestCase):
    def test_patched_pinned_body_over_256_mock_contexts(self):
        compiler = shutil.which('g++') or shutil.which('clang++')
        if compiler is None:
            self.skipTest('C++ compiler unavailable; pure Python tests still run')
        prelude = r'''
#include <cstdint>
#include <map>
#include <iostream>
enum class ChainType { MAIN, TESTNET, SIGNET, REGTEST };
constexpr unsigned SCRIPT_VERIFY_P2SH=1, SCRIPT_VERIFY_WITNESS=2, SCRIPT_VERIFY_TAPROOT=4;
constexpr unsigned SCRIPT_VERIFY_DERSIG=8, SCRIPT_VERIFY_CHECKLOCKTIMEVERIFY=16;
constexpr unsigned SCRIPT_VERIFY_CHECKSEQUENCEVERIFY=32, SCRIPT_VERIFY_NULLDUMMY=64;
constexpr unsigned SCRIPT_VERIFY_RESEARCH_TXCOMMIT=1U<<21, SCRIPT_VERIFY_RESEARCH_CAT=1U<<22;
constexpr unsigned SCRIPT_VERIFY_RESEARCH_P2MR=1U<<23;
namespace Consensus {
struct Params { bool keyless_research{false}; std::map<int, unsigned> script_flag_exceptions; };
enum DeploymentPos { DEPLOYMENT_DERSIG, DEPLOYMENT_CLTV, DEPLOYMENT_CSV, DEPLOYMENT_SEGWIT };
}
struct CBlockIndex { const int* phashBlock; };
struct MockParams { ChainType chain; ChainType GetChainType() const { return chain; } };
struct ChainstateManager {
    Consensus::Params consensus;
    MockParams params;
    unsigned deployment_mask;
    const Consensus::Params& GetConsensus() const { return consensus; }
    const MockParams& GetParams() const { return params; }
};
const int* Assert(const int* ptr) { return ptr; }
bool DeploymentActiveAt(const CBlockIndex&, const ChainstateManager& m, Consensus::DeploymentPos p) {
    return m.deployment_mask & (1U << p);
}
'''
        baseline = BODY.replace('GetBlockScriptFlags(', 'BaselineGetBlockScriptFlags(', 1)
        patched = P.patch_script_flags(BODY)
        program = prelude + baseline + patched + r'''
int main() {
    int hash=7;
    CBlockIndex block{&hash};
    unsigned checked=0;
    for (int net=0; net<4; ++net)
    for (bool on : {false, true})
    for (unsigned deployments=0; deployments<16; ++deployments)
    for (bool exception : {false, true}) {
        ChainstateManager manager{{on, {}}, {static_cast<ChainType>(net)}, deployments};
        if (exception) manager.consensus.script_flag_exceptions[hash]=0;
        unsigned base=BaselineGetBlockScriptFlags(block, manager);
        unsigned research=SCRIPT_VERIFY_RESEARCH_TXCOMMIT|SCRIPT_VERIFY_RESEARCH_CAT|SCRIPT_VERIFY_RESEARCH_P2MR;
        unsigned expected=base|((on && net==3) ? research : 0);
        if (GetBlockScriptFlags(block, manager)!=expected) return 1;
        ++checked;
    }
    std::cout << "guard_contexts_checked=" << checked << "\n";
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'guard.cpp').write_text(program)
            built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                    str(path/'guard.cpp'), '-o', str(path/'guard')],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            checked = subprocess.run([str(path/'guard')], capture_output=True, text=True, timeout=10)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn('guard_contexts_checked=256', checked.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
