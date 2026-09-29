# coding=utf-8
"""抖音创作者中心（creator.douyin.com）图文 / 视频发布接口（纯算）。

图文链路（2026-08-30 Chrome 实测）：
  1. GET  /web/api/media/upload/auth/v5/             取上传 STS 临时凭证
  2. GET  imagex ApplyImageUpload  (AWS V4)         申请上传，拿 StoreUri/Auth/UploadHost
  3. POST <UploadHost>/upload/v1/<StoreUri>         上传图片字节（content-crc32）
  4. POST imagex CommitImageUpload (AWS V4)          提交，拿 ImageUri/宽高
  5. POST /web/api/media/aweme/create_v2/           发布图文

视频链路（2026-08-30 Chrome 实测入口，后续网关动作沿用 uploader）：
  1. 同上取 STS（同一份凭证同时授权 ImageX 与 vod 动作）
  2. GET  vod ApplyUploadInner   (AWS V4)           拿 StoreUri/Auth/UploadHost/SessionKey
  3. POST <UploadHost>/upload/v1/<StoreUri>         ≤3MB 直传；更大走 init/transfer/finish 分片
  4. POST vod CommitUploadInner  (AWS V4)           带 GetMeta+Snapshot，拿 Vid/时长/封面帧
  5. POST /web/api/media/aweme/create_v2/           发布视频

签名沿用项目现有纯算：query 带 msToken + a_bogus；网关签名用 utils/imagex_sign。
风格对齐 dy_apis/douyin_api.py 的 DouyinAPI（静态方法 + Params/HeaderBuilder）。
"""

import io
import json
import math
import os
import random
import shutil
import string
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid
import wave
import zlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from utils import http_client as requests
requests.packages.urllib3.disable_warnings()
from loguru import logger

from builder.header import Header, HeaderBuilder, HeaderType
from builder.params import Params
from utils.dy_util import splice_url, generate_a_bogus, generate_csrf_token
from utils.imagex_sign import (
    IMAGEX_HOST, IMAGEX_REGION, IMAGEX_SERVICE,
    VOD_HOST, VOD_SERVICE, sign_request,
)


# 实测常量（抓包 2026-08-30）
IMAGEX_SERVICE_ID = "jm8ajry58r"
IMAGEX_APP_ID = "2906"          # ImageX 网关 app_id
CREATOR_READ_AID = "2906"       # creator 站点 aid（read_aid / 取服务端证书用）
CREATOR_AID = "1128"            # 创作者发布接口 aid
CREATOR_ORIGIN = "https://creator.douyin.com"
CREATOR_HOST = "creator.douyin.com"   # a_bogus 内嵌的 (aid, page_id) 按子域取
POST_IMAGE_REFERER = (
    "https://creator.douyin.com/creator-micro/content/post/image"
    "?enter_from=publish_page&media_type=image&type=new"
)
POST_VIDEO_REFERER = (
    "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page"
)
# 换 x-secsdk-csrf-token 的探针端点（2026-08-16 实录，creator 页面用的就是它）
CSRF_PROBE_PATH = "/web/api/media/anchor/search"

# VOD 上传常量（创作者前端 main.js 里的 uploader config，2026-08-16）
VOD_SPACE_NAME = "aweme"
VOD_API_VERSION = "2020-11-19"
VOD_PROCESS_ACTION = [
    {"name": "GetMeta"},
    {"name": "Snapshot", "input": {"SnapshotTime": 0}},
]
_MB = 1024 * 1024


_BROWSER_RANDOM_S_POOL = deque()
_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _fallback_browser_random_s():
    """Node 不可用时的无固定长度 base36 退路。

    精确路径使用同为 V8 的 Node 执行浏览器原表达式；这个分支只保证不再人为固定
    11/12 位，并保留 base36 字符集。生产对齐环境应安装 Node（仓库现有 JS 工具也
    依赖它）。
    """
    value = random.getrandbits(53)
    chars = []
    while value:
        value, digit = divmod(value, 36)
        chars.append(_BASE36_ALPHABET[digit])
    return "".join(reversed(chars)) or "0"


def _browser_random_s():
    """逐字复用 ``Math.random().toString(36).substr(2)`` 的 V8 语义。

    JS ``Number#toString(36)`` 的最短浮点序列化会自然产生 10/11/12 等不同长度，
    不能用 Python 固定位数随机串替代。一次向 Node 取 64 个，避免每张图都启动进程。
    """
    if not _BROWSER_RANDOM_S_POOL:
        node = shutil.which("node")
        if node:
            script = (
                "process.stdout.write(Array.from({length:64},"
                "()=>Math.random().toString(36).substr(2)).join('\\n'))"
            )
            try:
                output = subprocess.check_output(
                    [node, "-e", script], timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    text=True,
                )
                _BROWSER_RANDOM_S_POOL.extend(
                    value for value in output.splitlines() if value
                )
            except Exception as error:
                logger.warning(f"V8 随机串生成失败，使用 base36 退路: {error}")
        if not _BROWSER_RANDOM_S_POOL:
            _BROWSER_RANDOM_S_POOL.extend(
                _fallback_browser_random_s() for _ in range(64)
            )
    return _BROWSER_RANDOM_S_POOL.popleft()


class CreatorRequestContext:
    """发布链路的确定性动态输入。

    需要复现请求时可固定所有本模块拥有的动态量；线上不传时保持原行为。随机串按
    label 分队列消费，例如 ``image_apply_s`` 可为两张图片提供两个不同的实录值。
    ``a_bogus_signer`` 的签名与 ``generate_a_bogus`` 相同，便于注入固定模式的
    ``ABogusPureSigner.sign_query``，而不是直接跳过算法塞一个结果。
    """

    def __init__(self, *, fixed_now_ms=None, fixed_now_s=None,
                 fixed_sigv4_now=None, fixed_bd_timestamp=None,
                 fixed_dtrait_timestamp=None, fixed_creation_id=None,
                 random_strings=None, a_bogus_signer=None,
                 dtrait_randbytes=None):
        self.fixed_now_ms = None if fixed_now_ms is None else int(fixed_now_ms)
        self.fixed_now_s = None if fixed_now_s is None else int(fixed_now_s)
        self.fixed_sigv4_now = (
            None if fixed_sigv4_now is None else float(fixed_sigv4_now)
        )
        self.fixed_bd_timestamp = (
            None if fixed_bd_timestamp is None else int(fixed_bd_timestamp)
        )
        self.fixed_dtrait_timestamp = (
            None if fixed_dtrait_timestamp is None else int(fixed_dtrait_timestamp)
        )
        self.fixed_creation_id = fixed_creation_id
        self.dtrait_randbytes = dtrait_randbytes
        self.a_bogus_signer = a_bogus_signer or generate_a_bogus
        self._random_strings = {}
        for label, values in (random_strings or {}).items():
            if isinstance(values, str):
                values = [values]
            self._random_strings[str(label)] = deque(str(value) for value in values)

    def now_ms(self):
        return self.fixed_now_ms if self.fixed_now_ms is not None else int(time.time() * 1000)

    def now_s(self):
        if self.fixed_now_s is not None:
            return self.fixed_now_s
        if self.fixed_now_ms is not None:
            return self.fixed_now_ms // 1000
        return int(time.time())

    def sigv4_now(self):
        if self.fixed_sigv4_now is not None:
            return self.fixed_sigv4_now
        if self.fixed_now_ms is not None:
            return self.fixed_now_ms / 1000
        return None

    def rand_str(self, label, n=None,
                 alphabet=string.ascii_lowercase + string.digits):
        queue = self._random_strings.get(label)
        if not queue:
            if n is None:
                return _browser_random_s()
            return "".join(random.choice(alphabet) for _ in range(n))
        value = queue.popleft()
        if n is not None and len(value) != n:
            raise ValueError(f"固定随机串 {label} 长度应为 {n}，实际为 {len(value)}")
        return value

    def browser_random_s(self, label):
        """消费任意实录长度的 ``Math.random().toString(36).substr(2)`` 值。"""
        return self.rand_str(label, None)

    def frontend_uuid(self, label="cover_item_id"):
        queue = self._random_strings.get(label)
        if queue:
            return queue.popleft()

        # creator 前端 module 13940 的 uuid：8 个 4 位十六进制片段直接拼接。
        def chunk():
            return f"{int(65536 * (1 + random.random())) & 0xFFFF:04x}"
        return "".join(chunk() for _ in range(8))

    def blob_url(self, label="cover_blob_url"):
        queue = self._random_strings.get(label)
        if queue:
            return queue.popleft()
        return f"blob:{CREATOR_ORIGIN}/{uuid.uuid4()}"

    def creation_id(self):
        if self.fixed_creation_id is not None:
            return str(self.fixed_creation_id)
        return self.rand_str(
            "creation_id_prefix", 8, string.ascii_lowercase + string.digits,
        ) + str(self.now_ms())

    def sign_a_bogus(self, query, body="", host=CREATOR_HOST):
        return self.a_bogus_signer(query, body, host=host)

def _rand_str(n, alphabet=string.ascii_lowercase + string.digits,
              request_context=None, label="default"):
    if request_context is not None:
        return request_context.rand_str(label, n, alphabet)
    return "".join(random.choice(alphabet) for _ in range(n))


def _imagex_random_s(request_context=None, label="image_apply_s"):
    if request_context is not None:
        return request_context.browser_random_s(label)
    return _browser_random_s()


def _now_ms(request_context=None):
    if request_context is not None:
        return request_context.now_ms()
    return int(time.time() * 1000)


def _now_s(request_context=None):
    if request_context is not None:
        return request_context.now_s()
    return int(time.time())


def _request(auth, method, url, **kwargs):
    """creator 全链优先复用 Auth 的持久会话；兼容旧 Auth 时回退模块函数。"""
    hostname = urllib.parse.urlsplit(url).hostname or ""
    # creator 同源请求需要 Cookie jar 与连接状态；ImageX/VOD/TOS 是跨域上传，
    # 浏览器本来也不会附带 creator Cookie。跨域请求使用独立 curl handle，既避免
    # 多文件并发时争用会临时清空 CookieJar 的 Auth session，也更接近浏览器连接池。
    if (
        auth is not None
        and hasattr(auth, "request")
        and hostname == CREATOR_HOST
    ):
        return auth.request(method, url, **kwargs)
    kwargs.pop("split_cookie_header", None)
    return requests.request(method, url, **kwargs)


def _cookie_str_for(auth, url, method="GET"):
    if hasattr(auth, "cookie_header_for_url"):
        return auth.cookie_header_for_url(url, method=method)
    return auth.cookie_str


def _crc32_hex(data: bytes) -> str:
    """小写 8 位十六进制 CRC32（content-crc32 头用）。"""
    return format(zlib.crc32(data) & 0xFFFFFFFF, "08x")


def _create_aweme_headers(*, bd_headers, referer, csrf_token, cookie_value,
                          body_bytes):
    """按 Chrome HTTP/2 wire 实录构造 create_v2 头顺序。"""
    headers = {
        "content-length": str(len(body_bytes)),
        "x-tt-session-dtrait": bd_headers["x-tt-session-dtrait"],
        "bd-ticket-guard-web-version": bd_headers["bd-ticket-guard-web-version"],
        "bd-ticket-guard-client-data": bd_headers["bd-ticket-guard-client-data"],
        "bd-ticket-guard-web-sign-type": bd_headers["bd-ticket-guard-web-sign-type"],
        "user-agent": HeaderBuilder.ua,
        "accept": "application/json, text/plain, */*",
        "x-secsdk-csrf-token": csrf_token,
        "content-type": "application/json",
        "bd-ticket-guard-ree-public-key": bd_headers["bd-ticket-guard-ree-public-key"],
        "bd-ticket-guard-version": bd_headers["bd-ticket-guard-version"],
        "origin": CREATOR_ORIGIN,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": referer,
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": HeaderBuilder.accept_language,
        "cookie": cookie_value,
        "priority": "u=1, i",
    }
    expected = [
        "content-length", "x-tt-session-dtrait",
        "bd-ticket-guard-web-version", "bd-ticket-guard-client-data",
        "bd-ticket-guard-web-sign-type", "user-agent", "accept",
        "x-secsdk-csrf-token", "content-type",
        "bd-ticket-guard-ree-public-key", "bd-ticket-guard-version",
        "origin", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
        "referer", "accept-encoding", "accept-language", "cookie",
        "priority",
    ]
    if list(headers) != expected:
        raise RuntimeError(f"create_v2 header wire 顺序构造异常: {list(headers)}")
    return headers


def _read_image_bytes(path_or_bytes) -> bytes:
    """接受本地路径 / bytes / http(s) URL，统一返回图片字节。"""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes)
    if isinstance(path_or_bytes, str) and path_or_bytes.startswith(("http://", "https://")):
        resp = requests.get(path_or_bytes, verify=False, timeout=30)
        resp.raise_for_status()
        return resp.content
    with open(path_or_bytes, "rb") as f:
        return f.read()


def _image_size(data: bytes):
    """本地读宽高（尽力而为，最终以 Commit 返回为准）。"""
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            return int(img.width), int(img.height)
    except Exception:
        return 0, 0


class _MediaSource:
    """统一本地路径 / bytes / URL 三种输入，支持按偏移取片段。

    本地大文件按需 seek 读取，避免把整个视频读进内存。
    """

    def __init__(self, src):
        self._path = None
        self._data = None
        if isinstance(src, (bytes, bytearray)):
            self._data = bytes(src)
        elif isinstance(src, str) and src.startswith(("http://", "https://")):
            resp = requests.get(src, verify=False, timeout=120)
            resp.raise_for_status()
            self._data = resp.content
        else:
            self._path = src
        self.size = len(self._data) if self._data is not None else os.path.getsize(self._path)

    def read(self, start=0, length=None):
        if length is None:
            length = self.size - start
        if self._data is not None:
            return self._data[start:start + length]
        with open(self._path, "rb") as f:
            f.seek(start)
            return f.read(length)

    @property
    def name(self):
        if self._path:
            return os.path.basename(os.fspath(self._path))
        return "video.mp4"


@contextmanager
def _video_path(source: "_MediaSource"):
    """给 OpenCV 提供本地路径；bytes/URL 输入只落到受控临时文件。"""
    if source._path is not None:
        yield os.fspath(source._path)
        return
    fd, path = tempfile.mkstemp(prefix="douyin_creator_", suffix=".mp4")
    try:
        with os.fdopen(fd, "wb") as file_obj:
            file_obj.write(source.read())
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _video_probe(source: "_MediaSource"):
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("视频封面链需要 opencv-python") from error
    with _video_path(source) as path:
        capture = cv2.VideoCapture(path)
        try:
            if not capture.isOpened():
                raise RuntimeError("OpenCV 无法打开视频")
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = frame_count / fps if fps > 0 else 0
            return {
                "width": width, "height": height, "fps": fps,
                "frame_count": frame_count, "duration": duration,
            }
        finally:
            capture.release()


def _extract_video_frames(source: "_MediaSource", times):
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("视频抽帧需要 opencv-python") from error
    frames = []
    with _video_path(source) as path:
        capture = cv2.VideoCapture(path)
        try:
            if not capture.isOpened():
                raise RuntimeError("OpenCV 无法打开视频")
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            last_time = (
                max(0, (frame_count - 1) / fps)
                if fps > 0 and frame_count > 0 else None
            )
            for value in times:
                seek_time = max(0, float(value))
                if last_time is not None:
                    seek_time = min(seek_time, last_time)
                capture.set(cv2.CAP_PROP_POS_MSEC, seek_time * 1000)
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError(f"视频在 {value}s 抽帧失败")
                frames.append(frame)
        finally:
            capture.release()
    return frames


def _extract_audio_analysis_wav(source: "_MediaSource", duration, *,
                                sample_rate=16000, max_duration=20):
    """生成 cover/gen 的 ``audio_uri`` 输入：16kHz/mono/PCM16，最长 20 秒。

    当前 23.7 秒浏览器样本为 640044 字节：44 字节 WAV 头 +
    ``16000 * 20 * 2`` 字节 PCM。严格模式直接使用浏览器导出字节；该函数只供
    非严格回退，仍保持采样率、声道、位深和截断长度一致。
    """
    seconds = min(max(0, float(duration)), float(max_duration))
    sample_count = int(round(seconds * int(sample_rate)))
    expected_bytes = sample_count * 2
    pcm = b""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and expected_bytes:
        with _video_path(source) as path:
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
                "-vn", "-ac", "1", "-ar", str(int(sample_rate)),
                "-acodec", "pcm_s16le", "-t", f"{seconds:.6f}",
                "-f", "s16le", "pipe:1",
            ]
            completed = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(30, int(seconds) + 15), check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode == 0:
                pcm = completed.stdout
    pcm = pcm[:expected_bytes].ljust(expected_bytes, b"\x00")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm)
    return output.getvalue()


def _resize_within(frame, max_width, max_height):
    import cv2
    height, width = frame.shape[:2]
    scale = min(float(max_width) / width, float(max_height) / height, 1.0)
    if scale >= 1:
        return frame
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(frame, target, interpolation=cv2.INTER_AREA)


def _resize_exact(frame, width, height):
    import cv2
    interpolation = (
        cv2.INTER_AREA
        if frame.shape[1] > width or frame.shape[0] > height
        else cv2.INTER_CUBIC
    )
    return cv2.resize(frame, (int(width), int(height)), interpolation=interpolation)


def _resize_to_width(frame, width):
    height, current_width = frame.shape[:2]
    target_width = int(width)
    target_height = max(1, int(round(height * target_width / current_width)))
    return _resize_exact(frame, target_width, target_height)


def _crop_ratio_from_left(frame, ratio):
    """对齐本次 Chrome 默认 cropBox：[0,0,0.75,1]，即从左侧裁 4:3。"""
    height, width = frame.shape[:2]
    target_width = min(width, int(round(height * float(ratio))))
    target_height = min(height, int(round(width / float(ratio))))
    if target_width < width:
        return frame[:, :target_width]
    return frame[:target_height, :]


def _crop_normalized(frame, crop_box):
    """按前端 video_reframe 的归一化 ``[x,y,w,h]`` 裁切。"""
    if not isinstance(crop_box, (list, tuple)) or len(crop_box) != 4:
        raise ValueError(f"无效 cropBox: {crop_box!r}")
    height, width = frame.shape[:2]
    x, y, crop_width, crop_height = [float(value) for value in crop_box]
    left = max(0, min(width - 1, int(round(x * width))))
    top = max(0, min(height - 1, int(round(y * height))))
    right = max(left + 1, min(width, int(round((x + crop_width) * width))))
    bottom = max(top + 1, min(height, int(round((y + crop_height) * height))))
    return frame[top:bottom, left:right]


def _encode_frame(frame, image_format, *, quality=None):
    import cv2
    image_format = image_format.lower()
    extension = ".jpg" if image_format in {"jpg", "jpeg"} else f".{image_format}"
    options = []
    if image_format in {"jpg", "jpeg"} and quality is not None:
        options = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif image_format == "webp" and quality is not None:
        options = [cv2.IMWRITE_WEBP_QUALITY, int(quality)]
    elif image_format == "png":
        options = [cv2.IMWRITE_PNG_COMPRESSION, 3]
    ok, encoded = cv2.imencode(extension, frame, options)
    if not ok:
        raise RuntimeError(f"{image_format} 编码失败")
    return encoded.tobytes()


def _floor_to(value, digits=1):
    factor = 10 ** digits
    return math.floor(float(value) * factor) / factor


def _js_string_length(value):
    """Return JavaScript ``String.length`` (UTF-16 code units)."""
    return len(str(value).encode("utf-16-le")) // 2


def _split_times(length, split_count=10, fraction_digits=1):
    if split_count <= 1:
        return [0]
    step = float(length) / (split_count - 1)
    return [
        _floor_to(min(max(step * index, 0), float(length)), fraction_digits)
        for index in range(split_count)
    ]


def _browser_frame_times(duration):
    """移植 creator module 43395 的 ``l2(duration, false)``。"""
    duration = max(0, float(duration))
    if duration > 20:
        # Chrome 实产 23.7s 样本的 20 张 JPEG 自带时间码 00..19 秒；这里不是
        # 把全时长均分成 20 份。长视频只取最前 20 个整数秒。
        upload_times = [float(index) for index in range(20)]
        indexes = _split_times(19, 10, 0)
        preview_indexes = [int(index) for index in indexes]
        preview_times = [upload_times[index] for index in preview_indexes]
    elif duration > 10:
        upload_times = [float(index) for index in range(math.floor(duration) + 1)]
        upload_times[-1] = _floor_to(duration, 1)
        indexes = _split_times(duration - 1, 10, 0)
        preview_indexes = [int(index) for index in indexes]
        preview_times = [upload_times[index] for index in preview_indexes]
    else:
        upload_times = [float(index) for index in range(math.floor(duration) + 1)]
        if upload_times:
            upload_times[-1] = _floor_to(duration, 1)
        preview_indexes = None
        preview_times = _split_times(duration, 10, 1)
        # 源码会把每个整数秒首次命中的预览点改成整数本身。
        for integer in range(math.floor(duration)):
            for index, value in enumerate(preview_times):
                if math.floor(value) == integer:
                    preview_times[index] = float(integer)
                    break
    return {
        "upload_times": upload_times,
        "preview_times": preview_times,
        "preview_indexes": preview_indexes,
    }


def _post_assistant_frame_times(duration, count=5):
    """post-assistant 取每个等长区间的起点，再由解码器落到最近视频帧。"""
    duration = max(0, float(duration))
    count = max(0, int(count))
    if not count:
        return []
    return [duration * index / count for index in range(count)]


def _select_browser_frame_indexes(frame_count, count=10):
    """移植 WebCodecsCaptureWorker ``getFramesByCount`` 的同步帧抽样。"""
    frame_count = int(frame_count)
    count = int(count)
    if frame_count <= 0 or count <= 0:
        return []
    if count > frame_count:
        return list(range(frame_count))
    ratio = frame_count / count
    return [
        frame_count - 1
        if ratio * (index + 1) >= frame_count
        else math.floor(ratio * index)
        for index in range(count)
    ]


def _browser_sync_frame_times(source: "_MediaSource", count=10):
    """按浏览器 MP4Box/WebCodecs 的时间基准返回最多 ``count`` 个同步帧。

    前端先把每个 sample 的 CTS 归一到 ``sample.cts - firstSample.dts``，再转成
    整数微秒；首 sample 小于 200ms 时强制归零。普通播放器展示的 PTS 没有这
    一步，因此 2.000000s 在当前 H.264 样本中会变成 2.066666s。
    """
    try:
        import av
    except ImportError as error:
        raise RuntimeError(
            "严格复现浏览器同步帧需要 PyAV；请安装 requirements.txt 中的 av"
        ) from error

    with _video_path(source) as path:
        container = av.open(path)
        try:
            if not container.streams.video:
                raise RuntimeError("视频中没有可用的视频流")
            stream = container.streams.video[0]
            first_dts = None
            sync_times_us = []
            sample_index = 0
            for packet in container.demux(stream):
                if packet.pts is None or packet.dts is None:
                    continue
                if first_dts is None:
                    first_dts = packet.dts
                timestamp_us = int(
                    (packet.pts - first_dts) * stream.time_base * 1_000_000
                )
                if sample_index == 0 and timestamp_us < 200_000:
                    timestamp_us = 0
                if packet.is_keyframe:
                    sync_times_us.append(timestamp_us)
                sample_index += 1
        finally:
            container.close()

    if not sync_times_us:
        raise RuntimeError("视频中未找到同步帧，无法对齐浏览器推荐封面候选")
    indexes = _select_browser_frame_indexes(len(sync_times_us), count)
    return [
        0 if sync_times_us[index] == 0 else sync_times_us[index] / 1_000_000
        for index in indexes
    ]


def _normalize_browser_recommend_frames(recommend_frames, candidate_times,
                                        *, strict=True):
    """核验 Bach 输出；严格模式不允许用静态 crop 或时长公式猜推荐帧。"""
    if recommend_frames is None:
        if strict:
            raise RuntimeError(
                "严格浏览器对齐缺少 recommend_frames：必须注入 Bach "
                "after_effect + video_reframe 的三帧实测结果"
            )
        recommend_frames = [
            {
                "frame_index": index,
                "time": value,
                "crop_box": [0, 0, 0.75, 1],
                "crop_box2": [0.08695652335882187, 0, 0.508695662021637, 1],
            }
            for index, value in enumerate(candidate_times[:3])
        ]

    normalized = []
    for raw in recommend_frames:
        if not isinstance(raw, dict):
            raise TypeError("recommend_frames 每项必须是包含 Bach 结果的 dict")
        frame = dict(raw)
        frame_index = int(frame.get("frameIndex", frame.get("frame_index", -1)))
        if frame_index < 0 or frame_index >= len(candidate_times):
            raise ValueError(
                f"recommend frame_index={frame_index} 超出候选帧范围 "
                f"0..{len(candidate_times) - 1}"
            )
        expected_time = candidate_times[frame_index]
        supplied_time = frame.get("time", expected_time)
        if abs(float(supplied_time) - float(expected_time)) > 0.0000005:
            raise ValueError(
                f"recommend frame_index={frame_index} 的 time={supplied_time} "
                f"与浏览器候选时间 {expected_time} 不一致"
            )
        crop_box = frame.get("cropBox", frame.get("crop_box"))
        crop_box2 = frame.get("cropBox2", frame.get("crop_box2"))
        if strict and (crop_box is None or crop_box2 is None):
            raise ValueError(
                f"recommend frame_index={frame_index} 缺少 video_reframe cropBox/cropBox2"
            )
        frame["frame_index"] = frame_index
        frame["time"] = expected_time
        frame["crop_box"] = crop_box or [0, 0, 0.75, 1]
        frame["crop_box2"] = crop_box2 or [
            0.08695652335882187, 0, 0.508695662021637, 1,
        ]
        normalized.append(frame)

    if strict and len(normalized) != 3:
        raise ValueError(
            f"浏览器 Bach 推荐封面应为 3 帧，实际注入 {len(normalized)} 帧"
        )
    indexes = [frame["frame_index"] for frame in normalized]
    if len(indexes) != len(set(indexes)):
        raise ValueError("recommend_frames 的 frame_index 不允许重复")
    # 前端通过数字 frame_index 对象键输出，最终顺序是 frame index 升序。
    return sorted(normalized, key=lambda frame: frame["frame_index"])


def _browser_cover_payloads(payloads, recommend_count, ai_input_count=10, *,
                            strict=True):
    """核验浏览器导出的 Canvas/WebCodecs 字节；严格路径不使用 OpenCV 编码。"""
    if payloads is None:
        if strict:
            raise RuntimeError(
                "严格浏览器对齐缺少 browser_cover_payloads；必须注入浏览器实产的 "
                "poster/audio_analysis/ai_inputs/recommend/ai_output/"
                "final_cover/post_assistant 字节"
            )
        return None
    if not isinstance(payloads, dict):
        raise TypeError("browser_cover_payloads 必须是 dict")

    def one(name):
        value = payloads.get(name)
        if not isinstance(value, (bytes, bytearray, memoryview)) or not value:
            raise ValueError(f"browser_cover_payloads.{name} 必须是非空 bytes")
        return bytes(value)

    def many(name, count):
        values = payloads.get(name)
        if not isinstance(values, (list, tuple)) or len(values) != count:
            raise ValueError(
                f"browser_cover_payloads.{name} 必须包含 {count} 个字节对象"
            )
        result = []
        for index, value in enumerate(values):
            if not isinstance(value, (bytes, bytearray, memoryview)) or not value:
                raise ValueError(
                    f"browser_cover_payloads.{name}[{index}] 必须是非空 bytes"
                )
            result.append(bytes(value))
        return result

    result = {
        "poster": one("poster"),
        "audio_analysis": one("audio_analysis"),
        "ai_inputs": many("ai_inputs", int(ai_input_count)),
        "recommend": many("recommend", int(recommend_count)),
        "final_cover": one("final_cover"),
        "post_assistant": many("post_assistant", 5),
    }
    ai_output = payloads.get("ai_output")
    if ai_output is not None:
        if not isinstance(ai_output, (bytes, bytearray, memoryview)) or not ai_output:
            raise ValueError("browser_cover_payloads.ai_output 必须是非空 bytes")
        result["ai_output"] = bytes(ai_output)
    return result


def _slice_size_for(size: int) -> int:
    """对齐 SDK getFileSliceLength：≥500MB 用 10MB，≥100MB 用 5MB，否则 3MB。"""
    if size >= 500 * _MB:
        return 10 * _MB
    if size >= 100 * _MB:
        return 5 * _MB
    return 3 * _MB


def _set_csrf(headers, auth, referer):
    """尽力设置 x-secsdk-csrf-token（失败不阻断）。

    creator 域必须向 creator 域换 token（csrf token 与 `csrf_session_id` 绑定），
    实录端点是 `HEAD creator.douyin.com/web/api/media/anchor/search`。
    """
    try:
        token = getattr(auth, "creator_csrf_token", "")
        if not token:
            token = generate_csrf_token(
                _cookie_str_for(auth, CREATOR_ORIGIN + CSRF_PROBE_PATH, "HEAD"),
                origin=CREATOR_ORIGIN, path=CSRF_PROBE_PATH,
                referer=referer,
            )[0]
        if token:
            headers.set_header("x-secsdk-csrf-token", token)
    except Exception:
        pass


def _creator_xhr_headers(referer, auth, content_type=None, *, method="GET",
                         first_headers=None, body_length=None):
    """creator.douyin.com 同源 XHR 的请求头，字段与顺序照抄浏览器实录
    （2026-08-16 用户真实 Chrome，`Network.requestWillBeSentExtraInfo`）：

        [业务首项] / referer / user-agent / accept / x-secsdk-csrf-token /
        [content-type] /
        accept-language / priority / sec-fetch-dest / sec-fetch-mode / sec-fetch-site

    **不带** `sec-ch-ua` / `-mobile` / `-platform`：实录里 creator 域的 XHR
    确实没有这三个（主站 www 的 aweme XHR 才有，两个域不一样，别混用
    `HeaderBuilder.build()`）。`accept-encoding` / `cookie` 由 HTTP 层补。
    """
    headers = Header()
    for name, value in (first_headers or {}).items():
        headers.set_header(name, value)
    headers.set_header("referer", referer)
    headers.set_header("user-agent", HeaderBuilder.ua)
    headers.set_header("accept", "application/json, text/plain, */*")
    _set_csrf(headers, auth, referer)
    if content_type:
        headers.set_header("content-type", content_type)
    headers.set_header("accept-language", HeaderBuilder.accept_language)
    # Chrome's network layer materializes Content-Length for creator POST/XHR
    # after accept-language and before Cookie.  curl_cffi would otherwise add
    # it at its own transport position, leaving the request semantically valid
    # but wire-different from the browser capture.
    if body_length is not None:
        headers.set_header("content-length", str(int(body_length)))
    if hasattr(auth, "creator_cookie_str"):
        headers.set_header("cookie", auth.creator_cookie_str)
    if method.upper() != "GET":
        headers.set_header("origin", CREATOR_ORIGIN)
    headers.set_header("priority", "u=1, i")
    headers.set_header("sec-fetch-dest", "empty")
    headers.set_header("sec-fetch-mode", "cors")
    headers.set_header("sec-fetch-site", "same-origin")
    return headers


def _creator_signed_params(auth, initial=None, *, include_platform=True,
                           include_ms_token=True, sign=True, body="",
                           request_context=None):
    """按插入顺序构造 creator query，并在最后追加 ``msToken/a_bogus``。"""
    params = Params()
    for key, value in (initial or []):
        params.add_param(key, value)
    if include_platform:
        params.with_creator_platform()
    if include_ms_token:
        params.add_param("msToken", auth.msToken)
    if sign:
        query_without_sign = splice_url(params.get())
        params.add_param(
            "a_bogus",
            request_context.sign_a_bogus(
                query_without_sign, body, host=CREATOR_HOST,
            ) if request_context else generate_a_bogus(
                query_without_sign, body, host=CREATOR_HOST,
            ),
        )
    return params.get()


def _gateway_headers(sign_headers, content_type=None):
    """ImageX / VOD 网关（跨域 XHR）的请求头，照抄 2026-08-16 实录。

    顺序（POST 比 GET 多首项）：x-amz-content-sha256 /
    x-amz-security-token / x-amz-date / referer / authorization /
    user-agent / [content-type] / accept / accept-language / origin /
    priority / sec-fetch-*（cross-site）。

    注意 referer 是 `https://creator.douyin.com/`（带斜杠的站点根，不是发布页 URL），
    且跨域请求同样**不带** `sec-ch-ua*`。
    """
    headers = {}
    if "x-amz-content-sha256" in sign_headers:
        headers["x-amz-content-sha256"] = sign_headers["x-amz-content-sha256"]
    headers["x-amz-security-token"] = sign_headers["x-amz-security-token"]
    headers["x-amz-date"] = sign_headers["x-amz-date"]
    headers["referer"] = f"{CREATOR_ORIGIN}/"
    headers["authorization"] = sign_headers["authorization"]
    headers["user-agent"] = HeaderBuilder.ua
    if content_type:
        headers["content-type"] = content_type
    headers.update({
        "accept": "*/*",
        "accept-language": HeaderBuilder.accept_language,
        "origin": CREATOR_ORIGIN,
        "priority": "u=1, i",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    })
    return headers


class DouyinCreatorAPI:
    creator_url = CREATOR_ORIGIN

    @staticmethod
    def build_image_apply_query(user_id="", request_context=None, random_s=None):
        return {
            "Action": "ApplyImageUpload",
            "Version": "2018-08-01",
            "ServiceId": IMAGEX_SERVICE_ID,
            "app_id": IMAGEX_APP_ID,
            "user_id": str(user_id or ""),
            "s": (
                str(random_s) if random_s is not None else _imagex_random_s(
                    request_context=request_context, label="image_apply_s",
                )
            ),
        }

    @staticmethod
    def build_image_commit_query(user_id=""):
        return {
            "Action": "CommitImageUpload",
            "Version": "2018-08-01",
            "ServiceId": IMAGEX_SERVICE_ID,
            "app_id": IMAGEX_APP_ID,
            "user_id": str(user_id or ""),
        }

    @staticmethod
    def build_video_apply_query(file_size, user_id="", request_context=None):
        return {
            "Action": "ApplyUploadInner",
            "Version": VOD_API_VERSION,
            "SpaceName": VOD_SPACE_NAME,
            "FileType": "video",
            "IsInner": 1,
            "FileSize": int(file_size),
            "app_id": IMAGEX_APP_ID,
            "user_id": str(user_id or ""),
            "s": _imagex_random_s(
                request_context=request_context, label="video_apply_s",
            ),
        }

    @staticmethod
    def build_video_commit_query(user_id=""):
        return {
            "Action": "CommitUploadInner",
            "Version": VOD_API_VERSION,
            "SpaceName": VOD_SPACE_NAME,
            "app_id": IMAGEX_APP_ID,
            "user_id": str(user_id or ""),
        }

    @staticmethod
    def build_creator_params(auth, initial=None, *, include_platform=True,
                             include_ms_token=True, sign=True, body="",
                             request_context=None):
        """公开纯构建入口，供固定浏览器样本逐字段核验 query 顺序。"""
        return _creator_signed_params(
            auth, initial, include_platform=include_platform,
            include_ms_token=include_ms_token, sign=sign, body=body,
            request_context=request_context,
        )

    @staticmethod
    def _creator_api_request(auth, method, api, *, initial=None,
                             include_platform=True, include_ms_token=True,
                             sign=True, body=None, content_type=None,
                             first_headers=None, referer=POST_VIDEO_REFERER,
                             proxies=None, request_context=None):
        if body is None:
            body_text = ""
            data = None
        elif isinstance(body, bytes):
            data = body
            body_text = body.decode("utf-8")
        else:
            body_text = str(body)
            data = body_text.encode("utf-8")
        params = DouyinCreatorAPI.build_creator_params(
            auth, initial, include_platform=include_platform,
            include_ms_token=include_ms_token, sign=sign, body=body_text,
            request_context=request_context,
        )
        headers = _creator_xhr_headers(
            referer, auth, content_type=content_type, method=method,
            first_headers=first_headers,
            body_length=(len(data) if data is not None else None),
        )
        response = _request(
            auth, method, f"{CREATOR_ORIGIN}{api}", headers=headers.get(),
            params=params, data=data, verify=False, proxies=proxies,
            # Chromium crumbles Cookie pairs into separate HTTP/2 fields.  The
            # old creator calls sent one flattened field, which is not wire
            # equivalent even when the Cookie string has the same bytes.
            split_cookie_header=True,
        )
        try:
            return response.json()
        except Exception as error:
            raise RuntimeError(
                f"creator 接口返回非 JSON: {api} HTTP {response.status_code}"
            ) from error

    @staticmethod
    def get_preview_video_list(auth, current_aweme_id="", proxies=None,
                               request_context=None):
        """复刻发布页历史作品预览映射；该接口实录不带 msToken/a_bogus。"""
        api = "/janus/douyin/creator/pc/work_list"
        result = DouyinCreatorAPI._creator_api_request(
            auth, "GET", api,
            initial=[
                ("scene", "star_atlas"),
                ("device_platform", "android"),
                ("status", 4),
                ("count", 18),
                ("max_cursor", 0),
            ],
            include_ms_token=False, sign=False, proxies=proxies,
            request_context=request_context,
        )
        if result.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"work_list 失败: {result}")
        if hasattr(auth, "creator_read_verified"):
            auth.creator_read_verified = True
        preview = [{"isCurrent": True}]
        for item in result.get("aweme_list") or []:
            video = item.get("video") or {}
            optimized = (video.get("optimized_cover") or {}).get("url_list") or []
            normal = (video.get("cover") or {}).get("url_list") or []
            cover_url = (optimized or normal or [""])[0]
            mapped = {"coverUrl": cover_url}
            if "is_pinned" in item:
                mapped["isPinned"] = item.get("is_pinned")
            timer = item.get("timer")
            mapped["isTiming"] = bool(timer and timer.get("status") == 0)
            mapped["isPreview"] = item.get("status_value") == 141
            mapped["isCurrent"] = bool(
                current_aweme_id and str(item.get("aweme_id")) == str(current_aweme_id)
            )
            mapped["isLiveReplay"] = bool(item.get("is_live_replay"))
            preview.append(mapped)
        return preview

    @staticmethod
    def get_cover_gen_ref(auth, creation_id, proxies=None, request_context=None):
        result = DouyinCreatorAPI._creator_api_request(
            auth, "GET", "/aweme/v1/cover/gen/ref/",
            initial=[("creation_id", str(creation_id))], proxies=proxies,
            request_context=request_context,
        )
        if result.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"cover/gen/ref 失败: {result}")
        return result

    @staticmethod
    def get_user_declaration_suggestion(auth, creation_id, *, item_type="video",
                                        proxies=None, request_context=None):
        judge_feats = json.dumps({
            "has_ai_metadata": False,
            "is_xing_tu_submit": False,
            "has_marketing_poi": False,
            "item_type": item_type,
        }, ensure_ascii=False, separators=(",", ":"))
        result = DouyinCreatorAPI._creator_api_request(
            auth, "GET", "/aweme/v3/user_declaration/suggestion/",
            initial=[
                ("scene", "new_self_media_before_publish"),
                ("creation_id", str(creation_id)),
                ("user_decl_judge_feats", judge_feats),
                ("libra_token", "douyin_pc"),
            ],
            proxies=proxies, request_context=request_context,
        )
        if result.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"user_declaration/suggestion 失败: {result}")
        return result

    @staticmethod
    def _video_signal(auth, api, video_id, proxies=None, request_context=None):
        result = DouyinCreatorAPI._creator_api_request(
            auth, "GET", api, initial=[("video_id", str(video_id))],
            proxies=proxies, request_context=request_context,
        )
        if result.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"{api} 失败: {result}")
        return result

    @staticmethod
    def video_enable(auth, video_id, proxies=None, request_context=None):
        return DouyinCreatorAPI._video_signal(
            auth, "/web/api/media/video/enable/", video_id,
            proxies=proxies, request_context=request_context,
        )

    @staticmethod
    def video_transend(auth, video_id, proxies=None, request_context=None):
        return DouyinCreatorAPI._video_signal(
            auth, "/web/api/media/video/transend/", video_id,
            proxies=proxies, request_context=request_context,
        )

    @staticmethod
    def build_fast_detect_body(video_id, duration, task_id=None):
        body = {
            "resource_list": [{
                "type": 2,
                "video_id": str(video_id),
                "duration": int(round(float(duration))),
                "cover_uri": "",
            }],
            "source": 1,
            "is_redetect": False,
        }
        if task_id:
            body["task_id"] = str(task_id)
        return body

    @staticmethod
    def post_fast_detect(auth, video_id, duration, task_id=None, proxies=None,
                         request_context=None):
        body = json.dumps(
            DouyinCreatorAPI.build_fast_detect_body(video_id, duration, task_id),
            ensure_ascii=False, separators=(",", ":"),
        )
        result = DouyinCreatorAPI._creator_api_request(
            auth, "POST", "/aweme/v1/post_assistant/fast_detect/poll",
            include_platform=False, body=body, content_type="application/json",
            first_headers={"agw-js-conv": "str"}, proxies=proxies,
            request_context=request_context,
        )
        base = result.get("base_resp") or {}
        if base.get("status_code", 0) not in (0, None):
            raise RuntimeError(f"fast_detect/poll 失败: {result}")
        return result

    @staticmethod
    def poll_fast_detect(auth, video_id, duration, task_id=None, *, timeout=180,
                         interval=2, proxies=None, request_context=None,
                         cancel_event=None):
        deadline = time.monotonic() + timeout
        current_task_id = task_id
        if current_task_id:
            if cancel_event is not None:
                if cancel_event.wait(max(0, interval)):
                    raise RuntimeError("fast_detect/poll 已取消")
            else:
                time.sleep(max(0, interval))
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("fast_detect/poll 已取消")
            result = DouyinCreatorAPI.post_fast_detect(
                auth, video_id, duration, task_id=current_task_id,
                proxies=proxies, request_context=request_context,
            )
            current_task_id = result.get("task_id") or current_task_id
            if result.get("has_done"):
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError("fast_detect/poll 超过 180 秒仍未完成")
            if cancel_event is not None:
                if cancel_event.wait(max(0, interval)):
                    raise RuntimeError("fast_detect/poll 已取消")
            else:
                time.sleep(max(0, interval))

    @staticmethod
    def _run_fast_detect_flow(auth, video_id, duration, *, proxies=None,
                              request_context=None, cancel_event=None):
        """浏览器同序：首个无 task_id 请求与其余封面链并发，随后每 2 秒轮询。"""
        initial = DouyinCreatorAPI.post_fast_detect(
            auth, video_id, duration, proxies=proxies,
            request_context=request_context,
        )
        final = DouyinCreatorAPI.poll_fast_detect(
            auth, video_id, duration, task_id=initial.get("task_id"),
            interval=2, proxies=proxies, request_context=request_context,
            cancel_event=cancel_event,
        )
        return initial, final

    @staticmethod
    def get_creator_media_url(auth, uri, proxies=None, request_context=None):
        result = DouyinCreatorAPI._creator_api_request(
            auth, "GET", "/aweme/v1/creator/get/url/",
            initial=[("uri", str(uri))], proxies=proxies,
            request_context=request_context,
        )
        urls = ((result.get("url") or {}).get("url_list") or [])
        if result.get("status_code", 0) not in (0, None) or not urls:
            raise RuntimeError(f"creator/get/url 失败: {result}")
        return urls[0]

    @staticmethod
    def build_cover_gen_body(cover_uri, img_uris, creation_id, uid, *,
                             audio_uri="", title="", caption="", ratio_type=1,
                             action=1):
        return {
            "cover_uri": str(cover_uri),
            "title": title or "",
            "caption": caption or "",
            "img_uris": [str(value) for value in img_uris],
            "audio_uri": str(audio_uri or ""),
            "ratio_type": int(ratio_type),
            "action": int(action),
            "creation_id": str(creation_id),
            "uid": str(uid),
        }

    @staticmethod
    def post_cover_gen_task(auth, cover_uri, img_uris, creation_id, uid, *,
                            audio_uri="", title="", caption="", ratio_type=1,
                            action=1, proxies=None, request_context=None):
        body = json.dumps(
            DouyinCreatorAPI.build_cover_gen_body(
                cover_uri, img_uris, creation_id, uid, title=title,
                caption=caption, audio_uri=audio_uri,
                ratio_type=ratio_type, action=action,
            ),
            ensure_ascii=False, separators=(",", ":"),
        )
        result = DouyinCreatorAPI._creator_api_request(
            auth, "POST", "/aweme/v1/cover/gen/post/",
            initial=[("noToast", "true")], body=body,
            content_type="application/x-www-form-urlencoded;charset=UTF-8",
            proxies=proxies, request_context=request_context,
        )
        if result.get("status_code", 0) not in (0, None) or not result.get("task_id"):
            raise RuntimeError(f"cover/gen/post 失败: {result}")
        return result

    @staticmethod
    def poll_cover_gen_task(auth, task_id, *, timeout=180, interval=3,
                            proxies=None, request_context=None,
                            cancel_event=None):
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("cover/gen/get 已取消")
            result = DouyinCreatorAPI._creator_api_request(
                auth, "GET", "/aweme/v1/cover/gen/get/",
                initial=[("task_id", str(task_id)), ("noToast", "true")],
                proxies=proxies, request_context=request_context,
            )
            code = result.get("gen_code")
            if code == 2:
                ai_cover = result.get("ai_cover") or {}
                if not (ai_cover.get("url_list") or []):
                    raise RuntimeError(f"cover/gen/get 缺 AI 封面: {result}")
                return result
            if code not in (0, 1, None):
                raise RuntimeError(f"cover/gen/get 异常: {result}")
            if time.monotonic() >= deadline:
                raise TimeoutError("cover/gen/get 超过 180 秒仍未完成")
            if cancel_event is not None:
                if cancel_event.wait(max(0, interval)):
                    raise RuntimeError("cover/gen/get 已取消")
            else:
                time.sleep(max(0, interval))

    # ---------- 步骤 1：取 ImageX/VOD STS 凭证 ----------
    @staticmethod
    def get_image_upload_auth(auth, referer=POST_VIDEO_REFERER, proxies=None,
                              request_context=None, include_platform=True) -> dict:
        """按当前 Chrome creator 页请求获取 ImageX/VOD STS 凭证。

        关键点：创作者页在真正选择图片后调用的是
        ``/web/api/media/upload/auth/v5/``。页面初始化时还会预取
        ``/aweme/mid/video/sts2/``，但那份凭证与图片上传动作并不等价；
        直接拿 ``sts2`` 的凭证调用 ImageX 会得到 ``AccessDenied``。
        v5 响应把 STS 放在 JSON 字符串 ``auth`` 中，这里解析后统一返回
        上传网关使用的 ``AccessKeyID`` / ``SecretAccessKey`` /
        ``SessionToken`` 键。

        :return: {"AccessKeyID","SecretAccessKey","SessionToken",...}
        """
        api = "/web/api/media/upload/auth/v5/"
        headers = _creator_xhr_headers(referer, auth)
        params = Params()
        if include_platform:
            params.with_creator_platform()
        params.add_param("msToken", auth.msToken)
        query_without_sign = splice_url(params.get())
        params.add_param(
            "a_bogus",
            request_context.sign_a_bogus(
                query_without_sign, "", host=CREATOR_HOST,
            ) if request_context else generate_a_bogus(
                query_without_sign, "", host=CREATOR_HOST,
            ),
        )
        resp = _request(
            auth, "GET", f"{CREATOR_ORIGIN}{api}", headers=headers.get(),
            params=params.get(), verify=False, proxies=proxies,
        )
        res_json = resp.json()
        if res_json.get("status_code", 0) not in (0, None) and "auth" not in res_json:
            raise RuntimeError(f"获取上传凭证失败: {res_json}")
        try:
            sts = json.loads(res_json["auth"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"获取上传凭证失败: {res_json}") from error
        required = ("AccessKeyID", "SecretAccessKey", "SessionToken")
        if any(not sts.get(key) for key in required):
            raise RuntimeError(f"获取上传凭证失败: {res_json}")
        return sts

    # ---------- 步骤 2：ApplyImageUpload ----------
    @staticmethod
    def apply_image_upload(auth, sts: dict, user_id="", proxies=None,
                           request_context=None, random_s=None) -> dict:
        """申请一次图片上传，返回上传地址节点。

        `user_id` 必须是真实登录 uid：实录里图片链路带的是
        `user_id=97872126662`（早先固定发空串，与浏览器不一致）。

        :return: {"store_uri","auth","upload_host","session_key"}
        """
        query = DouyinCreatorAPI.build_image_apply_query(
            user_id=user_id, request_context=request_context,
            random_s=random_s,
        )
        sign_headers = sign_request(
            sts["AccessKeyID"], sts["SecretAccessKey"], sts["SessionToken"],
            method="GET", query_params=query, body=b"",
            now=request_context.sigv4_now() if request_context else None,
        )
        headers = _gateway_headers(sign_headers)
        resp = _request(
            auth, "GET", f"https://{IMAGEX_HOST}/", headers=headers, params=query,
            verify=False, proxies=proxies,
        )
        res_json = resp.json()
        result = res_json.get("Result")
        if not result:
            raise RuntimeError(f"ApplyImageUpload 失败: {res_json}")
        addr = result["UploadAddress"]
        store = addr["StoreInfos"][0]
        return {
            "store_uri": store["StoreUri"],
            "auth": store["Auth"],
            "upload_host": addr["UploadHosts"][0],
            "session_key": addr["SessionKey"],
            "upload_id": store.get("UploadID") or "",
            "upload_header": addr.get("UploadHeader") or {},
        }

    # ---------- 步骤 3：上传字节到 TOS ----------
    @staticmethod
    def upload_image_bytes(upload_host, store_uri, ticket, data: bytes,
                           user_id="", proxies=None, auth=None,
                           request_context=None):
        """把图片字节上传到 TOS。

        头字段与顺序照抄浏览器实录（2026-08-16）：
        authorization / referer / user-agent / x-storage-u / content-crc32 /
        content-type / content-disposition / accept / accept-language /
        origin / sec-fetch-*（cross-site，无 sec-ch-ua*、无 priority）。
        """
        url = f"https://{upload_host}/upload/v1/{store_uri}"
        headers = {
            "authorization": ticket,
            "referer": f"{CREATOR_ORIGIN}/",
            "user-agent": HeaderBuilder.ua,
            "x-storage-u": urllib.parse.quote(str(user_id or "")),
            "content-crc32": _crc32_hex(data),
            "content-type": "application/octet-stream",
            "content-disposition": 'attachment; filename="undefined"',
            "accept": "*/*",
            "accept-language": HeaderBuilder.accept_language,
            "origin": CREATOR_ORIGIN,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        }
        resp = _request(
            auth, "POST", url, headers=headers, data=data,
            verify=False, proxies=proxies,
        )
        res_json = resp.json()
        if res_json.get("code") != 2000:
            raise RuntimeError(f"图片字节上传失败: {res_json}")
        return res_json

    # ---------- 步骤 4：CommitImageUpload ----------
    @staticmethod
    def commit_image_upload(auth, sts: dict, session_key: str, user_id="", proxies=None,
                            request_context=None) -> dict:
        """提交上传，返回图片信息（含真实宽高）。

        :return: {"uri","width","height","format","size"}
        """
        query = DouyinCreatorAPI.build_image_commit_query(user_id=user_id)
        body = json.dumps({"SessionKey": session_key},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sign_headers = sign_request(
            sts["AccessKeyID"], sts["SecretAccessKey"], sts["SessionToken"],
            method="POST", query_params=query, body=body,
            now=request_context.sigv4_now() if request_context else None,
        )
        headers = _gateway_headers(sign_headers, content_type="application/json")
        resp = _request(
            auth, "POST", f"https://{IMAGEX_HOST}/", headers=headers,
            params=query, data=body,
            verify=False, proxies=proxies,
        )
        res_json = resp.json()
        result = res_json.get("Result")
        if not result or not result.get("PluginResult"):
            raise RuntimeError(f"CommitImageUpload 失败: {res_json}")
        info = result["PluginResult"][0]
        return {
            "uri": info["ImageUri"],
            "width": int(info.get("ImageWidth") or 0),
            "height": int(info.get("ImageHeight") or 0),
            "format": info.get("ImageFormat"),
            "size": int(info.get("ImageSize") or 0),
        }

    # ---------- 编排：上传一张图 ----------
    @staticmethod
    def upload_one_image(auth, sts: dict, path_or_bytes, user_id=None, proxies=None,
                         request_context=None, random_s=None) -> dict:
        """完成一张图片的 Apply -> 上传 -> Commit，返回 {uri,width,height}。"""
        data = _read_image_bytes(path_or_bytes)
        if user_id is None:
            user_id = DouyinCreatorAPI._resolve_user_id(auth)
        node = DouyinCreatorAPI.apply_image_upload(
            auth, sts, user_id=user_id, proxies=proxies,
            request_context=request_context, random_s=random_s,
        )
        DouyinCreatorAPI.upload_image_bytes(
            node["upload_host"], node["store_uri"], node["auth"], data,
            user_id=user_id, proxies=proxies, auth=auth,
            request_context=request_context,
        )
        info = DouyinCreatorAPI.commit_image_upload(
            auth, sts, node["session_key"], user_id=user_id, proxies=proxies,
            request_context=request_context,
        )
        if not info["width"] or not info["height"]:
            info["width"], info["height"] = _image_size(data)
        return info

    @staticmethod
    def upload_image_batch(auth, images, *, user_id="", sts=None, proxies=None,
                           request_context=None, max_workers=None):
        """一个前端 uploader 批次只取一份 STS，并发 Apply/Upload/Commit。

        浏览器对 20 张 AI 输入使用 ``Promise.all``；Apply 在百毫秒内成批发出，TOS
        上传随后并发完成。结果仍按输入数组顺序返回，供 cover/gen 的 img_uris 保持
        前端数组顺序。固定调试时先顺序消费 random_s，再开线程，避免线程调度改变
        固定随机队列和图片索引的绑定。
        """
        images = list(images)
        if not images:
            return []
        if sts is None:
            sts = DouyinCreatorAPI.get_image_upload_auth(
                auth, referer=POST_VIDEO_REFERER, proxies=proxies,
                request_context=request_context, include_platform=True,
            )
        random_values = [
            _imagex_random_s(
                request_context=request_context, label="image_apply_s",
            )
            for _ in images
        ]
        workers = min(len(images), 20) if max_workers is None else int(max_workers)
        if workers <= 1:
            return [
                DouyinCreatorAPI.upload_one_image(
                    auth, sts, image, user_id=user_id, proxies=proxies,
                    request_context=request_context, random_s=random_values[index],
                )
                for index, image in enumerate(images)
            ]
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="douyin-image-upload",
        ) as executor:
            futures = [
                executor.submit(
                    DouyinCreatorAPI.upload_one_image,
                    auth, sts, image, user_id, proxies, request_context,
                    random_values[index],
                )
                for index, image in enumerate(images)
            ]
            return [future.result() for future in futures]

    # ---------- 视频步骤 2：ApplyUploadInner ----------
    @staticmethod
    def apply_video_upload(auth, sts: dict, file_size: int, user_id="", proxies=None,
                           request_context=None) -> dict:
        """向 VOD 申请一次视频上传。

        query 字段与顺序对齐浏览器实录（2026-08-16）：Action/Version/SpaceName/
        FileType/IsInner/FileSize 之后还要带 app_id、user_id、s。

        :return: {"store_uri","auth","upload_host","session_key","upload_id","upload_header"}
        """
        query = DouyinCreatorAPI.build_video_apply_query(
            file_size, user_id=user_id, request_context=request_context,
        )
        sign_headers = sign_request(
            sts["AccessKeyID"], sts["SecretAccessKey"], sts["SessionToken"],
            method="GET", query_params=query, body=b"",
            service=VOD_SERVICE, region=IMAGEX_REGION,
            now=request_context.sigv4_now() if request_context else None,
        )
        headers = _gateway_headers(sign_headers)
        resp = _request(
            auth, "GET", f"https://{VOD_HOST}/", headers=headers, params=query,
            verify=False, proxies=proxies,
        )
        res_json = resp.json()
        result = res_json.get("Result") or {}
        nodes = (result.get("InnerUploadAddress") or {}).get("UploadNodes") or []
        if not nodes:
            raise RuntimeError(f"ApplyUploadInner 失败: {res_json}")
        node = nodes[0]
        store = node["StoreInfos"][0]
        return {
            "store_uri": store["StoreUri"],
            "auth": store["Auth"],
            "upload_id": store.get("UploadID") or "",
            "upload_host": node["UploadHost"],
            "session_key": node["SessionKey"],
            "upload_header": node.get("UploadHeader") or {},
        }

    # ---------- 视频步骤 3：上传字节到 TOS ----------
    @staticmethod
    def _tos_headers(node, user_id, crc32=None):
        """TOS 上传头，字段与顺序照抄浏览器实录（2026-08-16）。

        跨域请求：带 sec-fetch-*（cross-site），**不带** sec-ch-ua* / priority。
        `UploadHeader` 里服务端下发的键值最后并上。
        """
        headers = {
            "authorization": node["auth"],
            "referer": f"{CREATOR_ORIGIN}/",
            "user-agent": HeaderBuilder.ua,
            "x-storage-u": urllib.parse.quote(str(user_id or "")),
        }
        if crc32 is not None:
            headers["content-crc32"] = crc32
        headers.update({
            "content-type": "application/octet-stream",
            "accept": "*/*",
            "accept-language": HeaderBuilder.accept_language,
            "origin": CREATOR_ORIGIN,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        })
        headers.update(node.get("upload_header") or {})
        return headers

    @staticmethod
    def _tos_post(url, headers, data=None, proxies=None, timeout=300, auth=None):
        resp = _request(
            auth, "POST", url, headers=headers, data=data, verify=False,
            proxies=proxies, timeout=timeout,
        )
        try:
            res_json = resp.json()
        except Exception:
            raise RuntimeError(f"TOS 返回非 JSON（HTTP {resp.status_code}）: {resp.text[:200]}")
        if res_json.get("code") != 2000:
            raise RuntimeError(f"TOS 请求失败: {res_json}")
        return res_json

    @staticmethod
    def upload_video_direct(node, source: "_MediaSource", user_id, proxies=None,
                            auth=None):
        """小文件直传（≤ 分片阈值走这条）。"""
        data = source.read()
        url = f"https://{node['upload_host']}/upload/v1/{node['store_uri']}"
        headers = DouyinCreatorAPI._tos_headers(node, user_id, crc32=_crc32_hex(data))
        return DouyinCreatorAPI._tos_post(
            url, headers, data=data, proxies=proxies, auth=auth,
        )

    @staticmethod
    def upload_video_parts(node, source: "_MediaSource", user_id, part_size, proxies=None,
                           auth=None):
        """分片上传：init 拿 uploadid -> 逐片 transfer -> finish 合并。"""
        base = f"https://{node['upload_host']}/upload/v1/{node['store_uri']}"
        headers = DouyinCreatorAPI._tos_headers(node, user_id)

        upload_id = node.get("upload_id")
        if not upload_id:
            init = DouyinCreatorAPI._tos_post(
                f"{base}?uploadmode=part&phase=init", headers, proxies=proxies,
                auth=auth,
            )
            upload_id = (init.get("data") or {}).get("uploadid")
            if not upload_id:
                raise RuntimeError(f"初始化分片上传失败: {init}")

        crc_list = []
        offset = 0
        index = 0
        while offset < source.size:
            chunk = source.read(offset, part_size)
            crc = _crc32_hex(chunk)
            part_url = (
                f"{base}?uploadid={upload_id}&part_number={index + 1}"
                f"&phase=transfer&part_offset={offset}"
            )
            DouyinCreatorAPI._tos_post(
                part_url, DouyinCreatorAPI._tos_headers(node, user_id, crc32=crc),
                data=chunk, proxies=proxies, auth=auth,
            )
            crc_list.append(crc)
            offset += len(chunk)
            index += 1
            logger.info(f"视频分片上传 {index} 片，{offset}/{source.size} 字节")

        merge_body = ",".join(f"{i + 1}:{c}" for i, c in enumerate(crc_list))
        return DouyinCreatorAPI._tos_post(
            f"{base}?uploadmode=part&phase=finish&uploadid={upload_id}",
            headers, data=merge_body.encode("utf-8"), proxies=proxies, auth=auth,
        )

    # ---------- 视频步骤 4：CommitUploadInner ----------
    @staticmethod
    def commit_video_upload(auth, sts: dict, session_key: str, user_id="", proxies=None,
                            request_context=None) -> dict:
        """提交视频上传，触发 GetMeta / Snapshot，返回 vid 与元信息。

        :return: {"vid","poster_uri","width","height","duration","size","format","md5"}
        """
        query = DouyinCreatorAPI.build_video_commit_query(user_id=user_id)
        body = json.dumps(
            {"SessionKey": session_key, "Functions": VOD_PROCESS_ACTION},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        sign_headers = sign_request(
            sts["AccessKeyID"], sts["SecretAccessKey"], sts["SessionToken"],
            method="POST", query_params=query, body=body,
            service=VOD_SERVICE, region=IMAGEX_REGION,
            now=request_context.sigv4_now() if request_context else None,
        )
        # 浏览器 body 是紧凑 JSON 字节，但 Fetch 发的是 text/plain。
        headers = _gateway_headers(
            sign_headers, content_type="text/plain;charset=UTF-8",
        )
        resp = _request(
            auth, "POST", f"https://{VOD_HOST}/", headers=headers,
            params=query, data=body,
            verify=False, proxies=proxies,
        )
        res_json = resp.json()
        result = res_json.get("Result") or {}
        items = result.get("Results") or []
        if not items:
            raise RuntimeError(f"CommitUploadInner 失败: {res_json}")
        info = items[0]
        meta = info.get("SourceInfo") or info.get("VideoMeta") or {}
        return {
            "vid": info.get("Vid") or meta.get("Vid") or "",
            "poster_uri": info.get("PosterUri") or "",
            "width": int(meta.get("Width") or 0),
            "height": int(meta.get("Height") or 0),
            "duration": float(meta.get("Duration") or 0),
            "size": int(meta.get("Size") or 0),
            "format": meta.get("Format") or "",
            "md5": meta.get("Md5") or "",
            "raw": info,
        }

    # ---------- 编排：上传一个视频 ----------
    @staticmethod
    def upload_one_video(auth, sts: dict, path_or_bytes, user_id="", proxies=None,
                         request_context=None) -> dict:
        """完成一个视频的 Apply -> 上传 -> Commit，返回 vid / 封面帧 / 元信息。"""
        source = _MediaSource(path_or_bytes)
        node = DouyinCreatorAPI.apply_video_upload(
            auth, sts, source.size, user_id=user_id, proxies=proxies,
            request_context=request_context,
        )

        return DouyinCreatorAPI.upload_prepared_video(
            auth, sts, node, source, user_id=user_id, proxies=proxies,
            request_context=request_context,
        )

    @staticmethod
    def upload_prepared_video(auth, sts: dict, node: dict, path_or_source,
                              user_id="", proxies=None,
                              request_context=None,
                              before_commit_future=None) -> dict:
        """上传已经 Apply 的视频节点并 Commit，允许本地封面链与 VOD Apply 重叠。"""
        source = (
            path_or_source if isinstance(path_or_source, _MediaSource)
            else _MediaSource(path_or_source)
        )

        slice_size = _slice_size_for(source.size)
        if source.size <= slice_size:
            DouyinCreatorAPI.upload_video_direct(
                node, source, user_id, proxies=proxies, auth=auth,
            )
        else:
            DouyinCreatorAPI.upload_video_parts(
                node, source, user_id, max(slice_size, 5 * _MB), proxies=proxies,
                auth=auth,
            )

        # Chrome 实录中 AI 封面结果上传完成后才发 VOD Commit。封面轮询与 TOS
        # 视频传输仍并行，但 Commit 是两条支路重新汇合的屏障。
        if before_commit_future is not None:
            before_commit_future.result()

        # 浏览器在 TOS 上传完成后重新获取带 creator platform 参数的 STS，
        # 再签 VOD Commit；初始 Apply 的 bare STS 不复用到这里。
        commit_sts = DouyinCreatorAPI.get_image_upload_auth(
            auth, referer=POST_VIDEO_REFERER, proxies=proxies,
            request_context=request_context, include_platform=True,
        )
        info = DouyinCreatorAPI.commit_video_upload(
            auth, commit_sts, node["session_key"], user_id=user_id, proxies=proxies,
            request_context=request_context,
        )
        if not info["vid"]:
            raise RuntimeError(f"提交后未拿到 vid: {info['raw']}")
        info["commit_sts"] = commit_sts
        return info

    @staticmethod
    def prepare_video_cover_state(auth, video, info, *, creation_id, user_id,
                                  preview_video_list=None, proxies=None,
                                  request_context=None, ai_title="", ai_caption="",
                                  recommend_frames=None,
                                  browser_cover_payloads=None,
                                  strict_browser_alignment=False):
        """执行浏览器默认视频封面、检测与 AI 封面链，返回最终发布封面状态。"""
        prepared = DouyinCreatorAPI._prepare_video_cover_preupload(
            auth, video, creation_id=creation_id, user_id=user_id,
            proxies=proxies, request_context=request_context,
            ai_title=ai_title, ai_caption=ai_caption,
            recommend_frames=recommend_frames,
            browser_cover_payloads=browser_cover_payloads,
            strict_browser_alignment=strict_browser_alignment,
        )
        return DouyinCreatorAPI._finalize_video_cover_state(
            auth, info, prepared, creation_id=creation_id, user_id=user_id,
            preview_video_list=preview_video_list, proxies=proxies,
            request_context=request_context,
        )

    @staticmethod
    def _complete_cover_gen_flow(auth, task_id, user_id, *, ai_output_payload=None,
                                 proxies=None, request_context=None,
                                 cancel_event=None, started_event=None):
        """轮询 AI 封面并上传输出；该任务与 VOD TOS 上传并行。"""
        if started_event is not None:
            started_event.set()
        ai_result = DouyinCreatorAPI.poll_cover_gen_task(
            auth, task_id, proxies=proxies,
            request_context=request_context, cancel_event=cancel_event,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("AI 封面输出上传已取消")
        payload = ai_output_payload
        if payload is None:
            ai_url = ai_result["ai_cover"]["url_list"][0]
            payload = _read_image_bytes(ai_url)
        ai_output = DouyinCreatorAPI.upload_image_batch(
            auth, [payload], user_id=user_id, proxies=proxies,
            request_context=request_context, max_workers=1,
        )[0]
        return {"ai_result": ai_result, "ai_output": ai_output}

    @staticmethod
    def _shutdown_prepared_cover(prepared, *, wait=True):
        """幂等取消并回收 preupload 创建的 AI 封面后台任务。"""
        if not isinstance(prepared, dict):
            return
        cancel_event = prepared.get("cover_cancel")
        if cancel_event is not None:
            cancel_event.set()
        future = prepared.get("cover_future")
        if future is not None:
            future.cancel()
        executor = prepared.pop("cover_executor", None)
        if executor is not None:
            executor.shutdown(wait=bool(wait), cancel_futures=True)

    @staticmethod
    def _prepare_video_cover_preupload(
            auth, video, *, creation_id, user_id, proxies=None,
            request_context=None, ai_title="", ai_caption="",
            recommend_frames=None, browser_cover_payloads=None,
            strict_browser_alignment=False):
        """VOD 字节上传前完成音频/首帧/20 帧/推荐帧，并启动 AI 封面任务。"""
        source = _MediaSource(video)
        probe = _video_probe(source)
        duration = float(probe["duration"] or 0)
        width = int(probe["width"] or 0)
        height = int(probe["height"] or 0)
        if duration <= 0 or width <= 0 or height <= 0:
            raise RuntimeError(f"视频元信息不完整: duration={duration}, {width}x{height}")

        timing = _browser_frame_times(duration)
        ai_times = timing["upload_times"] or [0]
        candidate_times = _browser_sync_frame_times(source, count=10)
        recommend_frames = _normalize_browser_recommend_frames(
            recommend_frames, candidate_times,
            strict=bool(strict_browser_alignment),
        )
        browser_cover_payloads = _browser_cover_payloads(
            browser_cover_payloads, len(recommend_frames), len(ai_times),
            strict=bool(strict_browser_alignment),
        )
        recommend_times = [frame["time"] for frame in recommend_frames]
        # 23.7s 实产 PNG 的帧时间为 0/4.733/9.467/14.2/18.933：
        # 即 duration/5 的五个区间起点，不是 10 张 preview 隔一张取一张。
        post_times = _post_assistant_frame_times(duration)

        frame_by_time = {}
        if browser_cover_payloads is None:
            all_times = []
            for value in [0.0] + ai_times + recommend_times + post_times:
                value = float(value)
                if value not in all_times:
                    all_times.append(value)
            extracted = _extract_video_frames(source, all_times)
            frame_by_time = dict(zip(all_times, extracted))

        audio_bytes = (
            browser_cover_payloads["audio_analysis"]
            if browser_cover_payloads is not None
            else _extract_audio_analysis_wav(source, duration)
        )
        audio_sts = DouyinCreatorAPI.get_image_upload_auth(
            auth, referer=POST_VIDEO_REFERER, proxies=proxies,
            request_context=request_context, include_platform=True,
        )
        audio_info = DouyinCreatorAPI.upload_one_image(
            auth, audio_sts, audio_bytes, user_id=user_id, proxies=proxies,
            request_context=request_context,
        )

        first_bytes = (
            browser_cover_payloads["poster"]
            if browser_cover_payloads is not None
            else _encode_frame(frame_by_time[0.0], "webp", quality=90)
        )
        poster_sts = DouyinCreatorAPI.get_image_upload_auth(
            auth, referer=POST_VIDEO_REFERER, proxies=proxies,
            request_context=request_context, include_platform=True,
        )
        first_info = DouyinCreatorAPI.upload_one_image(
            auth, poster_sts, first_bytes, user_id=user_id,
            proxies=proxies, request_context=request_context,
        )
        preview_poster_uri = first_info["uri"]

        # 23.7 秒实录上传 20 张源分辨率 JPEG；cover/gen 的 img_uris 也是 20 项，
        # 不是早期误判的「缩到 460 后只上传 10 张」。
        ai_payloads = (
            browser_cover_payloads["ai_inputs"]
            if browser_cover_payloads is not None
            else [
                _encode_frame(frame_by_time[float(value)], "jpeg", quality=75)
                for value in ai_times
            ]
        )
        ai_inputs = DouyinCreatorAPI.upload_image_batch(
            auth, ai_payloads, user_id=user_id, proxies=proxies,
            request_context=request_context,
        )

        cover_url = ""
        for _ in range(3):
            cover_url = DouyinCreatorAPI.get_creator_media_url(
                auth, preview_poster_uri, proxies=proxies,
                request_context=request_context,
            )

        recommend_payloads = []
        uploaded_recommend_frames = []
        for index, frame in enumerate(recommend_frames):
            value = frame["time"]
            if browser_cover_payloads is not None:
                payload = browser_cover_payloads["recommend"][index]
            else:
                crop = _crop_normalized(
                    frame_by_time[float(value)], frame["crop_box"],
                )
                payload = _encode_frame(
                    _resize_exact(crop, 480, 360), "jpeg", quality=100,
                )
            recommend_payloads.append(payload)
            sts = DouyinCreatorAPI.get_image_upload_auth(
                auth, referer=POST_VIDEO_REFERER, proxies=proxies,
                request_context=request_context, include_platform=True,
            )
            DouyinCreatorAPI.upload_one_image(
                auth, sts, payload, user_id=user_id, proxies=proxies,
                request_context=request_context,
            )
            uploaded_recommend_frames.append({
                **frame,
                "time": value,
                "frame_index": frame["frame_index"],
                "crop_height": 360,
                "crop_width": 480,
            })

        horizontal = width >= height
        task = DouyinCreatorAPI.post_cover_gen_task(
            auth, preview_poster_uri, [item["uri"] for item in ai_inputs],
            creation_id, user_id, audio_uri=audio_info["uri"],
            title=ai_title, caption=ai_caption,
            ratio_type=1 if horizontal else 2, proxies=proxies,
            request_context=request_context,
        )
        cover_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="douyin-cover-gen",
        )
        cover_cancel = threading.Event()
        cover_started = threading.Event()
        cover_future = cover_executor.submit(
            DouyinCreatorAPI._complete_cover_gen_flow,
            auth, task["task_id"], user_id,
            ai_output_payload=(
                browser_cover_payloads.get("ai_output")
                if browser_cover_payloads is not None else None
            ),
            proxies=proxies, request_context=request_context,
            cancel_event=cover_cancel, started_event=cover_started,
        )
        if not cover_started.wait(timeout=5):
            prepared = {
                "cover_cancel": cover_cancel,
                "cover_executor": cover_executor,
                "cover_future": cover_future,
            }
            DouyinCreatorAPI._shutdown_prepared_cover(prepared)
            raise RuntimeError("cover/gen/get 后台线程未能启动")

        post_payloads = (
            browser_cover_payloads["post_assistant"]
            if browser_cover_payloads is not None
            else [
                _encode_frame(
                    _resize_to_width(frame_by_time[float(value)], 256), "png",
                )
                for value in post_times
            ]
        )
        final_cover_payload = (
            browser_cover_payloads["final_cover"]
            if browser_cover_payloads is not None
            else recommend_payloads[0]
        )
        return {
            "source": source,
            "duration": duration,
            "width": width,
            "height": height,
            "preview_poster_uri": preview_poster_uri,
            "cover_url": cover_url,
            "uploaded_recommend_frames": uploaded_recommend_frames,
            "post_payloads": post_payloads,
            "final_cover_payload": final_cover_payload,
            "cover_cancel": cover_cancel,
            "cover_started": cover_started,
            "cover_executor": cover_executor,
            "cover_future": cover_future,
        }

    @staticmethod
    def _finalize_video_cover_state(
            auth, info, prepared, *, creation_id, user_id,
            preview_video_list=None, proxies=None, request_context=None):
        """VOD Commit 后并发快速检测，上传最终封面与 post-assistant 五帧。"""
        fast_cancel = threading.Event()
        fast_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="douyin-fast-detect",
        )
        fast_future = fast_executor.submit(
            DouyinCreatorAPI._run_fast_detect_flow,
            auth, info["vid"], prepared["duration"], proxies=proxies,
            request_context=request_context, cancel_event=fast_cancel,
        )
        try:
            DouyinCreatorAPI.video_enable(
                auth, info["vid"], proxies=proxies,
                request_context=request_context,
            )
            DouyinCreatorAPI.get_user_declaration_suggestion(
                auth, creation_id, proxies=proxies,
                request_context=request_context,
            )
            DouyinCreatorAPI.get_creator_media_url(
                auth, prepared["preview_poster_uri"], proxies=proxies,
                request_context=request_context,
            )
            for _ in range(2):
                DouyinCreatorAPI.video_transend(
                    auth, info["vid"], proxies=proxies,
                    request_context=request_context,
                )

            final_cover = DouyinCreatorAPI.upload_image_batch(
                auth, [prepared["final_cover_payload"]], user_id=user_id,
                proxies=proxies, request_context=request_context,
                max_workers=1,
            )[0]
            poster_uri = final_cover["uri"]
            cover_url = DouyinCreatorAPI.get_creator_media_url(
                auth, poster_uri, proxies=proxies,
                request_context=request_context,
            )

            DouyinCreatorAPI.upload_image_batch(
                auth, prepared["post_payloads"], user_id="", proxies=proxies,
                request_context=request_context,
            )
            cover_result = prepared["cover_future"].result()
            detect, detect_result = fast_future.result()
            extend = DouyinCreatorAPI.build_video_cover_tools_extend_info(
                poster_uri,
                video_name=prepared["source"].name,
                cover_url=cover_url,
                recommend_frames=prepared["uploaded_recommend_frames"],
                ai_uri=cover_result["ai_output"]["uri"],
                preview_video_list=preview_video_list or [{"isCurrent": True}],
                request_context=request_context,
            )
            return {
                "poster_uri": poster_uri,
                "cover_url": cover_url,
                "cover_tools_extend_info": extend,
                "detect": detect,
                "detect_result": detect_result,
                "ai_result": cover_result["ai_result"],
            }
        finally:
            fast_cancel.set()
            fast_executor.shutdown(wait=True, cancel_futures=True)
            DouyinCreatorAPI._shutdown_prepared_cover(prepared)

    @staticmethod
    def _prepare_video_cover_state_impl(
            auth, video, info, *, creation_id, user_id,
            preview_video_list=None, proxies=None, request_context=None,
            ai_title="", ai_caption="", recommend_frames=None,
            browser_cover_payloads=None, strict_browser_alignment=False,
            background_jobs=None):
        prepared = DouyinCreatorAPI._prepare_video_cover_preupload(
            auth, video, creation_id=creation_id, user_id=user_id,
            proxies=proxies, request_context=request_context,
            ai_title=ai_title, ai_caption=ai_caption,
            recommend_frames=recommend_frames,
            browser_cover_payloads=browser_cover_payloads,
            strict_browser_alignment=strict_browser_alignment,
        )
        return DouyinCreatorAPI._finalize_video_cover_state(
            auth, info, prepared, creation_id=creation_id, user_id=user_id,
            preview_video_list=preview_video_list, proxies=proxies,
            request_context=request_context,
        )

    # ---------- 文案与 text_extra ----------
    @staticmethod
    def _build_text_and_extra(title, desc):
        """标题+描述拼成 text，并生成 text_extra（对齐浏览器：标题段 type7、分隔符 type8）。

        start/end 与前端 JavaScript 一样按 UTF-16 code unit 计数。
        """
        title = title or ""
        desc = desc or ""
        text = ""
        text_extra = []
        if title:
            text = title
            title_length = _js_string_length(title)
            text_extra.append({
                "start": 0, "end": title_length,
                "hashtag_id": 0, "hashtag_name": "", "type": 7,
            })
        if desc:
            if text:
                sep_start = _js_string_length(text)
                text += "。"
                text_extra.append({
                    "start": sep_start, "end": sep_start + 1,
                    "hashtag_id": 0, "hashtag_name": "", "type": 8,
                })
            text += desc
        return text, text_extra

    @staticmethod
    def _build_video_text(title, desc):
        """视频版文案派生，对齐前端 eA()：标题独立成 item_title，不进 text_extra。

        text 为「标题 空格 描述」，caption 只放描述；text_extra 的 start/end 需按
        标题长度+1 右移，同时保留基于 caption 的原始偏移。
        """
        title = (title or "").strip()
        desc = (desc or "").strip()
        return {
            "text": f"{title} {desc}" if title else desc,
            "item_title": title,
            "caption": desc,
            "text_extra": [],
            "challenges": [],
            "mentions": [],
            "activity": [],
            "hashtag_source": "",
        }

    @staticmethod
    def build_image_create_item(image_infos, *, title="", desc="", visibility=1,
                                allow_download=True, timing=None, cover_index=0,
                                cover_uri=None, challenges=None, mentions=None,
                                activity=None, poi=None, mix_id=None, hot_spot=None,
                                creation_id):
        """纯构建图集 create_v2 item，便于固定浏览器样本逐字节对拍。"""
        text, text_extra = DouyinCreatorAPI._build_text_and_extra(title, desc)
        cover = cover_uri or image_infos[
            max(0, min(cover_index, len(image_infos) - 1))
        ]["uri"]
        dump = lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"),
        )
        common = {
            "text": text,
            "text_extra": dump(text_extra),
            "activity": dump(activity or []),
            "challenges": dump(challenges or []),
            "hashtag_source": "",
            "mentions": dump(mentions or []),
            "visibility_type": int(visibility),
            "download": 1 if allow_download else 0,
            "timing": int(timing) if timing else -1,
            "media_type": 2,
            "images": [
                {"uri": info["uri"], "width": info["width"], "height": info["height"]}
                for info in image_infos
            ],
            "creation_id": str(creation_id),
        }
        if mix_id:
            common["mix_id"] = mix_id
        if poi:
            common["poi_id"] = poi.get("poi_id", "")
            common["poi_name"] = poi.get("poi_name", "")
        if hot_spot:
            common["hot_sentence"] = hot_spot.get("word", "")
        anchor = {"poi": poi} if poi else {}
        return {"item": {"common": common, "cover": {"poster": cover}, "anchor": anchor}}

    @staticmethod
    def build_video_create_item(info, *, title="", desc="", visibility=1,
                                allow_download=True, timing=None, poster_uri=None,
                                cover_delay=0, challenges=None, mentions=None,
                                activity=None, poi=None, mix_id=None, hot_spot=None,
                                creation_id, cover_tools_extend_info=None,
                                cover_tools_info=None, chapter=None,
                                request_context=None):
        """纯构建视频 create_v2 item；前端封面状态可显式注入用于浏览器对拍。"""
        parts = DouyinCreatorAPI._build_video_text(title, desc)
        dump = lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"),
        )
        common = {
            "text": parts["text"],
            "caption": parts["caption"],
            "item_title": parts["item_title"],
            "activity": dump(activity if activity is not None else parts["activity"]),
            "text_extra": dump(parts["text_extra"]),
            "challenges": dump(challenges if challenges is not None else parts["challenges"]),
            "mentions": dump(mentions if mentions is not None else parts["mentions"]),
            "hashtag_source": parts["hashtag_source"],
            "hot_sentence": (hot_spot or {}).get("word", ""),
            "interaction_stickers": "[]",
            "visibility_type": int(visibility),
            "download": 1 if allow_download else 0,
            "timing": int(timing) if timing else 0,
            "creation_id": str(creation_id),
            "media_type": 4,
            "video_id": info["vid"],
            "music_source": 0,
            "music_id": None,
        }
        if mix_id:
            common["mix_id"] = mix_id
        if poi:
            common["poi_id"] = poi.get("poi_id", "")
            common["poi_name"] = poi.get("poi_name", "")
        poster_uri = poster_uri or info.get("poster_uri") or ""
        extend = (
            cover_tools_extend_info if cover_tools_extend_info is not None
            else DouyinCreatorAPI._cover_tools_extend_info(poster_uri)
        )
        cover_section = {
            "cover_text_uri": None,
            "cover_text": None,
            "poster": poster_uri,
            "poster_delay": int(cover_delay),
            "cover_tools_extend_info": dump(extend),
            "cover_tools_info": dump(cover_tools_info or {}),
        }
        anchor = {"poi": poi} if poi else {}
        chapter = chapter if chapter is not None else DouyinCreatorAPI._empty_chapter(
            request_context,
        )
        return {"item": {
            "common": common,
            "cover": cover_section,
            "mix": {},
            "selected_member": {"is_selected_member_video": False},
            "chapter": {"chapter": dump(chapter)},
            "anchor": anchor,
            "sync": {"should_sync": False, "sync_to_toutiao": 0},
            "open_platform": {},
            "assistant": {"is_preview": 0, "is_post_assistant": 1},
        }}

    # ---------- 步骤 5：发布图文（编排全流程） ----------
    @staticmethod
    def _require_publish_security(auth):
        """发布前强制校验浏览器 create_v2 所需的全部安全素材。

        这里必须在上传媒体前调用。发布是强校验写接口，不能沿用普通读取接口
        的“缺头继续请求”策略，否则会产生浏览器抓包与代码不一致的假成功。
        """
        missing = []
        for attr, label in (
            ("ticket", "DY_TICKET"),
            ("ts_sign", "DY_TS_SIGN"),
            ("private_key", "DY_PRIVATE_KEY"),
        ):
            if not getattr(auth, attr, None):
                missing.append(label)
        if missing:
            raise RuntimeError(
                "发布安全凭据缺失: " + ", ".join(missing)
            )
        if not auth.ticket_matches_session():
            raise RuntimeError(
                "ticket/ts_sign 与 Cookie 不属于同一次登录，禁止发送 create_v2"
            )
        if not (
            getattr(auth, "dtrait_blob", None)
            or getattr(auth, "dtrait_profile", None)
        ):
            raise RuntimeError(
                "缺少可按 create_v2 path 和当前时间重算的 DY_DTRAIT_BLOB "
                "或内置 dtrait_profile；"
                "静态 DY_SESSION_DTRAIT 不能用于发布，禁止发送请求"
            )

    @staticmethod
    def post_images(auth, images, title="", desc="",
                    visibility=1, allow_download=True, timing=None,
                    cover_index=0, cover_uri=None,
                    challenges=None, mentions=None, activity=None,
                    poi=None, mix_id=None, hot_spot=None,
                    creation_id=None, proxies=None, request_context=None):
        """发布图片 / 图文作品。

        :param auth: DouyinAuth object.
        :param images: 图片列表（本地路径 / bytes / URL）。
        :param title: 标题（作品描述首段，<=20 字）。
        :param desc: 正文描述（可内嵌 #话题 @好友 纯文本）。
        :param visibility: 谁可以看 0 公开 / 1 仅自己可见 / 2 好友可见（默认 1）。
        :param allow_download: 保存权限 True 允许 / False 不允许。
        :param timing: None 立即发布；传秒级时间戳则为定时发布。
        :param cover_index: 用第几张图作封面（默认第 0 张）。
        :param cover_uri: 显式封面 uri（优先于 cover_index）。
        :param challenges: 话题挑战列表（JSON 可序列化），默认 []。
        :param mentions: @好友列表（JSON 可序列化），默认 []。
        :param activity: 官方活动列表（JSON 可序列化），默认 []。
        :param poi: 位置信息 dict（写入 common.poi_* / anchor），默认无。
        :param mix_id: 合集 ID，默认无。
        :param hot_spot: 关联热点 dict，默认无。
        :param creation_id: 前端 creationId，默认自动生成。
        :return: (success: bool, msg: str, res_json: dict)
        """
        try:
            DouyinCreatorAPI._require_publish_security(auth)
            if not images:
                raise ValueError("images 不能为空")

            # 2026-08-23 图集实录：ImageX user_id 与 TOS X-Storage-U 均为空。
            # 视频及视频封面链才带真实 uid，二者不能混用。
            user_id = ""

            # 浏览器会在每张图的 Apply 之前重新获取一份 STS，不能跨图复用。
            image_infos = []
            for idx, image in enumerate(images):
                sts = DouyinCreatorAPI.get_image_upload_auth(
                    auth, referer=POST_IMAGE_REFERER, proxies=proxies,
                    request_context=request_context,
                )
                info = DouyinCreatorAPI.upload_one_image(
                    auth, sts, image, user_id=user_id, proxies=proxies,
                    request_context=request_context,
                )
                logger.info(
                    f"图片上传成功 [{idx + 1}/{len(images)}] "
                    f"{info['width']}x{info['height']}"
                )
                image_infos.append(info)

            creation_id = creation_id or (
                request_context.creation_id() if request_context
                else _rand_str(8) + str(_now_ms())
            )
            item = DouyinCreatorAPI.build_image_create_item(
                image_infos, title=title, desc=desc, visibility=visibility,
                allow_download=allow_download, timing=timing,
                cover_index=cover_index, cover_uri=cover_uri,
                challenges=challenges, mentions=mentions, activity=activity,
                poi=poi, mix_id=mix_id, hot_spot=hot_spot,
                creation_id=creation_id,
            )

            success, msg, res_json = DouyinCreatorAPI._create_aweme(
                auth, item, proxies=proxies, request_context=request_context,
            )
            return success, msg, res_json
        except Exception as error:
            logger.exception(f"发布图文失败: {error}")
            return False, str(error), None

    # ---------- 步骤 5：发布视频（编排全流程） ----------
    @staticmethod
    def post_video(auth, video, title="", desc="",
                   visibility=1, allow_download=True, timing=None,
                   cover=None, cover_delay=0,
                   challenges=None, mentions=None, activity=None,
                   poi=None, mix_id=None, hot_spot=None,
                   creation_id=None, user_id=None, proxies=None,
                   request_context=None, cover_tools_extend_info=None,
                   cover_tools_info=None, chapter=None,
                   recommend_frames=None, browser_cover_payloads=None,
                   strict_browser_alignment=False):
        """发布视频作品。

        :param auth: DouyinAuth object.
        :param video: 视频文件（本地路径 / bytes / URL）。
        :param title: 标题（作品描述首段，<=20 字）。
        :param desc: 正文描述（可内嵌 #话题 @好友 纯文本）。
        :param visibility: 谁可以看 0 公开 / 1 仅自己可见 / 2 好友可见（默认 1）。
        :param allow_download: 保存权限 True 允许 / False 不允许。
        :param timing: None 立即发布；传秒级时间戳则为定时发布。
        :param cover: 封面图 uri，默认用 Snapshot 抽的首帧。
        :param cover_delay: 取封面的时间点（秒），默认 0。
        :param challenges: 话题挑战列表（JSON 可序列化），默认 []。
        :param mentions: @好友列表（JSON 可序列化），默认 []。
        :param activity: 官方活动列表（JSON 可序列化），默认 []。
        :param poi: 位置信息 dict（写入 common.poi_* / anchor），默认无。
        :param mix_id: 合集 ID，默认无。
        :param hot_spot: 关联热点 dict，默认无。
        :param creation_id: 前端 creationId，默认自动生成。
        :param user_id: 上传用的抖音 uid（X-Storage-U），默认自动获取。
        :param recommend_frames: 浏览器 Bach 实测的 3 帧 frame_index/time/cropBox/cropBox2。
        :param browser_cover_payloads: 浏览器导出的各阶段 Canvas/WebCodecs 编码字节。
        :param strict_browser_alignment: 默认 False，纯 HTTP 生成封面素材；传 True 时要求
            同时提供浏览器 Bach 推荐帧和封面 payload。
        :return: (success: bool, msg: str, res_json: dict)
        """
        prepared = None
        try:
            DouyinCreatorAPI._require_publish_security(auth)
            if not video:
                raise ValueError("video 不能为空")
            if (
                strict_browser_alignment
                and cover_tools_extend_info is None
                and not cover
                and (recommend_frames is None or browser_cover_payloads is None)
            ):
                raise RuntimeError(
                    "严格浏览器对齐缺少 recommend_frames 或 browser_cover_payloads；"
                    "已在上传前停止，不会使用猜帧或 OpenCV 编码冒充浏览器"
                )
            if user_id is None:
                user_id = DouyinCreatorAPI._resolve_user_id(auth)

            creation_id = creation_id or (
                request_context.creation_id() if request_context
                else _rand_str(8) + str(_now_ms())
            )
            preview_video_list = DouyinCreatorAPI.get_preview_video_list(
                auth, proxies=proxies, request_context=request_context,
            )
            DouyinCreatorAPI.get_cover_gen_ref(
                auth, creation_id, proxies=proxies,
                request_context=request_context,
            )
            DouyinCreatorAPI.get_user_declaration_suggestion(
                auth, creation_id, proxies=proxies,
                request_context=request_context,
            )

            sts = DouyinCreatorAPI.get_image_upload_auth(
                auth, proxies=proxies, request_context=request_context,
                include_platform=True,
            )
            source = _MediaSource(video)
            video_node = DouyinCreatorAPI.apply_video_upload(
                auth, sts, source.size, user_id=user_id, proxies=proxies,
                request_context=request_context,
            )
            if cover_tools_extend_info is None and not cover:
                # 浏览器在 VOD TOS 传输前先上传 audio/poster/20 AI 帧/3 推荐帧，
                # 发起 cover/gen 后才让视频字节与 AI 轮询并行推进。
                prepared = DouyinCreatorAPI._prepare_video_cover_preupload(
                    auth, video, creation_id=creation_id, user_id=user_id,
                    proxies=proxies, request_context=request_context,
                    recommend_frames=recommend_frames,
                    browser_cover_payloads=browser_cover_payloads,
                    strict_browser_alignment=strict_browser_alignment,
                )
            info = DouyinCreatorAPI.upload_prepared_video(
                auth, sts, video_node, source, user_id=user_id,
                proxies=proxies, request_context=request_context,
                before_commit_future=(
                    prepared["cover_future"] if prepared is not None else None
                ),
            )
            logger.info(
                f"视频上传成功 vid_len={len(info['vid'])} "
                f"{info['width']}x{info['height']} "
                f"{info['duration']:.1f}s"
            )

            # 默认走完整首帧/推荐帧/post-assistant/AI 封面链；显式 cover 保留手工封面。
            poster_uri = info["poster_uri"]
            if prepared is not None:
                finalized = DouyinCreatorAPI._finalize_video_cover_state(
                    auth, info, prepared, creation_id=creation_id,
                    user_id=user_id,
                    preview_video_list=preview_video_list, proxies=proxies,
                    request_context=request_context,
                )
                poster_uri = finalized["poster_uri"]
                cover_tools_extend_info = finalized["cover_tools_extend_info"]
            elif cover:
                poster_uri = DouyinCreatorAPI.upload_one_image(
                    auth, info.get("commit_sts") or sts, cover,
                    user_id=user_id, proxies=proxies,
                    request_context=request_context,
                )["uri"] if not str(cover).startswith("tos-") else cover

            item = DouyinCreatorAPI.build_video_create_item(
                info, title=title, desc=desc, visibility=visibility,
                allow_download=allow_download, timing=timing,
                poster_uri=poster_uri, cover_delay=cover_delay,
                challenges=challenges, mentions=mentions, activity=activity,
                poi=poi, mix_id=mix_id, hot_spot=hot_spot,
                creation_id=creation_id,
                cover_tools_extend_info=cover_tools_extend_info,
                cover_tools_info=cover_tools_info, chapter=chapter,
                request_context=request_context,
            )

            return DouyinCreatorAPI._create_aweme(
                auth, item, referer=POST_VIDEO_REFERER, proxies=proxies,
                request_context=request_context,
            )
        except Exception as error:
            logger.exception(f"发布视频失败: {error}")
            return False, str(error), None
        finally:
            DouyinCreatorAPI._shutdown_prepared_cover(prepared)

    @staticmethod
    def _empty_chapter(request_context=None):
        """无章节时的 chapter 结构，键集合与浏览器一致。"""
        return {
            "chapter_abstract": "",
            "chapter_details": [],
            "chapter_type": 1,
            "chapter_tools_info": {
                "chapter_recommend_detail": [],
                "chapter_recommend_abstract": "",
                "chapter_source": 2,
                "chapter_recommend_type": -2,
                "create_date": _now_s(request_context),
                "is_pc": "1",
                "is_pre_generated": "0",
                "is_syn": "1",
            },
        }

    @staticmethod
    def build_video_cover_tools_extend_info(
            poster_uri, *, video_name="", cover_url="", recommend_frames=None,
            ai_uri="", preview_video_list=None, request_context=None):
        """按 creator atom selector 的字段与顺序组装最终封面编辑器状态。"""
        context = request_context

        def frontend_uuid():
            if context is not None:
                return context.frontend_uuid()
            return CreatorRequestContext().frontend_uuid()

        def blob_url():
            if context is not None:
                return context.blob_url()
            return f"blob:{CREATOR_ORIGIN}/{uuid.uuid4()}"

        cover_list = []
        for index, frame in enumerate(recommend_frames or []):
            value = frame.get("time", 0)
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            preview_blob = (
                frame.get("previewBlobSrc")
                or frame.get("preview_blob_src")
                or blob_url()
            )
            source_blob = frame.get("src") or blob_url()
            is_ai = bool(frame.get("isAIGen", index == 0 and ai_uri))
            uri1 = frame.get("uri1") or (ai_uri if is_ai else "NOT_READY")
            cover_list.append({
                "id": frame.get("id") or frontend_uuid(),
                "time": value,
                "uri": frame.get("uri", "NOT_READY"),
                "frameIndex": int(frame.get("frameIndex", frame.get("frame_index", index))),
                "previewBlobSrc": preview_blob,
                "cropHeight": int(frame.get("cropHeight", frame.get("crop_height", 360))),
                "cropWidth": int(frame.get("cropWidth", frame.get("crop_width", 480))),
                "cropBox": frame.get("cropBox", frame.get("crop_box", [0, 0, 0.75, 1])),
                "cropBox2": frame.get(
                    "cropBox2", frame.get(
                        "crop_box2",
                        [0.08695652335882187, 0, 0.508695662021637, 1],
                    ),
                ),
                "src": source_blob,
                "rawBlob": {},
                "fileName": frame.get("fileName", frame.get("file_name", video_name)),
                "isAIGen": is_ai,
                "uri1": uri1,
            })

        return {
            "recommendServerInfo": {"res": [], "times": []},
            "recommendCoverList": cover_list,
            "recommendCoverInfo": {
                "isFromRecommend": bool(cover_list), "isDefaultSelect": False,
                "isRecommendClickFrom": "", "selectInfo": {}, "editingInfo": {},
            },
            "recommendCoverTime": 0,
            "coverInfo": {
                "firstFrameCoverUri": poster_uri, "videoName": video_name,
                "uri": poster_uri, "url": cover_url, "posterDelay": 0,
            },
            "coverUrl": cover_url,
            "coverHorizontalInfo": None,
            "coverHorizontalUrl": "",
            "pasterInfo": None,
            "stateInfo": None,
            "croppedCoverInfo": None,
            "uploadBackgroundInfo": None,
            "uploadPasterInfo": None,
            "uploadCoverStateInfo": None,
            "xiguaCoverInfo": {"posterDelay": 0},
            "xiguaPasterInfo": None,
            "xiguaStateInfo": None,
            "xiguaUploadCoverStateInfo": None,
            "xiguaUploadBackgroundInfo": None,
            "xiguaUploadPasterInfo": None,
            "editXigua": False,
            "coverSource": "",
            "previewVideoList": preview_video_list or [],
        }

    @staticmethod
    def _cover_tools_extend_info(poster_uri):
        """兼容旧调用：只保留键集合，不伪造不存在的前端推荐状态。"""
        return DouyinCreatorAPI.build_video_cover_tools_extend_info(poster_uri)

    @staticmethod
    def _resolve_user_id(auth):
        """取当前登录 uid（TOS 上传的 X-Storage-U），失败则退回空串。"""
        cached = getattr(auth, "creator_uid", None)
        if cached:
            return cached
        try:
            from dy_apis.douyin_api import DouyinAPI
            uid = str(DouyinAPI.get_my_uid(auth))
        except Exception as error:
            logger.warning(f"获取 uid 失败，X-Storage-U 置空: {error}")
            uid = ""
        auth.creator_uid = uid
        return uid

    @staticmethod
    def _create_aweme(auth, item: dict, referer=POST_IMAGE_REFERER, proxies=None,
                      request_context=None):
        """POST create_v2 发布，返回 (success, msg, res_json)。

        注意：create_v2 是 **bd-ticket-guard 强校验** 接口（实测无 bd 头必返 403
        空响应，浏览器有效会话亦然）。需 auth 具备扫码登录写入的
        ticket / ts_sign / private_key（.env 的 DY_TICKET / DY_TS_SIGN /
        DY_PRIVATE_KEY），否则无法发布。
        """
        api = "/web/api/media/aweme/create_v2/"
        try:
            DouyinCreatorAPI._require_publish_security(auth)
        except Exception as security_error:
            msg = f"create_v2 安全校验失败，请求未发送: {security_error}"
            logger.error(msg)
            return False, msg, None

        # 头集合与顺序照抄浏览器实录（2026-08-16）：不带 cache-control / pragma /
        # sec-ch-ua*，这条 XHR 浏览器确实没发这几个。
        bd = Header()
        try:
            bd.with_bd(
                api, auth, aid=CREATOR_READ_AID, origin=CREATOR_ORIGIN,
                timestamp=(request_context.fixed_bd_timestamp
                           if request_context else None),
                dtrait_timestamp=(request_context.fixed_dtrait_timestamp
                                  if request_context else None),
                dtrait_randbytes=(request_context.dtrait_randbytes
                                  if request_context else None),
                require_dtrait=True,
            )
        except Exception as bd_error:
            msg = f"create_v2 加密头构造失败，请求未发送: {bd_error}"
            logger.error(msg)
            return False, msg, None
        bd_headers = bd.get()
        body = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        body_bytes = body.encode("utf-8")
        try:
            # creator 域必须向 creator 域换 csrf token（与 csrf_session_id 绑定），
            # 早先固定打 www 域，token 与会话对不上
            token = getattr(auth, "creator_csrf_token", "") or generate_csrf_token(
                _cookie_str_for(
                    auth, CREATOR_ORIGIN + CSRF_PROBE_PATH, "HEAD",
                ),
                origin=CREATOR_ORIGIN, path=CSRF_PROBE_PATH, referer=referer,
            )[0]
        except Exception as csrf_error:
            msg = f"create_v2 CSRF 头构造失败，请求未发送: {csrf_error}"
            logger.error(msg)
            return False, msg, None
        if not token:
            msg = "create_v2 缺少 x-secsdk-csrf-token，请求未发送"
            logger.error(msg)
            return False, msg, None
        cookie_value = getattr(auth, "creator_cookie_str", "")
        if not cookie_value:
            msg = "create_v2 缺少 Cookie，请求未发送"
            logger.error(msg)
            return False, msg, None
        try:
            headers = _create_aweme_headers(
                bd_headers=bd_headers, referer=referer, csrf_token=token,
                cookie_value=cookie_value, body_bytes=body_bytes,
            )
        except Exception as header_error:
            msg = f"create_v2 header 构造失败，请求未发送: {header_error}"
            logger.error(msg)
            return False, msg, None

        params = Params()
        params.add_param("read_aid", CREATOR_READ_AID)
        params.with_creator_platform()
        params.add_param("msToken", auth.msToken)
        # a_bogus 需与 body 一起计算（POST 带 body）
        query_without_sign = splice_url(params.get())
        params.add_param(
            "a_bogus",
            request_context.sign_a_bogus(
                query_without_sign, body, host=CREATOR_HOST,
            ) if request_context else generate_a_bogus(
                query_without_sign, body, host=CREATOR_HOST,
            ),
        )

        if hasattr(auth, "publish_attempted"):
            auth.publish_attempted = True
        resp = _request(
            auth, "POST", f"{CREATOR_ORIGIN}{api}", headers=headers,
            params=params.get(), data=body_bytes, verify=False, proxies=proxies,
            split_cookie_header=True,
        )
        try:
            res_json = resp.json()
        except Exception:
            # 403 空响应基本等于缺 bd-ticket-guard
            hint = (
                "发布接口返回非 JSON（HTTP %s）。create_v2 为 bd-ticket-guard 强校验接口，"
                "请确保 auth 已配置 DY_TICKET / DY_TS_SIGN / DY_PRIVATE_KEY"
                "（扫码登录后由 login_grab_ticket 写入 .env）。"
            ) % resp.status_code
            return False, hint, None

        success = res_json.get("status_code") == 0 and bool(res_json.get("item_id"))
        if success and hasattr(auth, "publish_server_verified"):
            auth.publish_server_verified = True
        if success and hasattr(auth, "creator_upload_verified"):
            auth.creator_upload_verified = True
        if success:
            msg = f"发布成功 item_id={res_json.get('item_id')}"
            logger.info(msg)
        else:
            msg = res_json.get("status_msg") or f"发布失败: {res_json}"
            logger.error(msg)
        return success, msg, res_json
