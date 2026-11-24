"""Publicly known keys for the isolated Bitcoin recovery fixtures."""

import hashlib

HOLDER_PUB = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
MINT_PUB = '02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def fixture_wif(scalar: int) -> str:
    key = b'\xef' + scalar.to_bytes(32, 'big') + b'\x01'
    checksum = hashlib.sha256(hashlib.sha256(key).digest()).digest()[:4]
    number = int.from_bytes(key + checksum, 'big')
    encoded = ''
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return encoded


def descriptor(holder: str, mint: str, delay: int, issuance_hash: str | None = None) -> str:
    policy = f'and_v(v:pk({holder}),or_i(pk({mint}),older({delay})))'
    if issuance_hash is not None:
        policy = f'and_v(v:sha256({issuance_hash}),{policy})'
    return f'wsh({policy})'
