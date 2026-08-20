"""开发入口:uv run python main.py

端口默认 8000,被占用时可用 COOKGPT_PORT 环境变量覆盖。
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("COOKGPT_PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=True)
