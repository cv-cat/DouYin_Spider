# -*- coding: utf-8 -*-
"""浏览器指纹"""

import random as _rnd

GEO_PRESETS = (
    (1920, 937, 1920, 1040, 1920, 1040, 1920, 1080),
    (1366, 637, 1366, 728, 1366, 728, 1366, 768),
    (1536, 737, 1536, 824, 1536, 824, 1536, 864),
    (1440, 773, 1440, 860, 1440, 860, 1440, 900),
    (1280, 593, 1280, 680, 1280, 680, 1280, 720),
)

_profile = None


def get_profile():
    """进程级指纹档案（UA/几何/硬件统一，进程内稳定）。"""
    global _profile
    if _profile is None:
        geo = _rnd.choice(GEO_PRESETS)
        _profile = {
            "ua": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"),
            "browser_name": "Chrome",
            "browser_version": "150.0.0.0",
            "engine_name": "Blink",
            "engine_version": "150.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "platform": "Win32",
            "cpu_core_num": "12",
            "device_memory": "8",
            "geo": geo,
            "screen_width": str(geo[6]),
            "screen_height": str(geo[7]),
        }
    return _profile
