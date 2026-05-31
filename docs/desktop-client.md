# 桌面客户端运行与打包

本项目已有 Tkinter 桌面客户端入口：`desktop.client`。桌面客户端直接复用现有服务层，不需要启动 Web UI。

## macOS 运行客户端

在项目根目录执行：

```bash
./scripts/desktop-client
```

脚本会优先使用项目内 `.venv/bin/python`。如果 `.venv/bin/python` 不存在，会回退到系统 `python3`：

```bash
python3 -m desktop.client
```

建议先准备项目运行依赖：

```bash
./scripts/portable-env prepare
```

## Windows 运行客户端

Windows 需要先在 Windows 环境中安装项目依赖，然后运行同一个 Python 模块入口：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m desktop.client
```

如果使用 Git Bash，也可以在项目根目录尝试：

```bash
./scripts/desktop-client
```

## Tkinter 运行要求

桌面客户端使用 Python 标准库 `tkinter`。Windows 官方 Python 通常自带 Tkinter；macOS 如果使用某些 Homebrew Python，可能会缺少 `_tkinter`。遇到“当前 Python 未启用 tkinter”时，换用带 Tk 的 Python 重新创建虚拟环境，例如 macOS 系统 Python 或 python.org 安装包。

## macOS 打包

PyInstaller 是打包工具，不是运行时依赖，所以默认不写入 `requirements.txt`。在打包环境安装一次即可：

```bash
.venv/bin/python -m pip install pyinstaller
./scripts/build-desktop
```

macOS 上运行打包脚本后，输出在：

```text
dist/douyin-desktop-client.app
dist/douyin-desktop-client
```

也可以只查看脚本将执行的 PyInstaller 命令：

```bash
./scripts/build-desktop command
```

## Windows 打包 exe

Windows exe 需要在 Windows 环境中打包：

```powershell
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --name douyin-desktop-client --paths . --collect-submodules desktop --collect-submodules web --collect-submodules dy_apis --collect-submodules dy_live desktop\client.py
```

如果在 Windows 的 Git Bash 中运行，也可以使用：

```bash
./scripts/build-desktop
```

PyInstaller 只能为当前操作系统生成可执行文件。macOS 上运行只能生成 macOS app/可执行文件，不能直接生成 Windows `.exe`；Windows `.exe` 必须在 Windows、Windows 虚拟机、CI Windows runner 或同等 Windows 环境中构建。

## Cookie 与风控注意事项

- Cookie 必须来自已登录的抖音账号，未登录 Cookie 通常不可用。
- 不同业务可能使用 `www.douyin.com`、`live.douyin.com`、私信等不同域名或能力范围的 Cookie。桌面端“私信功能”里可以手动保存 Cookie，默认 scope 为 `douyin`。
- Cookie 是账号凭证，不要提交到 Git，也不要打进公开发布包。
- 抖音有登录态、验证码、访问频率、设备环境、IP 和账号行为等风控，打包成客户端不等于绕过风控。
- 采集、直播监听、群聊和私信相关功能建议控制频率，并遵守平台规则和法律要求。

## 群聊与私信能力边界

群聊监控复用项目已有 IM 接收通道，收到的 IM 事件会落到 `event_feed`，桌面端可查看、筛选、清空和导出。当前底层私信发送只接入文本消息；界面中的卡片配置会保存，但执行发送时会明确提示“只支持文本私信”，不会伪装成已支持卡片发送。

## 私信默认行为

桌面客户端提供“私信功能”页面用于导入 UID、查看目标和手动触发动作。默认不会在启动客户端后自动私信，也不会自动批量发送私信；是否发送取决于用户在界面中显式触发的操作以及现有服务层配置。
