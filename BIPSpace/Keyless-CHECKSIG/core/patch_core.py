#!/usr/bin/env python3
"""Patch Core v30.0 for isolated tests. Research flags are never enabled by
network consensus or policy defaults. Restricted P2MR path, not full BIP360.
"""
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
hp, cp, tp = (root/p for p in ('src/script/interpreter.h','src/script/interpreter.cpp','src/test/script_tests.cpp'))
h, c, t = hp.read_text(), cp.read_text(), tp.read_text()

def once(text, old, new):
    if old == '    if (witversion == 0) {':
        # Another witness-version check occurs outside VerifyWitnessProgram.
        prefix = '    ScriptExecutionData execdata;\n\n'
        old, new = prefix+old, prefix+new
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'Expected one patch anchor, found {count}: {old[:90]}')
    return text.replace(old,new,1)

h = once(h,'    // Constants to point to the highest flag in use.','''    // Research only: never selected by a network's default flags.
    SCRIPT_VERIFY_RESEARCH_TXCOMMIT = (1U << 21),
    SCRIPT_VERIFY_RESEARCH_CAT = (1U << 22),
    SCRIPT_VERIFY_RESEARCH_P2MR = (1U << 23),

    // Constants to point to the highest flag in use.''')
h = once(h,'enum class SigVersion\n{','enum class SigVersion\n{\n    TAPSCRIPT_TXCOMMIT = 4, // Research sighash domain only.')
selector = b'\x02'+hashlib.sha256(b'BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft').digest()
decl = 'static const valtype RESEARCH_TXCOMMIT_KEY{'+','.join(hex(b) for b in selector)+'};\n\n'
c = once(c,'static bool EvalChecksigTapscript(',decl+'static bool EvalChecksigTapscript(')
c = once(c,'''    } else {
        /*
         *  New public key version softforks''','''    } else if ((flags & SCRIPT_VERIFY_RESEARCH_TXCOMMIT) && pubkey == RESEARCH_TXCOMMIT_KEY) {
        if (success && !checker.CheckSchnorrSignature(sig, pubkey, SigVersion::TAPSCRIPT_TXCOMMIT, execdata, serror)) return false;
    } else {
        /*
         *  New public key version softforks''')
c = once(c,'            if (opcode == OP_CAT ||','            if ((opcode == OP_CAT && !(sigversion == SigVersion::TAPSCRIPT && (flags & SCRIPT_VERIFY_RESEARCH_CAT))) ||')
c = once(c,'                case OP_1NEGATE:','''                case OP_CAT: {
                    if (!(sigversion == SigVersion::TAPSCRIPT && (flags & SCRIPT_VERIFY_RESEARCH_CAT))) return set_error(serror, SCRIPT_ERR_DISABLED_OPCODE);
                    if (stack.size() < 2) return set_error(serror, SCRIPT_ERR_INVALID_STACK_OPERATION);
                    const auto tail = stack.back();
                    popstack(stack);
                    if (stack.back().size()+tail.size() > MAX_SCRIPT_ELEMENT_SIZE) return set_error(serror, SCRIPT_ERR_PUSH_SIZE);
                    stack.back().insert(stack.back().end(),tail.begin(),tail.end());
                    break;
                }
                case OP_1NEGATE:''')
c = once(c,'            if (IsOpSuccess(opcode)) {','            if (IsOpSuccess(opcode) && !(opcode == OP_CAT && (flags & SCRIPT_VERIFY_RESEARCH_CAT))) {')
c = once(c,'    case SigVersion::TAPROOT:\n        ext_flag = 0;','''    case SigVersion::TAPSCRIPT_TXCOMMIT:
        ext_flag = 1;
        key_version = 2;
        break;
    case SigVersion::TAPROOT:
        ext_flag = 0;''')
c = once(c,'''    // Additional data for BIP 342 signatures
    if (sigversion == SigVersion::TAPSCRIPT) {''','''    // Additional data for BIP342 signatures and research digest checks.
    if (sigversion == SigVersion::TAPSCRIPT || sigversion == SigVersion::TAPSCRIPT_TXCOMMIT) {''')
c = once(c,'''    assert(sigversion == SigVersion::TAPROOT || sigversion == SigVersion::TAPSCRIPT);
    // Schnorr signatures have 32-byte public keys.''','''    if (sigversion == SigVersion::TAPSCRIPT_TXCOMMIT) {
        if (sig.size() != 32) return set_error(serror,SCRIPT_ERR_SCHNORR_SIG_SIZE);
        uint256 actual;
        if (!this->txdata) return HandleMissingData(m_mdb);
        if (!SignatureHashSchnorr(actual,execdata,*txTo,nIn,SIGHASH_DEFAULT,sigversion,*this->txdata,m_mdb)) return set_error(serror,SCRIPT_ERR_SCHNORR_SIG_HASHTYPE);
        if (!std::equal(sig.begin(),sig.end(),actual.begin())) return set_error(serror,SCRIPT_ERR_SCHNORR_SIG);
        return true;
    }
    assert(sigversion == SigVersion::TAPROOT || sigversion == SigVersion::TAPSCRIPT);
    // Schnorr signatures have 32-byte public keys.''')
c = once(c,'    if (witversion == 0) {','''    // Restricted fixture path: positive-depth c0 P2MR with no annex.
    if (witversion == 2 && program.size() == 32 && !is_p2sh && (flags & SCRIPT_VERIFY_RESEARCH_P2MR)) {
        if (stack.size() < 2) return set_error(serror,SCRIPT_ERR_WITNESS_PROGRAM_WITNESS_EMPTY);
        const valtype& control = SpanPopBack(stack);
        const valtype& script = SpanPopBack(stack);
        if (control.size() < 33 || control.size() > 4097 || (control.size()-1)%32 != 0 || control[0] != 0xc0) return set_error(serror,SCRIPT_ERR_TAPROOT_WRONG_CONTROL_SIZE);
        execdata.m_tapleaf_hash = ComputeTapleafHash(0xc0,script);
        execdata.m_tapleaf_hash_init = true;
        uint256 root = execdata.m_tapleaf_hash;
        for (size_t pos=1;pos<control.size();pos+=32) root = ComputeTapbranchHash(root,std::span{control}.subspan(pos,32));
        if (!std::equal(program.begin(),program.end(),root.begin())) return set_error(serror,SCRIPT_ERR_WITNESS_PROGRAM_MISMATCH);
        execdata.m_annex_init = true;
        execdata.m_annex_present = false;
        execdata.m_validation_weight_left = ::GetSerializeSize(witness.stack)+VALIDATION_WEIGHT_OFFSET;
        execdata.m_validation_weight_left_init = true;
        exec_script = CScript(script.begin(),script.end());
        return ExecuteWitnessScript(stack,exec_script,flags,SigVersion::TAPSCRIPT,checker,execdata,serror);
    }
    if (witversion == 0) {''')
t = once(t,'#include <cstdint>','#include <cstdint>\n#include <cstdlib>\n#include <iostream>\n#include <iterator>')
case = r'''
BOOST_AUTO_TEST_CASE(keyless_research_transaction_vectors)
{
    const char* path = std::getenv("KEYLESS_CORE_VECTORS");
    BOOST_REQUIRE(path != nullptr);
    std::ifstream file(path);
    BOOST_REQUIRE(file.good());
    std::string data((std::istreambuf_iterator<char>(file)),std::istreambuf_iterator<char>());
    UniValue vectors;
    BOOST_REQUIRE(vectors.read(data));
    size_t total = 0;
    for (const UniValue& v : vectors.getValues()) {
        CMutableTransaction tx;
        BOOST_REQUIRE(DecodeHexTx(tx,v["tx_hex"].get_str()));
        const auto spk = ParseHex(v["spent_script"].get_str());
        const CTxOut spent(v["spent_value"].getInt<int64_t>(),CScript(spk.begin(),spk.end()));
        PrecomputedTransactionData precomputed;
        precomputed.Init(tx,std::vector<CTxOut>{spent},true);
        MutableTransactionSignatureChecker checker(&tx,0,spent.nValue,precomputed,MissingDataBehavior::FAIL);
        const unsigned base = SCRIPT_VERIFY_P2SH|SCRIPT_VERIFY_WITNESS|SCRIPT_VERIFY_TAPROOT|SCRIPT_VERIFY_MINIMALDATA;
        unsigned flags = base|SCRIPT_VERIFY_RESEARCH_P2MR|SCRIPT_VERIFY_RESEARCH_CAT;
        if (!v.exists("disable_txcommit") || !v["disable_txcommit"].get_bool()) flags |= SCRIPT_VERIFY_RESEARCH_TXCOMMIT;
        ScriptError error;
        const bool ok = VerifyScript(tx.vin[0].scriptSig,spent.scriptPubKey,&tx.vin[0].scriptWitness,flags,checker,&error);
        std::cout << "KEYLESS_CORE " << v["name"].get_str() << " accepted=" << ok << " error=" << ScriptErrorString(error) << std::endl;
        BOOST_CHECK_MESSAGE(ok == v["expected"].get_bool(),v["name"].get_str());
        ++total;
    }
    std::cout << "KEYLESS_CORE_VECTOR_COUNT " << total << std::endl;
}

'''
t = once(t,'BOOST_AUTO_TEST_SUITE_END()',case+'BOOST_AUTO_TEST_SUITE_END()')
hp.write_text(h)
cp.write_text(c)
tp.write_text(t)
print('Patched opt-in Core interpreter flags and isolated transaction tests.')
