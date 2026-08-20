"""Milvus Lite 向量库:进程内嵌入式运行,数据落在本地文件。

注意:Milvus Lite 同一时刻只能被一个进程打开,
导入任务和应用服务必须串行执行(见 README「云端部署」)。
"""

import logging
import threading
import time

from milvus_lite import server_manager
from pymilvus import DataType, MilvusClient

from backend.app import config

logger = logging.getLogger(__name__)

COLLECTION = "recipes"

_client: MilvusClient | None = None
_client_lock = threading.Lock()


def get_client() -> MilvusClient:
    """进程内单例 MilvusClient(传本地文件路径即自动使用 Milvus Lite)。

    不能每次调用都新建:每个 client 带独立 gRPC 通道与 keepalive 心跳,
    请求一多服务端会 'Too many pings' 限流踢连接,最终 Connect 失败。
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            config.MILVUS_DIR.mkdir(parents=True, exist_ok=True)
            _client = MilvusClient(config.MILVUS_DB_PATH)
        return _client


def reset_client() -> None:
    """连接异常时重置单例:关闭旧 client 并释放内嵌服务,下次调用重建。"""
    global _client
    with _client_lock:
        try:
            if _client is not None:
                _client.close()
        except Exception:
            logger.warning("关闭 MilvusClient 失败", exc_info=True)
        finally:
            _client = None
    try:
        server_manager.server_manager_instance.release_all()
    except Exception:
        logger.warning("释放 milvus-lite 内嵌服务失败", exc_info=True)


def _wait_loaded(client: MilvusClient, timeout: float = 30.0) -> bool:
    """load_collection 是异步的;轮询等待 Loaded,避免进程刚启动时首次检索返回空。

    get_load_state 返回 dict 形态:{"state": <LoadState: Loaded>}。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = client.get_load_state(COLLECTION)
            state = result.get("state") if isinstance(result, dict) else result
            if getattr(state, "name", str(state)) == "Loaded":
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def ensure_collection(client: MilvusClient) -> None:
    """建 collection(幂等)并加载到内存,保证可检索。

    主键用菜谱 id,便于 upsert 去重。
    注意:从磁盘重新打开的 collection 默认是 released 状态,
    不 load 直接 search 会报 MilvusException(code=101)。
    """
    if not client.has_collection(COLLECTION):
        schema = client.create_schema(auto_id=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("name", DataType.VARCHAR, max_length=128)
        schema.add_field("description", DataType.VARCHAR, max_length=2048)
        schema.add_field("dietary", DataType.VARCHAR, max_length=255)
        schema.add_field("tags", DataType.VARCHAR, max_length=255)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=config.EMBED_DIM)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",  # bge-m3 向量需归一化,余弦与内积等价
            params={"M": 16, "efConstruction": 200},
        )
        client.create_collection(COLLECTION, schema=schema, index_params=index_params)

    client.load_collection(COLLECTION)  # 幂等:已加载时是快速 no-op
    if not _wait_loaded(client):
        logger.warning("collection %s 加载超时,检索可能暂时为空", COLLECTION)
