"""Research-only Pallas inner-product argument (IPA) verification kernel.

Standalone, non-zero-knowledge IPA; neither Nova's full SNARK nor Script.
Version 3 binds the inner-product generator to the public statement.
Version 2 fixed direct claim binding: C commits ONLY to the two vectors,
and the verifier forms C + claim*U before folding. Transcript binding of
claim alone does not enforce claim == <a,b>. A fixed U also allows a
chosen-commitment offset attack, prevented here by a statement challenge.

Relation: C = sum(a_i G_i) + sum(b_i H_i), claim = <a,b>.
The public transaction context is included in Fiat-Shamir. Generators use
a research-only deterministic mapping, with no secret setup material.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import struct

P = int("40000000000000000000000000000000224698fc094cf91b992d30ed00000001", 16)
Q = int("40000000000000000000000000000000224698fc0994a8dd8c46eb2100000001", 16)
B = 5
Point = tuple[int, int] | None
O = None
DOMAIN = b"BIPSpace/Keyless-CHECKSIG/IPA-demo-v3"

class Reject(ValueError):
    pass

def require(ok, message):
    if not ok: raise Reject(message)

def sha(data):
    return sha256(data).digest()

def enc_scalar(v: int) -> bytes:
    require(type(v) is int and 0 <= v < Q, "noncanonical_scalar")
    return v.to_bytes(32, "little")

def sqrt(a: int):
    """Tonelli-Shanks. Returns None if the argument is not a square."""
    a %= P
    if a == 0: return 0
    if pow(a, (P-1)//2, P) != 1: return None
    q, s = P-1, 0
    while q % 2 == 0: q //= 2; s += 1
    z = 2
    while pow(z, (P-1)//2, P) != P-1: z += 1
    m, c, t, r = s, pow(z, q, P), pow(a, q, P), pow(a, (q+1)//2, P)
    while t != 1:
        i, u = 1, (t*t) % P
        while i < m and u != 1:
            u = (u*u) % P
            i += 1
        require(i < m, "sqrt_failed")
        b = pow(c, 1 << (m-i-1), P)
        m, c, t, r = i, (b*b) % P, (t*b*b) % P, (r*b) % P
    return r

def on_curve(a: Point):
    return a is None or (type(a) is tuple and len(a) == 2 and
            all(type(v) is int and 0 <= v < P for v in a) and
            (a[1]*a[1]-a[0]**3-B) % P == 0)

def neg(a):
    require(on_curve(a), "invalid_point")
    return None if a is None else (a[0], (-a[1]) % P)

def add(a, b):
    require(on_curve(a) and on_curve(b), "invalid_point")
    if a is None: return b
    if b is None: return a
    x,y = a; u,v = b
    if x == u and (y+v) % P == 0: return None
    if x == u:
        require(y != 0, "doubling")
        m = (3*x*x * pow(2*y,-1,P)) % P
    else:
        m = ((v-y) * pow((u-x)%P,-1,P)) % P
    rx = (m*m-x-u) % P
    return (rx, (m*(x-rx)-y) % P)

def mul(a, n):
    require(on_curve(a) and type(n) is int, "invalid_scalar_or_point")
    if n < 0: return mul(neg(a),-n)
    r = None
    while n:
        if n & 1: r = add(r,a)
        a = add(a,a)
        n >>= 1
    return r

def msm(points, scalars):
    require(len(points) == len(scalars), "msm_length")
    r = None
    for p, s in zip(points, scalars):
        r = add(r, mul(p, s % Q))
    return r

def encode_point(a: Point) -> bytes:
    require(on_curve(a), "point_encoding")
    return b"\x00"*33 if a is None else bytes((2+(a[1]&1),))+a[0].to_bytes(32,"big")

def decode_point(bs: bytes) -> Point:
    require(len(bs) == 33, "point_size")
    if bs == bytes(33): return None
    require(bs[0] in (2,3), "point_tag")
    x = int.from_bytes(bs[1:], "big")
    require(x < P, "point_range")
    y = sqrt((pow(x,3,P)+B)%P)
    require(y is not None, "point_nonsquare")
    if (y & 1) != (bs[0] & 1): y = P-y
    pt = (x,y)
    require(on_curve(pt), "point_curve")
    return pt

@lru_cache(maxsize=1024)
def generator(tag: bytes, i: int = 0) -> Point:
    """Research try-and-increment mapping; not Nova's generator derivation."""
    require(len(tag) <= 32 and 0 <= i < 2**32, "generator_id")
    for ctr in range(256):
        x = int.from_bytes(sha(DOMAIN+b"/G/"+tag+struct.pack("<II",i,ctr)),"big") % P
        y = sqrt((pow(x,3,P)+B)%P)
        if y is not None:
            if y & 1: y = P-y
            return (x,y)
    raise Reject("hash_to_curve_exhausted")

@lru_cache(maxsize=16)
def basis(n: int):
    require(n >= 2 and n <= 16 and n & (n-1) == 0, "ipa_dimension")
    return ([generator(b"G",i) for i in range(n)],
            [generator(b"H",i) for i in range(n)],generator(b"U",0))

def inner(a,b):
    require(len(a)==len(b), "vector_length")
    return sum(x*y for x,y in zip(a,b)) % Q

def transcript_init(n: int, C: Point, claim: int, context: bytes):
    require(len(context)==32,"context_length")
    return sha(DOMAIN+b"/statement"+struct.pack("<I",n)+encode_point(C)+
               enc_scalar(claim)+context)

def bind_inner_product_generator(base: Point, transcript: bytes) -> Point:
    """Challenge after C and claim are fixed, before IPA rounds.
    A statement-derived U prevents shifting C by a known fixed-U multiple
    to offset a false inner product. This remains research cryptography.
    """
    scale = int.from_bytes(sha(transcript+b"/inner-product-generator"),"little") % Q
    require(scale != 0,"zero_generator_challenge")
    return mul(base,scale)

def challenge(transcript: bytes, L: Point, R: Point):
    require(L is not None and R is not None, "infinite_round_point")
    t = sha(transcript + encode_point(L) + encode_point(R))
    x = int.from_bytes(sha(t+b"/challenge"),"little") % Q
    require(x != 0,"zero_challenge")
    return t, x

@dataclass(frozen=True)
class IpaProof:
    L: tuple[bytes, ...]
    R: tuple[bytes, ...]
    a: int
    b: int

    def encode(self):
        require(len(self.L) == len(self.R) and 1 <= len(self.L) <= 4,"rounds")
        return (bytes([len(self.L)])+b"".join(self.L)+b"".join(self.R)
                +enc_scalar(self.a)+enc_scalar(self.b))

    @staticmethod
    def decode(raw: bytes):
        require(len(raw)>0,"proof_empty")
        n = raw[0]
        require(1 <= n <= 4 and len(raw) == 1+66*n+64,"proof_length")
        j = 1
        L = tuple(raw[j+33*i:j+33*(i+1)] for i in range(n))
        j += 33*n
        R = tuple(raw[j+33*i:j+33*(i+1)] for i in range(n))
        j += 33*n
        a,b = int.from_bytes(raw[j:j+32],"little"), int.from_bytes(raw[j+32:j+64],"little")
        enc_scalar(a);enc_scalar(b)
        for l,r in zip(L,R):
            require(decode_point(l) is not None and decode_point(r) is not None, "infinite_round")
        return IpaProof(L,R,a,b)

def prove(a, b, context: bytes):
    n = len(a)
    G,H,U = basis(n)
    require(len(b)==n and all(type(s) is int and 0<=s<Q for s in a+b),"vector_inputs")
    c = inner(a,b)
    C = add(msm(G,a),msm(H,b))
    tr = transcript_init(n,C,c,context)
    U = bind_inner_product_generator(U,tr)
    aa,bb=list(a),list(b)
    Ls,Rs=[],[]
    while len(aa)>1:
        k = len(aa)//2
        al,ar=aa[:k],aa[k:]
        bl,br=bb[:k],bb[k:]
        gl,gr=G[:k],G[k:]
        hl,hr=H[:k],H[k:]
        L=add(add(msm(gr,al),msm(hl,br)),mul(U,inner(al,br)))
        R=add(add(msm(gl,ar),msm(hr,bl)),mul(U,inner(ar,bl)))
        require(L is not None and R is not None, "round_infinity")
        tr,x=challenge(tr,L,R)
        xi=pow(x,-1,Q)
        aa=[(x*u+xi*v)%Q for u,v in zip(al,ar)]
        bb=[(xi*u+x*v)%Q for u,v in zip(bl,br)]
        G=[add(mul(g,xi),mul(h,x)) for g,h in zip(gl,gr)]
        H=[add(mul(g,x),mul(h,xi)) for g,h in zip(hl,hr)]
        Ls.append(encode_point(L));Rs.append(encode_point(R))
    return C,c,IpaProof(tuple(Ls),tuple(Rs),aa[0],bb[0])

def verify(C: Point, claim: int, proof: IpaProof | bytes, context: bytes):
    try:
        require(C is not None and on_curve(C),"commitment_invalid")
        enc_scalar(claim)
        if isinstance(proof,bytes): proof=IpaProof.decode(proof)
        require(isinstance(proof,IpaProof),"proof_type")
        require(1 <= len(proof.L) <= 4 and len(proof.R)==len(proof.L),"round_count")
        n = 1 << len(proof.L)
        G,H,U = basis(n)
        tr=transcript_init(n,C,claim,context)
        U=bind_inner_product_generator(U,tr)
        state=add(C,mul(U,claim))
        for lb,rb in zip(proof.L,proof.R):
            L,R=decode_point(lb),decode_point(rb)
            tr,x=challenge(tr,L,R)
            xi=pow(x,-1,Q)
            state=add(add(mul(L,x*x % Q),state),mul(R,xi*xi % Q))
            k=len(G)//2
            G=[add(mul(g,xi),mul(h,x)) for g,h in zip(G[:k],G[k:])]
            H=[add(mul(g,x),mul(h,xi)) for g,h in zip(H[:k],H[k:])]
        enc_scalar(proof.a);enc_scalar(proof.b)
        expected=add(add(mul(G[0],proof.a),mul(H[0],proof.b)),
                     mul(U,(proof.a*proof.b)%Q))
        return expected==state
    except (Reject,ValueError,ZeroDivisionError,OverflowError,TypeError):
        return False

if __name__=="__main__":
    context=sha(b"example unsigned keyless tx context")
    C,c,proof=prove([3,5,7,9],[2,4,6,8],context)
    print({"curve":"Pallas","dimension":4,"bytes":len(proof.encode()),
           "valid":verify(C,c,proof.encode(),context),
           "different_context_rejected":not verify(C,c,proof,sha(b"another transaction"))})
