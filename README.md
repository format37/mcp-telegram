# mcp-telegram

MCP server that lets an agent send notifications to a user via Telegram between
job stages. One tool, one parameter, one purpose.

## MCP Tool

**`send_telegram`** — Send a notification message to a Telegram chat.

Parameters:
- `message` (required): The text to send. No length limit — messages over
  Telegram's 4096-character cap are automatically sent as a `.txt` document
  attachment so nothing is dropped or truncated.
- `chat_id` (optional): Telegram chat ID. Defaults to `TELEGRAM_CHAT` from
  `.env` when omitted.

Returns a status string: `Sent text to chat <id>`, `Sent document (N chars) to
chat <id>`, or `Error: <reason>`.

## Setup

### 1. Telegram bot

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → grab the token
2. To find your chat ID:
   - Personal: message [@userinfobot](https://t.me/userinfobot)
   - Group: add the bot to the group, then visit
     `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending a message

### 2. Environment

Edit `.env` in the project root (already gitignored):

```
TELEGRAM_TOKEN=<your bot token>
TELEGRAM_CHAT=<your chat ID>
MCP_TOKENS=<long random string for auth>
MCP_NAME=telegram
PORT=8019
```

### 3. Docker

```bash
./compose.sh
```

Health check: `docker exec mcp-telegram curl -sf http://localhost:8019/health`

### 4. Caddy (reverse proxy)

Add to your Caddyfile inside the site block:

```
handle /telegram* {
    reverse_proxy mcp-telegram:8019
}
```

MCP endpoint: `https://your-domain.example.com/telegram/<MCP_TOKENS>/`

## Examples

### Manual smoke test (no MCP client needed)

```bash
python examples/send_message.py
```

Sends one short message via `sendMessage` and one long message via the
`sendDocument` fallback so you can confirm both paths work end-to-end.
