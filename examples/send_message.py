"""Standalone Telegram bot test — exercises the underlying API the MCP tool wraps.

Run from the repo root:
    python examples/send_message.py

Reads TELEGRAM_TOKEN and TELEGRAM_CHAT from .env. Sends both a short message
(via sendMessage) and a long one (via sendDocument fallback) so you can confirm
both delivery paths work for your bot/chat before exercising the MCP endpoint.
"""

import os
import sys
from pathlib import Path

# Make backend/ importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv  # noqa: E402

from telegram_tools import send_to_telegram  # noqa: E402


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.getenv("TELEGRAM_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT", "")
    if not token or not chat:
        print("Error: TELEGRAM_TOKEN and TELEGRAM_CHAT must be set in .env")
        sys.exit(1)

    print("[1/2] Short message via sendMessage...")
    print("  ", send_to_telegram("Hello from mcp-telegram smoke test.", chat, token))

    print("[2/2] Long message via sendDocument fallback...")
    long_msg = "This is a long message. " * 250  # ~6000 chars, exceeds 4096 limit
    print("  ", send_to_telegram(long_msg, chat, token))


if __name__ == "__main__":
    main()
