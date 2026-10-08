# -*- coding: utf-8 -*-
"""加载 dtrait 纯算所需的设备档案。

``@byted/uc-secure-dtrait-core`` 的渲染类特征只能从同一浏览器采样，
因此把 DevTools 取证得到的设备字段和渲染哈希存成 JSON。认证流程只把它
当作没有显式素材时的默认回退；调用方仍可用 ``DY_DTRAIT_PROFILE`` 指向
另一份档案，或用 ``DY_DTRAIT_BLOB`` 完全覆盖它。
"""

import json
import os
from pathlib import Path

from utils.dtrait_features import build_blob


DEFAULT_PROFILE_PATH = Path(__file__).with_name("dtrait_profile.json")


def _normalise_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("dtrait profile must be a JSON object")
    for field in ("bools", "render_hashes"):
        values = profile.get(field)
        if not isinstance(values, dict):
            raise ValueError(f"dtrait profile field {field!r} must be an object")
        profile[field] = {int(key): value for key, value in values.items()}
    # Validate all required fields and the generated blob while the profile is
    # being loaded, rather than failing later in a request header builder.
    build_blob(profile)
    return profile


def load_dtrait_profile(path=None):
    """Load and validate a dtrait profile.

    ``path`` is primarily useful for tests.  In normal use the
    ``DY_DTRAIT_PROFILE`` environment variable selects a custom profile;
    otherwise the checked-in Chrome profile is used.
    """
    selected = path or os.getenv("DY_DTRAIT_PROFILE") or DEFAULT_PROFILE_PATH
    with Path(selected).open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    return _normalise_profile(profile)

