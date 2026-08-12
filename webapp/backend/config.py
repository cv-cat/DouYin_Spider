"""路径与运行配置。"""
import os

# 仓库根目录(webapp/ 的上两级)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 数据目录:复用 SDK 的 datas/
DATA_DIR = os.path.join(REPO_ROOT, "datas")
MEDIA_DIR = os.path.join(DATA_DIR, "media_datas")
EXCEL_DIR = os.path.join(DATA_DIR, "excel_datas")

# webapp 自身数据目录(数据库等)
WEBAPP_DATA_DIR = os.path.join(REPO_ROOT, "webapp", "data")
DB_PATH = os.path.join(WEBAPP_DATA_DIR, "webapp.db")

# 前端构建产物(生产态由 FastAPI 托管)
FRONTEND_DIST = os.path.join(REPO_ROOT, "webapp", "frontend", "dist")

# 运行参数
API_PREFIX = "/api"
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def ensure_dirs():
    for d in (DATA_DIR, MEDIA_DIR, EXCEL_DIR, WEBAPP_DATA_DIR):
        os.makedirs(d, exist_ok=True)
