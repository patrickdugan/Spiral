import unittest
from stark_trace import fixture
from weight import weight,serialize_stripped,witness_bytes

class WeightTests(unittest.TestCase):
    def test_toy_weight_exactly_serialized(self):
        tx,script,control,wit=fixture()
        w=weight(tx,wit,script,control)
        self.assertEqual(w["weight_units"],
            4*len(serialize_stripped(tx))+2+len(witness_bytes(wit,script,control)))
        self.assertEqual(w["script_bytes"],296)
        self.assertLess(w["weight_units"],4000000)
        self.assertEqual(w["witness_items"],11)

    def test_different_witness_satisfies_same_script(self):
        tx1,script1,c1,w1=fixture(3,0)
        tx2,script2,c2,w2=fixture(5,1)
        self.assertEqual(script1,script2)
        self.assertEqual(c1,c2)
        self.assertEqual(weight(tx1,w1,script1,c1)["weight_units"],
                         weight(tx2,w2,script2,c2)["weight_units"])

    def test_adding_witness_bytes_increases_weight(self):
        tx,script,c,wit=fixture()
        baseline=weight(tx,wit,script,c)["weight_units"]
        new=list(wit)
        new[0]+=b"\x01"
        self.assertEqual(weight(tx,new,script,c)["weight_units"],baseline+1)

if __name__=="__main__":
    unittest.main()
