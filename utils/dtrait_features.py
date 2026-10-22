# -*- coding: utf-8 -*-
"""dtrait 内层设备特征 blob 的纯算生成。

结构逆自 `@byted/uc-secure-dtrait-core` 的字节码 VM::

    [1 字节头][bool 位图][数值段][字符串特征段]

- 头字节 = `(reserved << 6) | (dTraitType << 5) | (accessType << 4) | version`
- bool 位图：`Uint8Array((floor(maxIdx/32)+1) * 5)`，第 n 个 bool 落在
  `buf[5*(floor(n/32)+1) - floor((n%32)/8) - 1]` 的第 `n%8` 位（见 VM 的 `getBoolBuffer`）
- 字符串特征段：每条 5 字节 = `[tag][murmur3 大端 4 字节]`（见 VM 的 `getCentralStringBuffer`）
- 特征名到 tag：`str_1..str_33` -> 32..64，`str_34` -> 71（见 VM 的 fn#177）

34 条字符串特征里，canvas / WebGL / audio / 字体像素这几类必须真实渲染才能得到，
无法用 Python 计算，因此按「设备档案常量」存哈希值；其余从档案字段现算。
"""

import base64
import math

# str_N -> tag
STR_TAGS = {n: (31 + n if n <= 33 else 71) for n in range(1, 35)}

# 只能作为档案常量的特征（存 murmur3 结果而非原串）：
# canvas/WebGL/audio/字体像素需真实渲染，css/domRect/svgRect/mediaTypes 随浏览器版本固定。
RENDER_FEATURES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13,
                   20, 21, 22, 23, 24, 25, 26, 33)

# V8 的 Math.expm1(1) 比 CPython 的 math.expm1(1) 高 1 ULP，其余数学函数两者一致
_V8_EXPM1_1 = 1.7182818284590453


def js_number_to_str(x):
    """等价于 JS 的 `Number.prototype.toString()`（ECMA-262 Number::toString）。

    Python 的 repr 同样是最短往返表示，但整数、指数阈值与指数格式不同，需要转换。
    """
    if x != x:
        return "NaN"
    if x == math.inf:
        return "Infinity"
    if x == -math.inf:
        return "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    r = repr(abs(x))
    if "e" in r:
        mant, exp = r.split("e")
        exp = int(exp)
        digits = mant.replace(".", "").rstrip("0") or "0"
        n = exp + (1 if "." not in mant else len(mant.split(".")[0]))
    elif "." in r:
        ip, fp = r.split(".")
        if ip == "0":
            stripped = fp.lstrip("0")
            n = -(len(fp) - len(stripped))
            digits = stripped.rstrip("0") or "0"
        else:
            digits = (ip + fp).rstrip("0") or "0"
            n = len(ip)
    else:
        digits = r.rstrip("0") or "0"
        n = len(r)

    k = len(digits)
    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        s = digits[0] + ("." + digits[1:] if k > 1 else "")
        s += "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + s


def math_features():
    """Math 指纹（str_11 / str_12）。入参全是字面常量，见 VM 的 fn#313。"""
    j = js_number_to_str
    tan = math.tan(-1e300)
    atanh = math.atanh(0.5)
    # SDK 自带的 atanh polyfill：log((1+x)/(1-x)) / 2
    atanh_pf = math.log((1 + 0.5) / (1 - 0.5)) / 2
    cos = math.cos(10.000000000123)
    sin = math.sin(-1e300)
    pow_pi = math.pow(math.pi, -100)
    return {
        11: f"{j(tan)},{j(atanh)},{j(atanh_pf)},{j(cos)}",
        12: f"{j(_V8_EXPM1_1)},{j(pow_pi)},{j(sin)},{j(tan)}",
    }


def murmur3_32(s, seed=0):
    """MurmurHash3 x86 32-bit，与 SDK 内实现一致。"""
    data = s.encode("utf-8") if isinstance(s, str) else s
    c1, c2 = 0xCC9E2D51, 0x1B873593
    h = seed
    n = len(data) // 4 * 4
    for i in range(0, n, 4):
        k = int.from_bytes(data[i:i + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    k, tail = 0, data[n:]
    for i, b in enumerate(tail):
        k |= b << (8 * i)
    if tail:
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def computed_features(p):
    """从设备档案算出可纯算的特征串。键是 str_N 的 N。

    每条都用真实 blob 逐一验证过（见 goal.md 的特征表）。
    """
    feats = dict(math_features())
    feats.update({
        14: f"{p['downlink']},{p['effective_type']}",
        15: f"{p['language']},{','.join(p['languages'])}",
        16: f"{','.join(p['str16_list'])},{p['vendor']}",
        17: f"{p['platform']},{p['str17_tail']}",
        18: ",".join(p["str18_list"]),
        19: p["ua"],
        27: f"{p['locale']}+{p['timezone']}",
        28: p["notification_permission"],
        29: f"{p['str29_head']},{p['device_memory']},{p['hardware_concurrency']},{p['max_touch_points']}",
        30: f"{p['avail_height']},{p['avail_left']},{p['avail_top']},{p['avail_width']}",
        31: f"{p['screen_height']},{p['screen_width']}",
        32: f"{p['color_depth']},{p['pixel_depth']},{p['device_pixel_ratio']}",
        # str_34(hook_score)：档案含 hook_score 时按上游语义以 murmur3(值) 覆盖
        # render_hashes[34]（键必须是 int，否则 sorted 混排 str/int 崩溃）；
        # 缺省时由 render_hashes[34] 提供真实设备哈希（2026-10-17）
        **({34: p["hook_score"]} if "hook_score" in p else {}),
    })
    return feats


def _bool_buffer(bools):
    """VM getBoolBuffer 的等价实现。bools: {序号: bool}"""
    if not bools:
        return b""
    max_idx = max(bools)
    size = (max_idx // 32 + 1) * 5
    buf = bytearray(size)
    for n in sorted(bools):
        if n % 32 == 0:
            buf[n // 32] = n // 8
        if bools[n]:
            idx = 5 * (n // 32 + 1) - (n % 32) // 8 - 1
            buf[idx] |= 1 << (n % 8)
    return bytes(buf)


def build_blob(profile, access_type=0):
    """生成内层 dtrait blob（base64 字符串）。

    :param profile: 设备档案，需含 `render_hashes`（渲染类特征的 murmur3 值）、
                    `bools`（bool 特征）与可算特征所需字段。
    :param access_type: central 用 0，edge 侧同样为 0（实测两者头字节都是 0x20）。
    """
    head = ((profile.get("reserved", 0) & 0x3) << 6) \
        | ((profile.get("dtrait_type", 1) & 0x1) << 5) \
        | ((access_type & 0x1) << 4) \
        | (profile.get("version", 0) & 0xF)

    values = dict(profile["render_hashes"])
    for n, s in computed_features(profile).items():
        values[n] = murmur3_32(s)

    body = bytearray()
    for n in range(1, 35):
        body.append(STR_TAGS[n])
        body += values[n].to_bytes(4, "big")

    blob = bytes([head]) + _bool_buffer(profile.get("bools", {})) + b"" + bytes(body)
    return base64.b64encode(blob).decode()


def parse_blob(blob_b64):
    """反解 blob，返回 (头字节, {bool序号: 值}, {str序号: murmur3值})。"""
    raw = base64.b64decode(blob_b64)
    head, bool_buf, body = raw[0], raw[1:6], raw[6:]
    bools = {}
    for n in range(1, 11):
        idx = 5 * (n // 32 + 1) - (n % 32) // 8 - 1
        bools[n] = bool(bool_buf[idx] >> (n % 8) & 1)
    tag2n = {t: n for n, t in STR_TAGS.items()}
    values = {}
    for i in range(0, len(body) - 4, 5):
        values[tag2n[body[i]]] = int.from_bytes(body[i + 1:i + 5], "big")
    return head, bools, values


def profile_from_blob(blob_b64, device_fields):
    """把一次抓到的 blob 加上已知设备字段，转成可复用的档案。

    渲染类特征直接沿用 blob 里的哈希，可算特征由 `device_fields` 现算，
    这样之后改 UA / 分辨率等字段时，对应特征会跟着变而保持自洽。
    """
    head, bools, values = parse_blob(blob_b64)
    profile = dict(device_fields)
    profile.update({
        "reserved": (head >> 6) & 0x3,
        "dtrait_type": (head >> 5) & 0x1,
        "version": head & 0xF,
        "bools": bools,
        "render_hashes": {n: values[n] for n in RENDER_FEATURES},
    })
    return profile
