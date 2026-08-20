"""cookGPT FastAPI 入口。

启动:uv run python main.py(根目录)或
     uv run uvicorn backend.app.main:app --reload
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app import conversations
from backend.app.auth import router as auth_router
from backend.app.chat import router as chat_router
from backend.app.conversations import router as conversations_router
from backend.app.db import init_db

logger = logging.getLogger(__name__)

init_db()
try:
    conversations.ensure_tables()  # 对话记录表(腾讯云 MySQL),幂等
except Exception:
    logger.warning("对话表初始化失败(MySQL 不可达?),会话功能暂不可用", exc_info=True)

app = FastAPI(title="cookGPT API", version="0.1.0")

# 开发时前端走 Vite proxy(/api -> 8000),正常不需要 CORS;
# 这里放开 localhost:5173,方便直连调试。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversations_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 生产形态:后端直接托管前端构建产物(单进程单端口,2GB 服务器无需 nginx)。
# 前端未构建(本地开发走 Vite dev server)时这一段自动跳过。
# ---------------------------------------------------------------------------
DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if (DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """SPA 回退:非 /api 的未知路径返回 index.html(前端路由接管)。

        注意:必须在所有 API 路由之后注册,保证 /api/* 优先匹配。
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        file = DIST_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST_DIR / "index.html")
