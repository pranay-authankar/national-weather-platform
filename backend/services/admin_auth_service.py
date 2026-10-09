"""
Authentication and authorization service for administrative operations.
Implements a secure, configurable token-based authentication mechanism.
Never hardcodes tokens and never trusts client-supplied moderator identities.
"""

import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

DEFAULT_MODERATOR_ID = "admin"


class AdminAuthError(Exception):
    """Raised when admin authentication fails."""
    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_configured_admin_tokens() -> Dict[str, str]:
    """
    Retrieve mapping of valid admin tokens to moderator identities.
    Supports:
    1. ADMIN_API_KEY: maps token to ADMIN_DEFAULT_MODERATOR_ID (default: 'admin')
    2. ADMIN_API_TOKENS: JSON map of {"token_string": "moderator_identity", ...}
    """
    load_dotenv(dotenv_path=env_path, override=False)
    tokens_map: Dict[str, str] = {}

    # Primary single token
    primary_key = os.getenv("ADMIN_API_KEY", "").strip()
    default_identity = os.getenv("ADMIN_DEFAULT_MODERATOR_ID", DEFAULT_MODERATOR_ID).strip()
    if primary_key:
        tokens_map[primary_key] = default_identity

    # Multi-moderator token mapping if configured
    multi_tokens_json = os.getenv("ADMIN_API_TOKENS", "").strip()
    if multi_tokens_json:
        try:
            parsed = json.loads(multi_tokens_json)
            if isinstance(parsed, dict):
                for tok, ident in parsed.items():
                    if tok and ident:
                        tokens_map[str(tok).strip()] = str(ident).strip()
        except Exception as exc:
            logger.warning("Failed to parse ADMIN_API_TOKENS JSON configuration: %s", exc)

    return tokens_map


def verify_admin_token(token: Optional[str]) -> str:
    """
    Verify an incoming token against server-configured admin credentials
    using constant-time comparison to prevent timing attacks.
    
    Returns:
        str: Authenticated moderator identity.
        
    Raises:
        AdminAuthError: If authentication is unconfigured or token is invalid.
    """
    if not token or not token.strip():
        raise AdminAuthError(
            "Missing admin authentication token. Please provide Authorization: Bearer <token> or X-Admin-Token header.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    clean_token = token.strip()
    tokens_map = get_configured_admin_tokens()

    if not tokens_map:
        raise AdminAuthError(
            "Admin authentication is not configured on the server. Please configure ADMIN_API_KEY in backend/.env.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Constant-time comparison across configured tokens
    for valid_tok, moderator_id in tokens_map.items():
        if hmac.compare_digest(clean_token, valid_tok):
            return moderator_id

    raise AdminAuthError(
        "Invalid admin authentication credentials.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


async def get_current_moderator(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> str:
    """
    FastAPI dependency that extracts and authenticates admin credentials from request headers.
    Supports standard 'Authorization: Bearer <token>' and 'X-Admin-Token: <token>'.
    
    Returns:
        str: Server-verified moderator identity.
        
    Raises:
        HTTPException: On missing, invalid, or unconfigured credentials.
    """
    raw_token: Optional[str] = None

    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1]
        elif len(parts) == 1:
            raw_token = parts[0]

    if not raw_token and x_admin_token:
        raw_token = x_admin_token.strip()

    try:
        return verify_admin_token(raw_token)
    except AdminAuthError as exc:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == status.HTTP_401_UNAUTHORIZED else None
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers=headers,
        )
