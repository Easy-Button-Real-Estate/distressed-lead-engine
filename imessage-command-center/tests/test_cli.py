"""Gate behavior with a fake imsg. No messages leave the machine."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fake_imsg.py"
sys.path.insert(0, str(ROOT))

from icc.cli import main  # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "state"
        self.home.mkdir()
        self.sent = Path(self.tmp.name) / "sent.jsonl"
        self.history = Path(self.tmp.name) / "history.ndjson"
        self.watch = Path(self.tmp.name) / "watch.ndjson"
        self.payloads = Path(self.tmp.name)
        self._old = os.environ.copy()
        os.environ["ICC_HOME"] = str(self.home)
        os.environ["ICC_IMSG_BIN"] = str(FAKE)
        os.environ["ICC_FAKE_SENT_FILE"] = str(self.sent)
        os.environ["ICC_FAKE_HISTORY_FILE"] = str(self.history)
        os.environ["ICC_FAKE_WATCH_FILE"] = str(self.watch)
        os.environ["ICC_FAKE_SEND"] = "sent"
        self.assertEqual(main(["use-chat", "--id", "7"]), 0)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old)
        self.tmp.cleanup()

    def _payload(self, name, body):
        path = self.payloads / name
        path.write_text(json.dumps(body), encoding="utf-8")
        return str(path)

    def _sent_rows(self):
        if not self.sent.exists():
            return []
        return [json.loads(line) for line in self.sent.read_text(encoding="utf-8").splitlines() if line]

    def _propose(self, payload):
        before = len(self._sent_rows())
        code = main(["propose", "--summary", "Do the thing I described, and nothing more.", "--payload", payload])
        self.assertEqual(code, 0, msg="propose should send the ask and nothing else")
        rows = self._sent_rows()
        self.assertEqual(len(rows), before + 1)
        last = rows[-1]
        self.assertTrue(last["text"].startswith("[icc]"))
        self.assertEqual(last["chat_id"], "7")
        self.assertEqual(last["to"], "")
        action_id = last["text"].split("YES ", 1)[1].split()[0]
        return action_id

    def _approve(self, action_id):
        self.history.write_text(
            json.dumps(
                {
                    "id": 5,
                    "guid": "yes-1",
                    "is_from_me": True,
                    "text": f"YES {action_id}",
                    "created_at": "2099-01-02T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_name_recipient_never_sends(self):
        path = self._payload("bad", {"kind": "imessage", "to": "Mom", "text": "Hello"})
        code = main(["propose", "--summary", "Text Mom.", "--payload", path])
        self.assertEqual(code, 2)
        self.assertFalse(self.sent.exists())

    def test_imessage_sends_once_and_only_the_approved_text(self):
        path = self._payload(
            "msg",
            {"kind": "imessage", "to": "+15555550123", "text": "Draft offer is ready for your review."},
        )
        action_id = self._propose(path)
        self.assertEqual(main(["commit", "--id", action_id]), 1)
        self.assertEqual(len(self._sent_rows()), 1)
        self._approve(action_id)
        self.assertEqual(main(["release", "--id", action_id]), 0)
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        rows = self._sent_rows()
        self.assertEqual(rows[-1]["to"], "+15555550123")
        self.assertEqual(rows[-1]["text"], "Draft offer is ready for your review.")
        self.assertEqual(rows[-1]["chat_id"], "")
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        self.assertEqual(len(self._sent_rows()), 2)

    def test_no_cancels_before_a_pipeline_write(self):
        path = self._payload(
            "pipe",
            {
                "kind": "pipeline",
                "address": "12 Oak Street",
                "status": "Offer",
                "next_step": "Call the agent",
                "owner": "",
                "notes": "",
            },
        )
        action_id = self._propose(path)
        self.history.write_text(
            json.dumps(
                {
                    "id": 9,
                    "guid": "no-1",
                    "is_from_me": True,
                    "text": f"NO {action_id}",
                    "created_at": "2099-01-02T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(main(["commit", "--id", action_id]), 3)
        self.assertFalse((self.home / "pipeline.csv").exists())

    def test_pipeline_and_todo_commit_once(self):
        pipe = self._payload(
            "pipe",
            {
                "kind": "pipeline",
                "address": "12 Oak Street",
                "status": "Offer",
                "next_step": "Call the agent",
            },
        )
        action_id = self._propose(pipe)
        self._approve(action_id)
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        rows = (self.home / "pipeline.csv").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 2)

    def test_bare_yes_does_not_approve_two_open_requests(self):
        note = self._payload("note", {"kind": "note", "detail": "Draft only."})
        first = self._propose(note)
        second = self._propose(self._payload("note2", {"kind": "note", "detail": "Second draft."}))
        self.history.write_text(
            json.dumps(
                {
                    "id": 4,
                    "guid": "bare",
                    "is_from_me": True,
                    "text": "YES",
                    "created_at": "2099-01-02T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(main(["release", "--id", first]), 1)
        self.assertEqual(main(["release", "--id", second]), 1)

    def test_connector_release_does_not_send_and_finish_waits_for_yes(self):
        path = self._payload(
            "mail",
            {
                "kind": "connector",
                "app": "Gmail",
                "operation": "Create a draft",
                "detail": "Do not send the draft.",
            },
        )
        action_id = self._propose(path)
        self._approve(action_id)
        before = len(self._sent_rows())
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        self.assertEqual(len(self._sent_rows()), before)
        self.assertEqual(main(["commit", "--id", action_id]), 0)
        self.history.write_text("", encoding="utf-8")
        self.assertEqual(main(["finish", "--id", action_id]), 1)
        self._approve(action_id)
        self.assertEqual(main(["finish", "--id", action_id]), 0)

    def test_reply_requires_approval_question_stays_in_command_chat(self):
        path = self._payload("note", {"kind": "note", "detail": "Draft only."})
        action_id = self._propose(path)
        self.assertEqual(main(["reply", "--id", action_id, "--text", "Here is the draft."]), 1)
        self.assertEqual(main(["reply", "--question", "--text", "Which address?"]), 0)
        self.assertTrue(self._sent_rows()[-1]["text"].startswith("[icc]"))
        self.assertEqual(self._sent_rows()[-1]["chat_id"], "7")
        self.assertEqual(main(["reply", "--question", "--text", "Which address"]), 2)

    def test_sync_starts_at_now_then_queues_a_new_text(self):
        self.history.write_text(
            json.dumps(
                {
                    "id": 3,
                    "chat_id": 7,
                    "guid": "old",
                    "is_from_me": True,
                    "text": "old command that should stay put",
                    "created_at": "2020-01-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(main(["sync"]), 0)
        inbox = json.loads(subprocess.check_output([sys.executable, "-m", "icc", "inbox"], cwd=ROOT, env=os.environ))
        self.assertEqual(inbox["commands"], [])
        with self.history.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": 4,
                        "chat_id": 7,
                        "guid": "new",
                        "is_from_me": True,
                        "text": "add a to-do: order the inspection",
                        "created_at": "2026-10-23T12:00:00Z",
                    }
                )
                + "\n"
            )
        self.assertEqual(main(["sync"]), 0)
        inbox = json.loads(subprocess.check_output([sys.executable, "-m", "icc", "inbox"], cwd=ROOT, env=os.environ))
        self.assertEqual([row["guid"] for row in inbox["commands"]], ["new"])

    def test_watch_queues_only_my_commands(self):
        lines = [
            {
                "id": 10,
                "chat_id": 7,
                "guid": "cmd",
                "is_from_me": True,
                "text": "pull comps for 12 Oak",
                "created_at": "2026-10-23T00:00:00Z",
            },
            {
                "id": 11,
                "chat_id": 7,
                "guid": "other",
                "is_from_me": False,
                "text": "YES abcdef12",
                "created_at": "2026-10-23T00:00:01Z",
            },
            {
                "id": 12,
                "chat_id": 7,
                "guid": "bot",
                "is_from_me": True,
                "text": "[icc] Nothing runs until you reply",
                "created_at": "2026-10-23T00:00:02Z",
            },
            {
                "id": 13,
                "chat_id": 7,
                "guid": "yes",
                "is_from_me": True,
                "text": "YES abcdef12",
                "created_at": "2026-10-23T00:00:03Z",
            },
        ]
        self.watch.write_text("".join(json.dumps(row) + "\n" for row in lines), encoding="utf-8")
        code = main(["watch"])
        self.assertEqual(code, 0)
        inbox = json.loads(subprocess.check_output([sys.executable, "-m", "icc", "inbox"], cwd=ROOT, env=os.environ))
        self.assertEqual([row["guid"] for row in inbox["commands"]], ["cmd"])


if __name__ == "__main__":
    unittest.main()
