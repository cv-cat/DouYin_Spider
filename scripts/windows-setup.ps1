# 两把刷子获客 - Windows 一键安装并运行
# 由根目录的「启动.bat」调用。自动安装 Python / Node.js / Python依赖 / chromium / node_modules，然后启动客户端。
# 依赖 winget（Windows 10 1709+ / Windows 11 自带「应用安装程序」）。

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$machine;$user"
}

function Has-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "==================================================="
Write-Host "   两把刷子获客 - Windows 一键安装运行"
Write-Host "==================================================="
Write-Host ""

# ---- 0) winget 检查 ----
if (-not (Has-Cmd "winget")) {
    Write-Host "[X] 没找到 winget（应用安装程序）。" -ForegroundColor Red
    Write-Host "    请打开 Microsoft Store 搜索并安装『应用安装程序』(App Installer)，"
    Write-Host "    或手动安装 Python 3.12 与 Node.js LTS 后，再双击「启动.bat」。"
    Read-Host "按回车退出"
    exit 1
}

# ---- 1) Python（python.org 版自带 tkinter）----
if (-not (Has-Cmd "python")) {
    Write-Host "[1/4] 正在安装 Python 3.12（约 30MB）..." -ForegroundColor Cyan
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
} else {
    Write-Host "[1/4] 已检测到 Python，跳过。" -ForegroundColor Green
}

# ---- 2) Node.js ----
if (-not (Has-Cmd "node")) {
    Write-Host "[2/4] 正在安装 Node.js LTS（约 30MB）..." -ForegroundColor Cyan
    winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
} else {
    Write-Host "[2/4] 已检测到 Node.js，跳过。" -ForegroundColor Green
}

# 安装后再确认一次
if (-not (Has-Cmd "python")) {
    Write-Host "[X] 安装完 Python 后仍找不到命令。请重启电脑后再双击「启动.bat」。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}
if (-not (Has-Cmd "node")) {
    Write-Host "[X] 安装完 Node.js 后仍找不到命令。请重启电脑后再双击「启动.bat」。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}

# ---- Git（让客户端「检查更新」能自助一键更新）----
if (-not (Has-Cmd "git")) {
    Write-Host "[*] 正在安装 Git（用于一键更新，用户无需手动操作）..." -ForegroundColor Cyan
    winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}
# 把当前文件夹关联成 git 仓库，之后「检查更新」即可自动 git pull
if ((Has-Cmd "git") -and (-not (Test-Path ".git"))) {
    Write-Host "[*] 关联 GitHub 仓库（便于以后一键更新）..." -ForegroundColor Cyan
    git init -q
    git remote add origin https://github.com/371066607/DouYin_Spider.git
    git fetch -q origin master
    git reset -q --hard origin/master
    git branch -q --set-upstream-to=origin/master master 2>$null
}

# ---- 3) Python 虚拟环境 + 依赖 + 浏览器 ----
$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[3/4] 创建虚拟环境并安装 Python 依赖..." -ForegroundColor Cyan
    python -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
    Write-Host "      下载 chromium 浏览器（约 150MB，首次较慢）..." -ForegroundColor Cyan
    & $venvPython -m playwright install chromium
} else {
    Write-Host "[3/4] Python 环境已就绪，跳过。" -ForegroundColor Green
}

# ---- 4) Node 签名依赖（必须本机编译）----
if (-not (Test-Path "node_modules\canvas")) {
    Write-Host "[4/4] 安装 Node 签名依赖（npm install，首次较慢）..." -ForegroundColor Cyan
    if (Test-Path "node_modules") { Remove-Item -Recurse -Force "node_modules" }
    npm install
} else {
    Write-Host "[4/4] 签名依赖已就绪，跳过。" -ForegroundColor Green
}

# ---- 启动 ----
Write-Host ""
Write-Host "环境就绪，正在启动客户端..." -ForegroundColor Green
& $venvPython -m desktop.client
