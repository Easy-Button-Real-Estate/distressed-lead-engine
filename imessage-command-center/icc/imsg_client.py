"""Subprocess wrapper for the imsg CLI.

Arguments are a list. Nothing is passed through a shell. The binary is
``imsg`` on PATH unless ICC_IMSG_BIN points at a test double.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


class ImsgError(RuntimeError):
    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@dataclass
class SendResult:
    state: str  # sent, not_started, uncertain
    detail: str


class ImsgClient:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("ICC_IMSG_BIN", "imsg")

    def run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if any(part in {"chat-create", "launch"} or part.startswith("--bb") for part in args):
            raise ImsgError("This tool does not use private iMessage APIs or SIP changes.")
        try:
            return subprocess.run(
                [self.binary, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise ImsgError(
                "imsg is not installed. On the Mac, the install script runs "
                "`brew install steipete/tap/imsg` only after you say yes."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            raise ImsgError("imsg timed out.", stderr=stdout + stderr) from exc

    def version(self) -> str:
        result = self.run(["--version"], timeout=15)
        if result.returncode != 0:
            raise ImsgError("imsg --version failed.", result.stderr.strip())
        return (result.stdout or result.stderr).strip()

    def json_lines(self, args: list[str], timeout: int = 30) -> list[dict]:
        result = self.run(args, timeout=timeout)
        if result.returncode != 0:
            raise ImsgError(
                result.stderr.strip() or "imsg failed.",
                result.stderr.strip(),
            )
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def chats(self, limit: int = 20) -> list[dict]:
        return self.json_lines(["chats", "--limit", str(limit), "--no-contacts", "--json"])

    def group(self, chat_id: int) -> dict:
        rows = self.json_lines(["group", "--chat-id", str(chat_id), "--json"])
        if not rows:
            raise ImsgError(f"No chat found for id {chat_id}.")
        return rows[0]

    def history(self, chat_id: int, limit: int = 50) -> list[dict]:
        return self.json_lines(
            [
                "history",
                "--chat-id",
                str(chat_id),
                "--limit",
                str(limit),
                "--no-contacts",
                "--json",
            ],
            timeout=30,
        )

    def send_text(self, text: str, chat_id: int | None = None, to: str | None = None) -> SendResult:
        if chat_id is None and not to:
            raise ImsgError("A send needs a command chat id or a recipient.")
        args = ["send", "--text", text, "--json"]
        if chat_id is not None:
            args.extend(["--chat-id", str(chat_id)])
        else:
            args.extend(["--to", to or ""])
        try:
            result = self.run(args, timeout=45)
        except ImsgError as exc:
            if "timed out" in str(exc):
                return SendResult("uncertain", "imsg timed out. Check Messages. This will not resend.")
            raise
        blob = f"{result.stdout}\n{result.stderr}"
        if "may_have_completed" in blob or "still_in_flight" in blob:
            return SendResult(
                "uncertain",
                "Messages did not confirm delivery. Check the chat. This will not resend.",
            )
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("status") == "sent":
                return SendResult("sent", "sent")
        if result.returncode != 0:
            detail = result.stderr.strip() or "imsg send failed before sending."
            return SendResult("not_started", detail)
        return SendResult(
            "uncertain",
            "imsg exited cleanly without a sent receipt. Check Messages. This will not resend.",
        )

    def watch(self, chat_id: int, since_rowid: int):
        """Start ``imsg watch``. Caller reads stdout and must terminate the process."""
        args = [
            self.binary,
            "watch",
            "--chat-id",
            str(chat_id),
            "--since-rowid",
            str(since_rowid),
            "--json",
        ]
        try:
            return subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ImsgError("imsg is not installed.") from exc
