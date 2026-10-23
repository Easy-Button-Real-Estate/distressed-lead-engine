"""Approval rules for the command chat.

A side effect is allowed only after the latest matching reply in that
chat is an approval. The ask we sent does not count: it is prefixed and
it is on the sent-text list. A thumbs-up buried inside a longer text
does not count either. The reply has to be the approval line and nothing else.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

ASK_PREFIX = "[icc]"
EXPIRY = timedelta(hours=12)
KINDS = ("note", "imessage", "connector", "pipeline", "todo")

_SKIN = re.compile("[\U0001F3FB-\U0001F3FF]")
_DECISION = re.compile(
    r"^(yes|approve|approved|thumbs up|thumbsup|👍|no|nope|cancel|stop|deny)"
    r"(?: ([0-9a-f]{8}))?$"
)
_DENY = {"no", "nope", "cancel", "stop", "deny"}
_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ID = re.compile(r"^[0-9a-f]{8}$")

WAITING = {"awaiting_yes", "ask_uncertain", "approved", "released", "sending"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_action_id() -> str:
    return secrets.token_hex(4)


def parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(text: str) -> str:
    cleaned = text.replace("\uFE0F", "").replace("\u200d", "")
    cleaned = _SKIN.sub("", cleaned)
    cleaned = cleaned.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.rstrip(".!")


def parse_decision(text: str) -> tuple[str, str | None] | None:
    """Return (approve|deny, id or None) when the whole message is a decision."""
    if not isinstance(text, str) or text.startswith(ASK_PREFIX):
        return None
    match = _DECISION.fullmatch(normalize_text(text))
    if not match:
        return None
    word, action_id = match.group(1), match.group(2)
    kind = "deny" if word in _DENY else "approve"
    return kind, action_id


def valid_recipient(value: str) -> bool:
    return bool(_PHONE.fullmatch(value) or _EMAIL.fullmatch(value))


def valid_action_id(value: str) -> bool:
    return bool(_ID.fullmatch(value))


def build_ask(summary: str, action_id: str) -> str:
    return (
        "[icc] Nothing runs until you reply with one exact line.\n"
        f"{summary.strip()}\n"
        f"YES {action_id}\n"
        "or\n"
        f"👍 {action_id}\n"
        f"NO {action_id} cancels it."
    )


def validate_payload(payload: Any) -> str | None:
    """Return a plain-language error, or None when the payload can be frozen."""
    if not isinstance(payload, dict):
        return "The payload has to be a JSON object."
    kind = payload.get("kind")
    if kind not in KINDS:
        return "kind must be note, imessage, connector, pipeline, or todo."
    if kind == "note":
        return _text_field(payload, "detail", 2000, required=True)
    if kind == "imessage":
        recipient = payload.get("to")
        if not isinstance(recipient, str) or not valid_recipient(recipient.strip()):
            return "imessage to must be an E.164 number like +15555550123 or an email."
        error = _text_field(payload, "text", 1000, required=True)
        if error:
            return error
        if str(payload.get("text", "")).startswith(ASK_PREFIX):
            return "Outgoing texts cannot start with [icc]."
        return None
    if kind == "connector":
        for key, limit in (("app", 40), ("operation", 200), ("detail", 1000)):
            error = _short_line(payload, key, limit)
            if error:
                return error
        return None
    if kind == "pipeline":
        for key, limit in (("address", 200), ("status", 40), ("next_step", 200)):
            error = _short_line(payload, key, limit)
            if error:
                return error
        for key in ("owner", "notes"):
            value = payload.get(key, "")
            if not isinstance(value, str) or len(value) > 500:
                return f"pipeline {key} must be short text."
        return None
    items = payload.get("items")
    if isinstance(items, list):
        if payload.get("op") not in {None, "add"}:
            return "A list of to-dos can only be added."
        if not items or len(items) > 20:
            return "Send between 1 and 20 to-dos in one list."
        seen = set()
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item) > 200 or "\n" in item:
                return "Each to-do has to be one short line."
            key = item.strip().casefold()
            if key in seen:
                return "That list repeats a to-do."
            seen.add(key)
        return None
    op = payload.get("op")
    if op not in {"add", "done"}:
        return "todo op must be add or done."
    return _short_line(payload, "item", 200)


def _text_field(payload: dict, key: str, limit: int, required: bool) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or (required and not value.strip()):
        return f"Needs {key}."
    if len(value) > limit:
        return f"{key} is too long."
    return None


def _short_line(payload: dict, key: str, limit: int) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return f"Needs {key}."
    if len(value) > limit or "\n" in value or "\r" in value:
        return f"{key} is too long or has a line break."
    return None


def freeze_payload(payload: dict) -> dict:
    kind = payload["kind"]
    if kind == "note":
        return {"kind": "note", "detail": payload["detail"].strip()}
    if kind == "imessage":
        return {
            "kind": "imessage",
            "to": payload["to"].strip(),
            "text": payload["text"].strip(),
        }
    if kind == "connector":
        return {
            "kind": "connector",
            "app": payload["app"].strip(),
            "operation": payload["operation"].strip(),
            "detail": payload["detail"].strip(),
        }
    if kind == "pipeline":
        return {
            "kind": "pipeline",
            "address": payload["address"].strip(),
            "status": payload["status"].strip(),
            "next_step": payload["next_step"].strip(),
            "owner": str(payload.get("owner", "")).strip(),
            "notes": str(payload.get("notes", "")).strip(),
        }
    if isinstance(payload.get("items"), list):
        return {
            "kind": "todo",
            "op": "add",
            "items": [item.strip() for item in payload["items"]],
        }
    return {"kind": "todo", "op": payload["op"], "item": payload["item"].strip()}


def message_text(message: dict) -> str:
    text = message.get("text")
    return text if isinstance(text, str) else ""


def is_ignored_message(message: dict, sent_guids: set[str], sent_bodies: set[str]) -> bool:
    if not isinstance(message, dict):
        return True
    if message.get("is_from_me") is not True:
        return True
    if message.get("is_reaction") is True:
        return True
    if message.get("type") in {"edited", "unsent"}:
        return True
    guid = message.get("guid")
    if isinstance(guid, str) and guid in sent_guids:
        return True
    text = message_text(message)
    if text.startswith(ASK_PREFIX):
        return True
    if text in sent_bodies:
        return True
    return False


def is_expired(proposal: dict, now: datetime) -> bool:
    try:
        created = parse_time(proposal["created_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return now - created > EXPIRY


def evaluate(
    proposal: dict,
    messages: list[dict],
    sent_guids: set[str],
    sent_bodies: set[str],
    now: datetime,
    sole_pending: bool,
) -> dict[str, str]:
    """Latest matching reply wins. A later NO cancels an earlier YES."""
    if is_expired(proposal, now):
        return {
            "state": "expired",
            "reason": "This request is more than 12 hours old. Ask again.",
        }
    try:
        created = parse_time(proposal["created_at"])
    except (KeyError, TypeError, ValueError):
        return {"state": "expired", "reason": "This request has no timestamp."}

    ask_id = proposal.get("ask_message_id")
    decisions: list[tuple[int, str, str, str]] = []
    for message in messages:
        if is_ignored_message(message, sent_guids, sent_bodies):
            continue
        message_id = message.get("id")
        if not isinstance(message_id, int):
            continue
        if isinstance(ask_id, int) and message_id <= ask_id:
            continue
        created_at = message.get("created_at")
        stamp = created_at if isinstance(created_at, str) else ""
        if not isinstance(ask_id, int):
            if not stamp:
                continue
            try:
                if parse_time(stamp) <= created:
                    continue
            except ValueError:
                continue
        parsed = parse_decision(message_text(message))
        if parsed is None:
            continue
        kind, action_id = parsed
        if action_id is None:
            if not sole_pending:
                continue
            action_id = str(proposal["id"])
        if action_id != proposal["id"]:
            continue
        guid = message.get("guid")
        decisions.append((message_id, stamp, kind, guid if isinstance(guid, str) else ""))

    if not decisions:
        return {"state": "pending", "reason": "No thumbs-up in the command chat yet."}
    decisions.sort()
    _, _, kind, guid = decisions[-1]
    if kind == "deny":
        return {
            "state": "denied",
            "reason": "You cancelled it in the command chat.",
            "guid": guid,
        }
    return {
        "state": "approved",
        "reason": "You approved it in the command chat.",
        "guid": guid,
    }
