#!/usr/bin/env python3
"""Add chain-consistency assertions to the isolated Core research test.

Run only after core/patch_core.py, in a disposable pinned Core checkout.
This changes tests, not Bitcoin's default validation flags or consensus rules.
"""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'src/test/script_tests.cpp'
text = path.read_text()


def once(old: str, new: str) -> None:
    global text
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one Core test anchor: {old[:80]}')
    text = text.replace(old, new, 1)


once('#include <iterator>', '#include <iterator>\n#include <optional>')
once('    size_t total = 0;\n    for (const UniValue& v : vectors.getValues()) {',
     '''    size_t total = 0;
    size_t chain_count = 0;
    std::optional<CMutableTransaction> chain_previous;
    for (const UniValue& v : vectors.getValues()) {''')
once('        PrecomputedTransactionData precomputed;\n        precomputed.Init(tx,std::vector<CTxOut>{spent},true);',
     '''        const std::string name = v["name"].get_str();
        const std::string prefix = "circle-chain-stage-";
        const bool chain_stage = name.size() == prefix.size()+3 && name.rfind(prefix,0) == 0;
        if (chain_stage) {
            BOOST_REQUIRE_EQUAL(std::stoul(name.substr(prefix.size())),chain_count);
            BOOST_REQUIRE_EQUAL(tx.vin.size(),1U);
            BOOST_REQUIRE_EQUAL(tx.vout.size(),1U);
            if (chain_previous) {
                BOOST_REQUIRE(tx.vin[0].prevout == COutPoint(chain_previous->GetHash(),0));
                BOOST_REQUIRE(spent == chain_previous->vout[0]);
            }
        }
        PrecomputedTransactionData precomputed;
        precomputed.Init(tx,std::vector<CTxOut>{spent},true);''')
once('        BOOST_CHECK_MESSAGE(ok == v["expected"].get_bool(),v["name"].get_str());\n        ++total;',
     '''        BOOST_CHECK_MESSAGE(ok == v["expected"].get_bool(),v["name"].get_str());
        if (chain_stage) {
            BOOST_REQUIRE(ok);
            BOOST_REQUIRE_EQUAL(tx.vout[0].nValue,spent.nValue-10000);
            chain_previous = tx;
            ++chain_count;
        }
        ++total;''')
once('    std::cout << "KEYLESS_CORE_VECTOR_COUNT " << total << std::endl;',
     '''    BOOST_REQUIRE_EQUAL(chain_count,72U);
    std::cout << "KEYLESS_CORE_LINKED_TRANSITIONS " << chain_count << std::endl;
    std::cout << "KEYLESS_CORE_VECTOR_COUNT " << total << std::endl;''')
path.write_text(text)
print('Added independent Core checks of 72 consecutive outpoints, spent outputs and value flow.')
