#!/usr/bin/env python3
"""Stand-in for the imsg CLI. Tests point ICC_IMSG_BIN here."""

from __future__ import annotations

import json
import os
import sys


def _history() -> None:
    path = os.environ.get("ICC_FAKE_HISTORY_FILE", "")
    if path and os.path.exists(path):
        sys.stdout.write(PathText(path))


def PathText(path: str) -> str:
    text = open(path, encoding="utf-8").read()
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        print("imsg 0.test")
        return 0
    if "watch" in args:
        path = os.environ.get("ICC_FAKE_WATCH_FILE", "")
        if path and os.path.exists(path):
            sys.stdout.write(PathText(path))
        return 0
    if "history" in args:
        _history()
        return 0
    if "send" in args:
        text = args[args.index("--text") + 1] if "--text" in args else ""
        target = args[args.index("--to") + 1] if "--to" in args else ""
        chat = args[args.index("--chat-id") + 1] if "--chat-id" in args else ""
        path = os.environ.get("ICC_FAKE_SENT_FILE", "")
        if path:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"text": text, "to": target, "chat_id": chat}) + "\n")
        mode = os.environ.get("ICC_FAKE_SEND", "sent")
        if mode == "uncertain":
            print('{"disposition":"may_have_completed"}')
            return 1
        if mode == "fail":
            print("send failed before it started", file=sys.stderr)
            return 1
        print('{"status":"sent"}')
        return 0
    if "chats" in args:
        print(
            json.dumps(
                {
                    "id": 7,
                    "name": "Command Center",
                    "display_name": "Command Center",
                    "service": "iMessage",
                    "is_group": True,
                }
            )
        )
        return 0
    if "group" in args:
        chat_id = args[args.index("--chat-id") + 1]
        if chat_id != "7":
            print("no chat", file=sys.stderr)
            return 1
        print(json.dumps({"id": 7, "name": "Command Center", "display_name": "Command Center"}))
        return 0
    print("unexpected " + " ".join(args), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
