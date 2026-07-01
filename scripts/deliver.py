#!/usr/bin/env python3
"""
deliver.py — send redline outputs (summary + files) via Telegram or email.

Usage:
    python3 deliver.py --method telegram --files a.html,b.docx --summary "..." [--chat-id 123456]
    python3 deliver.py --method email --to user@example.com --files a.html,b.docx --summary "..."

Reads TELEGRAM_BOT_TOKEN / RESEND_API_KEY from ~/.redline/.env (simple KEY=VALUE lines,
'#' comments ignored). If a config.json exists with a saved chatId/email, that's used
unless overridden by --chat-id / --to.

Exits non-zero with a clear message if the required key is missing — callers (SKILL.md
Step 7) should treat that as "delivery failed, fall back to local file paths."
"""
import argparse
import base64
import json
import os
import sys

CONFIG_DIR = os.path.expanduser("~/.redline")
ENV_PATH = os.path.join(CONFIG_DIR, ".env")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def deliver_telegram(files, summary, chat_id, env):
    import requests

    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in ~/.redline/.env", file=sys.stderr)
        sys.exit(1)
    if not chat_id:
        print("ERROR: no Telegram chat ID (pass --chat-id or set delivery.chatId in config.json)", file=sys.stderr)
        sys.exit(1)

    base = f"https://api.telegram.org/bot{token}"

    if summary:
        resp = requests.post(f"{base}/sendMessage", data={"chat_id": chat_id, "text": summary})
        if not resp.ok:
            print(f"ERROR: sendMessage failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)

    for path in files:
        if not os.path.exists(path):
            print(f"WARNING: file not found, skipping: {path}", file=sys.stderr)
            continue
        with open(path, "rb") as f:
            resp = requests.post(
                f"{base}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": (os.path.basename(path), f)},
            )
        if not resp.ok:
            print(f"ERROR: sendDocument failed for {path}: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)

    print(f"Delivered {len(files)} file(s) + summary to Telegram chat {chat_id}.")


def deliver_email(files, summary, to_address, env):
    import requests

    api_key = env.get("RESEND_API_KEY")
    if not api_key:
        print("ERROR: RESEND_API_KEY not set in ~/.redline/.env", file=sys.stderr)
        sys.exit(1)
    if not to_address:
        print("ERROR: no recipient email (pass --to or set delivery.email in config.json)", file=sys.stderr)
        sys.exit(1)

    attachments = []
    for path in files:
        if not os.path.exists(path):
            print(f"WARNING: file not found, skipping: {path}", file=sys.stderr)
            continue
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")
        attachments.append({"filename": os.path.basename(path), "content": content})

    payload = {
        "from": env.get("RESEND_FROM", "redline@resend.dev"),
        "to": [to_address],
        "subject": "Your redline is ready",
        "text": summary or "See attached redline files.",
        "attachments": attachments,
    }
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    if not resp.ok:
        print(f"ERROR: Resend API call failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(f"Delivered {len(attachments)} file(s) + summary to {to_address}.")


def main():
    parser = argparse.ArgumentParser(description="Deliver redline outputs via Telegram or email.")
    parser.add_argument("--method", required=True, choices=["telegram", "email"])
    parser.add_argument("--files", required=True, help="Comma-separated list of file paths to attach.")
    parser.add_argument("--summary", default="", help="Summary text to send alongside the files.")
    parser.add_argument("--chat-id", help="Telegram chat ID (overrides config.json).")
    parser.add_argument("--to", help="Email recipient (overrides config.json).")
    args = parser.parse_args()

    files = [f.strip() for f in args.files.split(",") if f.strip()]
    env = load_env()
    config = load_config()
    delivery_cfg = config.get("delivery", {})

    if args.method == "telegram":
        chat_id = args.chat_id or delivery_cfg.get("chatId")
        deliver_telegram(files, args.summary, chat_id, env)
    else:
        to_address = args.to or delivery_cfg.get("email")
        deliver_email(files, args.summary, to_address, env)


if __name__ == "__main__":
    main()
