"""密码哈希(pbkdf2,stdlib 实现)与 JWT 签发/校验。"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from backend.app import config  # 先于任何 os.getenv 导入,保证 .env 已加载

SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> tuple[str, str]:
    """返回 (hash_hex, salt_hex)。"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest.hex(), stored_hash)


def create_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    """校验并返回用户名;无效/过期抛 jwt.PyJWTError。"""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]
