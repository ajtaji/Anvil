#!/usr/bin/env python3
"""Verify Anvil's selected public tree, source closures, and boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PROVENANCE.json"
INCLUDE_RE = re.compile(r'^\s*(?:XIncludeFile|IncludeFile)\s+"([^"]+)"')
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
PRIVATE_PATH_RE = re.compile(
    r"(?i)(?:[A-Za-z]:[\\/](?:Users|Embedded Compiler|wt_[^\\/\s]+)|"
    r"/(?:home|Users)/[^/\s]+/)"
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
ACCESS_TOKEN_RE = re.compile(
    r"(?i)\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16})\b"
)
CREDENTIAL_LITERAL_RE = re.compile(
    r"(?i)\b(?:wifi_?(?:ssid|password|passphrase|psk)|ssid|password|"
    r"passphrase|psk|api_?key|access_?token)\b\s*(?:=|:)\s*"
    r"(?:\"[^\"<>]{1,}\"|'[^'<>]{1,}')"
)
TEXT_SUFFIXES = {
    "", ".board", ".def", ".gitignore", ".json", ".md", ".pb", ".pbi",
    ".pi4", ".py", ".txt", ".unoq",
}


def run_git(*arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"could not run Git: {error}") from error
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def git_paths(*arguments: str) -> set[PurePosixPath]:
    raw = run_git(*arguments)
    return {
        PurePosixPath(item.decode("utf-8"))
        for item in raw.split(b"\0")
        if item
    }


def safe_relative(raw: str, context: str) -> PurePosixPath:
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or WINDOWS_ABSOLUTE_RE.match(normalized)
        or ".." in path.parts
        or "." in path.parts
    ):
        raise RuntimeError(f"unsafe path in {context}: {raw}")
    return path


def closure(entry: PurePosixPath) -> set[PurePosixPath]:
    seen: set[PurePosixPath] = set()
    pending = [entry]
    root_resolved = ROOT.resolve()

    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        path = ROOT.joinpath(*relative.parts)
        if not path.is_file():
            raise RuntimeError(f"missing source: {relative.as_posix()}")
        if path.is_symlink():
            raise RuntimeError(f"source include is a symlink: {relative.as_posix()}")
        seen.add(relative)

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise RuntimeError(
                f"source is not UTF-8 text: {relative.as_posix()}"
            ) from error

        for line_number, line in enumerate(lines, 1):
            match = INCLUDE_RE.match(line)
            if not match:
                continue
            include = safe_relative(
                match.group(1), f"{relative.as_posix()}:{line_number}"
            )
            root_candidate = ROOT.joinpath(*include.parts)
            local_candidate = path.parent.joinpath(*include.parts)
            if root_candidate.is_file():
                candidate = root_candidate
            elif local_candidate.is_file():
                candidate = local_candidate
            else:
                raise RuntimeError(
                    f"missing include from {relative.as_posix()}:{line_number}: "
                    f"{include.as_posix()}"
                )
            try:
                child = PurePosixPath(
                    candidate.resolve().relative_to(root_resolved).as_posix()
                )
            except ValueError as error:
                raise RuntimeError(
                    f"include escapes repository from "
                    f"{relative.as_posix()}:{line_number}"
                ) from error
            pending.append(child)
    return seen


def public_selection(working_tree: bool) -> tuple[set[PurePosixPath], list[str]]:
    failures: list[str] = []
    if working_tree:
        selected = git_paths(
            "ls-files", "-z", "--cached", "--others", "--exclude-standard"
        )
        return selected, failures

    selected = git_paths("ls-files", "-z", "--cached")
    untracked = git_paths("ls-files", "-z", "--others", "--exclude-standard")
    if untracked:
        failures.append(
            "non-ignored untracked files exist; stage, ignore, or remove them "
            "before verifying the public selection"
        )
    unstaged = git_paths("diff", "--name-only", "-z")
    if unstaged:
        failures.append(
            "tracked files have unstaged changes; the worktree does not match "
            "the Git selection being verified"
        )
    return selected, failures


def inspect_text(relative: PurePosixPath) -> list[str]:
    path = ROOT.joinpath(*relative.parts)
    if path.suffix.casefold() not in TEXT_SUFFIXES and path.name != ".gitignore":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"public text is not UTF-8: {relative.as_posix()}"]

    failures: list[str] = []
    checks = (
        (PRIVATE_PATH_RE, "machine-specific private path"),
        (PRIVATE_KEY_RE, "private-key material"),
        (ACCESS_TOKEN_RE, "access-token-shaped value"),
        (CREDENTIAL_LITERAL_RE, "credential-like literal"),
    )
    for pattern, description in checks:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{description}: {relative.as_posix()}:{line}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--working-tree",
        action="store_true",
        help="check all tracked and non-ignored candidate files before staging",
    )
    args = parser.parse_args()
    failures: list[str] = []

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Public-tree verification failed: cannot read PROVENANCE.json: {error}")
        return 1

    if manifest.get("schema") != 2:
        failures.append("PROVENANCE.json must use schema 2")
    policy = manifest.get("current_tree")
    if not isinstance(policy, dict) or policy.get("manifest") != "git-index":
        failures.append("PROVENANCE.json has no git-index current-tree policy")
        policy = {}

    try:
        selected, selection_failures = public_selection(args.working_tree)
        failures.extend(selection_failures)
    except RuntimeError as error:
        print(f"Public-tree verification failed: {error}")
        return 1

    if not selected:
        failures.append("the selected public tree is empty")

    allowed_prefixes = tuple(policy.get("allowed_prefixes", ()))
    allowed_root_files = set(policy.get("allowed_root_files", ()))
    forbidden_prefixes = tuple(policy.get("forbidden_prefixes", ()))
    forbidden_names = {name.casefold() for name in policy.get("forbidden_names", ())}
    forbidden_suffixes = {
        suffix.casefold() for suffix in policy.get("forbidden_suffixes", ())
    }

    for relative in sorted(selected, key=lambda item: item.as_posix()):
        name = relative.as_posix()
        path = ROOT.joinpath(*relative.parts)
        if name not in allowed_root_files and not name.startswith(allowed_prefixes):
            failures.append(f"path is outside the public allowlist: {name}")
        if name.startswith(forbidden_prefixes):
            failures.append(f"forbidden path is selected: {name}")
        if relative.name.casefold() in forbidden_names:
            failures.append(f"private or generated filename is selected: {name}")
        if path.suffix.casefold() in forbidden_suffixes:
            failures.append(f"private or generated suffix is selected: {name}")
        if not path.is_file():
            failures.append(f"selected file is missing from the worktree: {name}")
            continue
        if path.is_symlink():
            failures.append(f"symbolic links are not allowed in the public tree: {name}")
            continue
        failures.extend(inspect_text(relative))

    for raw in policy.get("required_paths", ()):
        try:
            required = safe_relative(raw, "PROVENANCE.json required_paths")
        except RuntimeError as error:
            failures.append(str(error))
            continue
        if required not in selected:
            failures.append(f"required public file is not selected: {required.as_posix()}")

    closure_counts: list[tuple[str, int]] = []
    for raw in policy.get("entrypoints", ()):
        try:
            entry = safe_relative(raw, "PROVENANCE.json entrypoints")
            members = closure(entry)
        except RuntimeError as error:
            failures.append(str(error))
            continue
        missing = sorted(members - selected, key=lambda item: item.as_posix())
        for relative in missing:
            failures.append(
                f"include dependency is not selected: {relative.as_posix()} "
                f"(from {entry.as_posix()})"
            )
        closure_counts.append((entry.as_posix(), len(members)))

    if failures:
        print("Public-tree verification failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    mode = "working-tree candidate" if args.working_tree else "Git-tracked selection"
    counts = ", ".join(f"{entry}: {count}" for entry, count in closure_counts)
    print(
        f"Public-tree verification passed: {mode}, {len(selected)} files; "
        f"include closures complete ({counts}); boundaries and notices intact."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
