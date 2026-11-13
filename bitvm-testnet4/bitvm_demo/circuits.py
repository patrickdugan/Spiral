"""Hash-committed NAND refutation leaves using only deployed Tapscript opcodes."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from .bitcoin import btc, fresh_secret, number, sign, sighash, tree, xonly


@dataclass(repr=False)
class Circuit:
    kind: str
    claimed: dict[str, int]
    labels: dict[str, bytes] = field(repr=False)
    challenger: int = field(repr=False)
    refund: int = field(repr=False)
    delay: int = 2

    @property
    def gates(self) -> tuple[tuple[str, str, str], ...]:
        if self.kind == 'nand':
            return (('a', 'b', 'out'),)
        if self.kind == 'half-adder':
            return (('a', 'b', 'n0'), ('a', 'n0', 'n1'), ('b', 'n0', 'n2'),
                    ('n1', 'n2', 'sum'), ('n0', 'n0', 'carry'))
        raise ValueError('unknown circuit kind')

    @classmethod
    def create(cls, kind: str, malicious: bool = True, a: int = 1, b: int = 1):
        if a not in (0, 1) or b not in (0, 1):
            raise ValueError('inputs must be bits')
        claimed = {'a': a, 'b': b}
        if kind == 'nand':
            claimed['out'] = 1 - (a & b)
            if malicious: claimed['out'] ^= 1
        elif kind == 'half-adder':
            claimed.update(n0=1 - (a & b), n1=1 - (a & (1 - (a & b))), n2=1 - (b & (1 - (a & b))))
            claimed.update(sum=1 - (claimed['n1'] & claimed['n2']), carry=a & b)
            if malicious: claimed['sum'] ^= 1
        else:
            raise ValueError('unknown circuit kind')
        return cls(kind, claimed, {name: os.urandom(32) for name in claimed},
                   fresh_secret(), fresh_secret())

    def bad_gates(self) -> list[int]:
        return [index for index, (a, b, c) in enumerate(self.gates)
                if self.claimed[c] != 1 - (self.claimed[a] & self.claimed[b])]

    def _open(self, name: str) -> bytes:
        return b'\xa8' + btc.push(btc.sha256(self.labels[name])) + b'\x88' + number(self.claimed[name]) + b'\x6b'

    def refutation_script(self, index: int) -> bytes:
        a, b, c = self.gates[index]
        return b''.join((self._open(a), self._open(b), self._open(c),
                         b'\x6c\x6c\x6c\x9a\x91\x87\x91\x69',
                         btc.push(xonly(self.challenger)), b'\xac'))

    @property
    def refund_script(self) -> bytes:
        return number(self.delay) + b'\xb2\x75' + btc.push(xonly(self.refund)) + b'\xac'

    def taproot(self):
        return tree([self.refutation_script(i) for i in range(len(self.gates))] + [self.refund_script])

    def public(self, network: str = 'testnet4') -> dict:
        if network not in ('testnet4', 'regtest'):
            raise ValueError('only Testnet4 and isolated regtest are supported')
        output = self.taproot()
        return {'schema': 'bitvm-gate-demo-v1', 'network': network, 'kind': self.kind,
                'claim': dict(self.claimed), 'gates': [list(gate) for gate in self.gates], 'bad_gates': self.bad_gates(),
                'commitments': {name: btc.sha256(value).hex() for name, value in self.labels.items()},
                'claim_openings': {name: value.hex() for name, value in self.labels.items()},
                'challenger_pubkey': xonly(self.challenger).hex(), 'refund_pubkey': xonly(self.refund).hex(),
                'refund_delay_blocks': self.delay, 'script_pubkey': output.script_pubkey.hex(),
                'address': btc.spk_to_address(output.script_pubkey, network),
                'refutation_scripts': [script.hex() for script in output.leaves[:-1]],
                'refund_script': output.leaves[-1].hex(), 'controls': [control.hex() for control in output.controls],
                'scope': 'Stock-opcode fixed-claim gate refutation primitive; no full BitVM bridge or garbled-verifier dispute graph'}

    def save_private(self, path: Path, network: str = 'testnet4') -> None:
        if network not in ('testnet4', 'regtest'):
            raise ValueError('unsupported network')
        path.parent.mkdir(parents=True, exist_ok=True)
        private = {'schema': 'bitvm-private-demo-v1', 'network': network, 'kind': self.kind, 'claimed': self.claimed,
                   'labels': {name: value.hex() for name, value in self.labels.items()},
                   'challenger': self.challenger.to_bytes(32, 'big').hex(), 'refund': self.refund.to_bytes(32, 'big').hex(),
                   'delay': self.delay}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(private, stream)
            stream.flush()
            os.fsync(stream.fileno())

    @classmethod
    def load_private(cls, path: Path, network: str = 'testnet4'):
        data = json.loads(path.read_text())
        if data.get('schema') != 'bitvm-private-demo-v1' or data.get('network') != network or network not in ('testnet4', 'regtest'):
            raise ValueError('private state has a different network or schema')
        result = cls(data['kind'], data['claimed'], {name: bytes.fromhex(value) for name, value in data['labels'].items()},
                     int(data['challenger'], 16), int(data['refund'], 16), data['delay'])
        if set(result.labels) != set(result.claimed) or any(v not in (0, 1) for v in result.claimed.values()):
            raise ValueError('invalid circuit state')
        if any(len(value) != 32 for value in result.labels.values()):
            raise ValueError('invalid wire labels')
        if not 1 <= result.delay <= 144:
            raise ValueError('unsupported refund delay')
        result.public(network)
        return result

    def spend(self, txid: str, vout: int, value_sats: int, destination: bytes, *, gate: int | None = None,
              fee_sats: int = 2000, refund: bool = False) -> btc.Tx:
        if not 0 <= vout <= 0xffffffff or not 0 < fee_sats <= 5000 or not 330 <= value_sats - fee_sats <= 1_000_000:
            raise ValueError('demo outpoint, amount or fee is outside its bounds')
        previous = bytes.fromhex(txid)
        if len(previous) != 32:
            raise ValueError('invalid funding txid')
        output = self.taproot()
        if refund:
            index, scalar = len(self.gates), self.refund
        else:
            if gate is None or not 0 <= gate < len(self.gates):
                raise ValueError('a valid gate index is required')
            index, scalar = gate, self.challenger
        sequence = self.delay if refund else 0xfffffffd
        tx = btc.Tx(2, [btc.TxIn(previous[::-1], vout, b'', sequence)],
                    [btc.TxOut(value_sats - fee_sats, destination)], 0)
        script, control = output.leaves[index], output.controls[index]
        signature = sign(sighash(tx, value_sats, output.script_pubkey, script), scalar)
        witness = [signature]
        if not refund:
            for name in reversed(self.gates[index]):
                witness.append(self.labels[name])
        tx.inputs[0].witness = witness + [script, control]
        return tx
