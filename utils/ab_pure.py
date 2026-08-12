# -*- coding: utf-8 -*-
"""a_bogus"""

import random as _rnd
import re
import time as _time
import urllib.parse

from utils.fingerprint import get_profile
from utils.sm3 import sm3_hash

SALT = "dhzx"
BDMS_VERSION = "1.0.1.19-fix.01"
FORTNIGHT_EPOCH = 1721836800000
DUMP_CLOSURE_TIME = 1720000000000
DUMP_COUNTER_INIT = 2
DUMP_BROWSER_NAME = "Firefox"
RC4_KEY_BYTE = 211
FIXED_NOW = 1720000000000
FIXED_RAND = 0.4142135623730951

ALPHABET_S3 = "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe"
ALPHABET_S4 = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"

GEO_VALUES = (2560, 1297, 2560, 1392, 2560, 1400, 2560, 1440)
GEO_PLATFORM = "Win32"

BROWSER_TABLE = (
    ("Huawei", (r"\bhuawei\b",)),
    ("Chrome", (r"(chrome)\/([\w.]+)(?!.*chromium)",)),
    ("Edge", (r"(edg|edge)\/([\w.]+)",)),
    ("Firefox", (r"\bfocus\/([\w.]+)", r"fxios\/([-\w.]+)",
                 r"mobile vr; rv:([\w.]+)\).+firefox", r"(firefox)\/([\w.]+)")),
    ("IE", (r"(msie |trident.*rv:)([\w.]+)",)),
    ("Opera", (r"(opera|opr)\/([\w.]+)",)),
    ("Safari", (r"(safari)\/([\w.]+)(?!.*chrome)",)),
)
BROWSER_OFFSET = {"Chrome": 0, "Firefox": 40, "Safari": 81, "Edge": 125, "Huawei": 170}

A98_PERM = (34, 44, 56, 61, 73, 29, 70, 45, 35, 49, 38, 66, 51, 68, 28, 48, 64, 47,
            30, 71, 26, 55, 31, 69, 59, 40, 62, 63, 27, 72, 41, 74, 57, 52, 42, 39,
            33, 67, 53, 43, 65, 46, 36, 24, 60, 32, 79, 80, 84, 85)

Z148_R_MASKS = (145, 66, 44)
Z148_IN_MASKS = (110, 189, 211)
Z146_MASK_A = 170
Z146_MASK_B = 85


def b64_custom(data, alphabet):
    out = []
    for i in range(0, len(data), 3):
        chunk = data[i:i + 3]
        n = len(chunk)
        b = list(chunk) + [0] * (3 - n)
        v = (b[0] << 16) | (b[1] << 8) | b[2]
        idx = [(v >> 18) & 63, (v >> 12) & 63, (v >> 6) & 63, v & 63]
        if n == 1:
            out += [alphabet[idx[0]], alphabet[idx[1]], "=", "="]
        elif n == 2:
            out += [alphabet[idx[0]], alphabet[idx[1]], alphabet[idx[2]], "="]
        else:
            out += [alphabet[k] for k in idx]
    return "".join(out)


def rc4_variant(key, data):
    sbox = [255 - x for x in range(256)]
    j = 0
    for i in range(256):
        j = (j * sbox[i] + j + key[i % len(key)]) % 256
        sbox[i], sbox[j] = sbox[j], sbox[i]
    out = []
    i = j = 0
    for b in data:
        i = (i + 1) % 256
        j = (j + sbox[i]) % 256
        sbox[i], sbox[j] = sbox[j], sbox[i]
        out.append(b ^ sbox[(sbox[i] + sbox[j]) % 256])
    return out


def str_to_bytes(s):
    out = []
    for ch in s:
        c = ord(ch)
        if c & 65280:
            out.append(c >> 8)
            out.append(c & 255)
        else:
            out.append(c)
    return out


def le_bytes(value, count):
    return [(int(value) >> (8 * i)) & 255 for i in range(count)]


def to_int32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def z146_blend(c0, c1, r0, r1):
    return [(r0 & Z146_MASK_A) | (c0 & Z146_MASK_B),
            (r0 & Z146_MASK_B) | (c0 & Z146_MASK_A),
            (r1 & Z146_MASK_A) | (c1 & Z146_MASK_B),
            (r1 & Z146_MASK_B) | (c1 & Z146_MASK_A)]


def z148_expand(arr, rand_fn):
    out = []
    i = 0
    n = len(arr)
    while i < n:
        if i + 2 < n:
            r = int(rand_fn() * 1000) & 255
            b0 = (r & Z148_R_MASKS[0]) | (arr[i] & Z148_IN_MASKS[0])
            b1 = (r & Z148_R_MASKS[1]) | (arr[i + 1] & Z148_IN_MASKS[1])
            b2 = (r & Z148_R_MASKS[2]) | (arr[i + 2] & Z148_IN_MASKS[2])
            b3 = ((arr[i] & Z148_R_MASKS[0]) | (arr[i + 1] & Z148_R_MASKS[1])
                  | (arr[i + 2] & Z148_R_MASKS[2]))
            out += [b0, b1, b2, b3]
        else:
            out.append(arr[i])
            if i + 1 < n and arr[i + 1]:
                out.append(arr[i + 1])
        i += 3
    return out


def escape_digest(digest, idx, reserved, fallback, force):
    v = digest[idx] if idx < len(digest) else fallback
    while v == reserved:
        idx += 1
        v = digest[idx] if idx < len(digest) else fallback
    return reserved if force else v


def browser_name(ua):
    for name, regs in BROWSER_TABLE:
        if any(re.search(p, ua, re.I) for p in regs):
            return name
    return "Other"


def z143_rand_offset(rand_fn, name):
    return int(rand_fn() * 40) + BROWSER_OFFSET.get(name, 210)


def z144_check(rand_fn, flags_byte):
    if flags_byte & 64:
        r = int(rand_fn() * 109)
        return r + 110 + (r % 2)
    r = int(rand_fn() * 240)
    return r + (r % 2) + 1 if r > 109 else r


def z145_pemrissions_bits(rand_fn):
    base = int(rand_fn() * 255) & 77
    return base | 2 | 16 | 32 | 128


def z149_counter_bucket(counter):
    if counter > 10745:
        return 3
    if counter > 1283:
        return 4
    if counter > 139:
        return 5
    return 6


def env_flags_byte(stack_is_node, ua):
    flags = 1
    flags |= 1 << 1
    flags |= int(stack_is_node) << 2
    flags |= int(browser_name(ua) == "Firefox") << 5
    return flags


class ABogusPureSigner:
    def __init__(self, fixed=True, ua=None):
        self.fixed = fixed
        self.ua = ua or (FIREFOX_UA if fixed else get_profile()["ua"])
        self.counter = DUMP_COUNTER_INIT
        self.geo = GEO_VALUES if fixed else get_profile()["geo"]
        self.offset_name = DUMP_BROWSER_NAME if fixed else browser_name(self.ua)

    def _now(self):
        return FIXED_NOW if self.fixed else int(_time.time() * 1000)

    def _rand(self):
        return FIXED_RAND if self.fixed else _rnd.random()

    def sign(self, url, body=""):
        return self.sign_query(urllib.parse.urlsplit(url).query, body)

    def sign_query(self, query, body=""):
        L = {}
        self.counter += 1
        L[12] = 3
        t = self._now()
        L[14] = t
        v129 = 129
        v14 = 14
        h1 = sm3_hash(sm3_hash((query + SALT).encode("utf-8")))
        h2 = sm3_hash(sm3_hash((body + SALT).encode("utf-8")))
        ua_key = [v129 // 256, v129 % 256, v14 % 256]
        ua_cipher = rc4_variant(ua_key, [ord(c) for c in self.ua.strip()])
        h_ua = sm3_hash(b64_custom(ua_cipher, ALPHABET_S3).encode("utf-8"))
        ink = t - 1
        L[23] = [3, 82]
        L[24] = 41
        L[25] = [1, 0, 1, 0, 1]
        L[26] = int((t - FORTNIGHT_EPOCH) / 1000 / 60 / 60 / 24 / 14)
        L[27] = z149_counter_bucket(self.counter)
        closure_t = DUMP_CLOSURE_TIME if self.fixed else t
        L[28] = (t - closure_t + 3) & 255 if closure_t > 0 else 2
        for i, b in enumerate(le_bytes(t, 6)):
            L[29 + i] = b
        L[35], L[36] = le_bytes(v129, 2)
        flags = env_flags_byte(self.fixed, self.ua)
        L[37] = [0, 0, 0, 0, flags]
        L[38], L[39] = le_bytes(flags, 2)
        for i in range(4):
            L[40 + i] = 0
        for i, b in enumerate(le_bytes(v14, 4)):
            L[44 + i] = b
        L[48], L[49] = h1[9], h1[18]
        L[51] = escape_digest(h1, 3, 11, 12, bool(flags & 2))
        L[52], L[53] = h2[10], h2[19]
        L[55] = escape_digest(h2, 4, 8, 9, bool(flags & 4))
        L[56], L[57] = h_ua[11], h_ua[21]
        L[59] = escape_digest(h_ua, 5, 12, 13, bool(flags & 8))
        for i, b in enumerate(le_bytes(ink, 6)):
            L[60 + i] = b
        L[66] = L[12]
        for i, b in enumerate(le_bytes(6383, 4)):
            L[67 + i] = b
        for i, b in enumerate(le_bytes(6383, 4)):
            L[71 + i] = b
        geo_str = "|".join([str(v) for v in self.geo] + [GEO_PLATFORM])
        L[77] = str_to_bytes(geo_str)
        L[78] = len(L[77])
        L[79], L[80] = le_bytes(L[78], 2)
        L[81] = str((t + 3) & 255) + ","
        L[82] = str_to_bytes(L[81])
        L[83] = len(L[82])
        L[84], L[85] = le_bytes(L[83], 2)
        v6 = self._rand() * 65535
        a8 = z146_blend(L[25][0], L[25][1], int(v6) & 255, (int(v6) >> 8) & 255)
        self._rand()
        a8 += z146_blend(L[25][2], L[25][3], z144_check(self._rand, flags),
                         z145_pemrissions_bits(self._rand))
        L[86] = a8
        chk = 0
        for b in a8 + [L[s] for s in (
                24, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 38, 39, 40, 41, 42, 43,
                44, 45, 46, 47, 48, 49, 51, 52, 53, 55, 56, 57, 59, 60, 61, 62, 63, 64,
                65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 79, 80, 84, 85)]:
            chk ^= b
        L[87] = to_int32(chk)
        a98 = [L[s] for s in A98_PERM] + L[77] + L[82] + [L[87]]
        L[88] = a98
        hr0 = int(self._rand() * 65535) & 255
        L[89] = z146_blend(3, 82, hr0, z143_rand_offset(self._rand, self.offset_name))
        plain = a8 + z148_expand(a98, self._rand)
        cipher = rc4_variant([RC4_KEY_BYTE], [x & 0xFFFF for x in plain])
        return b64_custom(L[89] + [c & 255 for c in cipher], ALPHABET_S4)
