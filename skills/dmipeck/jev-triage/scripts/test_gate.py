#!/usr/bin/env python3
from __future__ import annotations

import unittest

from forges import hostname_from_base_url
from gate import (
    DISCLAIMER,
    ChoiceResult,
    Classification,
    build_state,
    format_comment,
    gate,
    labels_after_apply,
    validate_classification,
    validate_confidence,
)


def classification(
    category: str = "bug",
    category_conf: float = 0.9,
    state: str = "ready-for-agent",
    state_conf: float = 0.9,
) -> Classification:
    return Classification(
        ChoiceResult(category, category_conf),
        ChoiceResult(state, state_conf),
    )


class ValidateTests(unittest.TestCase):
    def test_confidence_bounds(self) -> None:
        self.assertEqual(validate_confidence(0.0), 0.0)
        self.assertEqual(validate_confidence(1.0), 1.0)
        with self.assertRaises(ValueError):
            validate_confidence(-0.01)
        with self.assertRaises(ValueError):
            validate_confidence(1.01)

    def test_classification_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            validate_classification(classification(category="chore"))
        with self.assertRaises(ValueError):
            validate_classification(classification(state="needs-triage"))


class GateTests(unittest.TestCase):
    def test_both_above_threshold_applies(self) -> None:
        decision = gate(classification(category_conf=0.8, state_conf=0.8), 0.8)
        self.assertTrue(decision.apply)
        self.assertEqual(decision.reason, "")

    def test_category_below_skips(self) -> None:
        decision = gate(classification(category_conf=0.7, state_conf=0.95), 0.8)
        self.assertFalse(decision.apply)
        self.assertIn("category confidence", decision.reason)
        self.assertIn("0.7000", decision.reason)

    def test_state_below_skips(self) -> None:
        decision = gate(classification(category_conf=0.95, state_conf=0.5), 0.8)
        self.assertFalse(decision.apply)
        self.assertIn("state confidence", decision.reason)

    def test_equal_to_threshold_applies(self) -> None:
        decision = gate(classification(category_conf=0.75, state_conf=0.75), 0.75)
        self.assertTrue(decision.apply)


class LabelsTests(unittest.TestCase):
    def test_adds_wanted_removes_triage_and_conflicts(self) -> None:
        add, remove = labels_after_apply(
            frozenset({"needs-triage", "enhancement", "needs-info"}),
            classification(category="bug", state="ready-for-human"),
            triage_label="needs-triage",
        )
        self.assertEqual(add, frozenset({"bug", "ready-for-human"}))
        self.assertEqual(remove, frozenset({"needs-triage", "enhancement", "needs-info"}))

    def test_noop_add_when_already_present(self) -> None:
        add, remove = labels_after_apply(
            frozenset({"needs-triage", "bug", "ready-for-agent"}),
            classification(),
            triage_label="needs-triage",
        )
        self.assertEqual(add, frozenset())
        self.assertEqual(remove, frozenset({"needs-triage"}))


class CommentAndStateTests(unittest.TestCase):
    def test_comment_starts_with_disclaimer(self) -> None:
        text = format_comment(classification())
        self.assertTrue(text.startswith(DISCLAIMER))
        self.assertIn("`bug`", text)
        self.assertIn("`ready-for-agent`", text)
        self.assertIn("0.9000", text)

    def test_build_state_includes_comments_when_present(self) -> None:
        bare = build_state(title="t", body="b")
        self.assertEqual(bare, {"title": "t", "body": "b"})
        with_comments = build_state(title="t", body="", comments=("c1", "c2"))
        self.assertEqual(
            with_comments,
            {"title": "t", "body": "", "recent_comments": ["c1", "c2"]},
        )


class HostnameTests(unittest.TestCase):
    def test_hostname_from_base_url(self) -> None:
        self.assertIsNone(hostname_from_base_url(None))
        self.assertEqual(hostname_from_base_url("https://gitlab.example/api/v4"), "gitlab.example")
        self.assertEqual(hostname_from_base_url("gitea.local"), "gitea.local")


if __name__ == "__main__":
    unittest.main()
