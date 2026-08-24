#!/bin/sh
set -e

# 启动 Xvfb 虚拟显示(:99),让 Playwright 以 headless=False 运行。
# 抖音风控会检测并拒绝真正的 headless Chrome,所以需要虚拟显示器。
Xvfb :99 -screen 0 1280x720x24 -nolisten tcp &
XVFB_PID=$!

# 等待 Xvfb 就绪
sleep 1
export DISPLAY=:99

# 运行容器主命令(uvicorn),退出时容器停止,Xvfb 随之结束
exec "$@"
