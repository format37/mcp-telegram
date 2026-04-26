"""Core logic: send a message to Telegram, with document fallback for long messages."""

import io
from datetime import datetime, timezone

import httpx

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4096
HTTP_TIMEOUT = 30.0


def send_to_telegram(message: str, chat_id: str, token: str) -> str:
    """Send `message` to `chat_id` via the Telegram Bot API.

    Messages within the 4096-character limit go through sendMessage. Longer
    messages are uploaded as a UTF-8 .txt document via sendDocument so the full
    content is preserved.

    Returns a human-readable status string. Raises httpx.HTTPError on transport
    failures; surfaces Telegram API errors as the returned string.
    """
    if not message:
        return "Error: empty message"

    if len(message) <= MAX_MESSAGE_CHARS:
        return _send_text(message, chat_id, token)
    return _send_document(message, chat_id, token)


def _send_text(message: str, chat_id: str, token: str) -> str:
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.post(url, data={"chat_id": chat_id, "text": message})
    return _format_response(resp, chat_id, "text")


def _send_document(message: str, chat_id: str, token: str) -> str:
    url = f"{TELEGRAM_API}/bot{token}/sendDocument"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"notification_{ts}.txt"
    payload = io.BytesIO(message.encode("utf-8"))
    files = {"document": (filename, payload, "text/plain; charset=utf-8")}
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.post(url, data={"chat_id": chat_id}, files=files)
    return _format_response(resp, chat_id, f"document ({len(message)} chars)")


def _format_response(resp: httpx.Response, chat_id: str, kind: str) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"Error: Telegram returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}"
    if resp.is_success and body.get("ok"):
        return f"Sent {kind} to chat {chat_id}"
    description = body.get("description", "unknown error")
    return f"Error: Telegram API rejected request (HTTP {resp.status_code}): {description}"
