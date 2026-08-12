# -*- coding: utf-8 -*-
"""strData 上报体纯算法生成。"""

import json
import random
import time

CUSTOM = "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe"

FINGERPRINT_TEMPLATE = '{"tokenList":[],"navigator":{"appCodeName":"Mozilla","appMinorVersion":"undefined","appName":"Netscape","appVersion":"5.0 (Windows)","buildID":"undefined","doNotTrack":"null","msDoNotTrack":"undefined","oscpu":"undefined","platform":"Win32","product":"Gecko","productSub":"20030107","cpuClass":"undefined","vendor":"Google Inc.","vendorSub":"undefined","deviceMemory":"8","language":"zh-CN","systemLanguage":"undefined","userLanguage":"undefined","webdriver":"false","cookieEnabled":1,"vibrate":4,"credentials":4,"storage":4,"requestMediaKeySystemAccess":4,"bluetooth":4,"hardwareConcurrency":12,"maxTouchPoints":-1,"languages":"zh-CN,zh","touchEvent":1,"touchstart":2},"wID":{"load":0,"nap":"6","nativeLength":33,"jsFontsList":"0","timestamp":"1784564385945","timezone":8,"magic":3,"canvas":"-1","wProps":374262,"dProps":2,"jsv":"","browserType":0,"iframe":2,"aid":0,"msgType":1,"privacyMode":0,"aidList":[],"index":1},"window":{"Image":3,"isSecureContext":4,"ActiveXObject":4,"toolbar":4,"locationbar":4,"external":4,"mozRTCPeerConnection":4,"postMessage":3,"webkitRequestAnimationFrame":4,"BluetoothUUID":4,"netscape":4,"localStorage":11,"sessionStorage":11,"indexDB":4,"devicePixelRatio":1,"location":"https://www.douyin.com/"},"webgl":{},"document":{"characterSet":"UTF-8","compatMode":"undefined","documentMode":"undefined","layers":4,"all":4,"images":4},"screen":{"innerWidth":1707,"innerHeight":809,"outerWidth":1707,"outerHeight":912,"screenX":0,"screenY":0,"pageXOffset":0,"pageYOffset":0,"availWidth":1707,"availHeight":912,"sizeWidth":1707,"sizeHeight":960,"clientWidth":1697,"clientHeight":809,"colorDepth":24,"pixelDepth":24},"plugins":{"plugin":[],"pv":"0"},"custom":{}}'


def rc4(key, data):
    S = list(range(256)); j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 255
        S[i], S[j] = S[j], S[i]
    out = bytearray(); i = j = 0
    for b in data:
        i = (i + 1) & 255; j = (j + S[i]) & 255
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) & 255])
    return bytes(out)


def b64_custom_encode(data):
    out = []
    n = len(data)
    for i in range(0, n, 3):
        chunk = data[i:i + 3]
        b0 = chunk[0]
        b1 = chunk[1] if len(chunk) > 1 else 0
        b2 = chunk[2] if len(chunk) > 2 else 0
        trip = (b0 << 16) | (b1 << 8) | b2
        out.append(CUSTOM[(trip >> 18) & 63])
        out.append(CUSTOM[(trip >> 12) & 63])
        out.append(CUSTOM[(trip >> 6) & 63] if len(chunk) > 1 else "=")
        out.append(CUSTOM[trip & 63] if len(chunk) > 2 else "=")
    return "".join(out)


def encode_strdata(plaintext_bytes, nonce):
    cipher = rc4(bytes([nonce]), plaintext_bytes)
    raw = bytes([0x41, nonce]) + cipher
    return b64_custom_encode(raw)


def build_fingerprint():
    from utils.fingerprint import get_profile
    prof = get_profile()
    g = prof["geo"]
    fp = json.loads(FINGERPRINT_TEMPLATE)
    fp["navigator"]["hardwareConcurrency"] = int(prof["cpu_core_num"])
    fp["navigator"]["deviceMemory"] = prof["device_memory"]
    fp["screen"].update({
        "innerWidth": g[0], "innerHeight": g[1], "outerWidth": g[2], "outerHeight": g[3],
        "availWidth": g[4], "availHeight": g[5], "sizeWidth": g[6], "sizeHeight": g[7],
        "clientWidth": g[0] - 10, "clientHeight": g[1],
    })
    fp["wID"]["timestamp"] = str(int(time.time() * 1000))
    return json.dumps(fp, ensure_ascii=False, separators=(",", ":"))


def build_report_body():
    plaintext = build_fingerprint()
    nonce = random.randint(0, 255)
    strData = encode_strdata(plaintext.encode("utf-8"), nonce)
    envelope = {"magic": 538969122, "version": 1, "dataType": 8,
                "strData": strData, "tspFromClient": int(time.time() * 1000), "ulr": 0}
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
