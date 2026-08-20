"""请求/响应的 Pydantic 模型。"""

from typing import Literal

from pydantic import BaseModel, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_一-龥]+$"


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=6, max_length=128)


class AuthResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)
    conversation_id: int | None = None  # 不传则由后端自动新建会话


class ConversationResponse(BaseModel):
    id: int
    title: str
    updated_at: str


class MessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", max_length=64)
