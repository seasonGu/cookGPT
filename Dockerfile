# cookGPT 镜像:前端构建 + Python 运行时(含 Milvus Lite)
# 单容器单进程,天然符合 Milvus Lite 的单进程约束;--workers 1 是硬性要求

# ---------- 阶段 1:构建前端 ----------
FROM node:22-alpine AS web
WORKDIR /build
# 国内服务器构建用 npm 镜像(海外部署可删掉这行)
ENV npm_config_registry=https://registry.npmmirror.com
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2:Python 运行时 ----------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# 用 uv 按锁文件装依赖(可复现),系统 Python 3.12 与 .python-version 一致
# 国内服务器构建用 PyPI 镜像(pymilvus/pyarrow 几百 MB,直连 PyPI 会卡死;海外部署可删):
# pip 和 uv 各读各的变量,两个都要配
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
COPY pyproject.toml uv.lock .python-version ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY backend/ backend/
COPY main.py ./
COPY --from=web /build/dist frontend/dist

EXPOSE 8000
# workers=1 必须保持:Milvus Lite 单进程嵌入式 + 2GB 内存
CMD [".venv/bin/uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
