"""Pallas group and public-state checks for one Nova relaxed-instance fold.

This is an algebraic verification kernel, not a complete NIFS proof and not
Microsoft Nova's native transcript. It deliberately leaves R1CS satisfaction,
cross-term correctness, Pedersen binding and Spartan IPA verification to other
components. Built to expose the exact obligations of a Script-level verifier.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import struct
from nova_ipa import O, Q, add, mul, on_curve, encode_point, enc_scalar, Reject, require

@dataclass(frozen=True)
class Instance:
    u: int
    x: tuple[int,...]
    w: tuple[int,int] | None
    e: tuple[int,int] | None

    def bytes(self) -> bytes:
        enc_scalar(self.u)
        require(0 < len(self.x) <= 32, "public_arity")
        require(on_curve(self.w) and on_curve(self.e), "commitment_not_on_curve")
        return (enc_scalar(self.u)+bytes([len(self.x)])
                +b"".join(enc_scalar(v) for v in self.x)
                +encode_point(self.w)+encode_point(self.e))

def challenge(old: Instance, fresh: Instance, cross, txcommit: bytes) -> int:
    require(len(txcommit)==32 and on_curve(cross), "context_or_cross")
    t=sha256(b"BIPSpace/Nova-NIFS-fold-research-v1"
              +txcommit+old.bytes()+fresh.bytes()+encode_point(cross)).digest()
    c=int.from_bytes(t,"little")%Q
    require(c != 0,"zero_challenge")
    return c

def expected_fold(old: Instance, fresh: Instance, cross, txcommit: bytes):
    require(len(old.x)==len(fresh.x),"arity_mismatch")
    r=challenge(old,fresh,cross,txcommit)
    folded=Instance(
        (old.u+r*fresh.u)%Q,
        tuple((a+r*b)%Q for a,b in zip(old.x,fresh.x)),
        add(old.w,mul(fresh.w,r)),
        add(add(old.e,mul(cross,r)),mul(fresh.e,r*r%Q)),
    )
    return r,folded

def verify_fold(old: Instance, fresh: Instance, cross, claimed: Instance,
                txcommit: bytes) -> bool:
    try:
        _,expect=expected_fold(old,fresh,cross,txcommit)
        claimed.bytes()
        return claimed==expect
    except (Reject,ValueError,TypeError,OverflowError):
        return False

if __name__=="__main__":
    from nova_ipa import generator
    digest=sha256(b"one keyless transaction").digest()
    g,h,t=generator(b"G",0),generator(b"H",1),generator(b"U",0)
    a=Instance(1,(2,5),mul(g,7),mul(h,11))
    b=Instance(1,(3,8),mul(g,13),None)
    r,out=expected_fold(a,b,t,digest)
    print({"challenge_hex":hex(r),"valid_fold":verify_fold(a,b,t,out,digest)})
