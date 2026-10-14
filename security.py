"""
Security layer for the chatbot backend.

Design: DENY BY DEFAULT.
Every route needs a valid dashboard login token (Authorization: Bearer ...)
unless it is explicitly listed in PUBLIC_PATHS below. So even if a new
endpoint is added later and the developer forgets about security, it is
protected automatically.

Environment variables (set these in Railway -> Variables):

    DASHBOARD_PASSWORD     password for the dashboard login (long, random)
    DASHBOARD_SECRET_KEY   random string, 32+ chars, signs login tokens
    WHATSAPP_APP_SECRET    Meta App Dashboard -> App settings -> Basic -> App secret
    WEBSITE_API_SECRET     (already exists) shared secret with website-api
    DASHBOARD_ORIGINS      comma separated allowed dashboard URLs, e.g.
                           https://rh-dashboard.vercel.app
    DASHBOARD_TOKEN_TTL_HOURS  optional, default 12

Generate secrets with:
    python -c "import secrets; print(secrets.token_urlsafe(48))"
"""

import os
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("security")


# ==========================================================
# CONFIG
# ==========================================================

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

# TEMPORARY: sirf tab use karein jab WHATSAPP_APP_SECRET abhi na mil sakta ho.
# "true" par WhatsApp webhooks bina signature check ke qubool hote hain
# (kam secure). Secret milte hi isay hata dein.
ALLOW_UNSIGNED_WHATSAPP = os.getenv(
    "ALLOW_UNSIGNED_WHATSAPP", ""
).strip().lower() in ("1", "true", "yes")

TOKEN_TTL_SECONDS = int(
    float(os.getenv("DASHBOARD_TOKEN_TTL_HOURS", "12")) * 3600
)

MAX_BODY_BYTES = 1_000_000          # 1 MB — webhooks/orders are tiny

GENERAL_LIMIT = (300, 60)           # 300 requests / 60 s per IP
LOGIN_LIMIT = (5, 900)              # 5 failed logins / 15 min per IP

WHATSAPP_WEBHOOK_PATH = "/webhook/whatsapp"

# Only these paths work without a dashboard token.
#   "/"                      health check (reveals nothing)
#   /privacy, /data-deletion required public pages for Meta
#   /auth/login              obtains a token (rate limited)
#   /webhook/whatsapp        Meta -> us; protected by signature check
#   /webhooks/website-order  website-api -> us; protected by secret header
PUBLIC_PATHS = {
    "/",
    "/privacy",
    "/data-deletion",
    "/auth/login",
    WHATSAPP_WEBHOOK_PATH,
    "/webhooks/website-order",
}


def allowed_origins() -> List[str]:

    raw = os.getenv("DASHBOARD_ORIGINS", "")

    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    if not origins:
        # Local development only. In production set DASHBOARD_ORIGINS.
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    return origins


def log_config_warnings() -> None:

    if not DASHBOARD_PASSWORD or len(DASHBOARD_PASSWORD) < 12:
        logger.error(
            "SECURITY: DASHBOARD_PASSWORD missing or shorter than 12 "
            "chars — dashboard login is DISABLED until it is set."
        )

    if len(DASHBOARD_SECRET_KEY) < 32:
        logger.error(
            "SECURITY: DASHBOARD_SECRET_KEY missing or shorter than 32 "
            "chars — dashboard login is DISABLED until it is set."
        )

    if not WHATSAPP_APP_SECRET:
        logger.error(
            "SECURITY: WHATSAPP_APP_SECRET missing — ALL incoming "
            "WhatsApp webhooks will be rejected until it is set."
        )

    if not os.getenv("WEBSITE_API_SECRET"):
        logger.error(
            "SECURITY: WEBSITE_API_SECRET missing — website orders "
            "will be rejected."
        )

    if not os.getenv("DASHBOARD_ORIGINS"):
        logger.warning(
            "SECURITY: DASHBOARD_ORIGINS not set — only localhost "
            "dashboards are allowed by CORS."
        )


# ==========================================================
# HELPERS
# ==========================================================

def safe_equals(a: Optional[str], b: Optional[str]) -> bool:
    """Constant-time string comparison. Empty values never match."""

    if not a or not b:
        return False

    return hmac.compare_digest(
        str(a).encode("utf-8"),
        str(b).encode("utf-8"),
    )


def client_ip(request: Request) -> str:
    """
    Behind Railway's proxy the real client is the LAST entry of
    X-Forwarded-For (added by the proxy). Earlier entries can be
    faked by the caller, so they are ignored.
    """

    forwarded = request.headers.get("x-forwarded-for", "")

    if forwarded:
        return forwarded.split(",")[-1].strip() or "unknown"

    return request.client.host if request.client else "unknown"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ==========================================================
# RATE LIMITER (in-memory, per process)
# ==========================================================

class RateLimiter:

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _prune(self, key: str, window: int, now: float) -> Deque[float]:

        q = self._hits[key]

        while q and q[0] <= now - window:
            q.popleft()

        return q

    def _gc(self, now: float) -> None:

        for key in list(self._hits.keys()):

            q = self._hits[key]

            if not q or q[-1] < now - 3600:
                del self._hits[key]

    def allow(self, key: str, limit: int, window: int) -> bool:
        """Count this request; False if over the limit."""

        now = time.monotonic()
        q = self._prune(key, window, now)

        if len(q) >= limit:
            return False

        q.append(now)

        if len(self._hits) > 20000:
            self._gc(now)

        return True

    def is_blocked(self, key: str, limit: int, window: int) -> bool:

        now = time.monotonic()

        return len(self._prune(key, window, now)) >= limit

    def add(self, key: str) -> None:
        self._hits[key].append(time.monotonic())


_general_limiter = RateLimiter()
_login_limiter = RateLimiter()


# ==========================================================
# SIGNED LOGIN TOKENS (stateless, expire automatically)
# ==========================================================

def _sign(body: str) -> str:

    return _b64e(
        hmac.new(
            DASHBOARD_SECRET_KEY.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )


def create_token() -> str:

    payload = {
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
        "n": secrets.token_hex(8),
    }

    body = _b64e(json.dumps(payload).encode("utf-8"))

    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> bool:

    if len(DASHBOARD_SECRET_KEY) < 32 or not token:
        return False

    try:

        body, signature = token.split(".", 1)

        if not hmac.compare_digest(_sign(body), signature):
            return False

        payload = json.loads(_b64d(body))

        return int(payload.get("exp", 0)) > time.time()

    except Exception:
        return False


# ==========================================================
# WHATSAPP WEBHOOK SIGNATURE (X-Hub-Signature-256)
#
# Meta signs every webhook POST with your App Secret. Without
# this check anyone on the internet could POST fake "customer
# messages" to the bot.
# ==========================================================

def verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: Optional[str],
) -> bool:

    if not WHATSAPP_APP_SECRET:
        # Fail closed, unless the owner explicitly opted in temporarily.
        return ALLOW_UNSIGNED_WHATSAPP

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        signature_header.split("=", 1)[1],
    )


# ==========================================================
# MIDDLEWARE — auth gate, rate limit, body size, headers
# ==========================================================

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cache-Control": "no-store",
}


def _reject(status: int, detail: str) -> JSONResponse:

    return JSONResponse(
        {"detail": detail},
        status_code=status,
        headers=SECURITY_HEADERS,
    )


class SecurityMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        # CORS preflight carries no data and no credentials.
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        length = request.headers.get("content-length", "")

        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _reject(413, "Request too large")

        ip = client_ip(request)

        # Meta's servers send many webhooks — they are protected by the
        # signature check instead of an IP rate limit.
        if path != WHATSAPP_WEBHOOK_PATH:

            if not _general_limiter.allow(ip, *GENERAL_LIMIT):
                return _reject(429, "Too many requests")

        if path not in PUBLIC_PATHS:

            auth = request.headers.get("authorization", "")

            token = (
                auth[7:].strip()
                if auth.lower().startswith("bearer ")
                else ""
            )

            if not verify_token(token):
                return _reject(401, "Unauthorized")

        response = await call_next(request)

        for name, value in SECURITY_HEADERS.items():

            # Privacy/legal pages may be cached by browsers.
            if name == "Cache-Control" and path in ("/privacy", "/data-deletion"):
                continue

            response.headers.setdefault(name, value)

        return response


# ==========================================================
# LOGIN ENDPOINTS
# ==========================================================

router = APIRouter()


class LoginRequest(BaseModel):
    password: str = Field(max_length=200)


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request):

    if len(DASHBOARD_PASSWORD) < 12 or len(DASHBOARD_SECRET_KEY) < 32:

        return _reject(
            503,
            "Dashboard login is not configured on the server.",
        )

    ip = client_ip(request)

    if _login_limiter.is_blocked(ip, *LOGIN_LIMIT):

        logger.warning("Login blocked (too many failures) from %s", ip)

        return _reject(429, "Too many failed attempts. Try again later.")

    if not safe_equals(body.password, DASHBOARD_PASSWORD):

        _login_limiter.add(ip)

        logger.warning("Failed dashboard login from %s", ip)

        await asyncio.sleep(0.7)  # slows down guessing

        return _reject(401, "Invalid password")

    return JSONResponse(
        {
            "token": create_token(),
            "expires_in": TOKEN_TTL_SECONDS,
        },
        headers=SECURITY_HEADERS,
    )


@router.get("/auth/check")
def auth_check():
    # Reaching this handler means the middleware accepted the token.
    return {"ok": True}