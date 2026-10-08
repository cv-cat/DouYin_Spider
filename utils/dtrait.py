# -*- coding: utf-8 -*-
"""x-tt-session-dtrait 头的构造（纯算）。

抖音 web 的高风控接口（评论、私信等）要求带该头，缺失会被 passport 判定为
需要二次身份验证（响应头 `X-Tt-Verify-Passport-Decision`，`verify_scene=comment`）。

结构（逆自 passport `zero.js` 的 `nB`/`nF` 与 DTraitSDK 调用点）::

    <pk1_version>_<base64(RSA_PKCS1v15(pk1, aes_key_hex))>_<base64(iv + AES128_CBC(payload))>

- `aes_key_hex`：16 字节随机数的 32 位小写十六进制字符串，RSA 加密的正是这个字符串本身
- AES：AES-128-CBC + PKCS7，密钥取 `bytes.fromhex(aes_key_hex)`，IV 随机 16 字节并前置到密文
- `payload`：`{"dtrait":<设备特征blob>,"timestamp":<秒级>,"sdkVersion":<ver>,"path":<pathname>}`
- `pk1_version`：公钥版本号（如 `d0`/`d1`），服务端据此选择解密私钥，必须与所用公钥一致

其中「设备特征 blob」由混淆过的 `@byted/uc-secure-dtrait-core` 采集生成；
当前仓库提供了经 DevTools 采样校验的设备档案（`utils/dtrait_profile.json`）
和纯算实现（`utils/dtrait_features.py`）。外层随机 AES/IV/RSA
材料仍必须与同一次浏览器调用配对，不能用长度或另一条 hook 记录替代。
"""

import base64
import json
import os
import time

from utils import http_client as requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

GET_TRAIT_CERT_API = "/passport/ticket_guard/get_client_cert/"
# zero.js 里写死的容器 SDK 版本，只用于拼 query
CONTAINER_SDK_VERSION = "1.0.0.381"
DEFAULT_TRAIT_SDK_VERSION = "1.0.0.16"

# The web login bundle ships this public key as its built-in fallback.  The
# browser uses it when the dtrait SDK is initialized with ``useBuildIn`` (the
# QR-login path does this on a fresh anonymous profile), so fetching
# ``type=trait`` before the first passport request would introduce a request
# that the browser never sends.  Keep the value here as base64 exactly as it
# appears in the bundle; decoding is lazy and does not expose the key in logs.
_BUILTIN_TRAIT_PK1_B64 = (
    "LS0tLS1CRUdJTiBSU0EgUFVCTElDIEtFWS0tLS0tCk1JSUJDZ0tDQVFFQTQrZHZ2WTd1"
    "TStvcGMrbkxHL0R1bVNlRm83YVZjSW0xTE8rbVVJcldwclJ6UDBhMUdwRVEKNHF0TzlN"
    "UmYvbHdFSXgzOCs0Qlo0WE9HemV2VnR1VXZmSU9VRTdBVHRRVzdGS0pmNVBuU0xDSTYv"
    "azB2bDFGQwpMVVNWbUVQNnFQSnJJalo0elhvcWkzeXVOWisxb2RiUkEvL0dIZ2NnU3l5"
    "eWFMcXp3amtwV0dYb3VNWW12WXNTCnBway9mdjJFV0FCc3RQTnhXYTRFT0JDYWRUVVBr"
    "WE5RNzZOQkVQOXh6ZkpTMjB3aUR2MW9TL3ZLdnJTVXBXY0oKbmF6a2tCdnFRYmJBcVZi"
    "UUZURi9EUGlrcHB1NlpUNmxHSVh2SktDcmVlRmlIQTJxSzZ0UzE4U1dWSFc5QVJ6MQor"
    "cGpCMWVxSUlZdG9oV3BUMkI0ME9DNE84dFZlQkFuYmlRSURBUUFCCi0tLS0tRU5EIFJT"
    "QSBQVUJMSUMgS0VZLS0tLS0="
)


def builtin_trait_pubkey() -> dict:
    """Return the d0 public key embedded in the browser login bundle.

    This is deliberately a pure/local operation.  Callers can opt into the
    remote endpoint when the service rotates the key (see ``DY_DTRAIT_CERT_MODE``
    in ``builder.auth``), but the default must match a fresh browser profile.
    """
    return {
        "pk1": base64.b64decode(_BUILTIN_TRAIT_PK1_B64).decode("ascii"),
        "pk1_version": "d0",
        "url_version": DEFAULT_TRAIT_SDK_VERSION,
        "dtrait_version": "0",
        "_set_cookies": {},
        "source": "builtin",
    }


def _der_len(buf, i):
    n = buf[i]
    i += 1
    if n < 0x80:
        return n, i
    k = n & 0x7F
    return int.from_bytes(buf[i:i + k], "big"), i + k


def parse_rsa_public_key(pem: str):
    """解析 PKCS#1 的 `BEGIN RSA PUBLIC KEY` PEM，返回 (n, e)。"""
    body = "".join(line for line in pem.strip().splitlines() if "-----" not in line)
    der = base64.b64decode(body)
    if der[0] != 0x30:
        raise ValueError("不是合法的 DER SEQUENCE")
    _, i = _der_len(der, 1)
    if der[i] != 0x02:
        raise ValueError("缺少 modulus")
    ln, i = _der_len(der, i + 1)
    n = int.from_bytes(der[i:i + ln], "big")
    i += ln
    if der[i] != 0x02:
        raise ValueError("缺少 exponent")
    le, i = _der_len(der, i + 1)
    e = int.from_bytes(der[i:i + le], "big")
    return n, e


def rsa_encrypt_pkcs1v15(n: int, e: int, message: bytes, randbytes=None) -> bytes:
    """RSA PKCS#1 v1.5 公钥加密（对齐 JSEncrypt 的默认行为）。"""
    randbytes = randbytes or os.urandom
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("明文超长")
    ps_len = k - len(message) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        chunk = randbytes(ps_len - len(ps))
        ps.extend(b for b in chunk if b != 0)
    em = b"\x00\x02" + bytes(ps[:ps_len]) + b"\x00" + message
    c = pow(int.from_bytes(em, "big"), e, n)
    return c.to_bytes(k, "big")


def _pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    pad = block - len(data) % block
    return data + bytes([pad]) * pad


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _build_session_dtrait_header(path, dtrait_blob, pk1_pem, pk1_version,
                                 key_hex, enc_key, sdk_version,
                                 timestamp=None, randbytes=None, iv=None):
    """用已缓存的会话密钥材料重建 dtrait 的 path-specific 第二段。

    Chrome 在同一页面会话中复用 RSA 加密后的 AES key（第一段），
    但每个请求重新生成 IV 并按 pathname 加密 payload（第二段）。
    ``build_session_dtrait`` 负责首次生成材料；后续调用走这里。
    """
    randbytes = randbytes or os.urandom
    if not isinstance(key_hex, str) or len(key_hex) != 32:
        raise ValueError("key_hex 必须是 16 字节随机数对应的 32 位十六进制字符串")
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as error:
        raise ValueError("key_hex 不是合法十六进制") from error
    iv = iv if iv is not None else randbytes(16)
    if len(iv) != 16:
        raise ValueError("iv 必须是 16 字节")
    payload = {
        "dtrait": dtrait_blob,
        "timestamp": int(timestamp if timestamp is not None else time.time()),
        "sdkVersion": sdk_version or DEFAULT_TRAIT_SDK_VERSION,
        "path": path,
    }
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = aes_cbc_encrypt(key, iv, plaintext)
    part1 = base64.b64encode(enc_key).decode()
    part2 = base64.b64encode(iv + cipher).decode()
    return f"{pk1_version}_{part1}_{part2}"


def fetch_trait_pubkey(aid, cookie_str, csrf_token="", origin="https://www.douyin.com",
                       user_agent=None, proxies=None) -> dict:
    """取 dtrait 的 RSA 公钥。

    与 bd-ticket-guard 的证书接口同路径，但要带 `type=trait`，
    且 body 的键值对用 `&` 连接（bd-ticket-guard 那个用的是 `,`）。

    :return: {"pk1": <PEM>, "pk1_version": "d1", "url_version": "...", "dtrait_version": "0"}
    """
    url = (f"{origin}{GET_TRAIT_CERT_API}?aid={aid}&type=trait"
           f"&sdk_version={CONTAINER_SDK_VERSION}&is_from_ttaccountsdk=1")
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "x-tt-passport-csrf-token": csrf_token or "",
        "cookie": cookie_str or "",
        "origin": origin,
        "referer": f"{origin}/",
    }
    if user_agent:
        headers["user-agent"] = user_agent
    resp = requests.post(url, headers=headers, data="server_data=1&need_session_dtrait=1",
                         verify=False, proxies=proxies, timeout=15)
    res_json = resp.json()
    if res_json.get("message") != "success":
        raise RuntimeError(f"获取 dtrait 公钥失败: {res_json}")
    data = res_json.get("data") or {}
    pk1_b64 = data.get("x-tt-session-dtrait-pk1")
    if not pk1_b64:
        raise RuntimeError(f"dtrait 公钥为空: {res_json}")
    return {
        "pk1": base64.b64decode(pk1_b64).decode(),
        "pk1_version": data.get("x-tt-session-dtrait-pk1-version", ""),
        "url_version": data.get("x-tt-session-dtrait-fe-url-version", ""),
        "dtrait_version": data.get("x-tt-session-dtrait-version", ""),
        # The same response also seeds passport_csrf_token(_default).  Keep
        # the names so the caller can merge them before its next request.
        "_set_cookies": resp.cookies.get_dict(),
    }


def build_session_dtrait(path, dtrait_blob, pk1_pem, pk1_version,
                         sdk_version=DEFAULT_TRAIT_SDK_VERSION, timestamp=None,
                         randbytes=None, session_material=None,
                         return_material=False):
    """拼出 x-tt-session-dtrait 头。

    :param path: 请求 pathname，不含 query。
    :param dtrait_blob: 设备特征 blob（payload 里的 `dtrait` 字段）。
    :param pk1_version: 必须与 `pk1_pem` 同一版本，会成为头的前缀。
    :param sdk_version: **已废弃，不再进 payload**，仅为兼容旧调用保留。

    浏览器 central d0 header 使用 4 个键。在真实浏览器里 hook
    `DTraitUcAesEncrypt.encryptData` 可以看到同一路径同时出现 central/edge
    两种内部调用；线上 `x-tt-session-dtrait` 采用带 `sdkVersion` 的 central 版本：

        {"dtrait":"IAAAAADQ...","timestamp":1787387417,"sdkVersion":"1.0.0.16","path":"/passport/web/challenge/"}

    键顺序也必须保持为 `dtrait,timestamp,sdkVersion,path`；省略该键会让
    challenge/check 的 header 分别短一个 AES 分组，无法与浏览器对齐。
    """
    randbytes = randbytes or os.urandom
    if session_material is not None:
        try:
            key_hex, enc_key = session_material
        except (TypeError, ValueError) as error:
            raise ValueError("session_material 必须是 (key_hex, enc_key) 二元组") from error
        header = _build_session_dtrait_header(
            path, dtrait_blob, pk1_pem, pk1_version,
            key_hex, enc_key, sdk_version,
            timestamp=timestamp, randbytes=randbytes,
        )
        return (header, (key_hex, enc_key)) if return_material else header

    # 保持旧实现的随机消耗顺序：key -> iv -> RSA padding。
    key_hex = randbytes(16).hex()
    iv = randbytes(16)
    n, e = parse_rsa_public_key(pk1_pem)
    enc_key = rsa_encrypt_pkcs1v15(
        n, e, key_hex.encode("ascii"), randbytes=randbytes,
    )
    header = _build_session_dtrait_header(
        path, dtrait_blob, pk1_pem, pk1_version,
        key_hex, enc_key, sdk_version,
        timestamp=timestamp, randbytes=randbytes, iv=iv,
    )
    return (header, (key_hex, enc_key)) if return_material else header
