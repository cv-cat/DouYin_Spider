"""全部 Pydantic 请求/响应模型。"""
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- 通用 ----------
class Ok(BaseModel):
    ok: bool = True
    msg: str = ""


class Err(BaseModel):
    detail: str


# ---------- 账号 ----------
class AccountOut(BaseModel):
    id: int
    label: str
    has_pm_credential: bool
    created_at: str
    last_used_at: Optional[str] = None
    status: str = "unknown"
    uid: Optional[int] = None
    nickname: Optional[str] = None


class CookieLoginIn(BaseModel):
    cookies: str
    label: str = "手动粘贴"
    extract_credential: bool = True  # 是否 headless 提取私信签名凭证


class AccountPatchIn(BaseModel):
    label: Optional[str] = None


class QrStartOut(BaseModel):
    temp_id: str
    qr_image: str  # data URL
    token: str


class QrPollOut(BaseModel):
    status: str  # new / scanned / confirmed / expired / error
    detail: str = ""
    account_id: Optional[int] = None


# ---------- 采集 ----------
class WorkInfoOut(BaseModel):
    work_id: str
    work_url: str
    work_type: str
    title: str
    digg_count: int
    comment_count: int
    collect_count: int
    share_count: int
    nickname: str
    user_url: str
    raw: dict[str, Any]


class UserWorksIn(BaseModel):
    user_url: str
    save_choice: str = "all"  # all/media/media-video/media-image/excel
    excel_name: str = ""


class CrawlFollowIn(BaseModel):
    user_id: str
    sec_id: str
    num: int = 20


class CrawlFavoriteIn(BaseModel):
    sec_id: str
    max_cursor: str = "0"
    num: str = "18"


class RankIn(BaseModel):
    room_id: str
    anchor_id: str
    sec_anchor_id: str


# ---------- 搜索 ----------
class SearchWorkIn(BaseModel):
    query: str
    num: int = 20
    sort_type: str = "0"
    publish_time: str = "0"
    filter_duration: str = ""
    search_range: str = "0"
    content_type: str = "0"
    save_choice: str = ""  # 可选:保存结果
    excel_name: str = ""


class SearchUserIn(BaseModel):
    query: str
    num: int = 20


class SearchLiveIn(BaseModel):
    query: str
    num: int = 20


# ---------- 直播 ----------
class LiveStartIn(BaseModel):
    room_id: str  # 直播间号(live_id)


class LiveDiggIn(BaseModel):
    room_id: str
    count: str = "1"


class LiveSendIn(BaseModel):
    room_id: str
    content: str


# ---------- 私信 ----------
class ConversationIn(BaseModel):
    to_user_id: Optional[int] = None
    user_url: Optional[str] = None  # 二选一;有 url 则先转 uid


class SendMsgIn(BaseModel):
    to_user_id: Optional[int] = None
    user_url: Optional[str] = None
    content: str
    # 复用已有会话(可选,避免每次都 create)
    conversation_id: Optional[str] = None
    conversation_short_id: Optional[int] = None
    ticket: Optional[str] = None


class SendMsgOut(BaseModel):
    success: bool
    conversation_id: Optional[str] = None
    conversation_short_id: Optional[int] = None
    ticket: Optional[str] = None


# ---------- 互动 ----------
class DiggIn(BaseModel):
    aweme_id: str
    digg_type: str = "1"  # 1 点赞 0 取消


class CommentIn(BaseModel):
    aweme_id: str
    content: str
    reply_id: str = ""


class CollectIn(BaseModel):
    aweme_id: str
    action: str = "1"


class CollectMoveIn(BaseModel):
    aweme_id: str
    collect_name: str
    collect_id: str


# ---------- 任务 ----------
class TaskOut(BaseModel):
    id: str
    kind: str
    status: str  # pending/running/done/failed/cancelled
    progress: float = 0.0
    result: Any = None
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


# ---------- 下载 ----------
class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int = 0
    has_children: bool = False
    children: list["FileNode"] = Field(default_factory=list)


FileNode.model_rebuild()
