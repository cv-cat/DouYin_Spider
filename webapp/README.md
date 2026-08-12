# 抖音 Spider Web 控制台

基于 `DouYin_Spider` SDK 的上层 Web 应用,覆盖 SDK 全部功能:数据采集、搜索、直播间监听、私信收发、互动操作,并集成抖音扫码登录流程。

## 技术栈

- **后端**:FastAPI + SQLite + asyncio(同步 SDK 调用走线程池)
- **前端**:Vue 3 + Vite + TypeScript + Element Plus + Pinia
- **实时**:WebSocket(直播事件、私信入站、任务进度)

## 目录结构

```
webapp/
├── backend/        FastAPI 后端(routers/services/bridges/accounts/tasks)
├── frontend/       Vue 3 SPA
├── data/           SQLite 数据库(运行时生成)
└── PLAN.md         设计方案
```

## 开发模式

后端(终端 1):
```bash
uvicorn webapp.backend.main:app --reload --port 8000
```
前端(终端 2):
```bash
cd webapp/frontend
npm install
npm run dev
```
打开 http://localhost:5173 。Vite 已把 `/api` 代理到 8000。

## 生产模式(单进程)

```bash
cd webapp/frontend && npm run build && cd ../..
uvicorn webapp.backend.main:app --port 8000
```
FastAPI 自动托管 `frontend/dist`,打开 http://localhost:8000 。

## 登录流程

1. 进入「账号」页,点「扫码登录」
2. 用抖音 App 扫描弹窗中的二维码
3. 后端轮询扫码状态,确认后自动 headless 提取私信签名凭证(ticket/private_key)
4. 登录成功后自动设为活跃账号,顶栏显示账号与「私信可用」标签

其他登录方式:
- **Cookie 粘贴**:从浏览器 F12 复制 cookie,可选 headless 提取凭证
- **有头浏览器登录**:服务端弹出 Chromium 窗口扫码(需有显示环境)

> Playwright 首次使用需安装浏览器:`playwright install chromium`

## 功能一览

| 页面 | 功能 |
|---|---|
| 账号 | 扫码/Cookie/有头登录,多账号管理,校验,切换 |
| 采集 | 作品/用户主页/评论/关注粉丝/收藏/通知/推荐流/收藏夹/直播间榜单 |
| 搜索 | 作品(全过滤)/用户/直播;结果可点赞/评论/收藏 |
| 直播间 | 实时弹幕/礼物/进场/点赞/关注/房间热度,发弹幕,点赞 |
| 私信 | WebSocket 实时接收(文本/表情/语音/图片/分享视频),主动发送 |
| 互动 | 点赞/评论/收藏/移动收藏 |
| 任务 | 长任务进度与结果(采集/搜索/评论/关注粉丝) |
| 下载 | 浏览采集产物(媒体/Excel),在线下载 |

## 注意

- 仅供学习与技术研究使用,严禁用于违法用途。
- 直播间监听与私信接收在服务端以独立线程运行,事件经事件总线推送到浏览器 WebSocket。
- 多账号:可在「账号」页登录多个抖音号并随时切换;活跃账号用于所有业务接口。
