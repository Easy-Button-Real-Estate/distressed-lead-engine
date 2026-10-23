"""Pure approval rules. These do not need a Mac or imsg."""

from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from icc.gate import (  # noqa: E402
    build_ask,
    evaluate,
    freeze_payload,
    iso,
    parse_decision,
    utcnow,
    validate_payload,
)


ASK = build_ask("Draft an offer and leave it in this chat.", "abcdef12")


def message(message_id, text, *, from_me=True, created_at="2099-01-02T00:00:00Z", guid=None):
    return {
        "id": message_id,
        "text": text,
        "is_from_me": from_me,
        "created_at": created_at,
        "guid": guid or f"g{message_id}",
    }


def proposal(created_at=None):
    return {
        "id": "abcdef12",
        "created_at": created_at or iso(utcnow()),
        "ask_text": ASK,
        "ask_message_id": 1,
        "status": "awaiting_yes",
        "payload": {"kind": "note", "detail": "Draft only."},
    }


class ParseTests(unittest.TestCase):
    def test_exact_yes_and_thumbs(self):
        self.assertEqual(parse_decision("YES abcdef12"), ("approve", "abcdef12"))
        self.assertEqual(parse_decision("👍 abcdef12"), ("approve", "abcdef12"))
        self.assertEqual(parse_decision("👍\U0001F3FD abcdef12"), ("approve", "abcdef12"))
        self.assertEqual(parse_decision("thumbs up abcdef12"), ("approve", "abcdef12"))
        self.assertEqual(parse_decision("NO abcdef12"), ("deny", "abcdef12"))

    def test_ask_and_sentences_are_not_approvals(self):
        self.assertIsNone(parse_decision(ASK))
        self.assertIsNone(parse_decision("yes please draft it abcdef12"))
        self.assertIsNone(parse_decision("I say YES abcdef12 now"))
        self.assertIsNone(parse_decision("[icc] YES abcdef12"))

    def test_bare_yes(self):
        self.assertEqual(parse_decision("YES"), ("approve", None))
        self.assertEqual(parse_decision("👍"), ("approve", None))


class EvaluateTests(unittest.TestCase):
    def test_yes_after_the_ask(self):
        row = proposal()
        decision = evaluate(row, [message(2, "YES abcdef12")], set(), {ASK}, utcnow(), False)
        self.assertEqual(decision["state"], "approved")

    def test_the_ask_itself_does_not_approve(self):
        row = proposal()
        decision = evaluate(row, [message(1, ASK, guid="ask")], {"ask"}, {ASK}, utcnow(), True)
        self.assertEqual(decision["state"], "pending")

    def test_someone_else_cannot_approve(self):
        row = proposal()
        decision = evaluate(
            row,
            [message(2, "YES abcdef12", from_me=False)],
            set(),
            {ASK},
            utcnow(),
            True,
        )
        self.assertEqual(decision["state"], "pending")

    def test_later_no_wins(self):
        row = proposal()
        messages = [
            message(2, "YES abcdef12", created_at="2099-01-02T00:00:00Z"),
            message(3, "NO abcdef12", created_at="2099-01-02T00:05:00Z"),
        ]
        decision = evaluate(row, messages, set(), {ASK}, utcnow(), True)
        self.assertEqual(decision["state"], "denied")

    def test_bare_yes_only_when_one_request_is_waiting(self):
        row = proposal()
        pending = evaluate(row, [message(2, "YES")], set(), {ASK}, utcnow(), False)
        approved = evaluate(row, [message(2, "YES")], set(), {ASK}, utcnow(), True)
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(approved["state"], "approved")

    def test_old_yes_before_the_ask_does_not_count(self):
        row = proposal()
        row["ask_message_id"] = 5
        decision = evaluate(row, [message(4, "YES abcdef12")], set(), {ASK}, utcnow(), True)
        self.assertEqual(decision["state"], "pending")

    def test_expired(self):
        row = proposal(created_at=iso(utcnow() - timedelta(hours=13)))
        decision = evaluate(row, [message(2, "YES abcdef12")], set(), set(), utcnow(), True)
        self.assertEqual(decision["state"], "expired")

    def test_wrong_id(self):
        row = proposal()
        decision = evaluate(row, [message(2, "YES 00000000")], set(), {ASK}, utcnow(), True)
        self.assertEqual(decision["state"], "pending")


class PayloadTests(unittest.TestCase):
    def test_rejects_a_name_as_a_recipient(self):
        error = validate_payload({"kind": "imessage", "to": "Mom", "text": "Hello"})
        self.assertIn("E.164", error or "")

    def test_freezes_the_fields_it_will_send(self):
        payload = {
            "kind": "imessage",
            "to": "+15555550123",
            "text": "  Offer attached as text.  ",
            "extra": "ignore me",
        }
        self.assertIsNone(validate_payload(payload))
        frozen = freeze_payload(payload)
        self.assertEqual(frozen, {"kind": "imessage", "to": "+15555550123", "text": "Offer attached as text."})

    def test_a_todo_batch_is_capped_at_20(self):
        items = [f"Task {index}" for index in range(21)]
        error = validate_payload({"kind": "todo", "items": items})
        self.assertIn("20", error or "")
        self.assertIsNone(validate_payload({"kind": "todo", "items": ["Order inspection", "Call the agent"]}))

    def test_rejects_system_prefix_on_outgoing_text(self):
        error = validate_payload({"kind": "imessage", "to": "+15555550123", "text": "[icc] hello"})
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
