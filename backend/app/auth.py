"""认证路由:注册 / 登录 / 当前用户。"""

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app import db
from backend.app.models import AuthResponse, Credentials, MeResponse
from backend.app.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """FastAPI 依赖:从 Authorization: Bearer <token> 中解析当前用户名。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录,请先登录"
        )
    try:
        return decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期,请重新登录"
        )


@router.post("/register", response_model=AuthResponse)
def register(creds: Credentials) -> AuthResponse:
    with db.get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (creds.username,)
        ).fetchone()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="用户名已存在"
            )
        pw_hash, salt = hash_password(creds.password)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (creds.username, pw_hash, salt),
        )
    return AuthResponse(token=create_token(creds.username), username=creds.username)


@router.post("/login", response_model=AuthResponse)
def login(creds: Credentials) -> AuthResponse:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE username = ?",
            (creds.username,),
        ).fetchone()
    if row is None or not verify_password(creds.password, row["password_hash"], row["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    return AuthResponse(token=create_token(creds.username), username=creds.username)


@router.get("/me", response_model=MeResponse)
def me(username: str = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=username)
