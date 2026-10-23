"""On-disk queue, proposals, pipeline, and to-dos. Mode 0600."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from icc.gate import WAITING, is_expired, utcnow
from icc.paths import ensure_state_dir, state_dir

PIPELINE_FIELDS = ["address", "status", "next_step", "owner", "notes", "updated_at"]


def _iso(moment: datetime | None = None) -> str:
    current = moment or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ensure_state_dir()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / name

    def _read_json(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, name: str, payload: Any) -> None:
        path = self._path(name)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def config(self) -> dict:
        data = self._read_json("config.json", {})
        if not isinstance(data, dict):
            return {}
        return data

    def save_config(self, updates: dict) -> dict:
        current = self.config()
        current.update(updates)
        self._write_json("config.json", current)
        return current

    def chat_id(self) -> int | None:
        value = self.config().get("chat_id")
        if isinstance(value, int) and value > 0:
            return value
        return None

    def proposals(self) -> dict[str, dict]:
        data = self._read_json("proposals.json", {})
        if not isinstance(data, dict):
            return {}
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}

    def save_proposals(self, proposals: dict[str, dict]) -> None:
        self._write_json("proposals.json", proposals)

    def get_proposal(self, action_id: str) -> dict | None:
        return self.proposals().get(action_id)

    def put_proposal(self, proposal: dict) -> None:
        proposals = self.proposals()
        proposals[proposal["id"]] = proposal
        self.save_proposals(proposals)

    def sent_guids(self) -> set[str]:
        return {row["guid"] for row in self._sent_rows() if isinstance(row.get("guid"), str)}

    def sent_bodies(self) -> set[str]:
        return {row["text"] for row in self._sent_rows() if isinstance(row.get("text"), str)}

    def _sent_rows(self) -> list[dict]:
        path = self._path("sent.jsonl")
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def remember_sent(self, text: str, guid: str | None = None) -> None:
        path = self._path("sent.jsonl")
        row = {"text": text, "guid": guid, "at": _iso()}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        os.chmod(path, 0o600)

    def audit(self, event: str, **fields: Any) -> None:
        path = self._path("audit.jsonl")
        row = {"at": _iso(), "event": event, **fields}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)

    def cursor(self) -> int:
        path = self._path("cursor.txt")
        if not path.exists():
            return 0
        raw = path.read_text(encoding="utf-8").strip()
        try:
            value = int(raw)
        except ValueError:
            return 0
        return value if value >= 0 else 0

    def save_cursor(self, value: int) -> None:
        path = self._path("cursor.txt")
        path.write_text(str(value) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def append_inbox(self, message: dict) -> bool:
        """Queue a user command. Return False when that guid is already queued."""
        guid = message.get("guid")
        existing = self._inbox_rows()
        if isinstance(guid, str) and any(row.get("guid") == guid for row in existing):
            return False
        path = self._path("inbox.jsonl")
        row = {
            "guid": guid,
            "message_id": message.get("id"),
            "text": message.get("text") or "",
            "created_at": message.get("created_at"),
            "chat_id": message.get("chat_id"),
            "acked": False,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
        return True

    def _inbox_rows(self) -> list[dict]:
        path = self._path("inbox.jsonl")
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def unacked(self) -> list[dict]:
        return [row for row in self._inbox_rows() if not row.get("acked")]

    def ack(self, guid: str) -> bool:
        rows = self._inbox_rows()
        found = False
        for row in rows:
            if row.get("guid") == guid:
                row["acked"] = True
                found = True
        if not found:
            return False
        path = self._path("inbox.jsonl")
        body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o600)
        return True

    def sole_pending(self, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        waiting = [
            proposal
            for proposal in self.proposals().values()
            if proposal.get("status") in WAITING and not is_expired(proposal, moment)
        ]
        return len(waiting) == 1

    def upsert_pipeline(self, payload: dict, when: str) -> None:
        path = self._path("pipeline.csv")
        rows: list[dict[str, str]] = []
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        target = payload["address"].casefold()
        updated = {
            "address": payload["address"],
            "status": payload["status"],
            "next_step": payload["next_step"],
            "owner": payload.get("owner", ""),
            "notes": payload.get("notes", ""),
            "updated_at": when,
        }
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("address", "")).casefold() == target:
                rows[index] = updated
                replaced = True
                break
        if not replaced:
            rows.append(updated)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PIPELINE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        os.chmod(path, 0o600)

    def read_pipeline(self) -> list[dict[str, str]]:
        path = self._path("pipeline.csv")
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def apply_todo(self, payload: dict, when: str) -> str | None:
        path = self._path("todos.json")
        items: list[dict] = []
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                items = [row for row in loaded if isinstance(row, dict)]
        if isinstance(payload.get("items"), list):
            keys = {item.casefold() for item in payload["items"]}
            open_keys = {
                str(row.get("item", "")).casefold() for row in items if not row.get("done")
            }
            overlap = keys & open_keys
            if overlap:
                return "One of those to-dos is already open: " + ", ".join(sorted(overlap))
            for item in payload["items"]:
                items.append({"item": item, "done": False, "updated_at": when})
            path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            return None
        item = payload["item"]
        key = item.casefold()
        if payload["op"] == "add":
            if any(not row.get("done") and str(row.get("item", "")).casefold() == key for row in items):
                return "That to-do is already open."
            items.append({"item": item, "done": False, "updated_at": when})
        else:
            match = next(
                (
                    row
                    for row in items
                    if not row.get("done") and str(row.get("item", "")).casefold() == key
                ),
                None,
            )
            if match is None:
                return "No open to-do matches that item."
            match["done"] = True
            match["updated_at"] = when
        path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return None

    def read_todos(self) -> list[dict]:
        path = self._path("todos.json")
        if not path.exists():
            return []
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, list) else []

    def question_count_today(self) -> int:
        day = _iso()[:10]
        count = 0
        path = self._path("audit.jsonl")
        if not path.exists():
            return 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") == "question" and str(row.get("at", "")).startswith(day):
                count += 1
        return count


def default_store() -> Store:
    return Store(state_dir())
