import secrets
import hashlib
from fastapi import HTTPException, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from app.database import get_db
from app.config import get_settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, hash_token(plain)


def _extract_bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    return authorization.removeprefix("Bearer ").strip()


async def require_admin(authorization: str = Header(...)) -> None:
    token = _extract_bearer(authorization)
    if not secrets.compare_digest(token, get_settings().admin_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")


async def require_enrollment(authorization: str = Header(...)) -> None:
    token = _extract_bearer(authorization)
    if not secrets.compare_digest(token, get_settings().worker_enrollment_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid enrollment token")


async def require_worker(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> "ApiToken":
    from app.models.user import ApiToken
    token = _extract_bearer(authorization)
    token_hash = hash_token(token)

    result = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.is_revoked.is_(False))
    )
    api_token = result.scalar_one_or_none()
    if not api_token or api_token.token_type != "worker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker token")

    await db.execute(
        update(ApiToken)
        .where(ApiToken.id == api_token.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    return api_token


async def require_admin_or_worker(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = _extract_bearer(authorization)

    if secrets.compare_digest(token, get_settings().admin_token):
        return {"type": "admin", "worker_id": None}

    from app.models.user import ApiToken
    token_hash = hash_token(token)
    result = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.is_revoked.is_(False))
    )
    api_token = result.scalar_one_or_none()
    if api_token and api_token.token_type == "worker":
        return {"type": "worker", "worker_id": api_token.worker_id}

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
