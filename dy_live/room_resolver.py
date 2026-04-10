import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

import requests


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class LiveRoomInfo:
    """直播间解析结果。"""

    input_value: str
    web_rid: str
    room_id: str
    user_id: str
    user_unique_id: str
    anchor_id: str
    sec_uid: str
    room_status: str
    room_title: str
    ttwid: str
    resolved_url: str

    @property
    def is_live_open(self) -> bool:
        return str(self.room_status) == "2"

    @property
    def status_label(self) -> str:
        return "已开播" if self.is_live_open else "未开播"


class LiveRoomResolver:
    """直播间链接解析器。"""

    def __init__(self, timeout: int = 10, user_agent: str = DEFAULT_USER_AGENT):
        self.timeout = timeout
        self.user_agent = user_agent
        self.session = requests.Session()

    @staticmethod
    def extract_v_douyin_link(text: str) -> Optional[str]:
        match = re.search(r"(https://v\.douyin\.com/[A-Za-z0-9_]+/?[^\s]*)", text or "")
        return match.group(1) if match else None

    @staticmethod
    def _decode_escaped_text(text: str) -> str:
        if not text:
            return ""
        try:
            return json.loads(f'"{text}"')
        except Exception:
            return text

    @staticmethod
    def _safe_encode_url(url: str) -> str:
        parsed = urlparse(url)
        safe_path = quote(
            parsed.path
            + (f"?{parsed.query}" if parsed.query else "")
            + (f"#{parsed.fragment}" if parsed.fragment else "")
        )
        return urlunparse((parsed.scheme, parsed.netloc, safe_path, "", "", ""))

    def resolve_redirect(self, url: str) -> str:
        encoded_url = self._safe_encode_url(url)
        response = self.session.get(
            encoded_url,
            headers={"User-Agent": self.user_agent, "Referer": "https://www.douyin.com/"},
            timeout=self.timeout,
            allow_redirects=True,
        )

        final_url = response.url.rstrip("/")
        if "live.douyin.com/" in final_url:
            return final_url

        html = response.text
        matches = re.findall(r'\\"?webRid\\"?:\\"?([0-9A-Za-z_.-]+)\\"?', html)
        for rid in matches:
            if rid:
                return f"https://live.douyin.com/{rid}"

        raise ValueError("短链解析失败")

    def normalize_live_url(self, raw_text: str) -> str:
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("直播间参数不能为空")

        short_link = self.extract_v_douyin_link(text)
        if short_link:
            return self.resolve_redirect(short_link)

        if text.startswith("https://live.douyin.com/"):
            return text.rstrip("/")

        if re.fullmatch(r"[A-Za-z0-9_.-]+", text):
            return f"https://live.douyin.com/{text}"

        raise ValueError("不支持的直播间格式")

    def fetch_room_info(self, live_short_id: str, cookie_str: str = "") -> LiveRoomInfo:
        url = f"https://live.douyin.com/{live_short_id}"
        headers = {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://live.douyin.com/?from_nav=1",
            "upgrade-insecure-requests": "1",
            "user-agent": self.user_agent,
        }
        if cookie_str:
            headers["cookie"] = cookie_str

        response = self.session.get(url, headers=headers, timeout=self.timeout)
        html = response.text
        ttwid = response.cookies.get("ttwid", "")
        resolved_url = response.url.rstrip("/")
        web_rid = resolved_url.split("/")[-1] if "live.douyin.com/" in resolved_url else str(live_short_id)

        room_id = self._must_match(r'\\"roomId\\":\\"(\d+)\\"', html, "room_id")
        user_unique_id = self._must_match(r'\\"user_unique_id\\":\\"(\d+)\\"', html, "user_unique_id")
        anchor_id = self._must_match(r'\\"anchor\\":\{\\"id_str\\":\\"(\d+)\\"', html, "anchor_id")
        sec_uid = self._must_match(r'\\"sec_uid\\":\\"(.*?)\\"', html, "sec_uid")
        room_match = re.search(
            r'\\"roomInfo\\":\{\\"room\\":\{\\"id_str\\":\\".*?\\",\\"status\\":(.*?),'
            r'\\"status_str\\":\\".*?\\",\\"title\\":\\"(.*?)\\"',
            html,
        )
        if not room_match:
            raise RuntimeError("直播间页面解析失败，未找到 roomInfo")

        room_status = room_match.group(1)
        room_title = self._decode_escaped_text(room_match.group(2))

        return LiveRoomInfo(
            input_value=url,
            web_rid=web_rid,
            room_id=room_id,
            user_id=user_unique_id,
            user_unique_id=user_unique_id,
            anchor_id=anchor_id,
            sec_uid=sec_uid,
            room_status=room_status,
            room_title=room_title,
            ttwid=ttwid,
            resolved_url=resolved_url,
        )

    def resolve(self, raw_text: str, cookie_str: str = "") -> LiveRoomInfo:
        url = self.normalize_live_url(raw_text)
        live_short_id = url.rstrip("/").split("/")[-1]
        info = self.fetch_room_info(live_short_id, cookie_str=cookie_str)
        info.input_value = raw_text.strip()
        info.resolved_url = url
        return info

    @staticmethod
    def _must_match(pattern: str, text: str, field_name: str) -> str:
        match = re.search(pattern, text)
        if not match:
            raise RuntimeError(f"直播间页面解析失败，未找到 {field_name}")
        return match.group(1)
