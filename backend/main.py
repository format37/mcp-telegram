import contextlib
import contextvars
import logging
import os
import re

import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from telegram_tools import send_to_telegram

load_dotenv(".env")

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT", "")

MCP_NAME = os.getenv("MCP_NAME", "telegram")
_safe_name = re.sub(r"[^a-z0-9_-]", "-", MCP_NAME.lower()).strip("-") or "service"
BASE_PATH = f"/{_safe_name}"
STREAM_PATH = f"{BASE_PATH}/"

MCP_TOKEN_CTX = contextvars.ContextVar("mcp_token", default=None)

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "localhost:*",
        "127.0.0.1:*",
        "mcp-telegram:*",
        "scriptlab.duckdns.org:*",
        "scriptlab.duckdns.org",
    ],
    allowed_origins=[
        "http://localhost:*",
        "https://localhost:*",
        "http://127.0.0.1:*",
        "http://mcp-telegram:*",
        "https://scriptlab.duckdns.org:*",
        "https://scriptlab.duckdns.org",
    ],
)

mcp = FastMCP(
    _safe_name,
    streamable_http_path=STREAM_PATH,
    json_response=True,
    transport_security=transport_security,
)


@mcp.tool()
def send_telegram(message: str, chat_id: str = "") -> str:
    """Send a notification message to a user via Telegram.

    Use this between job stages to keep the user informed of progress, completions,
    or anything that warrants their attention. Messages over Telegram's 4096-character
    limit are automatically sent as a .txt document attachment so the full content is
    preserved.

    Args:
        message: The notification text to send. No length limit (long messages
            are delivered as a text-file attachment).
        chat_id: Optional Telegram chat ID to send to. If omitted, the chat
            configured in TELEGRAM_CHAT (env) is used.
    """
    if not TELEGRAM_TOKEN:
        return "Error: TELEGRAM_TOKEN not configured"
    target_chat = chat_id.strip() if chat_id else TELEGRAM_CHAT
    if not target_chat:
        return "Error: no chat_id provided and TELEGRAM_CHAT not configured"
    try:
        return send_to_telegram(
            message=message,
            chat_id=target_chat,
            token=TELEGRAM_TOKEN,
        )
    except Exception as e:
        return f"Error: {e}"


mcp_asgi = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_: Starlette):
    async with mcp.session_manager.run():
        yield


async def health_check(request):
    return JSONResponse({"status": "healthy"})


app = Starlette(
    routes=[
        Route("/health", health_check, methods=["GET"]),
        Mount("/", app=mcp_asgi),
    ],
    lifespan=lifespan,
)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Token gate for requests under BASE_PATH.

    Accepts tokens via:
    - Authorization header: "Bearer <token>"
    - URL path: /<service>/<token>/...

    If MCP_TOKENS is unset, auth is disabled (allows all).
    """

    def __init__(self, app):
        super().__init__(app)
        raw = os.getenv("MCP_TOKENS", "")
        self.allowed_tokens = {t.strip() for t in raw.split(",") if t.strip()}
        self.allow_url_tokens = True
        self.require_auth = (
            os.getenv("MCP_REQUIRE_AUTH", "").lower() in ("1", "true", "yes")
        )
        if not self.allowed_tokens:
            if self.require_auth:
                logger.warning(
                    "MCP_TOKENS not set; MCP_REQUIRE_AUTH=true -> all %s requests rejected",
                    BASE_PATH,
                )
            else:
                logger.warning(
                    "MCP_TOKENS not set; token auth DISABLED for %s", BASE_PATH
                )

    async def dispatch(self, request, call_next):
        path = request.url.path or "/"
        if not path.startswith(BASE_PATH):
            return await call_next(request)

        def accept(token_value, source):
            request.state.mcp_token = token_value
            logger.info("Authenticated %s %s via %s", request.method, path, source)
            return MCP_TOKEN_CTX.set(token_value)

        async def proceed(token_value, source):
            token_scope = accept(token_value, source)
            try:
                return await call_next(request)
            finally:
                MCP_TOKEN_CTX.reset(token_scope)

        if not self.require_auth:
            segs = [s for s in path.split("/") if s != ""]
            if len(segs) >= 2 and segs[0] == _safe_name:
                remainder = "/".join([_safe_name] + segs[2:])
                new_path = "/" + (
                    remainder + "/"
                    if path.endswith("/") or not segs[2:]
                    else remainder
                )
                if new_path == BASE_PATH:
                    new_path = STREAM_PATH
                request.scope["path"] = new_path
                if "raw_path" in request.scope:
                    request.scope["raw_path"] = new_path.encode("utf-8")
                logger.info("Auth disabled, rewriting path %s -> %s", path, new_path)
            else:
                logger.info("Auth disabled, allowing request to %s", path)
            return await call_next(request)

        if not self.allowed_tokens:
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = None
        auth = request.headers.get("authorization") or request.headers.get(
            "Authorization"
        )
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

        if token and token in self.allowed_tokens:
            return await proceed(token, "header")

        if self.allow_url_tokens:
            url_token = request.query_params.get("token")
            if url_token and url_token in self.allowed_tokens:
                return await proceed(url_token, "query")

            segs = [s for s in path.split("/") if s != ""]
            if len(segs) >= 2 and segs[0] == _safe_name:
                candidate = segs[1]
                if candidate in self.allowed_tokens:
                    remainder = "/".join([_safe_name] + segs[2:])
                    new_path = "/" + (
                        remainder + "/"
                        if path.endswith("/") and not remainder.endswith("/")
                        else remainder
                    )
                    if new_path == BASE_PATH:
                        new_path = STREAM_PATH
                    request.scope["path"] = new_path
                    if "raw_path" in request.scope:
                        request.scope["raw_path"] = new_path.encode("utf-8")
                    return await proceed(candidate, "path")

        return JSONResponse(
            {"detail": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )


app.add_middleware(TokenAuthMiddleware)


def main():
    PORT = int(os.getenv("PORT", "8019"))
    logger.info(f"Starting {MCP_NAME} MCP server on port {PORT} at {STREAM_PATH}")
    uvicorn.run(
        app=app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=PORT,
        log_level=os.getenv("LOG_LEVEL", "info"),
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=120,
    )


if __name__ == "__main__":
    main()
