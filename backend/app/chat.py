"""问答接口:跑 LangGraph Agent,把最终生成的文本流式推给前端(SSE)。

流格式(每行一个事件):
  data: {"delta": "文本增量"}     # 生成中的增量
  data: [DONE]                   # 结束
  data: {"error": "错误信息"}     # 出错(同样以流返回,前端在气泡里展示)
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.app import agent, conversations, profile
from backend.app.auth import get_current_user
from backend.app.models import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(req: ChatRequest, username: str = Depends(get_current_user)):
    def event_stream():
        conv_id = req.conversation_id
        try:
            # 未指定会话 -> 自动新建,标题取用户第一句话
            if conv_id is None:
                conv_id = conversations.create_conversation(
                    username, req.message[:20] or "新对话"
                )

            # 多轮上下文:有会话时优先用库里的历史(取完再落本次用户消息,避免重复)
            history = [m.model_dump() for m in req.history]
            if req.conversation_id is not None:
                msgs = conversations.get_messages(conv_id, username)
                if msgs is None:
                    yield _sse({"error": "会话不存在"})
                    return
                history = msgs[-6:]
            conversations.append_message(conv_id, "user", req.message)

            # 用户饮食画像:从库读入 → 图内使用 → 增量合并回库(跨会话记住忌口)
            user_profile = profile.load_profile(username)
            state = agent.run_agent(req.message, history, user_profile)
            try:
                update = state.get("profile_update") or {}
                if any(update.values()):
                    profile.save_profile(
                        username, profile.merge_profile(user_profile, update)
                    )
            except Exception:
                logger.warning("画像落库失败,不影响本轮回答", exc_info=True)

            final_stream = state.get("final_response")
            if final_stream is None:
                yield _sse({"error": "生成阶段没有产出,请重试", "conversation_id": conv_id})
                return
            full_text: list[str] = []
            for delta in final_stream:
                full_text.append(delta)
                yield _sse({"delta": delta})
            conversations.append_message(conv_id, "assistant", "".join(full_text))
            yield _sse({"conversation_id": conv_id})
            yield "data: [DONE]\n\n"  # 哨兵行是字面量,不做 JSON 编码
        except Exception as e:  # 图内任一步失败都转成流内错误,不让前端断在半路
            logger.exception("chat 处理失败")
            # 前端会统一加「出错了:」前缀,这里只给原始信息
            yield _sse({"error": str(e), "conversation_id": conv_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
