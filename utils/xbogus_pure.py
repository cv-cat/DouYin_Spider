# -*- coding: utf-8 -*-
"""X-Bogus"""

import hashlib
import random as _rnd

ALPHABET = "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe"


def b64_custom(data):
    out = []
    for i in range(0, len(data), 3):
        chunk = data[i:i + 3]
        n = len(chunk)
        b = list(chunk) + [0] * (3 - n)
        v = (b[0] << 16) | (b[1] << 8) | b[2]
        idx = [(v >> 18) & 63, (v >> 12) & 63, (v >> 6) & 63, v & 63]
        if n == 1:
            out += [ALPHABET[idx[0]], ALPHABET[idx[1]], "=", "="]
        elif n == 2:
            out += [ALPHABET[idx[0]], ALPHABET[idx[1]], ALPHABET[idx[2]], "="]
        else:
            out += [ALPHABET[k] for k in idx]
    return "".join(out)


def rc4(key, data):
    sbox = list(range(256))
    j = 0
    for i in range(256):
        j = (j + sbox[i] + key[i % len(key)]) & 255
        sbox[i], sbox[j] = sbox[j], sbox[i]
    out = []
    i = j = 0
    for b in data:
        i = (i + 1) & 255
        j = (j + sbox[i]) & 255
        sbox[i], sbox[j] = sbox[j], sbox[i]
        out.append(b ^ sbox[(sbox[i] + sbox[j]) & 255])
    return out


def _rand255(r):
    return int(255 * r) & 255


def compute_env_flags(browser="Chrome", top_level=True, geometry_sane=True):
    z716 = False
    z704 = False
    z724 = True
    z722 = False
    z714 = browser == "Firefox"
    z727 = not top_level
    z720 = not geometry_sane
    return (1 | z716 << 1 | z704 << 2 | z724 << 3 | z722 << 4
            | z714 << 5 | z727 << 6 | z720 << 7)


def compute_v14():
    return 4 | 8


def generate_xbogus(stub_hex, counter, r1, r2, r3, payload="", env_flags=None, v14=None):
    if env_flags is None:
        env_flags = compute_env_flags()
    if v14 is None:
        v14 = compute_v14()
    h1 = hashlib.md5(hashlib.md5(payload.encode("utf-8")).digest()).digest()
    h2 = hashlib.md5(bytes.fromhex(stub_hex)).digest()
    counter += 1
    plain = [
        counter & 0x3F,
        (counter >> 8) & 255,
        env_flags,
        v14,
        h1[14], h1[15],
        h2[14], h2[15],
        _rand255(r2),
    ]
    chk = 0
    for b in plain:
        chk ^= b
    key_byte = _rand255(r3)
    cipher = rc4([key_byte], plain + [chk])
    eef = (1 << 6) | ((int(100 * r1) & 1) << 4)
    return b64_custom([eef, key_byte] + cipher)


class XbogusSigner:

    def __init__(self, browser="Chrome", top_level=True, geometry_sane=True):
        self.counter = 0
        self.env_flags = compute_env_flags(browser, top_level, geometry_sane)
        self.v14 = compute_v14()

    def sign(self, stub_hex, payload=""):
        xb = generate_xbogus(stub_hex, self.counter, _rnd.random(), _rnd.random(), _rnd.random(),
                             payload, self.env_flags, self.v14)
        self.counter += 1
        return xb
