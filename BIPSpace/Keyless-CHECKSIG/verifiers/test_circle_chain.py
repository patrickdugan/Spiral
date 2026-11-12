"""Compiler regressions. The separate Core job executes the real proof stages."""
import unittest
from circle_chain import Builder, compile_transition, compare_to_constant, comparison_hint, serialize, message_digest, h, ZERO, snum, TXCOMMIT


def read_num(raw):
    if len(raw)>4:
        raise ValueError('Numeric size')
    if raw and raw[-1]&0x7f==0 and (len(raw)==1 or not raw[-2]&0x80):
        raise ValueError('Nonminimal numeric encoding')
    if not raw:
        return 0
    value=int.from_bytes(raw,'little')
    return -(value&~(0x80<<((len(raw)-1)*8))) if raw[-1]&0x80 else value


def vm(script, witness, digest=None):
    """Test-only subset interpreter. Bitcoin Core remains the execution gate."""
    stack=list(witness); alt=[]; cond=[]; pos=0; peak=len(stack)
    if peak>1000 or any(len(x)>520 for x in stack):
        raise ValueError('Initial stack budget')
    def pop():
        if not stack:
            raise ValueError('Stack underflow')
        return stack.pop()
    while pos<len(script):
        code=script[pos]; pos+=1; data=None
        if 1<=code<=75:
            data=script[pos:pos+code]; pos+=code
            if len(data)!=code:
                raise ValueError('Push truncation')
        elif code in (76,77,78):
            width={76:1,77:2,78:4}[code]
            n=int.from_bytes(script[pos:pos+width],'little'); pos+=width
            data=script[pos:pos+n]; pos+=n
            if len(data)!=n:
                raise ValueError('Push truncation')
        if code==0x63:
            if all(cond):
                flag=pop()
                if flag not in (b'',b'\x01'):
                    raise ValueError('MINIMALIF')
                cond.append(flag==b'\x01')
            else:
                cond.append(False)
            continue
        if code==0x67:
            if not cond:
                raise ValueError('ELSE')
            cond[-1]=not cond[-1]
            continue
        if code==0x68:
            if not cond:
                raise ValueError('ENDIF')
            cond.pop()
            continue
        if not all(cond):
            continue
        if data is not None:
            stack.append(data)
        elif code==0:
            stack.append(b'')
        elif code==0x4f:
            stack.append(b'\x81')
        elif 0x51<=code<=0x60:
            stack.append(snum(code-0x50))
        elif code==0x6b:
            alt.append(pop())
        elif code==0x6c:
            if not alt:
                raise ValueError('Altstack underflow')
            stack.append(alt.pop())
        elif code==0x76:
            x=pop(); stack.extend([x,x])
        elif code==0x75:
            pop()
        elif code==0x82:
            stack.append(snum(len(stack[-1])))
        elif code==0x79:
            n=read_num(pop())
            if not 0<=n<len(stack):
                raise ValueError('PICK')
            stack.append(stack[-n-1])
        elif code==0x7c:
            stack[-2:]=stack[-2:][::-1]
        elif code==0x7e:
            b,a=pop(),pop(); stack.append(a+b)
        elif code==0xa8:
            stack.append(h(pop()))
        elif code==0x88:
            if pop()!=pop():
                raise ValueError('EQUALVERIFY')
        elif code==0x69:
            if read_num(pop())==0:
                raise ValueError('VERIFY')
        elif code==0xa5:
            upper,lower,n=read_num(pop()),read_num(pop()),read_num(pop())
            stack.append(snum(int(lower<=n<upper)))
        elif code in (0x9c,0x9e,0x9f,0xa2):
            b,a=read_num(pop()),read_num(pop())
            result={0x9c:a==b,0x9e:a!=b,0x9f:a<b,0xa2:a>=b}[code]
            stack.append(snum(int(result)))
        elif code==0xad:
            key,candidate=pop(),pop()
            if key!=TXCOMMIT or candidate!=digest:
                raise ValueError('TXCOMMIT')
        elif code==0x6a:
            raise ValueError('OP_RETURN')
        else:
            raise ValueError('Unsupported test opcode '+hex(code))
        peak=max(peak,len(stack)+len(alt))
        if peak>1000 or any(len(x)>520 for x in stack+alt):
            raise ValueError('Stack budget')
    if cond:
        raise ValueError('Unterminated conditional')
    return stack,peak


class ChainComparatorTests(unittest.TestCase):
    def check(self,value,constant,alter=None):
        b=Builder(['new_leaf','cmp_pos','cmp_raw','cmp_tail','cmp_num'])
        compare_to_constant(b,constant)
        args=[value]+comparison_hint(value,constant)
        if alter:
            alter(args)
        return vm(b.code,args)[0][-1]

    def test_all_first_difference_positions_and_byte_boundaries(self):
        for pos in range(32):
            for a,b in ((0,1),(1,0),(127,128),(128,127),(255,254),(254,255)):
                first=b'\x35'*pos+bytes([a])+b'\x77'*(31-pos)
                second=b'\x35'*pos+bytes([b])+b'\x44'*(31-pos)
                self.assertEqual(self.check(first,second),snum(int(first<second)))

    def test_wrong_numeric_value_rejected(self):
        with self.assertRaises(ValueError):
            self.check(bytes(32),b'\x01'+bytes(31),lambda a:a.__setitem__(4,b'\x02'))

    def test_wrong_suffix_rejected(self):
        with self.assertRaises(ValueError):
            self.check(bytes(32),b'\x01'+bytes(31),lambda a:a.__setitem__(3,b'\xff'*31))

    def test_wrong_position_rejected(self):
        with self.assertRaises(ValueError):
            self.check(bytes(32),b'\x01'+bytes(31),lambda a:a.__setitem__(1,b'\x01'))

    def test_nonminimal_numeric_rejected(self):
        with self.assertRaises(ValueError):
            self.check(bytes(32),b'\x01'+bytes(31),lambda a:a.__setitem__(4,b'\x00'))

    def test_identical_hashes_fail_closed(self):
        with self.assertRaises(ValueError):
            comparison_hint(bytes(32),bytes(32))


class StateChainTests(unittest.TestCase):
    def setUp(self):
        self.mid=h(b'initial demo transition')
        self.end=h(self.mid)
        self.last=compile_transition(b'\xa8',1,None)
        from circle_chain import tapleaf, push
        self.first=compile_transition(push(self.mid),0,tapleaf(self.last))
        self.a=serialize(0,self.first,ZERO,self.mid,[],h(b'fund'),self.last)
        self.b=serialize(1,self.last,self.mid,self.end,[self.mid],bytes.fromhex(self.a['txid_internal']),None)

    def execute(self,r,s):
        result,peak=vm(s,r['stack'],message_digest(r,s))
        self.assertEqual(result,[b'\x01'])
        self.assertLessEqual(peak,1000)

    def test_valid_linked_transition_pair(self):
        self.execute(self.a,self.first)
        self.execute(self.b,self.last)
        self.assertEqual(self.a['output_script'],self.b['spent_script'])
        self.assertEqual(self.a['txid_internal'],self.b['previous_txid_internal'])

    def test_terminal_recipient_can_change_after_funding(self):
        alternate=serialize(1,self.last,self.mid,self.end,[self.mid],bytes.fromhex(self.a['txid_internal']),None,1)
        self.assertEqual(self.b['spent_script'],alternate['spent_script'])
        self.assertNotEqual(self.b['tx_hex'],alternate['tx_hex'])
        self.execute(alternate,self.last)

    def test_fresh_valid_transition_from_wrong_old_state_fails(self):
        wrong=h(b'unrelated state')
        # The SHA256 stage maps wrong -> H(wrong) correctly. The actual UTXO
        # commits a different old state, which the transaction check rejects.
        r=serialize(1,self.last,wrong,h(wrong),[wrong],bytes.fromhex(self.a['txid_internal']),None,actual_old_state=self.mid)
        with self.assertRaisesRegex(ValueError,'TXCOMMIT'):
            vm(self.last,r['stack'],message_digest(r,self.last))

    def test_wrong_successor_state_fails(self):
        r=serialize(0,self.first,ZERO,h(b'fake new state'),[],h(b'fund'),self.last)
        with self.assertRaises(ValueError):
            vm(self.first,r['stack'],message_digest(r,self.first))

    def test_wrong_self_leaf_fails(self):
        r=dict(self.a); r['stack']=list(r['stack']); r['stack'][0]=bytes(32)
        with self.assertRaises(ValueError):
            vm(self.first,r['stack'],message_digest(r,self.first))

    def test_wrong_old_merkle_order_fails(self):
        r=dict(self.a); r['stack']=list(r['stack']); r['stack'][1]=b'' if r['stack'][1] else b'\x01'
        with self.assertRaises(ValueError):
            vm(self.first,r['stack'],message_digest(r,self.first))

    def test_changed_funding_outpoint_without_new_context_fails(self):
        r=dict(self.a); r['previous_txid_internal']=h(b'other fund').hex()
        with self.assertRaises(ValueError):
            vm(self.first,r['stack'],message_digest(r,self.first))

    def test_wrong_next_program_fails(self):
        wrong=compile_transition(b'\xa8',2,None)
        r=serialize(0,self.first,ZERO,self.mid,[],h(b'fund'),wrong)
        with self.assertRaises(ValueError):
            vm(self.first,r['stack'],message_digest(r,self.first))

    def test_reserve_scripts_have_no_signing_key(self):
        self.assertTrue(self.a['spent_script'].startswith('5220'))
        self.assertTrue(self.b['spent_script'].startswith('5220'))
        self.assertEqual(self.a['control'][0],0xc0)


if __name__=='__main__':
    unittest.main(verbosity=2)
