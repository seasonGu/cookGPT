"""全局环境变量配置。

云端部署时把这些变量写进项目根目录的 .env(启动时自动加载)或 systemd 的 EnvironmentFile。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 加载项目根目录 .env(不存在时静默跳过)

# ---- 应用 ----
# 生产环境务必通过环境变量覆盖(见 .env.example)
SECRET_KEY = os.getenv("COOKGPT_SECRET", "dev-secret-please-change-in-production")

# ---- Embedding:硅基流动 bge-m3 ----
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_BASE_URL = os.getenv(
    "EMBED_BASE_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))  # 单次 API 请求的条数
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))  # bge-m3 输出维度
EMBED_MAX_RETRIES = int(os.getenv("EMBED_MAX_RETRIES", "5"))

# ---- LLM 问答生成:DeepSeek V4 官方 API(OpenAI 兼容接口)----
# 官方只有两个模型 ID:deepseek-v4-flash(快/便宜)、deepseek-v4-pro(旗舰推理)
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")

# ---- MySQL(腾讯云内网地址) ----
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "cookgpt")

# ---- Milvus Lite ----
# 数据目录必须放在持久盘(云服务器重启/重装不丢)
MILVUS_DIR = Path(
    os.getenv(
        "COOKGPT_MILVUS_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "milvus"),
    )
)
MILVUS_DB_PATH = str(MILVUS_DIR / "cookgpt.db")
