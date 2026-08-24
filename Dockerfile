# ---------- 前端构建 ----------
FROM node:18-slim AS frontend
WORKDIR /build
COPY webapp/frontend/package.json webapp/frontend/package-lock.json* ./
RUN npm install
COPY webapp/frontend/ ./
RUN npm run build

# ---------- 后端运行 ----------
FROM python:3.10-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg build-essential git xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 浏览器(用于扫码登录提取凭证)
RUN playwright install chromium --with-deps \
    || (playwright install-deps chromium && playwright install chromium)

COPY . .

# 前端构建产物
COPY --from=frontend /build/dist ./webapp/frontend/dist

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DISPLAY=:99

EXPOSE 8000

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "webapp.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
