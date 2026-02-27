"""FastAPI dependency functions — auth, request utilities."""
from __future__ import annotations
from typing import Optional
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    # X-API-Key header
    key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if key:
        return key
    # Cookie fallback
    return request.cookies.get("token")


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> dict:
    """Require authenticated user. Raises 401 if missing/invalid."""
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from salmalm.web.auth import extract_auth
    payload = extract_auth({"authorization": f"Bearer {token}"})
    if not payload:
        # Try as API key
        from salmalm.web.auth import extract_auth
        payload = extract_auth({"x-api-key": token})
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


async def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> Optional[dict]:
    """Optional auth — returns None if unauthenticated."""
    token = _extract_token(request, credentials)
    if not token:
        return None
    from salmalm.web.auth import extract_auth
    return extract_auth({"authorization": f"Bearer {token}"})
