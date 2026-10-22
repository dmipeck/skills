"""Forge adapters via ``gh`` / ``glab`` / ``tea`` subprocesses."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

Runner = Callable[[Sequence[str]], str]


class ForgeError(RuntimeError):
    """A forge CLI call failed or returned unexpected data."""


@dataclass(frozen=True)
class Issue:
    id: str
    number: str
    title: str
    body: str
    labels: frozenset[str]
    url: str
    comments: tuple[str, ...] = ()


class Forge(Protocol):
    def list_open_labeled(self, label: str, *, limit: int | None) -> tuple[Issue, ...]: ...

    def apply(
        self,
        issue: Issue,
        *,
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
        comment: str,
    ) -> None: ...


def hostname_from_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = (parsed.hostname or "").lower().strip(".")
    return host or None


def run_cmd(args: Sequence[str], *, runner: Runner | None = None) -> str:
    if runner is not None:
        return runner(args)
    proc = subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise ForgeError(f"{args[0]} failed: {err}")
    return proc.stdout


def _json_loads(text: str, *, what: str) -> Any:
    text = text.strip()
    if not text:
        raise ForgeError(f"{what}: empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ForgeError(f"{what}: invalid JSON") from exc


@dataclass(frozen=True)
class GitHubForge:
    project: str
    hostname: str | None = None
    runner: Runner | None = None
    comment_limit: int = 10

    def list_open_labeled(self, label: str, *, limit: int | None) -> tuple[Issue, ...]:
        lim = limit if limit is not None else 100
        args = [
            "gh",
            "issue",
            "list",
            "-R",
            self.project,
            "--state",
            "open",
            "--label",
            label,
            "--limit",
            str(lim),
            "--json",
            "number,title,body,labels,url",
        ]
        if self.hostname:
            args[1:1] = ["--hostname", self.hostname]
        rows = _json_loads(run_cmd(args, runner=self.runner), what="gh issue list")
        if not isinstance(rows, list):
            raise ForgeError("gh issue list: expected JSON array")
        issues: list[Issue] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            number = str(row["number"])
            labels = _label_names(row.get("labels"))
            comments = self._comments(number)
            issues.append(
                Issue(
                    id=number,
                    number=number,
                    title=str(row.get("title") or ""),
                    body=str(row.get("body") or ""),
                    labels=labels,
                    url=str(row.get("url") or ""),
                    comments=comments,
                )
            )
        return tuple(issues)

    def apply(
        self,
        issue: Issue,
        *,
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
        comment: str,
    ) -> None:
        edit = ["gh", "issue", "edit", issue.number, "-R", self.project]
        if self.hostname:
            edit[1:1] = ["--hostname", self.hostname]
        for name in add_labels:
            edit.extend(["--add-label", name])
        for name in remove_labels:
            edit.extend(["--remove-label", name])
        if add_labels or remove_labels:
            run_cmd(edit, runner=self.runner)
        note = [
            "gh",
            "issue",
            "comment",
            issue.number,
            "-R",
            self.project,
            "--body",
            comment,
        ]
        if self.hostname:
            note[1:1] = ["--hostname", self.hostname]
        run_cmd(note, runner=self.runner)

    def _comments(self, number: str) -> tuple[str, ...]:
        path = f"repos/{self.project}/issues/{number}/comments?per_page={self.comment_limit}"
        args = ["gh", "api", path]
        if self.hostname:
            args[1:1] = ["--hostname", self.hostname]
        try:
            payload = _json_loads(run_cmd(args, runner=self.runner), what="gh api comments")
        except ForgeError:
            return ()
        if not isinstance(payload, list):
            return ()
        bodies: list[str] = []
        for row in payload:
            if isinstance(row, Mapping) and row.get("body"):
                bodies.append(str(row["body"]))
        return tuple(bodies)


@dataclass(frozen=True)
class GitLabForge:
    project: str
    hostname: str | None = None
    runner: Runner | None = None
    comment_limit: int = 10

    def list_open_labeled(self, label: str, *, limit: int | None) -> tuple[Issue, ...]:
        per_page = limit if limit is not None else 100
        enc = urllib.parse.quote(self.project, safe="")
        path = (
            f"projects/{enc}/issues"
            f"?state=opened&labels={urllib.parse.quote(label, safe='')}"
            f"&per_page={per_page}"
        )
        rows = _json_loads(self._api(path), what="glab api issues")
        if not isinstance(rows, list):
            raise ForgeError("glab api issues: expected JSON array")
        if limit is not None:
            rows = rows[:limit]
        issues: list[Issue] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            iid = str(row.get("iid") or row.get("id") or "")
            if not iid:
                continue
            labels = _label_names(row.get("labels"))
            comments = self._notes(iid)
            issues.append(
                Issue(
                    id=str(row.get("id") or iid),
                    number=iid,
                    title=str(row.get("title") or ""),
                    body=str(row.get("description") or ""),
                    labels=labels,
                    url=str(row.get("web_url") or ""),
                    comments=comments,
                )
            )
        return tuple(issues)

    def apply(
        self,
        issue: Issue,
        *,
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
        comment: str,
    ) -> None:
        repo = self._repo_arg()
        if add_labels or remove_labels:
            args = ["glab", "issue", "update", issue.number, "-R", repo]
            if add_labels:
                args.extend(["--label", ",".join(add_labels)])
            if remove_labels:
                args.extend(["--unlabel", ",".join(remove_labels)])
            run_cmd(args, runner=self.runner)
        run_cmd(
            [
                "glab",
                "issue",
                "note",
                issue.number,
                "-R",
                repo,
                "--message",
                comment,
            ],
            runner=self.runner,
        )

    def _repo_arg(self) -> str:
        if self.hostname:
            return f"https://{self.hostname}/{self.project}"
        return self.project

    def _api(self, path: str) -> str:
        args = ["glab", "api", path]
        if self.hostname:
            args.extend(["--hostname", self.hostname])
        return run_cmd(args, runner=self.runner)

    def _notes(self, iid: str) -> tuple[str, ...]:
        enc = urllib.parse.quote(self.project, safe="")
        path = f"projects/{enc}/issues/{iid}/notes?per_page={self.comment_limit}&sort=desc"
        try:
            payload = _json_loads(self._api(path), what="glab api notes")
        except ForgeError:
            return ()
        if not isinstance(payload, list):
            return ()
        bodies: list[str] = []
        for row in payload:
            if not isinstance(row, Mapping):
                continue
            if row.get("system"):
                continue
            body = row.get("body")
            if body:
                bodies.append(str(body))
        return tuple(reversed(bodies))


@dataclass(frozen=True)
class GiteaForge:
    project: str
    base_url: str | None = None
    runner: Runner | None = None
    comment_limit: int = 10

    def list_open_labeled(self, label: str, *, limit: int | None) -> tuple[Issue, ...]:
        lim = limit if limit is not None else 50
        args = [
            "tea",
            "issues",
            "list",
            "--state",
            "open",
            "--kind",
            "issues",
            "--labels",
            label,
            "--limit",
            str(lim),
            "--repo",
            self.project,
            "--output",
            "json",
        ]
        rows = _json_loads(run_cmd(args, runner=self.runner), what="tea issues list")
        if isinstance(rows, Mapping):
            maybe = rows.get("issues") or rows.get("data") or rows
            rows = maybe if isinstance(maybe, list) else [rows]
        if not isinstance(rows, list):
            raise ForgeError("tea issues list: expected JSON array")
        issues: list[Issue] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            number = str(row.get("number") or row.get("index") or "")
            if not number:
                continue
            labels = _label_names(row.get("labels"))
            comments = self._comments(number)
            issues.append(
                Issue(
                    id=number,
                    number=number,
                    title=str(row.get("title") or ""),
                    body=str(row.get("body") or ""),
                    labels=labels,
                    url=str(row.get("html_url") or row.get("url") or ""),
                    comments=comments,
                )
            )
        return tuple(issues)

    def apply(
        self,
        issue: Issue,
        *,
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
        comment: str,
    ) -> None:
        if add_labels or remove_labels:
            args = ["tea", "issues", "edit", issue.number, "--repo", self.project]
            if add_labels:
                args.extend(["--add-labels", ",".join(add_labels)])
            if remove_labels:
                args.extend(["--remove-labels", ",".join(remove_labels)])
            run_cmd(args, runner=self.runner)
        path = self._api_path(f"repos/{self.project}/issues/{issue.number}/comments")
        run_cmd(
            ["tea", "api", "--method", "POST", "-f", f"body={comment}", path],
            runner=self.runner,
        )

    def _comments(self, number: str) -> tuple[str, ...]:
        path = self._api_path(
            f"repos/{self.project}/issues/{number}/comments?limit={self.comment_limit}"
        )
        try:
            payload = _json_loads(self._api_get(path), what="tea api comments")
        except ForgeError:
            return ()
        if not isinstance(payload, list):
            return ()
        bodies: list[str] = []
        for row in payload:
            if isinstance(row, Mapping) and row.get("body"):
                bodies.append(str(row["body"]))
        return tuple(bodies)

    def _api_get(self, path: str) -> str:
        return run_cmd(["tea", "api", path], runner=self.runner)

    def _api_path(self, path: str) -> str:
        if not self.base_url:
            return path
        root = self.base_url.rstrip("/")
        if root.endswith("/api/v1"):
            return f"{root}/{path.lstrip('/')}"
        return f"{root}/api/v1/{path.lstrip('/')}"


def make_forge(
    provider: str,
    project: str,
    *,
    base_url: str | None = None,
    runner: Runner | None = None,
) -> Forge:
    host = hostname_from_base_url(base_url)
    if provider == "github":
        return GitHubForge(project, hostname=host, runner=runner)
    if provider == "gitlab":
        return GitLabForge(project, hostname=host, runner=runner)
    if provider == "gitea":
        return GiteaForge(project, base_url=base_url, runner=runner)
    raise ForgeError(f"unknown provider {provider!r}")


def _label_names(raw: Any) -> frozenset[str]:
    names: set[str] = set()
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, Mapping) and item.get("name"):
                names.add(str(item["name"]))
    return frozenset(names)
