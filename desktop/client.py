from __future__ import annotations

import os
import re
import threading
import webbrowser
from dataclasses import dataclass
from queue import Empty, SimpleQueue
import sys
from typing import Any, Callable, Iterable

_CTK_IMPORT_ERROR: BaseException | None = None
try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox, ttk

    ctk.set_appearance_mode("System")
    _theme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_theme.json")
    try:
        ctk.set_default_color_theme(_theme_path)
    except Exception:
        ctk.set_default_color_theme("blue")
except (ModuleNotFoundError, ImportError) as exc:
    _CTK_IMPORT_ERROR = exc

    class _MissingCtk:
        class CTk:
            pass
        class CTkFrame:
            pass
        class CTkButton:
            pass
        class CTkLabel:
            pass
        class CTkEntry:
            pass
        class CTkTextbox:
            pass
        class CTkScrollbar:
            pass
        class CTkScrollableFrame:
            pass

        class CTkSwitch:
            pass

        class CTkFont:
            def __init__(self, **kw): pass

        @staticmethod
        def set_appearance_mode(m): pass

        @staticmethod
        def set_default_color_theme(t): pass

    class _MissingTk:
        class TclError(Exception):
            pass

        class Tk:
            pass

        class StringVar:
            pass

    class _MissingTtk:
        class Treeview:
            pass

        class Frame:
            pass

        class Scrollbar:
            pass

        class Style:
            pass

    class _MissingMessagebox:
        @staticmethod
        def showerror(title: str, message: str) -> None:
            raise RuntimeError(f"{title}: {message}") from _CTK_IMPORT_ERROR

        @staticmethod
        def showwarning(title: str, message: str) -> None:
            raise RuntimeError(f"{title}: {message}") from _CTK_IMPORT_ERROR

        @staticmethod
        def showinfo(title: str, message: str) -> None:
            raise RuntimeError(f"{title}: {message}") from _CTK_IMPORT_ERROR

        @staticmethod
        def askyesno(title: str, message: str) -> bool:
            raise RuntimeError(f"{title}: {message}") from _CTK_IMPORT_ERROR

    ctk = _MissingCtk()
    tk = _MissingTk()
    ttk = _MissingTtk()
    messagebox = _MissingMessagebox()

_NAV_BG = "#241D17"
_NAV_ACTIVE = "#D97757"
_NAV_HOVER = "#3A2E24"
_NAV_FG = "#C9BBA9"
_NAV_ACTIVE_FG = "#FFFFFF"


@dataclass
class DesktopServices:
    agent: Any
    session_service: Any | None = None
    live_service: Any | None = None


class AgentDesktopApp(ctk.CTk):
    NAV_ITEMS = (
        ("视频采集", "video"),
        ("评论监控", "comments"),
        ("直播监控", "live"),
        ("群聊监控", "groups"),
        ("私信功能", "private"),
    )

    def __init__(self, services: DesktopServices):
        if _CTK_IMPORT_ERROR is not None:
            raise RuntimeError(
                "customtkinter 未安装，无法启动桌面客户端。\n"
                "请运行: pip install customtkinter"
            ) from _CTK_IMPORT_ERROR
        super().__init__()
        self.services = services
        self.title("两把刷子获客")
        self.geometry("1280x780")
        self.minsize(1100, 680)

        self._page_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._status_var = tk.StringVar(value="就绪")
        self._active_page: str | None = None
        self._table_sigs: dict[int, int] = {}
        self._sync_signal: SimpleQueue = SimpleQueue()
        self._tick_ms = 300
        self._poll_every = 5  # 每 ~1.5s 兜底全量刷新一次
        self._poll_counter = 0
        self._poll_job: str | None = None
        self._closing = False

        self._configure_treeview_style()
        self._build_layout()
        self.show_page("video")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_live_sync()

    @property
    def agent(self) -> Any:
        return self.services.agent

    def _configure_treeview_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Treeview",
            rowheight=28,
            font=("Arial", 10),
            background="#2A231D",
            fieldbackground="#2A231D",
            foreground="#E8DFD3",
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#D97757")],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            "Treeview.Heading",
            font=("Arial", 10, "bold"),
            background="#241D17",
            foreground="#C9BBA9",
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", "#3A2E24")])

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        nav = ctk.CTkFrame(self, fg_color=_NAV_BG, corner_radius=0, width=212)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_propagate(False)
        nav.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            nav,
            text="两把刷子\n获客",
            text_color="#F5EFE7",
            font=ctk.CTkFont(size=22, weight="bold"),
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(28, 4))
        ctk.CTkLabel(
            nav,
            text="桌面客户端",
            text_color="#B5A48F",
            font=ctk.CTkFont(size=10),
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 20))

        for idx, (label, key) in enumerate(self.NAV_ITEMS):
            btn = ctk.CTkButton(
                nav,
                text=label,
                anchor="w",
                fg_color="transparent",
                text_color=_NAV_FG,
                hover_color=_NAV_HOVER,
                font=ctk.CTkFont(size=12),
                corner_radius=6,
                height=40,
                command=lambda page_key=key: self.show_page(page_key),
            )
            btn.grid(row=idx + 2, column=0, sticky="ew", padx=10, pady=2)
            self._page_buttons[key] = btn

        login_btn = ctk.CTkButton(
            nav,
            text="🔑 网页登录",
            anchor="w",
            fg_color=_NAV_ACTIVE,
            text_color=_NAV_ACTIVE_FG,
            hover_color="#C2613F",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            height=40,
            command=self._browser_login,
        )
        login_btn.grid(row=len(self.NAV_ITEMS) + 3, column=0, sticky="ew", padx=10, pady=(18, 4))

        update_btn = ctk.CTkButton(
            nav,
            text="🔄 检查更新",
            anchor="w",
            fg_color="transparent",
            text_color=_NAV_FG,
            hover_color=_NAV_HOVER,
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            height=32,
            command=self._check_update,
        )
        update_btn.grid(row=len(self.NAV_ITEMS) + 4, column=0, sticky="ew", padx=10, pady=(2, 4))

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        stack = ctk.CTkFrame(shell, fg_color="transparent")
        stack.grid(row=0, column=0, sticky="nsew")
        stack.grid_rowconfigure(0, weight=1)
        stack.grid_columnconfigure(0, weight=1)

        self._pages = {
            "video": self._build_video_page(stack),
            "comments": self._build_comments_page(stack),
            "live": self._build_live_page(stack),
            "groups": self._build_groups_page(stack),
            "private": self._build_private_page(stack),
        }
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(shell, textvariable=self._status_var, anchor="w", text="").grid(
            row=1, column=0, sticky="ew", pady=(8, 0)
        )

    def show_page(self, key: str) -> None:
        self._active_page = key
        self._pages[key].tkraise()
        for page_key, btn in self._page_buttons.items():
            if page_key == key:
                btn.configure(fg_color=_NAV_ACTIVE, text_color=_NAV_ACTIVE_FG)
            else:
                btn.configure(fg_color="transparent", text_color=_NAV_FG)
        refresh = getattr(self, f"_refresh_{key}", None)
        if callable(refresh):
            refresh()

    def _build_video_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = self._page(parent, "视频采集", "按关键词采集作品，结果统一进入服务层落库。")
        main = self._content_grid(page)
        left = self._panel(main, "采集结果", row=0, column=0)
        right = self._panel(main, "采集配置", row=0, column=1, width=350)

        toolbar = self._toolbar(left)
        self._button(toolbar, "开始", lambda: self._run_agent_action("queue_video_collect", before=self._video_config_values))
        self._button(toolbar, "停止", lambda: self._run_agent_action("stop_video_collect"))
        self._button(toolbar, "清空", lambda: self._confirm_action("清空视频采集结果？", "clear_videos", refresh=self._refresh_video))
        self._button(toolbar, "导出", lambda: self._export_action("export_videos"))
        self._button(toolbar, "刷新", self._refresh_video)
        self._button(toolbar, "→ 评论监控", self._send_videos_to_comments)

        self.video_table = self._table(
            left,
            ("id", "关键词", "发布时间", "标题", "昵称", "用户ID", "评论", "粉丝", "视频ID", "链接"),
            (56, 100, 150, 220, 110, 120, 56, 56, 128, 190),
            selectmode="extended",
        )
        defaults = self._safe_call("get_video_config", fallback={})
        self.video_fields = self._form(
            right,
            [
                ("keywords", "关键词"),
                ("collect_count", "采集数量"),
                ("comment_count_min", "最低评论数"),
                ("recent_days", "最近天数"),
                ("sort_type", "排序类型"),
                ("publish_time", "发布时间"),
                ("filter_duration", "视频时长"),
                ("intercept", "过滤拦截"),
            ],
            defaults,
            multiline={"keywords"},
            hints={
                "keywords": "要搜索的关键词；多个用顿号（、）或换行分隔，逐个搜索",
                "collect_count": "每个关键词采集多少个作品；填 0 或留空 = 默认采 20 个",
                "comment_count_min": "只保留评论数 ≥ 此值的作品，筛掉冷门；0 = 不限",
                "recent_days": "只采集最近 N 天发布的作品；0 = 不限时间",
                "sort_type": "0 综合排序　　1 最多点赞　　2 最新发布",
                "publish_time": "0 不限　　1 一天内　　7 一周内　　180 半年内",
                "filter_duration": "留空 不限　　0-1 一分钟内　　1-5 一到五分钟　　5-10000 五分钟以上",
                "intercept": "预留项，当前版本不影响采集，保持默认即可",
            },
        )
        return page

    def _build_comments_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = self._page(parent, "评论监控", "按作品 ID 周期扫描评论，筛选高意向线索。")
        main = self._content_grid(page)
        left = self._panel(main, "评论线索", row=0, column=0)
        right = self._panel(main, "监控配置", row=0, column=1, width=380)

        toolbar = self._toolbar(left)
        self._button(toolbar, "开始监控", lambda: self._run_agent_action("queue_comment_monitor", before=self._comment_config_values))
        self._button(toolbar, "停止监控", lambda: self._run_agent_action("stop_comment_monitor"))
        self._button(toolbar, "清空", lambda: self._confirm_action("清空评论监控结果？", "clear_comments", refresh=self._refresh_comments))
        self._button(toolbar, "导出", self._export_comments_filtered)
        self._button(toolbar, "刷新", self._refresh_comments)
        self._button(toolbar, "→ 私信", self._send_comments_to_private)

        self.comments_table = self._table(
            left,
            ("id", "视频ID", "评论ID", "昵称", "用户ID", "内容", "评级", "分数", "时间"),
            (60, 125, 130, 120, 120, 260, 80, 70, 120),
            selectmode="extended",
        )
        defaults = self._safe_call("get_comment_config", fallback={})
        self.comment_fields = self._form(
            right,
            [
                ("video_ids", "视频 ID（每行一个）"),
                ("monitor_minutes", "时间窗口（分钟）"),
                ("date_from", "起始日期"),
                ("date_to", "结束日期"),
                ("include_keywords", "包含关键词"),
                ("exclude_keywords", "排除关键词"),
                ("only_intent", "仅高意向（S/A 级）"),
                ("fetch_first_level", "仅一级评论"),
                ("auto_to_private", "高意向自动入私信名单"),
                ("page_count", "抓取页数"),
                ("thread_count", "线程数"),
                ("interval_minutes", "轮询间隔（分钟）"),
                ("enterprise_webhook", "企微 Webhook"),
                ("proxy_url", "代理"),
            ],
            defaults,
            multiline={"video_ids", "include_keywords", "exclude_keywords"},
            switches={"only_intent", "fetch_first_level", "auto_to_private"},
            hints={
                "monitor_minutes": "只保留最近 N 分钟内发布的评论；填 0 = 不限时间",
                "date_from": "与结束日期一起填则按日期范围过滤（YYYY-MM-DD，优先于时间窗口）",
                "include_keywords": "评论需至少包含其一；逗号或换行分隔；留空不限",
                "exclude_keywords": "命中任一即丢弃；逗号或换行分隔",
                "only_intent": "开启后只保留高意向 S/A 级评论；关闭可看到全部评论",
                "auto_to_private": "开启后：监控每扫到高意向(S/A)评论，自动把作者加入私信名单（去重）",
            },
            on_change=self._comment_config_values,
        )
        return page

    def _build_live_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = self._page(parent, "直播监控", "导入直播间 ID 或链接后批量监听直播事件。")
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=1, column=0, sticky="nsew")
        top.grid_rowconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)

        rooms = self._panel(top, "直播间列表", row=0, column=0)
        events = self._panel(top, "直播事件", row=0, column=1)

        toolbar = self._toolbar(rooms)
        self._button(toolbar, "导入", self._import_live_rooms)
        self._button(toolbar, "全部开始", lambda: self._run_agent_action("start_all_live_rooms", refresh=self._refresh_live))
        self._button(toolbar, "全部停止", lambda: self._run_agent_action("stop_all_live_rooms", refresh=self._refresh_live))
        self._button(toolbar, "清空", lambda: self._confirm_action("清空直播间和事件？", "clear_live_rooms", refresh=self._refresh_live))
        self._button(toolbar, "刷新", self._refresh_live)

        self.live_table = self._table(rooms, ("id", "直播间ID", "标题", "状态", "在线", "更新时间"), (60, 140, 180, 90, 90, 160))
        self.live_input = self._text(rooms, height=4)
        self.live_input.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.live_input.insert("0.0", "每行一个直播间 ID 或链接")

        self.live_events_table = self._table(events, ("id", "类型", "直播间", "内容", "时间"), (60, 100, 120, 360, 150))
        return page

    def _build_groups_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = self._page(parent, "群聊监控", "复用私信接收通道监听群聊消息，消息落库后可筛选和导出。")
        main = self._content_grid(page)
        left = self._panel(main, "群聊消息", row=0, column=0)
        right = self._panel(main, "监控配置", row=0, column=1, width=350)

        toolbar = self._toolbar(left)
        self._button(toolbar, "开始", lambda: self._run_agent_action("start_group_monitor", before=self._group_config_values, refresh=self._refresh_groups))
        self._button(toolbar, "停止", lambda: self._run_agent_action("stop_group_monitor", refresh=self._refresh_groups))
        self._button(toolbar, "清空", lambda: self._confirm_action("清空群聊消息？", "clear_group_messages", refresh=self._refresh_groups))
        self._button(toolbar, "导出", lambda: self._export_action("export_group_messages"))
        self._button(toolbar, "刷新", self._refresh_groups)

        self.groups_table = self._table(left, ("时间", "群ID", "昵称", "用户ID", "内容", "状态"), (150, 120, 120, 130, 320, 90))
        defaults = self._safe_call("get_group_config", fallback={})
        self.group_fields = self._form(
            right,
            [
                ("group_ids", "群聊 ID"),
                ("include_keywords", "包含关键词"),
                ("exclude_keywords", "排除关键词"),
                ("interval_seconds", "轮询秒数"),
            ],
            defaults,
            multiline={"group_ids", "include_keywords", "exclude_keywords"},
            hints={
                "group_ids": "要监控的群聊 ID；多个用换行分隔",
                "include_keywords": "只保留含这些词的消息；逗号或换行分隔；留空不限",
                "exclude_keywords": "命中任一即丢弃；逗号或换行分隔",
                "interval_seconds": "轮询间隔秒数，越小越实时、越耗资源；默认 1",
            },
        )
        return page

    def _build_private_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = self._page(parent, "私信功能", "导入 UID 后按配置批量发送私信。")
        main = self._content_grid(page)
        left = self._panel(main, "发送目标", row=0, column=0)
        right = self._panel(main, "私信配置", row=0, column=1, width=380)

        toolbar = self._toolbar(left)
        self._button(toolbar, "导入 UID", self._import_private_uids)
        self._button(toolbar, "半自动", self._semi_auto_dm)
        self._button(toolbar, "单个发送", self._auto_send_dm)
        self._button(toolbar, "自动发送", self._start_auto_send_batch)
        self._button(toolbar, "停止", self._stop_auto_send)
        self._send_daemon_btn = ctk.CTkButton(
            toolbar, text="守护", command=self._toggle_send_daemon, height=28, width=72, font=ctk.CTkFont(size=11)
        )
        self._send_daemon_btn.pack(side="left", padx=(0, 5))
        self._button(toolbar, "清空", lambda: self._confirm_action("清空私信发送目标？", "clear_private_targets", refresh=self._refresh_private))
        self._button(toolbar, "刷新", self._refresh_private)

        self.private_table = self._table(
            left,
            ("id", "UID", "昵称", "主页", "评论内容", "评论时间", "评级", "状态", "错误", "创建时间"),
            (46, 120, 100, 240, 210, 125, 55, 70, 150, 140),
        )
        self.private_table.bind("<Double-1>", self._open_private_profile)
        self.private_log = self._text(left, height=5)
        self.private_log.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.private_log.insert("0.0", "📋 发送日志会显示在这里\n")
        self.private_log.configure(state="disabled")

        defaults = self._safe_call("get_private_config", fallback={})
        self.private_fields = self._form(
            right,
            [
                ("message_text", "私信文本"),
                ("send_interval_seconds", "发送间隔秒"),
                ("batch_size", "每批数量"),
                ("batch_pause_minutes", "批次间隔分钟"),
                ("headless_mode", "后台静默发送"),
                ("send_mode", "发送模式"),
                ("proxy_api", "代理 API"),
                ("auto_refresh_minutes", "自动刷新分钟"),
                ("card_payload", "卡片 Payload"),
                ("proxy_url", "代理"),
            ],
            defaults,
            multiline={"message_text", "card_payload"},
            switches={"headless_mode"},
            hints={
                "message_text": "要群发的私信内容（纯文本）",
                "send_interval_seconds": "每条基础间隔秒数；实际会在此值~2倍之间随机，建议 ≥ 30",
                "batch_size": "每发这么多条就长休息一次（分批轮流，防风控）；建议 5-10",
                "batch_pause_minutes": "每批之间长休息的分钟数，模拟真人节奏；建议 ≥ 10",
                "headless_mode": "开启=浏览器后台静默运行（不弹窗口）。注意：无头更易被抖音识别，可能发不出，先小批量测",
                "send_mode": "填 text（卡片 card 模式底层暂未接入）",
                "proxy_api": "动态代理 API 地址，用于切换 IP（可选，留空不用）",
                "auto_refresh_minutes": "每隔 N 分钟自动刷新登录态；默认 60",
                "card_payload": "卡片消息内容（当前仅支持纯文本，可留空）",
                "proxy_url": "固定代理地址（可选，留空不用）",
            },
        )

        cookie_box = ctk.CTkFrame(right, fg_color="transparent")
        cookie_box.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        cookie_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cookie_box, text="Cookie scope", text_color="gray", anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 3))
        self.private_cookie_scope = ctk.CTkEntry(cookie_box)
        self.private_cookie_scope.grid(row=1, column=0, sticky="ew")
        self.private_cookie_scope.insert(0, "douyin")
        ctk.CTkLabel(cookie_box, text="手动 Cookie", text_color="gray", anchor="w").grid(row=2, column=0, sticky="w", pady=(8, 3))
        self.private_cookie_text = self._text(cookie_box, height=3)
        self.private_cookie_text.grid(row=3, column=0, sticky="ew")
        cookie_btns = ctk.CTkFrame(cookie_box, fg_color="transparent")
        cookie_btns.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self._button(cookie_btns, "保存 Cookie", self._save_private_cookie)
        self._button(cookie_btns, "Cookie 状态", self._show_cookie_status)
        return page

    # --- Layout helpers ---

    def _page(self, parent: ctk.CTkFrame, title: str, subtitle: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(head, text=title, font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text=subtitle, text_color="gray", anchor="w").pack(anchor="w", pady=(4, 0))
        return page

    def _content_grid(self, page: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(page, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _panel(self, parent: ctk.CTkFrame, title: str, row: int, column: int, width: int | None = None) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, corner_radius=8)
        panel.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0), pady=0)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        if width:
            panel.configure(width=width)
            panel.grid_propagate(False)
        ctk.CTkLabel(panel, text=title, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 8)
        )
        return panel

    def _toolbar(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="e", padx=(0, 12), pady=(8, 0))
        return toolbar

    def _button(self, parent: ctk.CTkFrame, text: str, command: Callable[[], None]) -> None:
        width = max(64, 16 + 13 * len(text))  # 按文字长度自适应，避免固定 140px 溢出工具栏
        ctk.CTkButton(parent, text=text, command=command, height=28, width=width, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 5))

    def _table(self, parent: ctk.CTkFrame, columns: Iterable[str], widths: Iterable[int], selectmode: str = "browse") -> ttk.Treeview:
        frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=tuple(columns), show="headings", selectmode=selectmode)
        for column, width in zip(columns, widths):
            tree.heading(column, text=column)
            tree.column(column, width=width, minwidth=50, anchor="w", stretch=True)
        yscroll = ctk.CTkScrollbar(frame, command=tree.yview)
        xscroll = ctk.CTkScrollbar(frame, orientation="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        return tree

    def _form(
        self,
        parent: ctk.CTkFrame,
        fields: list[tuple[str, str]],
        values: dict[str, Any],
        multiline: set[str] | None = None,
        switches: set[str] | None = None,
        hints: dict[str, str] | None = None,
        on_change=None,
    ) -> dict[str, Any]:
        multiline = multiline or set()
        switches = switches or set()
        hints = hints or {}
        form = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        form.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        form.grid_columnconfigure(0, weight=1)
        widgets: dict[str, Any] = {}
        row = 0
        for key, label in fields:
            ctk.CTkLabel(
                form,
                text=label,
                anchor="w",
                text_color=("#5C4D40", "#D7C9B8"),
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 12, 2))
            row += 1
            if key in hints:
                ctk.CTkLabel(
                    form,
                    text=hints[key],
                    anchor="w",
                    justify="left",
                    text_color=("#9A8C7B", "#9A8C7B"),
                    font=ctk.CTkFont(size=10),
                    wraplength=300,
                ).grid(row=row, column=0, sticky="w", pady=(0, 4))
                row += 1
            if key in switches:
                widget = ctk.CTkSwitch(form, text="启用", onvalue="on", offvalue="", command=on_change)
                if self._checkbox_truthy(values.get(key)):
                    widget.select()
                else:
                    widget.deselect()
                widget.grid(row=row, column=0, sticky="w", pady=(0, 2))
            elif key in multiline:
                widget = ctk.CTkTextbox(form, height=72, wrap="word")
                widget.grid(row=row, column=0, sticky="ew")
                widget.insert("0.0", str(values.get(key, "")))
            else:
                widget = ctk.CTkEntry(form)
                widget.grid(row=row, column=0, sticky="ew")
                widget.insert(0, str(values.get(key, "")))
            widgets[key] = widget
            row += 1
        self._enable_mousewheel(form)
        return widgets

    def _enable_mousewheel(self, scroll_frame) -> None:
        canvas = getattr(scroll_frame, "_parent_canvas", None)
        if canvas is None:
            return

        def _on_wheel(event):
            try:
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            except Exception:
                pass

        def _bind(widget):
            try:
                widget.bind("<MouseWheel>", _on_wheel, add="+")
            except Exception:
                pass
            for child in widget.winfo_children():
                _bind(child)

        _bind(scroll_frame)

    def _text(self, parent: ctk.CTkFrame, height: int) -> ctk.CTkTextbox:
        return ctk.CTkTextbox(parent, height=height * 22, wrap="word")

    def _values(self, fields: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, widget in fields.items():
            if isinstance(widget, ctk.CTkSwitch):
                result[key] = widget.get()  # "on" 或 ""
            elif isinstance(widget, ctk.CTkTextbox):
                result[key] = widget.get("0.0", "end").strip()
            else:
                result[key] = widget.get().strip()
        return result

    @staticmethod
    def _checkbox_truthy(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _video_config_values(self) -> None:
        self.agent.save_video_config(self._values(self.video_fields))

    def _comment_config_values(self) -> None:
        self.agent.save_comment_config(self._values(self.comment_fields))

    def _group_config_values(self) -> None:
        self.agent.save_group_config(self._values(self.group_fields))

    def _private_config_values(self) -> None:
        self.agent.save_private_config(self._values(self.private_fields))

    def _run_agent_action(self, method_name: str, before: Callable[[], None] | None = None, refresh: Callable[[], None] | None = None) -> None:
        try:
            if before:
                before()
        except Exception as exc:
            self._show_error(method_name, exc)
            return

        def worker() -> None:
            try:
                result = getattr(self.agent, method_name)()
                self.after(0, lambda r=result: self._action_done(method_name, r, refresh))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error(method_name, e))

        self._status_var.set(f"执行中：{method_name}")
        threading.Thread(target=worker, daemon=True).start()

    def _confirm_action(self, prompt: str, method_name: str, refresh: Callable[[], None]) -> None:
        if messagebox.askyesno("确认", prompt):
            self._run_agent_action(method_name, refresh=refresh)

    def _export_action(self, method_name: str) -> None:
        try:
            path = getattr(self.agent, method_name)()
        except Exception as exc:
            self._show_error(method_name, exc)
            return
        self._status_var.set(f"已导出：{path}")
        messagebox.showinfo("导出完成", f"文件已导出：\n{path}")

    def _action_done(self, method_name: str, result: Any, refresh: Callable[[], None] | None) -> None:
        self._status_var.set(f"{method_name} 完成：{result}")
        if refresh:
            refresh()

    def _show_error(self, title: str, exc: BaseException) -> None:
        self._status_var.set(f"{title} 失败：{type(exc).__name__}: {exc}")
        messagebox.showerror(title, f"{type(exc).__name__}: {exc}")

    def _safe_call(self, method_name: str, fallback: Any) -> Any:
        try:
            return getattr(self.agent, method_name)()
        except Exception:
            return fallback

    def _fill_table(self, tree: ttk.Treeview, rows: Iterable[Iterable[Any]]) -> None:
        normalized = [tuple("" if value is None else str(value) for value in row) for row in rows]
        signature = hash(tuple(normalized))
        sigs = getattr(self, "_table_sigs", None)
        if sigs is not None and sigs.get(id(tree)) == signature:
            return  # 数据未变化，跳过重建，避免闪烁与丢失选中
        if sigs is not None:
            sigs[id(tree)] = signature
        selection = tree.selection()
        for item in tree.get_children():
            tree.delete(item)
        for row in normalized:
            tree.insert("", "end", values=row)
        if selection:
            existing = set(tree.get_children())
            keep = [item for item in selection if item in existing]
            if keep:
                tree.selection_set(keep)

    # --- 实时同步：事件驱动刷新 + 兜底轮询 ---

    def _start_live_sync(self) -> None:
        broker = getattr(self.services, "broker", None)
        if broker is not None:
            for channel in ("tasks", "events"):
                threading.Thread(
                    target=self._broker_listen, args=(broker, channel), daemon=True
                ).start()
        self._poll_job = self.after(self._tick_ms, self._sync_tick)

    def _broker_listen(self, broker: Any, channel: str) -> None:
        """后台线程：阻塞订阅 broker，只往线程安全队列投信号，不直接碰 UI。"""
        try:
            queue = broker.subscribe(channel)
        except Exception:
            return
        while not self._closing:
            try:
                queue.get()
            except Exception:
                return
            self._sync_signal.put(channel)

    def _sync_tick(self) -> None:
        """主线程定时心跳：有事件信号则立即刷新，否则每 ~1.5s 兜底刷新一次。"""
        if self._closing:
            return
        triggered = False
        try:
            while True:
                self._sync_signal.get_nowait()
                triggered = True
        except Empty:
            pass
        self._poll_counter += 1
        if triggered or self._poll_counter >= self._poll_every:
            self._poll_counter = 0
            self._refresh_active_page()
        try:
            self._poll_job = self.after(self._tick_ms, self._sync_tick)
        except tk.TclError:
            self._poll_job = None

    def _refresh_active_page(self) -> None:
        key = self._active_page
        if not key:
            return
        refresh = getattr(self, f"_refresh_{key}", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    def _on_close(self) -> None:
        self._closing = True
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        self.destroy()

    def _refresh_video(self) -> None:
        rows = self._safe_call("list_videos", fallback=[])
        rows = sorted(rows, key=lambda r: r.get("create_time") or 0, reverse=True)  # 按发布时间，最新在前
        self._fill_table(
            self.video_table,
            (
                (
                    row.get("id"),
                    row.get("keyword"),
                    row.get("create_time_label"),
                    row.get("title"),
                    row.get("nickname"),
                    row.get("user_id"),
                    row.get("comment_count"),
                    row.get("follower_count"),
                    row.get("aweme_id"),
                    row.get("share_url"),
                )
                for row in rows
            ),
        )
        status = self._safe_call("video_status", fallback={})
        self._status_var.set(status.get("label", f"视频采集：{len(rows)} 条"))

    def _split_terms(self, value: Any) -> list[str]:
        return [t.strip() for t in re.split(r"[\n,，、]+", str(value or "")) if t.strip()]

    def _read_widget(self, widget: Any) -> str:
        if widget is None:
            return ""
        if isinstance(widget, ctk.CTkSwitch):
            return widget.get()
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("0.0", "end")
        return widget.get()

    def _comment_visible_rows(self, rows: list) -> list:
        """按评论面板上当前的 包含/排除 关键词即时过滤（不依赖是否已保存）。"""
        fields = getattr(self, "comment_fields", None)
        if not fields:
            return rows
        include = self._split_terms(self._read_widget(fields.get("include_keywords")))
        exclude = self._split_terms(self._read_widget(fields.get("exclude_keywords")))
        if not include and not exclude:
            return rows
        result = []
        for row in rows:
            text = str(row.get("comment_text") or "")
            if include and not any(term in text for term in include):
                continue
            if exclude and any(term in text for term in exclude):
                continue
            result.append(row)
        return result

    def _export_comments_filtered(self) -> None:
        all_rows = self._safe_call("list_comments", fallback=[])
        rows = self._comment_visible_rows(all_rows)
        if not rows:
            messagebox.showinfo("导出", "当前过滤后没有可导出的评论")
            return
        try:
            path = self.agent.export_comments(rows)
        except Exception as exc:
            self._show_error("export_comments", exc)
            return
        self._status_var.set(f"已导出：{path}（{len(rows)} 条）")
        messagebox.showinfo("导出完成", f"已导出 {len(rows)} 条评论：\n{path}")

    def _refresh_comments(self) -> None:
        all_rows = self._safe_call("list_comments", fallback=[])
        all_rows = sorted(all_rows, key=lambda r: r.get("create_time") or 0, reverse=True)  # 最新评论在前
        rows = self._comment_visible_rows(all_rows)
        self._fill_table(
            self.comments_table,
            (
                (
                    row.get("id"),
                    row.get("aweme_id"),
                    row.get("comment_id"),
                    row.get("nickname"),
                    row.get("user_id"),
                    row.get("comment_text"),
                    row.get("grade"),
                    row.get("score"),
                    row.get("comment_time_label"),
                )
                for row in rows
            ),
        )
        status = self._safe_call("comment_status", fallback={})
        if status.get("running"):
            shown = f"显示 {len(rows)}/{len(all_rows)}" if len(rows) != len(all_rows) else f"{len(rows)} 条"
            self._status_var.set(f"{status.get('label', '监控中')} · {shown}")
        elif len(rows) != len(all_rows):
            self._status_var.set(f"评论监控：显示 {len(rows)} / 共 {len(all_rows)} 条（已按关键词过滤）")
        else:
            self._status_var.set(status.get("label", f"评论监控：{len(rows)} 条"))

    def _refresh_live(self) -> None:
        rooms = self._safe_call("list_live_rooms", fallback=[])
        self._fill_table(
            self.live_table,
            (
                (
                    row.get("id"),
                    row.get("live_id"),
                    row.get("title"),
                    row.get("status"),
                    row.get("online_text"),
                    row.get("updated_at"),
                )
                for row in rooms
            ),
        )
        events = self._safe_call("list_live_events", fallback=[])
        self._fill_table(
            self.live_events_table,
            (
                (
                    row.get("id"),
                    row.get("event_label") or row.get("event_type"),
                    row.get("room_id"),
                    row.get("content") or row.get("payload"),
                    row.get("created_at"),
                )
                for row in events
            ),
        )
        self._status_var.set(f"直播监控：{len(rooms)} 个直播间，{len(events)} 条事件")

    def _refresh_groups(self) -> None:
        rows = self._safe_call("list_group_messages", fallback=[])
        self._fill_table(
            self.groups_table,
            (
                (row.get("created_at"), row.get("group_id"), row.get("nickname"), row.get("user_id"), row.get("content"), row.get("status"))
                for row in rows
            ),
        )
        status = self._safe_call("group_status", fallback={})
        self._status_var.set(status.get("label", f"群聊消息：{len(rows)} 条"))

    def _refresh_private(self) -> None:
        rows = self._safe_call("list_private_targets", fallback=[])
        self._fill_table(
            self.private_table,
            (
                (
                    row.get("id"),
                    row.get("uid"),
                    row.get("nickname"),
                    row.get("profile_url"),
                    row.get("comment_text"),
                    row.get("comment_time_label"),
                    row.get("grade"),
                    row.get("status"),
                    row.get("error_message"),
                    row.get("created_at"),
                )
                for row in rows
            ),
        )
        status = self._safe_call("private_status", fallback={})
        self._status_var.set(status.get("label", f"私信目标：{len(rows)} 个"))

    def _collect_video_ids(self, only_selected: bool) -> list[str]:
        tree = self.video_table
        items = tree.selection() if only_selected else ()
        if not items:  # 未选中则取全部
            items = tree.get_children()
        ids: list[str] = []
        for item in items:
            values = tree.item(item, "values")
            if len(values) > 8:  # 列顺序: id,关键词,发布时间,标题,昵称,用户ID,评论,粉丝,视频ID,链接
                vid = str(values[8]).strip()
                if vid and vid not in ids:
                    ids.append(vid)
        return ids

    def _send_videos_to_comments(self) -> None:
        ids = self._collect_video_ids(only_selected=True)
        if not ids:
            messagebox.showinfo("转评论监控", "暂无视频ID，请先在视频采集页采集作品。")
            return
        box = self.comment_fields["video_ids"]
        existing = [line.strip() for line in box.get("0.0", "end").splitlines() if line.strip()]
        merged = list(dict.fromkeys(existing + ids))  # 合并去重，保留原有
        box.delete("0.0", "end")
        box.insert("0.0", "\n".join(merged))
        try:
            self._comment_config_values()  # 持久化到评论配置
        except Exception:
            pass
        self.show_page("comments")
        added = len(merged) - len(existing)
        self._status_var.set(f"已导入 {len(ids)} 个视频ID到评论监控（新增 {added}，共 {len(merged)}）")

    def _open_private_profile(self, event: Any = None) -> None:
        tree = self.private_table
        item = tree.focus() or (tree.selection()[0] if tree.selection() else None)
        if not item:
            return
        values = tree.item(item, "values")
        url = str(values[3]).strip() if len(values) > 3 else ""  # 列顺序: id,UID,昵称,主页,...
        if url.startswith("http"):
            try:
                webbrowser.open(url)
                self._status_var.set(f"已在浏览器打开主页：{url[:48]}…")
            except Exception as exc:
                self._show_error("打开主页", exc)
        else:
            self._status_var.set("该行没有可用的主页链接")

    def _start_auto_send_batch(self) -> None:
        rows = self._safe_call("list_private_targets", fallback=[])
        targets = [
            {"id": r.get("id"), "sec_uid": r.get("sec_uid"), "nickname": r.get("nickname")}
            for r in rows
            if r.get("status") == "pending" and r.get("sec_uid")
        ]
        if not targets:
            messagebox.showinfo(
                "批量自动发送",
                "没有「待发送(pending) 且有主页」的目标。\n（手动导入的纯 UID 没有主页 sec_uid，无法定位，不会被发送）",
            )
            return
        message = self._values(self.private_fields).get("message_text", "").strip()
        if not message:
            messagebox.showinfo("批量自动发送", "请先在右侧「私信文本」里填写内容。")
            return
        vals = self._values(self.private_fields)
        try:
            interval = int(float(vals.get("send_interval_seconds") or "15"))
        except Exception:
            interval = 15
        interval = max(interval, 1)

        def _as_int(key, default):
            try:
                return max(int(float(vals.get(key) or str(default))), 0)
            except Exception:
                return default

        batch_size = _as_int("batch_size", 5)
        batch_pause = _as_int("batch_pause_minutes", 10)
        headless = vals.get("headless_mode") == "on"
        login = getattr(self.services, "login", None)
        if login is None or not hasattr(login, "send_dm_batch"):
            messagebox.showwarning("批量自动发送", "登录服务不可用。")
            return
        mode_text = "后台静默（无窗口，更易被风控识别）" if headless else "有头（弹出可见浏览器）"
        cadence = (
            f"每条间隔 {interval}~{interval * 2} 秒（随机）"
            + (f"，每 {batch_size} 条休息 {batch_pause} 分钟" if batch_size > 0 else "")
        )
        if not messagebox.askyesno(
            "批量自动发送（实验功能）",
            f"将用浏览器分批轮流给 {len(targets)} 人自动发送私信。\n"
            f"模式：{mode_text}\n节奏：{cadence}\n\n"
            "⚠️ 真实发送、有封号风险！\n建议：先小批量、间隔 ≥ 30 秒、话术写得自然。\n\n确定开始？",
        ):
            return
        self._dm_stop = threading.Event()
        hint = "后台静默运行中" if headless else "请勿关闭弹出的浏览器"
        self._status_var.set(f"批量自动发送中：0/{len(targets)}（{hint}）……")

        def worker() -> None:
            if not self._ensure_browser_ready():
                return
            try:
                result = login.send_dm_batch(
                    targets, message, interval_seconds=interval,
                    batch_size=batch_size, batch_pause_minutes=batch_pause,
                    headless=headless, should_stop=lambda: self._dm_stop.is_set(),
                )
                self.after(0, lambda r=result: self._batch_send_done(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("批量自动发送", e))

        threading.Thread(target=worker, daemon=True).start()

    def _stop_auto_send(self) -> None:
        ev = getattr(self, "_dm_stop", None)
        if ev is not None:
            ev.set()
            self._status_var.set("已请求停止：当前这条发完后停止。")
        else:
            self._status_var.set("当前没有正在进行的批量发送。")

    def _batch_send_done(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        sent = result.get("sent", 0)
        failed = result.get("failed", 0)
        total = result.get("total", 0)
        self._status_var.set(f"批量发送结束：成功 {sent}，失败 {failed}，共 {total}")
        self._log_private(f"———— 批量结束：成功 {sent} / 失败 {failed} / 共 {total} ————")
        for r in (result.get("results") or []):
            if r.get("ok"):
                self._log_private(f"✅ {r.get('nickname', '')} 发送成功")
            else:
                self._log_private(f"❌ {r.get('nickname', '')} 失败 @ {r.get('step', '')}")
        self._refresh_private()

    def _log_private(self, message: str) -> None:
        log = getattr(self, "private_log", None)
        if log is None:
            return
        try:
            log.configure(state="normal")
            log.insert("end", message.rstrip() + "\n")
            log.see("end")
            log.configure(state="disabled")
        except Exception:
            pass

    def _toggle_send_daemon(self) -> None:
        if getattr(self, "_send_daemon_running", False):
            ev = getattr(self, "_send_daemon_stop", None)
            if ev:
                ev.set()
            self._send_daemon_running = False
            self._send_daemon_btn.configure(text="守护")
            self._status_var.set("自动发送守护已停止")
            self._log_private("⏹ 自动发送守护已停止")
            return
        vals = self._values(self.private_fields)
        message = vals.get("message_text", "").strip()
        if not message:
            messagebox.showinfo("守护", "请先在右侧「私信文本」里填写内容。")
            return
        login = getattr(self.services, "login", None)
        if login is None or not hasattr(login, "send_dm_batch"):
            messagebox.showwarning("守护", "登录服务不可用。")
            return
        if not messagebox.askyesno(
            "自动发送守护（最高风险）",
            "开启后：后台持续盯着私信名单，一发现新的待发送(pending)就自动发出。\n"
            "配合『评论监控 + 高意向自动入名单』= 全自动无人值守获客。\n\n"
            "⚠️ 封号风险最高！务必先小批量验证稳定后，再长时间挂机。\n\n确定开启？",
        ):
            return

        def _as_int(key, default):
            try:
                return max(int(float(vals.get(key) or str(default))), 0)
            except Exception:
                return default

        cfg = {
            "message": message,
            "interval": max(_as_int("send_interval_seconds", 15), 1),
            "batch_size": _as_int("batch_size", 5),
            "batch_pause": _as_int("batch_pause_minutes", 10),
            "headless": vals.get("headless_mode") == "on",
        }
        self._send_daemon_stop = threading.Event()
        self._send_daemon_running = True
        self._send_daemon_btn.configure(text="停止守护")
        self._status_var.set("🟢 自动发送守护已开启")
        self._log_private("🟢 自动发送守护已开启，每 30 秒盯一次名单……")
        threading.Thread(target=self._send_daemon_loop, args=(cfg,), daemon=True).start()

    def _send_daemon_loop(self, cfg: dict) -> None:
        stop = self._send_daemon_stop
        login = getattr(self.services, "login", None)
        if login is None:
            return
        try:
            from desktop.bootstrap import ensure_chromium
            ensure_chromium()
        except Exception:
            pass
        while not stop.is_set():
            rows = self._safe_call("list_private_targets", fallback=[])
            targets = [
                {"id": r.get("id"), "sec_uid": r.get("sec_uid"), "nickname": r.get("nickname")}
                for r in rows
                if r.get("status") == "pending" and r.get("sec_uid")
            ]
            if targets:
                self.after(0, lambda n=len(targets): self._log_private(f"🔔 守护发现 {n} 个待发送，开始发送…"))
                try:
                    result = login.send_dm_batch(
                        targets, cfg["message"], interval_seconds=cfg["interval"],
                        batch_size=cfg["batch_size"], batch_pause_minutes=cfg["batch_pause"],
                        headless=cfg["headless"], should_stop=lambda: stop.is_set(),
                    )
                    self.after(0, lambda r=result: self._daemon_round_logged(r))
                except Exception as exc:
                    self.after(0, lambda e=exc: self._log_private(f"守护发送异常：{type(e).__name__}: {e}"))
            if stop.wait(30):  # 每 30 秒扫一次名单
                break

    def _daemon_round_logged(self, result: Any) -> None:
        if isinstance(result, dict):
            self._log_private(f"守护本轮：成功 {result.get('sent', 0)} / 失败 {result.get('failed', 0)}")
        self._refresh_private()

    def _auto_send_dm(self) -> None:
        tree = self.private_table
        item = tree.focus() or (tree.selection()[0] if tree.selection() else None)
        if not item:
            messagebox.showinfo("自动发送", "请先选中一个人（强烈建议先用你自己的小号测试）。")
            return
        values = tree.item(item, "values")
        profile = str(values[3]).strip() if len(values) > 3 else ""
        if "/user/" not in profile:
            messagebox.showinfo("自动发送", "该行没有主页链接（缺 sec_uid），无法定位用户。")
            return
        sec_uid = profile.rsplit("/user/", 1)[-1]
        nickname = values[2] if len(values) > 2 else ""
        vals = self._values(self.private_fields)
        message = vals.get("message_text", "").strip()
        if not message:
            messagebox.showinfo("自动发送", "请先在右侧「私信文本」里填写要发送的内容。")
            return
        headless = vals.get("headless_mode") == "on"
        login = getattr(self.services, "login", None)
        if login is None or not hasattr(login, "send_dm_browser"):
            messagebox.showwarning("自动发送", "登录服务不可用。")
            return
        if not messagebox.askyesno(
            "单个发送",
            f"将用浏览器给「{nickname}」发送一条私信：\n\n{message[:60]}\n\n"
            "⚠️ 真实发送、有封号风险。\n第一次请务必先用你自己的小号测试。\n\n确定继续？",
        ):
            return
        self._status_var.set(f"正在自动私信「{nickname}」（浏览器操作中）……")

        def worker() -> None:
            if not self._ensure_browser_ready():
                return
            try:
                result = login.send_dm_browser(sec_uid, message, headless=headless)
                self.after(0, lambda r=result: self._auto_send_done(nickname, r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("自动发送", e))

        threading.Thread(target=worker, daemon=True).start()

    def _auto_send_done(self, nickname: str, result: Any) -> None:
        if isinstance(result, dict) and result.get("ok"):
            self._status_var.set(f"✅ 已自动私信「{nickname}」")
            self._log_private(f"✅ 「{nickname}」发送成功")
        else:
            step = result.get("step", "?") if isinstance(result, dict) else "?"
            detail = result.get("detail", "") if isinstance(result, dict) else str(result)
            self._status_var.set(f"❌ 「{nickname}」发送失败：{step}")
            self._log_private(f"❌ 「{nickname}」失败 @ {step}：{str(detail)[:80]}")

    def _semi_auto_dm(self) -> None:
        tree = self.private_table
        item = tree.focus() or (tree.selection()[0] if tree.selection() else None)
        if not item:
            messagebox.showinfo("半自动私信", "请先在列表里选中一个人。")
            return
        values = tree.item(item, "values")
        profile = str(values[3]).strip() if len(values) > 3 else ""  # 主页列含 /user/{sec_uid}
        if "/user/" not in profile:
            messagebox.showinfo("半自动私信", "该行没有主页链接（缺 sec_uid），无法定位用户。")
            return
        sec_uid = profile.rsplit("/user/", 1)[-1]
        nickname = values[2] if len(values) > 2 else ""
        message = self._values(self.private_fields).get("message_text", "").strip()
        login = getattr(self.services, "login", None)
        if login is None or not hasattr(login, "open_compose_browser"):
            messagebox.showwarning("半自动私信", "登录服务不可用。")
            return
        if message:  # 话术放进剪贴板，方便在私信框粘贴
            try:
                self.clipboard_clear()
                self.clipboard_append(message)
            except Exception:
                pass
        self._status_var.set(f"正在打开「{nickname}」的主页……")

        def worker() -> None:
            if not self._ensure_browser_ready():
                return
            try:
                login.open_compose_browser(sec_uid)
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("半自动私信", e))

        threading.Thread(target=worker, daemon=True).start()
        messagebox.showinfo(
            "半自动私信",
            f"已为「{nickname}」打开登录态浏览器主页。\n\n"
            + ("✅ 话术已复制到剪贴板。\n\n" if message else "（私信文本为空，可先在右侧「私信文本」里填写）\n\n")
            + "请在浏览器里：点对方主页的「私信」按钮 → 在输入框粘贴（Cmd/Ctrl+V）→ 检查无误后手动发送。",
        )

    def _send_comments_to_private(self) -> None:
        tree = self.comments_table
        items = tree.selection() or tree.get_children()  # 未选则取当前列表（已按关键词过滤）
        uids: list[str] = []
        for item in items:
            values = tree.item(item, "values")
            if len(values) > 4:  # 列顺序: id,视频ID,评论ID,昵称,用户ID,内容,...
                uid = str(values[4]).strip()
                if uid and uid not in uids:
                    uids.append(uid)
        if not uids:
            messagebox.showinfo("转私信", "暂无用户ID，请先在评论监控抓取评论。")
            return
        try:
            result = self.agent.import_private_uids("\n".join(uids))
        except Exception as exc:
            self._show_error("转私信", exc)
            return
        imported = result.get("imported_count", 0) if isinstance(result, dict) else result
        self.show_page("private")
        self._status_var.set(f"已选 {len(uids)} 人 → 私信列表（新增 {imported}，重复自动跳过）")

    def _import_live_rooms(self) -> None:
        live_text = self.live_input.get("0.0", "end").strip()
        try:
            result = self.agent.import_live_rooms(live_text)
        except Exception as exc:
            self._show_error("导入直播间", exc)
            return
        self._status_var.set(f"导入直播间完成：{result}")
        self._refresh_live()

    def _import_private_uids(self) -> None:
        dialog = ctk.CTkInputDialog(text="粘贴要私信的 UID（多个用逗号 / 空格分隔）：", title="导入 UID")
        uid_text = dialog.get_input()
        if not uid_text:
            return
        try:
            result = self.agent.import_private_uids(uid_text)
        except Exception as exc:
            self._show_error("导入 UID", exc)
            return
        imported = result.get("imported_count", 0) if isinstance(result, dict) else result
        self._status_var.set(f"导入 UID 完成：新增 {imported}")
        self._log_private(f"导入 UID：新增 {imported}")
        self._refresh_private()

    def _show_cookie_status(self) -> None:
        session_service = self.services.session_service
        if session_service is None:
            messagebox.showwarning("Cookie 状态", "未注入 session_service")
            return
        lines = []
        for scope in ("douyin", "live", "im", "private"):
            try:
                auth = session_service.load_auth(scope)
            except Exception as exc:
                lines.append(f"{scope}: 读取失败 ({type(exc).__name__}: {exc})")
            else:
                lines.append(f"{scope}: {'已配置' if auth is not None else '未配置'}")
        messagebox.showinfo("Cookie 状态", "\n".join(lines))

    def _save_private_cookie(self) -> None:
        session_service = self.services.session_service
        if session_service is None:
            messagebox.showwarning("Cookie", "未注入 session_service")
            return
        scope = self.private_cookie_scope.get().strip() or "douyin"
        cookie = self.private_cookie_text.get("0.0", "end").strip()
        if not cookie:
            messagebox.showwarning("Cookie", "Cookie 内容为空")
            return
        try:
            session_service.save_cookie(scope, cookie, status="desktop-manual")
        except Exception as exc:
            self._show_error("保存 Cookie", exc)
            return
        self._status_var.set(f"Cookie 已保存：{scope}")
        messagebox.showinfo("Cookie", f"已保存 {scope} Cookie")

    def _test_private_connection(self) -> None:
        def worker() -> None:
            try:
                result = self.agent.test_private_connection()
                self.after(0, lambda r=result: self._private_test_done(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_private_test_error(e))

        self._status_var.set("正在测试私信连接……")
        threading.Thread(target=worker, daemon=True).start()

    def _private_test_done(self, result: Any) -> None:
        uid = result.get("uid") if isinstance(result, dict) else ""
        self._status_var.set(f"✅ 私信连接正常（已与 {uid} 建立会话，未发送消息）")
        messagebox.showinfo(
            "测试连接",
            "✅ 私信链路正常！\n\n"
            "· douyin cookie 有效\n"
            "· 私信接口可调通\n\n"
            f"已与用户 {uid} 建立会话通道，但未发送任何消息内容，对方不会收到消息或通知。\n\n"
            "可以放心使用「开始发送」。",
        )

    def _show_private_test_error(self, exc: BaseException) -> None:
        self._status_var.set(f"❌ 私信连接失败：{type(exc).__name__}: {exc}")
        messagebox.showerror(
            "测试连接",
            f"❌ 私信链路异常：\n{type(exc).__name__}: {exc}\n\n"
            "常见原因：douyin cookie 失效或私信列表为空。\n"
            "请确认列表里有目标、并重新保存 Cookie 后再试。",
        )

    # --- 网页登录：弹出真实浏览器登录（过 JS 风控），自动保存 cookie ---

    def _ensure_browser_ready(self) -> bool:
        """在 worker 线程里调用：确保 chromium 就绪（打包版首次会自动下载）。"""
        try:
            from desktop.bootstrap import ensure_chromium
        except Exception:
            return True
        self.after(0, lambda: self._status_var.set("检查浏览器（首次使用需下载，约 1-2 分钟，请稍候）……"))
        ok, msg = ensure_chromium()
        if not ok:
            self.after(0, lambda m=msg: messagebox.showerror("浏览器准备失败", f"无法准备浏览器：\n{m}"))
        return ok

    def _browser_login(self) -> None:
        login = getattr(self.services, "login", None)
        if login is None:
            messagebox.showwarning("网页登录", "未注入 login service，无法登录。")
            return
        self._status_var.set("正在打开登录浏览器（首次约 10 秒）……")

        def begin() -> None:
            if not self._ensure_browser_ready():
                return
            try:
                state = login.begin_browser_login()
                self.after(0, lambda s=state: self._show_browser_login_window(s))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("网页登录", e))

        threading.Thread(target=begin, daemon=True).start()

    def _show_browser_login_window(self, state: Any) -> None:
        win = ctk.CTkToplevel(self)
        win.title("网页登录")
        win.geometry("460x380")
        win.transient(self)
        self._bl_win = win
        self._bl_closed = False
        self._bl_session = state.get("session_id")

        ctk.CTkLabel(win, text="抖音网页登录", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(
            win,
            text="已弹出浏览器窗口，请在里面用抖音 App 扫码或账号登录。",
            text_color="gray",
            wraplength=420,
            justify="left",
        ).pack(pady=(0, 10), padx=18)
        self._bl_status = ctk.CTkLabel(
            win,
            text=state.get("message", "正在启动…"),
            text_color=("#5C4D40", "#D7C9B8"),
            wraplength=420,
            justify="left",
        )
        self._bl_status.pack(pady=10, padx=18)
        self._bl_confirm_btn = ctk.CTkButton(
            win,
            text="我已完成登录 / 验证，保存 Cookie",
            command=self._confirm_browser_login,
            state="disabled",
            height=38,
        )
        self._bl_confirm_btn.pack(pady=18)
        ctk.CTkLabel(
            win,
            text="提示：登录成功后若弹出滑块/验证，先完成它，再点上方按钮。",
            text_color="gray",
            font=ctk.CTkFont(size=10),
            wraplength=420,
            justify="left",
        ).pack(pady=(0, 8), padx=18)

        win.protocol("WM_DELETE_WINDOW", lambda: self._close_browser_login(False))
        self._poll_browser_login()

    def _poll_browser_login(self) -> None:
        if getattr(self, "_bl_closed", True) or getattr(self, "_bl_win", None) is None:
            return
        login = self.services.login
        session_id = self._bl_session

        def poll() -> None:
            try:
                state = login.poll_browser_login(session_id)
                self.after(0, lambda s=state: self._on_browser_login_poll(s))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_browser_login_error(e))

        threading.Thread(target=poll, daemon=True).start()

    def _on_browser_login_poll(self, state: Any) -> None:
        if getattr(self, "_bl_closed", True) or getattr(self, "_bl_win", None) is None:
            return
        status = str(state.get("status"))
        self._bl_status.configure(text=state.get("message", ""))
        if status == "awaiting_confirm":
            self._bl_confirm_btn.configure(state="normal")
        if status == "success":
            self._status_var.set("✅ 网页登录成功，Cookie 已保存到 douyin/live")
            self.after(1000, lambda: self._close_browser_login(True))
            return
        if status in ("failed", "missing"):
            self._bl_confirm_btn.configure(state="disabled")
            self._status_var.set(f"网页登录结束：{state.get('message', status)}")
            return
        self.after(1500, self._poll_browser_login)

    def _confirm_browser_login(self) -> None:
        login = self.services.login
        session_id = self._bl_session
        self._bl_confirm_btn.configure(state="disabled", text="正在保存 Cookie……")

        def confirm() -> None:
            try:
                login.confirm_browser_login(session_id)
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("网页登录", e))

        threading.Thread(target=confirm, daemon=True).start()

    def _close_browser_login(self, ok: bool) -> None:
        self._bl_closed = True
        win = getattr(self, "_bl_win", None)
        self._bl_win = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        if ok:
            messagebox.showinfo(
                "网页登录",
                "登录成功，Cookie 已保存到 douyin / live。\n现在可以使用视频采集、评论监控等功能。",
            )

    def _on_browser_login_error(self, exc: BaseException) -> None:
        label = getattr(self, "_bl_status", None)
        if label is not None:
            label.configure(text=f"出错：{type(exc).__name__}: {exc}")

    # --- 检查更新 ---

    def _project_root(self) -> str:
        cfg = getattr(self.services, "config", None)
        root = getattr(cfg, "project_root", None)
        if root:
            return str(root)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _check_update(self) -> None:
        self._status_var.set("正在检查更新……")

        def worker() -> None:
            try:
                result = self._do_check_update()
                self.after(0, lambda r=result: self._show_update_result(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("检查更新", e))

        threading.Thread(target=worker, daemon=True).start()

    def _do_check_update(self) -> dict:
        import subprocess
        root = self._project_root()
        if os.path.isdir(os.path.join(root, ".git")):
            def run(args):
                return subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=30)
            run(["git", "fetch", "--quiet"])
            local = run(["git", "rev-parse", "HEAD"]).stdout.strip()
            remote = run(["git", "rev-parse", "origin/master"]).stdout.strip()
            behind = run(["git", "rev-list", "--count", "HEAD..origin/master"]).stdout.strip() or "0"
            return {
                "mode": "git",
                "up_to_date": bool(local) and local == remote,
                "behind": behind,
                "local": local[:7],
                "remote": remote[:7],
            }
        import requests
        resp = requests.get(
            "https://api.github.com/repos/371066607/DouYin_Spider/commits/master", timeout=15
        )
        data = resp.json()
        msg = (data.get("commit", {}).get("message", "") or "").splitlines()
        return {
            "mode": "zip",
            "latest": (data.get("sha", "") or "")[:7],
            "date": (data.get("commit", {}).get("author", {}).get("date", "") or "")[:10],
            "msg": (msg[0] if msg else "")[:60],
        }

    def _show_update_result(self, r: dict) -> None:
        if r.get("mode") == "git":
            if r.get("up_to_date"):
                self._status_var.set("已是最新版本")
                messagebox.showinfo("检查更新", "✅ 已是最新版本。")
            else:
                if messagebox.askyesno(
                    "检查更新",
                    f"发现新版本（落后 {r.get('behind')} 个提交）。\n"
                    f"本地 {r.get('local')} → 最新 {r.get('remote')}\n\n"
                    "是否现在自动更新（git pull）？更新后请重启程序。",
                ):
                    self._do_git_pull()
        else:
            self._status_var.set("已获取最新版本信息")
            messagebox.showinfo(
                "检查更新",
                f"GitHub 最新版本：{r.get('latest')} · {r.get('date')}\n{r.get('msg')}\n\n"
                "你是 zip 下载版，无法自动更新。\n请到 GitHub 仓库重新「Download ZIP」覆盖即可。",
            )

    def _do_git_pull(self) -> None:
        self._status_var.set("正在更新（git pull）……")

        def worker() -> None:
            try:
                import subprocess
                out = subprocess.run(
                    ["git", "pull"], cwd=self._project_root(), capture_output=True, text=True, timeout=120
                )
                ok = out.returncode == 0
                msg = (out.stdout + out.stderr).strip()[-400:]
                self.after(0, lambda o=ok, m=msg: self._git_pull_done(o, m))
            except Exception as exc:
                self.after(0, lambda e=exc: self._show_error("更新", e))

        threading.Thread(target=worker, daemon=True).start()

    def _git_pull_done(self, ok: bool, msg: str) -> None:
        if not ok:
            messagebox.showerror("更新失败", msg or "git pull 失败，请检查网络或手动 git pull。")
            return
        if messagebox.askyesno("更新完成", f"{msg}\n\n✅ 更新成功！是否立即重启使新版本生效？"):
            self._restart_app()
        else:
            self._status_var.set("更新完成，下次启动生效")

    def _restart_app(self) -> None:
        """git pull 后自动重启程序，加载新代码（近似热更新）。"""
        try:
            self._closing = True
            os.chdir(self._project_root())
            os.execv(sys.executable, [sys.executable, "-m", "desktop.client"])
        except Exception as exc:
            messagebox.showerror("重启失败", f"更新已完成，请手动关闭并重启程序。\n{exc}")


def run(services: DesktopServices) -> None:
    if _CTK_IMPORT_ERROR is not None:
        raise RuntimeError(
            "customtkinter 未安装，无法启动桌面客户端。\n"
            "请运行: pip install customtkinter"
        ) from _CTK_IMPORT_ERROR
    app = AgentDesktopApp(services)
    app.mainloop()


def main() -> None:
    if _CTK_IMPORT_ERROR is not None:
        sys.stderr.write(
            "customtkinter 未安装，无法启动桌面客户端。\n"
            "请运行: pip install customtkinter\n"
        )
        raise SystemExit(1)
    try:
        from desktop.bootstrap import build_services
    except Exception as exc:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        root = _tk.Tk()
        root.withdraw()
        _mb.showerror("启动失败", f"无法导入 desktop.bootstrap.build_services：\n{type(exc).__name__}: {exc}")
        root.destroy()
        return
    run(build_services())


if __name__ == "__main__":
    main()
