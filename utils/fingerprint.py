# -*- coding: utf-8 -*-
"""浏览器指纹档案。

必须与 `.env` 里 cookie 所属的那台浏览器一致：cookie 里的
`stream_recommend_feed_params` 已经写死了屏幕尺寸 / CPU 核数 / 内存，
query 里再报另一套值就会自相矛盾。默认值取自 2026-08-16 的 Chrome 实录抓包，
换设备时用环境变量覆盖即可（见 DY_FP_* ）。
"""

import base64
import hashlib
import json
import math
import os
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 2026-08-16 Chrome 实录：create_v2 抓包所用设备
_DEFAULTS = {
    "ua": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
    "browser_version": "151.0.0.0",
    "engine_version": "151.0.0.0",
    "screen_width": "2560",
    "screen_height": "1440",
    "cpu_core_num": "20",
    "device_memory": "32",
    "webgl_vendor": "Google Inc. (NVIDIA)",
    # 2026-08-22 更正：原值写的是 RTX 4070，但本机实际是 RTX 5060 Ti
    # （浏览器实录的 account_sdk_source_info 里就是这串）。这条必须与
    # DY_DTRAIT_BLOB 里的 webGL 特征同源——那个 blob 是从这台机器抓的，
    # 显卡型号对不上等于自曝。
    "webgl_renderer": ("ANGLE (NVIDIA, NVIDIA GeForce RTX 5060 Ti (0x00002D04) "
                       "Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    # 浏览器实录的 accept-language，与 browser_language=zh-CN 配套
    "accept_language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7,ja;q=0.6",
}

_profile = None
_COMPONENTS = None
_UNDEFINED = object()

# CryptoJS's ``AES.encrypt(message, passphrase)`` uses the OpenSSL-compatible
# EVP_BytesToKey derivation (MD5, one 8-byte random salt).  Keep this helper
# local so fpk1 generation has exactly the same wire format as the page SDK.
_FP_SECRET = b"byte_fingerprint"


def _env(key, default):
    return os.getenv("DY_FP_" + key.upper()) or default


def _int_env(key, default):
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return int(default)


def get_profile() -> dict[str, str]:
    """进程级指纹档案（UA/几何/硬件统一，进程内稳定）。"""
    global _profile
    if _profile is None:
        ua = _env("ua", _DEFAULTS["ua"])
        major = _env("browser_version", _DEFAULTS["browser_version"]).split(".")[0]
        _profile = {
            "ua": ua,
            # Chrome 151 truth from the live login capture / user's curl.
            # Keep the brand order and GREASE token exactly as emitted by the
            # browser; this header is present on both passport and mssdk XHRs.
            "sec_ch_ua": (f'"Not=A?Brand";v="99", "Google Chrome";v="{major}", '
                          f'"Chromium";v="{major}"'),
            "sec_ch_ua_platform": '"Windows"',
            "browser_name": "Chrome",
            "browser_version": _env("browser_version", _DEFAULTS["browser_version"]),
            "engine_name": "Blink",
            "engine_version": _env("engine_version", _DEFAULTS["engine_version"]),
            "os_name": "Windows",
            "os_version": "10",
            "platform": "Win32",
            "cpu_core_num": _env("cpu_core_num", _DEFAULTS["cpu_core_num"]),
            "device_memory": _env("device_memory", _DEFAULTS["device_memory"]),
            "webgl_vendor": _env("webgl_vendor", _DEFAULTS["webgl_vendor"]),
            "webgl_renderer": _env("webgl_renderer", _DEFAULTS["webgl_renderer"]),
            "screen_width": _env("screen_width", _DEFAULTS["screen_width"]),
            "screen_height": _env("screen_height", _DEFAULTS["screen_height"]),
            "screen_x": _int_env("screen_x", 0),
            "screen_y": _int_env("screen_y", 0),
            "accept_language": _env("accept_language", _DEFAULTS["accept_language"]),
        }
        w, h = int(_profile["screen_width"]), int(_profile["screen_height"])
        # a_bogus 里拼成 "w|innerH|w|outerH|w|availH|w|h|Win32"。
        # 偏移取自 2026-08-16 页面 SDK 真值（2560x1440 → 1215/1392/1392）：
        # 任务栏占 48px，窗口最大化时 outerHeight == availHeight。
        # Current Chrome truth (isolated parity context):
        # inner 2560x1215, outer 2560x1392, avail 2560x1392, screen 2560x1440.
        # Keep screen dimensions separate and allow per-machine overrides.
        inner_w = _int_env("inner_width", w)
        inner_h = _int_env("inner_height", h - 225)
        outer_w = _int_env("outer_width", w)
        outer_h = _int_env("outer_height", h - 48)
        avail_w = _int_env("avail_width", w)
        avail_h = _int_env("avail_height", h - 48)
        _profile["geo"] = (inner_w, inner_h, outer_w, outer_h,
                            avail_w, avail_h, w, h)
    return _profile


def build_fpk2(ua=None):
    """Return the proven ``fpk2`` value for a user agent.

    The current browser implementation is simply lowercase MD5 of the full
    User-Agent string (not the Chrome major version and not a truncated hash).
    """
    value = (ua or get_profile()["ua"]).encode("utf-8")
    return hashlib.md5(value).hexdigest()


def _load_fingerprint_components():
    """Load the captured FingerprintJS orchestrator component values.

    Components without a ``value`` property are hashed as JavaScript
    ``undefined``; they must not be collapsed to an empty string.
    """
    global _COMPONENTS
    if _COMPONENTS is None:
        path = os.getenv("DY_FP_COMPONENTS_FILE") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "challenge_profile.json"
        )
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        raw = (data.get("fingerprintjs_components")
               or data.get("components")
               or data.get("fingerprint") or {})
        _COMPONENTS = _normalize_component_values(raw)
        _COMPONENTS.pop("id", None)
        _COMPONENTS.pop("visitorId", None)
    return dict(_COMPONENTS)


def _normalize_component_values(components):
    values = {}
    for name, item in dict(components or {}).items():
        if isinstance(item, dict) and ("value" in item or "duration" in item):
            values[name] = item["value"] if "value" in item else _UNDEFINED
        else:
            values[name] = item
    return values


def _js_number(value):
    if not math.isfinite(value):
        return "null"
    if value == 0:
        return "0"
    if value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    text = repr(value).lower()
    if "e" not in text:
        return text
    mantissa, exponent = text.split("e")
    exp = int(exponent)
    if 1e-6 <= abs(value) < 1e21:
        sign = ""
        if mantissa.startswith("-"):
            sign, mantissa = "-", mantissa[1:]
        digits = mantissa.replace(".", "")
        point = (mantissa.index(".") if "." in mantissa else len(mantissa)) + exp
        if point <= 0:
            return sign + "0." + "0" * (-point) + digits
        if point >= len(digits):
            return sign + digits + "0" * (point - len(digits))
        return sign + digits[:point] + "." + digits[point:]
    return f"{mantissa}e{'+' if exp >= 0 else ''}{exp}"


def _js_json_stringify(value):
    if value is _UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_js_json_stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(str(key), ensure_ascii=False, separators=(",", ":"))
            + ":" + _js_json_stringify(item)
            for key, item in value.items() if item is not _UNDEFINED
        ) + "}"
    raise TypeError(f"unsupported FingerprintJS component value: {type(value)!r}")


def fingerprint_component_string(components=None):
    """Build the exact ordered string fed to ``murmurX64Hash128``."""
    values = (_load_fingerprint_components() if components is None
              else _normalize_component_values(components))
    pieces = []
    for name in sorted(values):
        escaped = name.replace("\\", "\\\\").replace(":", "\\:").replace("|", "\\|")
        pieces.append(f"{escaped}:{_js_json_stringify(values[name])}")
    return "|".join(pieces)


def _rotl64(value, count):
    mask = (1 << 64) - 1
    count %= 64
    return ((value << count) | (value >> (64 - count))) & mask if count else value


def _fmix64(value):
    mask = (1 << 64) - 1
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & mask
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & mask
    value ^= value >> 33
    return value & mask


def murmur_x64_128(text, seed=0):
    """FingerprintJS' UTF-8 MurmurHash3 x64 128 implementation.

    The result ordering and hexadecimal formatting match the bundled
    ``murmurX64Hash128`` helper (for example ``abc`` ->
    ``b4963f3f3fad78673ba2744126ca2d52``).
    """
    mask = (1 << 64) - 1
    data = str(text or "").encode("utf-8")
    h1 = h2 = int(seed) & mask
    c1, c2 = 0x87C37B91114253D5, 0x4CF5AD432745937F
    full = len(data) - (len(data) % 16)
    for offset in range(0, full, 16):
        k1 = int.from_bytes(data[offset:offset + 8], "little")
        k2 = int.from_bytes(data[offset + 8:offset + 16], "little")
        k1 = (_rotl64((k1 * c1) & mask, 31) * c2) & mask
        h1 ^= k1
        h1 = (_rotl64(h1, 27) + h2) & mask
        h1 = (h1 * 5 + 0x52DCE729) & mask
        k2 = (_rotl64((k2 * c2) & mask, 33) * c1) & mask
        h2 ^= k2
        h2 = (_rotl64(h2, 31) + h1) & mask
        h2 = (h2 * 5 + 0x38495AB5) & mask

    tail = data[full:]
    k1 = k2 = 0
    for index, byte in enumerate(tail[:8]):
        k1 ^= byte << (8 * index)
    for index, byte in enumerate(tail[8:]):
        k2 ^= byte << (8 * index)
    if len(tail) > 8:
        k2 = (_rotl64((k2 * c2) & mask, 33) * c1) & mask
        h2 ^= k2
    if tail:
        k1 = (_rotl64((k1 * c1) & mask, 31) * c2) & mask
        h1 ^= k1

    h1 ^= len(data)
    h2 ^= len(data)
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    h1 = _fmix64(h1)
    h2 = _fmix64(h2)
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    return f"{h1:016x}{h2:016x}"


def build_fingerprint_digest(components=None):
    """Derive the 32-hex FingerprintJS digest used as fpk1 plaintext."""
    return murmur_x64_128(fingerprint_component_string(components))


def _evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
    output = b""
    previous = b""
    while len(output) < key_len + iv_len:
        previous = hashlib.md5(previous + password + salt).digest()
        output += previous
    return output[:key_len], output[key_len:key_len + iv_len]


def build_fpk1(fingerprint_digest=None, *, salt=None):
    """Generate an OpenSSL-format ``fpk1`` value.

    The browser encrypts the *ASCII 32-character digest* with passphrase
    ``byte_fingerprint`` using AES-256-CBC and an 8-byte random salt.  Supplying
    ``salt`` is useful for deterministic byte-parity fixtures; omitting it
    follows the browser's secure-random salt behavior.
    """
    digest = str(fingerprint_digest or build_fingerprint_digest()).lower()
    if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("fpk1 plaintext must be a 32-character hexadecimal digest")
    salt = secrets.token_bytes(8) if salt is None else bytes(salt)
    if len(salt) != 8:
        raise ValueError("OpenSSL fpk1 salt must be exactly 8 bytes")
    key, iv = _evp_bytes_to_key(_FP_SECRET, salt)
    plaintext = digest.encode("ascii")
    pad = 16 - (len(plaintext) % 16)
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(plaintext + bytes([pad]) * pad) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("ascii")


def decrypt_fpk1(value):
    """Decode an fpk1 fixture and return its plaintext digest (diagnostics)."""
    raw = base64.b64decode(str(value), validate=True)
    if raw[:8] != b"Salted__" or len(raw) < 32:
        raise ValueError("invalid OpenSSL fpk1 value")
    key, iv = _evp_bytes_to_key(_FP_SECRET, raw[8:16])
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(raw[16:]) + decryptor.finalize()
    pad = plain[-1]
    if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid fpk1 PKCS#7 padding")
    return plain[:-pad].decode("ascii")


__all__ = [
    "get_profile", "build_fpk1", "build_fpk2", "build_fingerprint_digest",
    "decrypt_fpk1", "fingerprint_component_string", "murmur_x64_128",
]
