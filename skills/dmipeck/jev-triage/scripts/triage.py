#!/usr/bin/env python3
"""Triage open needs-triage issues via Jev (typesafe-sdk) and forge CLIs."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any

from forges import Forge, ForgeError, Issue, make_forge
from gate import (
    CATEGORIES,
    STATES,
    ChoiceResult,
    Classification,
    build_state,
    format_comment,
    gate,
    labels_after_apply,
    validate_confidence,
)


def argument_parser(prog: str = "triage.py") -> argparse.ArgumentParser:
    class Parser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            self.print_usage(sys.stderr)
            print(f"{self.prog}: error: {message}", file=sys.stderr)
            raise SystemExit(2)

    parser = Parser(
        prog=prog,
        description=(
            "Classify open issues with the triage label via Jev and optionally "
            "apply category/state labels. Writes are on by default; use --dry-run "
            "to classify without label or comment changes."
        ),
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=("github", "gitlab", "gitea"),
        help="forge host",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="OWNER/REPO (GitLab also accepts numeric id or URL-encoded path)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        required=True,
        help="apply writes only if both Choice confidences are >= this (0–1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="classify and print; do not change labels or post comments",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="self-hosted GitLab/Gitea API root (hostname extracted for gh/glab)",
    )
    parser.add_argument(
        "--label",
        default="needs-triage",
        help="triage queue label to scan (default: needs-triage)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max open issues to process",
    )
    return parser


def classify_issue(client: Any, issue: Issue) -> Classification:
    from typesafe_sdk import Choice

    state = build_state(title=issue.title, body=issue.body, comments=issue.comments)
    response = client.system_one(
        state,
        {
            "category": Choice(
                instructions=(
                    "Classify the issue as bug (something broken) or enhancement "
                    "(new feature or improvement)."
                ),
                criteria={name: None for name in sorted(CATEGORIES)},
            ),
            "state": Choice(
                instructions=(
                    "Pick exactly one triage state after needs-triage: "
                    "needs-info (waiting on reporter), "
                    "ready-for-agent (fully specified for an AFK agent), "
                    "ready-for-human (requires human implementation), "
                    "or wontfix (will not be actioned)."
                ),
                criteria={name: None for name in sorted(STATES)},
            ),
        },
    )
    return classification_from_response(response)


def classification_from_response(response: Any) -> Classification:
    choices = response.choices
    category = choices["category"]
    state = choices["state"]
    return Classification(
        ChoiceResult(str(category.choice), float(category.confidence)),
        ChoiceResult(str(state.choice), float(state.confidence)),
    )


def process_issue(
    forge: Forge,
    client: Any,
    issue: Issue,
    *,
    min_confidence: float,
    triage_label: str,
    dry_run: bool,
    classify: Callable[[Any, Issue], Classification] | None = None,
) -> int:
    """Return 0 on success (including gated skip), 1 on error."""
    try:
        classification = (classify or classify_issue)(client, issue)
    except Exception as exc:
        print(f"#{issue.number}: classify error: {exc}", file=sys.stderr)
        return 1

    decision = gate(classification, min_confidence)
    summary = (
        f"#{issue.number}: category={classification.category.choice}"
        f"({classification.category.confidence:.4f}) "
        f"state={classification.state.choice}"
        f"({classification.state.confidence:.4f})"
    )
    if not decision.apply:
        print(f"{summary} SKIP: {decision.reason}")
        return 0

    add, remove = labels_after_apply(
        issue.labels,
        classification,
        triage_label=triage_label,
    )
    comment = format_comment(classification)
    if dry_run:
        print(
            f"{summary} DRY-RUN would add={{{', '.join(sorted(add))}}} "
            f"remove={{{', '.join(sorted(remove))}}}"
        )
        return 0

    try:
        forge.apply(
            issue,
            add_labels=sorted(add),
            remove_labels=sorted(remove),
            comment=comment,
        )
    except ForgeError as exc:
        print(f"#{issue.number}: write error: {exc}", file=sys.stderr)
        return 1
    print(f"{summary} APPLIED")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        validate_confidence(args.min_confidence)
    except ValueError as exc:
        print(f"triage.py: error: {exc}", file=sys.stderr)
        return 2

    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("triage.py: error: TYPESAFE_API_KEY is required", file=sys.stderr)
        return 2

    try:
        forge = make_forge(args.provider, args.project, base_url=args.base_url)
        issues = forge.list_open_labeled(args.label, limit=args.limit)
    except ForgeError as exc:
        print(f"triage.py: error: {exc}", file=sys.stderr)
        return 1

    if not issues:
        print(f"no open issues with label {args.label!r}")
        return 0

    try:
        from typesafe_sdk import TypeSafeClient
    except ImportError as exc:
        print(
            "triage.py: error: typesafe-sdk is required "
            f"(pip/uv install typesafe-sdk): {exc}",
            file=sys.stderr,
        )
        return 1

    failures = 0
    with TypeSafeClient() as client:
        for issue in issues:
            failures += process_issue(
                forge,
                client,
                issue,
                min_confidence=args.min_confidence,
                triage_label=args.label,
                dry_run=args.dry_run,
            )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
