# 抖音 SDK 上层 Web 交互站点 — 实施方案

基于 `DouYin_Spider` SDK,构建一个覆盖 SDK 全部功能、集成抖音登录流程的 Web 应用。

**已确认决策**:Vue 3 + Vite SPA 前端 / 单用户个人工具(账号管理器,无 Web 登录) / 一次性全量交付。

---

## 1. 架构总览

```
webapp/
├── backend/                      FastAPI 后端
│   ├── main.py                   应用入口、静态托管、路由挂载、CORS、异常处理
│   ├── config.py                 路径/端口/SDK 路径配置
│   ├── deps.py                   依赖提供者(account_manager, task_manager, event_bus)
│   ├── models/
│   │   ├── schemas.py            全部 Pydantic 请求/响应模型
│   │   └── events.py             WebSocket 事件信封
│   ├── accounts/
│   │   ├── store.py              SQLite 账号存储(CRUD)
│   │   └── manager.py            账号管理器(登录流程、活跃会话、校验)
│   ├── services/                 SDK 薄封装(sync→async 桥)
│   │   ├── crawl.py   search.py   interact.py
│   │   ├── live.py               直播监听桥管理器
│   │   └── message.py            私信接收桥管理器 + 发送
│   ├── tasks/manager.py          进程内异步任务注册表 + 进度
│   ├── eventbus.py               进程内 pub/sub(asyncio)
│   ├── bridges/
│   │   ├── live_bridge.py        子类化 SDK DouyinLive,on_message→eventbus
│   │   └── msg_bridge.py         子类化 SDK DouyinRecvMsg,on_message→eventbus
│   └── routers/
│       ├── accounts.py  crawl.py  search.py  live.py  messages.py
│       ├── interact.py  tasks.py  downloads.py
└── frontend/                     Vue 3 + Vite SPA
    ├── vite.config.ts            /api、/ws 代理到后端
    └── src/
        ├── main.ts  App.vue  router/  stores/  api/  composables/  views/  components/
```

**核心设计点**:
- SDK 全是同步阻塞(`requests` / `ws.run_forever` / `playwright` async)。FastAPI handler 用 `asyncio.to_thread` 把同步调用丢线程池;长任务走 `TaskManager`。
- 直播/私信的阻塞 WebSocket 循环跑在独立线程,事件经 `eventbus` 转发到 FastAPI WebSocket → 浏览器。
- 账号(多个抖音号)存 SQLite,每个账号一个 `DouyinAuth` 实例,内存维护活跃账号。

---

## 2. 抖音登录流程集成

三种登录方式,QR 为主:

### 2.1 QR 扫码登录(Web 友好,主路径)
1. `POST /api/accounts/login/qr/start` → 后端 `dyGenerateInitData()`(headless Playwright,匿名)取初始 cookies+msToken → `dyGenerateQRcode(auth)` 取 `{token, qrcode_index_url}` → 后端用 `qrcode` 库把 `qrcode_index_url` 渲染成 PNG data URL → 返回 `{temp_id, qr_image, token}`。临时 auth 存内存。
2. 前端展示 QR。
3. `GET /api/accounts/login/qr/poll?temp_id=` → 后端 `dyCheckQrCodeLogin(auth, token)` 轮询。状态:new/scanned/confirmed/expired。
4. confirmed 后:跟 `redirect_url` 跳转链收集登录 cookies(复用 `phoneMain` 里的 302 跟随逻辑)→ `dyGenerateInitData(cookie_str=登录cookies)` headless 二次提取 `web_protect`+`keys` → 构造完整 `DouyinAuth` → 存 SQLite → 置为活跃。

### 2.2 Cookie 粘贴登录
`POST /api/accounts/login/cookie {cookies, label}` → 存 cookies;可选 headless 提取签名凭证(无 Playwright 则标记 PM 不可用)。

### 2.3 有头浏览器登录(本地兜底)
`POST /api/accounts/login/headed` → 调用 SDK `login_grab_ticket(headless=False)`(服务端开 Chromium 窗口,用户扫码)→ 一次性拿全 cookies+凭证 → 存盘。

### 2.4 账号管理
- `GET /api/accounts` 列表 / `GET /api/accounts/active` / `PUT /api/accounts/{id}/active` 切换 / `DELETE /api/accounts/{id}` / `PATCH /api/accounts/{id}` 改标签 / `POST /api/accounts/{id}/validate`(用 `get_my_uid` 探活)。

---

## 3. 功能 ↔ 接口完整映射

所有业务接口默认用活跃账号;无活跃账号返回 400。

### 采集 `/api/crawl`
| 接口 | SDK 方法 | 同步/任务 |
|---|---|---|
| `GET /work?url=` | get_work_info + handle_work_info | 同步 |
| `POST /user-works` | spider_user_all_work(save_choice) | 任务 |
| `GET /user-info?url=` | get_user_info | 同步 |
| `GET /comments?url=` | get_work_all_comment | 任务 |
| `GET /followers` | get_some_user_follower_list | 任务 |
| `GET /following` | get_some_user_following_list | 任务 |
| `GET /favorites?sec_id=` | get_user_favorite | 任务 |
| `GET /notices?num=` | get_some_notice_list | 同步 |
| `GET /feed?count=` | get_feed | 同步 |
| `GET /collect-list` | get_collect_list | 同步 |
| `GET /rank` | get_rank_list | 同步 |

### 搜索 `/api/search`
| `POST /work`(含 sort/time/duration/range/content_type 全过滤) | search_some_general_work | 任务 |
| `POST /user` | search_some_user | 同步 |
| `POST /live` | search_some_live | 同步 |

### 直播 `/api/live` + `/ws/live/{room_id}`
| `POST /start?room_id=` / `POST /stop?room_id=` / `GET /status` | 启停桥 | — |
| `POST /digg` | diggLiveRoom | 同步 |
| `POST /send` | sendMsgInRoom | 同步 |
| `WS /ws/live/{room_id}` | 事件流:gift/chat/member/like/social/room_stats | 实时 |

### 私信 `/api/messages` + `/ws/messages`
| `POST /conversation`(by user_url 或 uid) | get_user_info→create_conversation | 同步 |
| `POST /send` | send_msg | 同步 |
| `POST /recv/start` / `stop` | 启停接收桥 | — |
| `WS /ws/messages` | 入站消息流(文本/表情/语音/图片/分享视频/已读) | 实时 |

### 互动 `/api/interact`
| `POST /digg` | digg(点赞/取消) | 同步 |
| `POST /comment` | publish_comment(含回复) | 同步 |
| `POST /collect` / `move` / `remove` | collect/move/remove_collect_aweme | 同步 |

### 任务 `/api/tasks` + `/ws/tasks`
`GET /` `GET /{id}` `DELETE /{id}` `POST /{id}/cancel` + `WS /ws/tasks` 进度流

### 下载 `/api/downloads`
`GET /media`(目录树) / `GET /file?path=`(带路径越界校验的文件服务) / `GET /excel`(列表+下载链接)

---

## 4. 关键实现细节

### 4.1 sync→async 桥
```python
async def search_work(req):
    auth = account_manager.get_active_auth()
    return await asyncio.to_thread(DouyinAPI.search_some_general_work, auth, ...)
```

### 4.2 后台桥(直播/私信)
子类化 SDK 的 `DouyinLive` / `DouyinRecvMsg`,重写 `on_message`:复用 SDK 的 protobuf 解码逻辑,但把结构化事件 publish 到 `eventbus` 而非 `print`。`start_ws`/`start` 在独立线程跑 `run_forever`。FastAPI `/ws/live/{room}` handler 订阅对应频道,把事件 JSON 转发给浏览器。

### 4.3 任务系统
`TaskManager`:`task_id → {status, progress, result, error, created_at, kind}`。`asyncio.create_task(asyncio.to_thread(...))` 执行;进度回调更新注册表并 publish 到 `/ws/tasks`。前端任务面板实时显示。

### 4.4 账号存储(SQLite)
表 `accounts(id, label, cookies_json, ticket, ts_sign, client_cert, private_key, created_at, last_used_at, status)` + `settings(key, value)`(存活跃账号 id)。加载时由 cookies_json 重建 `DouyinAuth`(走 `perepare_auth` 再补 ticket/private_key 等)。

### 4.5 事件总线
`EventBus`:asyncio `dict[channel → set[asyncio.Queue]]`。`publish(channel, msg)` 向每个订阅 Queue put;`subscribe(channel)` 返回 Queue。WS handler 消费 Queue 转发。简单、进程内、够用。

---

## 5. 前端设计

- **UI 库**:Element Plus(Vue 3 成熟组件库,中文友好,表格/表单/对话框/通知开箱即用)+ `@element-plus/icons-vue`。
- **状态**:Pinia(account / tasks / live / messages)。
- **路由**:Vue Router,侧边栏导航:账号 / 采集 / 搜索 / 直播 / 私信 / 互动 / 任务 / 下载。
- **布局**:左侧固定侧边栏(导航 + 活跃账号指示器) + 顶栏(账号切换、登录状态) + 主内容区。
- **实时**:`useWebSocket` composable 封装 WS 连接、自动重连、事件分发。
- **视图**:
  - `Accounts.vue`:账号列表 + QR 登录弹窗(轮询状态) + Cookie 粘贴 + 有头登录 + 校验/切换/删除
  - `Crawl.vue`:作品/用户主页/评论/关注粉丝/收藏/通知/推荐流 表单 + 结果表格 + 保存选项
  - `Search.vue`:关键词 + 全过滤项 + 结果卡片网格
  - `Live.vue`:房间号输入 + 启停 + 实时事件流(彩色标签区分类型)+ 发弹幕/点赞
  - `Messages.vue`:会话列表 + 消息流 + 发送框 + 接收启停
  - `Interactions.vue`:点赞/评论/收藏 快捷操作面板(可从采集/搜索结果跳入)
  - `Tasks.vue`:任务列表 + 进度条 + 取消 + 结果查看
  - `Downloads.vue`:文件树浏览 + 下载

---

## 6. 依赖与部署

### 后端新增依赖(追加到 `requirements.txt`)
`fastapi`、`uvicorn[standard]`、`pydantic>=2`、`playwright`、`blackboxprotobuf`、`aiohttp`(login_api 已 import 但未声明)、`aiosqlite`(可选,否则用 sqlite3+to_thread)。

### 前端依赖
`vue@3`、`vite`、`vue-router`、`pinia`、`axios`、`element-plus`、`@element-plus/icons-vue`、`typescript`、`sass`。

### 部署
- **开发**:`uvicorn webapp.backend.main:app --reload --port 8000` + `cd webapp/frontend && npm run dev`(Vite 代理 `/api`、`/ws` 到 8000)。
- **生产**:`npm run build` → FastAPI 挂载 `frontend/dist` 为静态 → 单 `uvicorn` 进程。
- **Dockerfile**:更新现有 Dockerfile,加 Node 构建阶段 + `playwright install chromium` + 复制前端 dist。
- **README**:新增 `webapp/README.md` 说明启停。

---

## 7. 实施顺序(一次性交付,分层可测)

1. 后端骨架:FastAPI app、config、eventbus、deps、SQLite 账号存储
2. 账号管理器 + 登录服务(QR/Cookie/有头)+ accounts 路由
3. TaskManager + 服务封装层(crawl/search/interact)
4. crawl / search / interact 路由
5. 直播桥 + live 路由 + WS
6. 私信桥 + messages 路由 + WS
7. downloads 路由 + 静态文件服务
8. 前端骨架:Vite + Vue + Router + Pinia + Element Plus + 布局 + API client + useWebSocket
9. 逐视图实现并接通后端(Accounts → Crawl → Search → Live → Messages → Interactions → Tasks → Downloads)
10. 生产构建接线 + Dockerfile 更新 + README

---

## 8. 范围与注意

- **覆盖 SDK 全部功能**:采集(用户/作品/评论/搜索/关注粉丝/通知/收藏/推荐/榜单)、直播(监听/发弹幕/点赞)、私信(收发/会话)、互动(点赞/评论/收藏)。
- **登录集成**:QR(主)+ Cookie 粘贴 + 有头兜底,完整提取 cookies 与私信签名凭证。
- **不改动现有 SDK 代码**,只在 `webapp/` 下新增上层;必要时追加缺失依赖。
- **安全**:文件服务做路径越界校验;CORS 仅开发开;不对外暴露敏感凭证。
- **限制**:手机验证码登录有滑块验证码,仅保留接口不主推;`get_conversation_list` 实际返回 secure_uid,按 SDK 原样封装。
