# -*- coding: utf-8 -*-
"""SM3"""

_IV = [
    0x7380166f, 0x4914b2b9, 0x172442d7, 0xda8a0600,
    0xa96f30bc, 0x163138aa, 0xe38dee4d, 0xb0fb0e4e,
]


def _rotl(x, n):
    n &= 31
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _tj(j):
    return 0x79CC4519 if j < 16 else 0x7A879D8A


def _ff(x, y, z, j):
    if j < 16:
        return x ^ y ^ z
    return (x & y) | (x & z) | (y & z)


def _gg(x, y, z, j):
    if j < 16:
        return x ^ y ^ z
    return (x & y) | (~x & z)


def _p0(x):
    return x ^ _rotl(x, 9) ^ _rotl(x, 17)


def _p1(x):
    return x ^ _rotl(x, 15) ^ _rotl(x, 23)


def _cf(v, block):
    w = list(range(68))
    for i in range(16):
        w[i] = int.from_bytes(block[i * 4:i * 4 + 4], "big")
    for j in range(16, 68):
        w[j] = (_p1(w[j - 16] ^ w[j - 9] ^ _rotl(w[j - 3], 15))
                ^ _rotl(w[j - 13], 7) ^ w[j - 6]) & 0xFFFFFFFF
    w1 = [(w[j] ^ w[j + 4]) & 0xFFFFFFFF for j in range(64)]

    a, b, c, d, e, f, g, h = v
    for j in range(64):
        ss1 = _rotl((_rotl(a, 12) + e + _rotl(_tj(j), j)) & 0xFFFFFFFF, 7)
        ss2 = ss1 ^ _rotl(a, 12)
        tt1 = (_ff(a, b, c, j) + d + ss2 + w1[j]) & 0xFFFFFFFF
        tt2 = (_gg(e, f, g, j) + h + ss1 + w[j]) & 0xFFFFFFFF
        d = c
        c = _rotl(b, 9)
        b = a
        a = tt1
        h = g
        g = _rotl(f, 19)
        f = e
        e = _p0(tt2)

    return [(x ^ y) & 0xFFFFFFFF for x, y in zip([a, b, c, d, e, f, g, h], v)]


def sm3_hash(msg: bytes) -> bytes:
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    msg = bytearray(msg)
    bit_len = len(msg) * 8

    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0x00)
    msg += bit_len.to_bytes(8, "big")

    v = _IV[:]
    for i in range(0, len(msg), 64):
        v = _cf(v, msg[i:i + 64])

    return b"".join(x.to_bytes(4, "big") for x in v)


def sm3_hex(msg) -> str:
    return sm3_hash(msg).hex()


if __name__ == "__main__":
    v1 = sm3_hex(b"abc")
    expect1 = "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    print("SM3('abc')      =", v1)
    print("expect          =", expect1)
    print("case1:", "PASS" if v1 == expect1 else "FAIL")

    v2 = sm3_hex(b"abcd" * 16)
    expect2 = "debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732"
    print("SM3('abcd'*16)  =", v2)
    print("expect          =", expect2)
    print("case2:", "PASS" if v2 == expect2 else "FAIL")
