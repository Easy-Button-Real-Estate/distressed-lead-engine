"""Command line for the iMessage Command Center gate."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from icc.gate import (
    ASK_PREFIX,
    build_ask,
    evaluate,
    freeze_payload,
    iso,
    is_ignored_message,
    new_action_id,
    parse_decision,
    utcnow,
    valid_action_id,
    validate_payload,
)
from icc.imsg_client import ImsgClient, ImsgError
from icc.store import Store

QUESTION_CAP = 30


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store()
    client = ImsgClient()
    try:
        return args.func(args, store, client)
    except ImsgError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1
    except BrokenPipeError:
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="icc",
        description="Queue real-estate texts and refuse every side effect until the command chat says YES.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check the Mac bridge without reading message bodies.")
    doctor.set_defaults(func=cmd_doctor)

    chats = sub.add_parser("chats", help="List recent chats so you can pick the command chat.")
    chats.add_argument("--limit", type=int, default=20)
    chats.set_defaults(func=cmd_chats)

    use_chat = sub.add_parser("use-chat", help="Save the command chat id after imsg confirms it exists.")
    use_chat.add_argument("--id", type=int, required=True)
    use_chat.set_defaults(func=cmd_use_chat)

    propose = sub.add_parser("propose", help="Text the approval ask to the command chat and wait.")
    propose.add_argument("--summary", required=True)
    propose.add_argument("--payload", required=True, help="Path to a JSON file, or - for stdin.")
    propose.set_defaults(func=cmd_propose)

    pending = sub.add_parser("pending", help="List requests that are still open.")
    pending.set_defaults(func=cmd_pending)

    release = sub.add_parser("release", help="Check the command chat. Does not perform the action.")
    release.add_argument("--id", required=True)
    release.set_defaults(func=cmd_release)

    commit = sub.add_parser("commit", help="Perform a local or iMessage action after a fresh YES check.")
    commit.add_argument("--id", required=True)
    commit.set_defaults(func=cmd_commit)

    finish = sub.add_parser("finish", help="Close a connector action after you did that exact step.")
    finish.add_argument("--id", required=True)
    finish.set_defaults(func=cmd_finish)

    reply = sub.add_parser("reply", help="Send a result to the command chat after approval.")
    reply.add_argument("--text", required=True)
    reply.add_argument("--id")
    reply.add_argument("--question", action="store_true")
    reply.set_defaults(func=cmd_reply)

    inbox = sub.add_parser("inbox", help="Show command-chat texts that are not approval lines.")
    inbox.set_defaults(func=cmd_inbox)

    ack = sub.add_parser("ack", help="Mark an inbox text as handled after you propose it.")
    ack.add_argument("--guid", required=True)
    ack.set_defaults(func=cmd_ack)

    watch = sub.add_parser("watch", help="Queue new texts from the command chat. Sends nothing.")
    watch.set_defaults(func=cmd_watch)

    sync = sub.add_parser("sync", help="Queue command-chat texts since the last check. Sends nothing.")
    sync.set_defaults(func=cmd_sync)

    pipeline = sub.add_parser("pipeline", help="Print the local pipeline. Read only.")
    pipeline.set_defaults(func=cmd_pipeline)

    todos = sub.add_parser("todos", help="Print the local to-do list. Read only.")
    todos.set_defaults(func=cmd_todos)

    return parser


def cmd_doctor(_args, store: Store, client: ImsgClient) -> int:
    info: dict[str, Any] = {
        "ok": True,
        "platform": sys.platform,
        "chat_id": store.chat_id(),
        "state_dir": str(store.root),
    }
    if sys.platform != "darwin":
        info["ok"] = False
        info["imsg"] = "not checked: imsg sends and reads Messages only on macOS."
        _emit(info)
        return 1
    try:
        info["imsg_version"] = client.version()
        client.chats(limit=1)
        info["messages_db"] = "readable"
    except ImsgError as exc:
        info["ok"] = False
        info["messages_db"] = "not readable"
        info["error"] = str(exc)
        info["fix"] = (
            "System Settings → Privacy & Security → Full Disk Access. "
            "Add Terminal and the imsg binary, quit Terminal, and open it again. "
            "Sending later needs Automation permission for Messages."
        )
        _emit(info)
        return 1
    _emit(info)
    return 0


def cmd_chats(args, _store: Store, client: ImsgClient) -> int:
    limit = args.limit if args.limit and args.limit > 0 else 20
    rows = []
    for chat in client.chats(limit=limit):
        rows.append(
            {
                "id": chat.get("id"),
                "name": chat.get("display_name") or chat.get("name"),
                "service": chat.get("service"),
                "is_group": chat.get("is_group"),
            }
        )
    _emit({"ok": True, "chats": rows})
    return 0


def cmd_use_chat(args, store: Store, client: ImsgClient) -> int:
    if args.id <= 0:
        _emit({"ok": False, "error": "Chat id has to be a positive number from `icc chats`."})
        return 2
    chat = client.group(args.id)
    store.save_config({"chat_id": args.id, "bridge": "imsg"})
    store.audit("use_chat", chat_id=args.id, name=chat.get("name"))
    _emit({"ok": True, "chat_id": args.id, "name": chat.get("display_name") or chat.get("name")})
    return 0


def cmd_propose(args, store: Store, client: ImsgClient) -> int:
    summary = " ".join(args.summary.split())
    if not summary or len(summary) > 500:
        _emit({"ok": False, "error": "Summary has to be one short paragraph."})
        return 2
    if summary.startswith(ASK_PREFIX):
        _emit({"ok": False, "error": "Summary cannot start with [icc]."})
        return 2
    payload = _load_payload(args.payload)
    if isinstance(payload, str):
        _emit({"ok": False, "error": payload})
        return 2
    error = validate_payload(payload)
    if error:
        _emit({"ok": False, "error": error})
        return 2
    chat_id = store.chat_id()
    if chat_id is None:
        _emit({"ok": False, "error": "No command chat yet. Run `icc use-chat --id` after you pick one."})
        return 1
    action_id = new_action_id()
    ask = build_ask(summary, action_id)
    proposal = {
        "id": action_id,
        "summary": summary,
        "payload": freeze_payload(payload),
        "status": "ask_failed",
        "created_at": iso(utcnow()),
        "ask_message_id": None,
        "ask_text": ask,
        "reply_count": 0,
    }
    store.put_proposal(proposal)
    result = client.send_text(ask, chat_id=chat_id)
    if result.state == "not_started":
        store.audit("propose_failed", action_id=action_id, detail=result.detail)
        _emit({"ok": False, "id": action_id, "status": "ask_failed", "error": result.detail})
        return 1
    store.remember_sent(ask)
    proposal["status"] = "awaiting_yes" if result.state == "sent" else "ask_uncertain"
    store.put_proposal(proposal)
    if result.state == "sent":
        try:
            history = client.history(chat_id, limit=20)
        except ImsgError:
            history = []
        match = None
        for message in history:
            if message.get("text") == ask and isinstance(message.get("id"), int):
                if match is None or message["id"] > match["id"]:
                    match = message
        if match is not None:
            proposal["ask_message_id"] = match["id"]
            if isinstance(match.get("guid"), str):
                store.remember_sent(ask, match["guid"])
            store.put_proposal(proposal)
    store.audit("propose", action_id=action_id, kind=proposal["payload"]["kind"], status=proposal["status"])
    _emit(
        {
            "ok": result.state == "sent",
            "id": action_id,
            "status": proposal["status"],
            "detail": result.detail,
            "message": "Waiting for YES "
            + action_id
            + " in the command chat. Nothing else has run.",
        }
    )
    return 0 if result.state == "sent" else 4


def cmd_pending(_args, store: Store, _client: ImsgClient) -> int:
    rows = [
        {
            "id": proposal["id"],
            "status": proposal.get("status"),
            "summary": proposal.get("summary"),
            "kind": (proposal.get("payload") or {}).get("kind"),
            "created_at": proposal.get("created_at"),
        }
        for proposal in store.proposals().values()
    ]
    rows.sort(key=lambda row: str(row.get("created_at") or ""))
    _emit({"ok": True, "pending": rows})
    return 0


def cmd_release(args, store: Store, client: ImsgClient) -> int:
    proposal = _require_proposal(store, args.id)
    if isinstance(proposal, int):
        return proposal
    if proposal.get("status") in {"done", "uncertain"}:
        _emit(
            {
                "ok": proposal["status"] == "done",
                "id": proposal["id"],
                "status": proposal["status"],
                "already_done": proposal["status"] == "done",
                "message": "Already closed. Do not do it again.",
            }
        )
        return 0 if proposal["status"] == "done" else 4
    decision = _refresh(store, client, proposal)
    _emit(
        {
            "ok": decision["state"] == "approved",
            "id": proposal["id"],
            "status": proposal["status"],
            "state": decision["state"],
            "reason": decision["reason"],
            "payload": proposal["payload"] if decision["state"] == "approved" else None,
        }
    )
    return _state_code(decision["state"])


def cmd_commit(args, store: Store, client: ImsgClient) -> int:
    proposal = _require_proposal(store, args.id)
    if isinstance(proposal, int):
        return proposal
    status = proposal.get("status")
    if status in {"done", "uncertain"}:
        _emit(
            {
                "ok": status == "done",
                "id": proposal["id"],
                "status": status,
                "already_done": status == "done",
                "payload": proposal["payload"],
                "message": "Already finished. Do not do it again.",
            }
        )
        return 0 if status == "done" else 4
    if status == "sending":
        proposal["status"] = "uncertain"
        store.put_proposal(proposal)
        store.audit("uncertain", action_id=proposal["id"])
        _emit(
            {
                "ok": False,
                "id": proposal["id"],
                "status": "uncertain",
                "message": "A send may already have gone out. Check Messages. This will not send it again.",
            }
        )
        return 4
    decision = _refresh(store, client, proposal)
    if decision["state"] != "approved":
        _emit(
            {
                "ok": False,
                "id": proposal["id"],
                "status": proposal["status"],
                "state": decision["state"],
                "reason": decision["reason"],
            }
        )
        return _state_code(decision["state"])

    payload = proposal["payload"]
    kind = payload["kind"]
    if kind == "connector":
        if proposal.get("status") == "released":
            _emit(
                {
                    "ok": True,
                    "id": proposal["id"],
                    "status": "released",
                    "already_released": True,
                    "payload": payload,
                    "message": "Already released. Do not run this connector step again.",
                }
            )
            return 0
        proposal["status"] = "released"
        store.put_proposal(proposal)
        store.audit("released", action_id=proposal["id"], kind=kind)
        _emit(
            {
                "ok": True,
                "id": proposal["id"],
                "status": "released",
                "already_released": False,
                "payload": payload,
                "message": "Approved for this connector step only. Do that step, reply, then `icc finish`.",
            }
        )
        return 0

    if kind == "imessage":
        proposal["status"] = "sending"
        store.put_proposal(proposal)
        result = client.send_text(payload["text"], to=payload["to"])
        if result.state == "sent":
            proposal["status"] = "done"
            store.put_proposal(proposal)
            store.audit("sent", action_id=proposal["id"], to=payload["to"])
            _emit({"ok": True, "id": proposal["id"], "status": "done", "to": payload["to"]})
            return 0
        if result.state == "not_started":
            proposal["status"] = "approved"
            store.put_proposal(proposal)
            _emit({"ok": False, "id": proposal["id"], "status": "approved", "error": result.detail})
            return 1
        proposal["status"] = "uncertain"
        store.put_proposal(proposal)
        store.audit("uncertain", action_id=proposal["id"], detail=result.detail)
        _emit({"ok": False, "id": proposal["id"], "status": "uncertain", "error": result.detail})
        return 4

    if kind == "pipeline":
        store.upsert_pipeline(payload, iso(utcnow()))
    elif kind == "todo":
        error = store.apply_todo(payload, iso(utcnow()))
        if error:
            _emit({"ok": False, "id": proposal["id"], "status": "approved", "error": error})
            return 1
    proposal["status"] = "done"
    store.put_proposal(proposal)
    store.audit("done", action_id=proposal["id"], kind=kind)
    _emit({"ok": True, "id": proposal["id"], "status": "done", "payload": payload})
    return 0


def cmd_finish(args, store: Store, client: ImsgClient) -> int:
    proposal = _require_proposal(store, args.id)
    if isinstance(proposal, int):
        return proposal
    if proposal["payload"]["kind"] != "connector":
        _emit({"ok": False, "error": "finish is only for connector actions. Use commit for the others."})
        return 2
    if proposal.get("status") == "done":
        _emit({"ok": True, "id": proposal["id"], "status": "done", "already_done": True})
        return 0
    decision = _refresh(store, client, proposal)
    if decision["state"] != "approved":
        _emit({"ok": False, "id": proposal["id"], "status": proposal["status"], "reason": decision["reason"]})
        return _state_code(decision["state"])
    proposal["status"] = "done"
    store.put_proposal(proposal)
    store.audit("finished", action_id=proposal["id"])
    _emit({"ok": True, "id": proposal["id"], "status": "done"})
    return 0


def cmd_reply(args, store: Store, client: ImsgClient) -> int:
    text = args.text.strip()
    if not text or len(text) > 1500:
        _emit({"ok": False, "error": "Reply text has to be short."})
        return 2
    chat_id = store.chat_id()
    if chat_id is None:
        _emit({"ok": False, "error": "No command chat yet."})
        return 1
    if args.question:
        if args.id:
            _emit({"ok": False, "error": "A question does not take an action id."})
            return 2
        if not text.endswith("?"):
            _emit({"ok": False, "error": "A question has to end with ?"})
            return 2
        if store.question_count_today() >= QUESTION_CAP:
            _emit({"ok": False, "error": "Question cap reached for today. Wait, or propose a note."})
            return 1
        body = text if text.startswith(ASK_PREFIX) else f"{ASK_PREFIX} {text}"
        return _send_command_chat(store, client, chat_id, body, event="question")
    if not args.id or not valid_action_id(args.id):
        _emit({"ok": False, "error": "A result reply needs --id of an approved action."})
        return 2
    proposal = _require_proposal(store, args.id)
    if isinstance(proposal, int):
        return proposal
    if proposal.get("status") not in {"approved", "released", "done"}:
        _emit({"ok": False, "error": "That action is not approved, so this reply was not sent."})
        return 1
    if int(proposal.get("reply_count") or 0) >= 5:
        _emit({"ok": False, "error": "Reply cap reached for this action."})
        return 1
    body = text if text.startswith(ASK_PREFIX) else f"{ASK_PREFIX} {text}"
    code = _send_command_chat(store, client, chat_id, body, event="reply", action_id=proposal["id"])
    if code == 0:
        proposal["reply_count"] = int(proposal.get("reply_count") or 0) + 1
        store.put_proposal(proposal)
    return code


def cmd_inbox(_args, store: Store, _client: ImsgClient) -> int:
    _emit({"ok": True, "commands": store.unacked()})
    return 0


def cmd_ack(args, store: Store, _client: ImsgClient) -> int:
    if not store.ack(args.guid):
        _emit({"ok": False, "error": "No inbox row has that guid."})
        return 1
    _emit({"ok": True, "guid": args.guid})
    return 0


def cmd_sync(_args, store: Store, client: ImsgClient) -> int:
    chat_id = store.chat_id()
    if chat_id is None:
        _emit({"ok": False, "error": "No command chat yet."})
        return 1
    messages = client.history(chat_id, limit=50)
    ids = [message["id"] for message in messages if isinstance(message.get("id"), int)]
    if store.cursor() == 0:
        store.save_cursor(max(ids) if ids else 0)
        _emit(
            {
                "ok": True,
                "queued": 0,
                "cursor": store.cursor(),
                "message": "Caught up to the latest text. Messages already in the chat were not queued.",
            }
        )
        return 0
    queued = 0
    for message in sorted(messages, key=lambda row: row.get("id") if isinstance(row.get("id"), int) else 0):
        message_id = message.get("id")
        if not isinstance(message_id, int) or message_id <= store.cursor():
            continue
        if _consume_watch_line(store, chat_id, json.dumps(message), echo=False):
            queued += 1
    _emit({"ok": True, "queued": queued, "cursor": store.cursor()})
    return 0


def cmd_watch(_args, store: Store, client: ImsgClient) -> int:
    chat_id = store.chat_id()
    if chat_id is None:
        _emit({"ok": False, "error": "No command chat yet. Watching would see every chat, so it stays off."})
        return 1
    process = client.watch(chat_id, store.cursor())
    assert process.stdout is not None
    code = 0
    try:
        for line in process.stdout:
            _consume_watch_line(store, chat_id, line, echo=True)
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        code = 0
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
        if process.poll() is None:
            process.wait(timeout=5)
    return code


def cmd_pipeline(_args, store: Store, _client: ImsgClient) -> int:
    _emit({"ok": True, "pipeline": store.read_pipeline()})
    return 0


def cmd_todos(_args, store: Store, _client: ImsgClient) -> int:
    _emit({"ok": True, "todos": store.read_todos()})
    return 0


def _consume_watch_line(store: Store, chat_id: int, line: str, echo: bool = False) -> bool:
    line = line.strip()
    if not line:
        return False
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(message, dict):
        return False
    message_id = message.get("id")
    if message.get("type") not in {"edited", "unsent"} and isinstance(message_id, int):
        if message_id > store.cursor():
            store.save_cursor(message_id)
    if message.get("chat_id") not in (None, chat_id):
        return False
    if is_ignored_message(message, store.sent_guids(), store.sent_bodies()):
        return False
    text = message.get("text") if isinstance(message.get("text"), str) else ""
    if not text.strip() or parse_decision(text) is not None:
        return False
    if not store.append_inbox(message):
        return False
    if echo:
        print(json.dumps({"queued": message.get("guid") or message_id}), flush=True)
    return True


def _send_command_chat(store, client, chat_id, body, event, action_id=None) -> int:
    result = client.send_text(body, chat_id=chat_id)
    if result.state == "sent":
        store.remember_sent(body)
        store.audit(event, action_id=action_id)
        _emit({"ok": True, "status": "sent"})
        return 0
    if result.state == "not_started":
        _emit({"ok": False, "error": result.detail})
        return 1
    store.remember_sent(body)
    store.audit("uncertain", action_id=action_id, detail=result.detail)
    _emit({"ok": False, "status": "uncertain", "error": result.detail})
    return 4


def _refresh(store: Store, client: ImsgClient, proposal: dict) -> dict:
    if proposal.get("status") == "ask_failed":
        return {"state": "pending", "reason": "The approval text never sent. Nothing is waiting."}
    if proposal.get("status") in {"done", "uncertain", "sending"}:
        return {"state": "pending", "reason": "That request is already closed."}
    chat_id = store.chat_id()
    if chat_id is None:
        return {"state": "pending", "reason": "No command chat is configured."}
    messages = client.history(chat_id, limit=100)
    decision = evaluate(
        proposal,
        messages,
        store.sent_guids(),
        store.sent_bodies(),
        utcnow(),
        store.sole_pending(),
    )
    if decision["state"] == "denied":
        proposal["status"] = "denied"
    elif decision["state"] == "expired":
        proposal["status"] = "expired"
    elif decision["state"] == "approved" and proposal.get("status") != "released":
        proposal["status"] = "approved"
    store.put_proposal(proposal)
    return decision


def _require_proposal(store: Store, action_id: str) -> dict | int:
    if not valid_action_id(action_id):
        _emit({"ok": False, "error": "Action id must be the 8-character id from the approval text."})
        return 2
    proposal = store.get_proposal(action_id)
    if proposal is None:
        _emit({"ok": False, "error": "No request has that id."})
        return 1
    return proposal


def _load_payload(path: str) -> dict | str:
    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            with open(path, encoding="utf-8") as handle:
                raw = handle.read()
        loaded = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return f"Could not read the payload JSON: {exc}"
    if not isinstance(loaded, dict):
        return "The payload has to be a JSON object."
    return loaded


def _state_code(state: str) -> int:
    if state == "approved":
        return 0
    if state == "denied":
        return 3
    if state == "expired":
        return 4
    return 1


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)
