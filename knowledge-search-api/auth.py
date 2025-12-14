import os
import time
from typing import Optional

import requests
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from schemas import TokenIdentity

_JWKS_CACHE: Optional[list] = None
_JWKS_CACHED_AT: Optional[float] = None

bearer_scheme = HTTPBearer(auto_error=False)


def _load_env_var(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is not configured",
        )
    return value


def _get_jwks() -> list:
    global _JWKS_CACHE, _JWKS_CACHED_AT

    jwks_url = _load_env_var("OIDC_JWKS_URL")
    cache_ttl = int(os.getenv("OIDC_JWKS_TTL", "300"))
    now = time.time()

    if _JWKS_CACHE is not None and _JWKS_CACHED_AT and now - _JWKS_CACHED_AT < cache_ttl:
        return _JWKS_CACHE

    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        _JWKS_CACHE = response.json().get("keys", [])
        _JWKS_CACHED_AT = now
        return _JWKS_CACHE
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to fetch JWKS",
        ) from exc


def _get_signing_key(token: str) -> dict:
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    jwks = _get_jwks()

    for key in jwks:
        if key.get("kid") == kid:
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Signing key not found for token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_token(token: str) -> dict:
    audience = _load_env_var("OIDC_AUDIENCE")
    issuer = _load_env_var("OIDC_ISSUER")

    signing_key = _get_signing_key(token)
    algorithm = signing_key.get("alg") or "RS256"

    try:
        return jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=audience,
            issuer=issuer,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_token_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_token(credentials.credentials)
    request.state.oidc_claims = claims

    user_claim = os.getenv("OIDC_USER_ID_CLAIM", "sub")
    org_claim = os.getenv("OIDC_ORG_ID_CLAIM", "org_id")

    user_id = claims.get(user_claim)
    org_id = claims.get(org_claim)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User id is missing in token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenIdentity(user_id=str(user_id), org_id=str(org_id) if org_id else None)
