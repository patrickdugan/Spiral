import unittest
from types import SimpleNamespace

from proofdesk import protected_registry as registry
from proofdesk.domain import Refused


class ProtectedRegistryTest(unittest.TestCase):
    def test_canonical_marker_binds_exact_one_or_more_vouts(self):
        txid = "a4" * 32
        payload = bytes.fromhex(registry.registration_payload(txid, (0, 3, 65536)))
        script = (bytes((0x6a, len(payload))) + payload).hex()
        self.assertEqual(registry._registration(script), {(txid, 0), (txid, 3), (txid, 65536)})
        for vouts in ((1, 0), (0, 0), (False,), (-1,), (2**32,), (), tuple(range(10))):
            with self.subTest(vouts=vouts), self.assertRaises(Refused):
                registry.registration_payload(txid, vouts)
        for changed in (script[:-2], "6a4c" + script[2:], "6a" + script[2:4] + "00" + script[6:], script.upper()):
            with self.subTest(changed=changed), self.assertRaises(Refused):
                registry._registration(changed)

    def test_registry_authority_cannot_enroll_itself_as_a_reserve(self):
        funding, spending, first, second = ("a1" * 32, "a2" * 32, "b1" * 32, "b2" * 32)
        script = "0014" + "d1" * 20
        coin = {"n": 0, "value": "0.001", "scriptPubKey": {"hex": script}}
        payload = bytes.fromhex(registry.registration_payload(funding, [0]))
        tagged = {"n": 1, "value": 0, "scriptPubKey": {"hex": (bytes((0x6a, len(payload))) + payload).hex()}}
        root = {"schema": registry.SCHEMA, "genesis": registry.GENESIS, "mint": "mint", "txid": funding,
                "vout": 0, "block": first, "height": 1, "script": script, "sats": 100000}

        def rpc(method, args):
            if method == "getblockhash":
                return {1: first, 2: second}[args[0]]
            if method == "getrawtransaction":
                if args[0] == funding:
                    return {"txid": funding, "in_active_chain": True, "vout": [coin]}
                return {"txid": spending, "in_active_chain": True, "hex": "raw",
                        "vin": [{"txid": funding, "vout": 0}], "vout": [coin, tagged]}
            if method == "gettxout":
                return None
            if method == "getblockheader":
                return {"height": 2}
            if method == "gettxspendingprevout":
                return [{"txid": funding, "vout": 0, "spendingtxid": spending,
                         "spendingtx": "raw", "blockhash": second}]
            raise AssertionError(method)

        with self.assertRaisesRegex(Refused, "registry_coin_reused_as_reserve"):
            registry.discover(SimpleNamespace(rpc=rpc), root, "mint",
                              {"blocks": 2, "bestblockhash": second}, max_reserves=4)


if __name__ == "__main__":
    unittest.main()
