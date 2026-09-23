#!/usr/bin/env python3
"""Verify Anvil's selected public tree, source closures, and boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PROVENANCE.json"
SHA256SUMS_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})[ \t]([* ])(.+)$")
# Board SHA256SUMS files this check walks. Scoped to the Pi 4's (forum 925/926)
# rather than every board's: the other boards' checksum files are a separate,
# currently-unaudited surface and are not this lane's to gate red or green.
CHECKSUM_FILES_TO_VERIFY: frozenset[str] = frozenset(
    {"Boards/RaspberryPi4/sdcard/SHA256SUMS"}
)
# A board's shipped SHA256SUMS checks the files its own build produces, but
# some boards tell an operator to add further files from elsewhere in this
# repository (forum 926: the Pi 4's radio firmware). Each such file is named
# here, relative to the SHA256SUMS file itself, so a checksum line for it
# cannot be silently dropped again.
REQUIRED_ADDITIONAL_CHECKSUMS: dict[str, frozenset[str]] = {
    "Boards/RaspberryPi4/sdcard/SHA256SUMS": frozenset(
        {
            "../../../Firmware/CYW43455/brcmfmac43455-sdio.bin",
            "../../../Firmware/CYW43455/brcmfmac43455-sdio.clm_blob",
        }
    ),
}
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
# EVERY SOURCE EXTENSION A BOARD USES MUST BE HERE. Until 2026-09-18 .pi3 and
# .rockpi4c were missing, so every Raspberry Pi 3 and ROCK Pi 4C source file
# was silently outside the private-path and credential scan. A new board's
# extension is added here in the commit that adds the board.
TEXT_SUFFIXES = {
    "", ".asm", ".board", ".def", ".example", ".gitattributes", ".gitignore",
    ".in", ".json", ".md", ".pb", ".pbi", ".pi3", ".pi4", ".py",
    ".rockpi4c", ".rsp", ".sh", ".txt", ".unoq",
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


def check_provenance_history(
    manifest: dict, selected: set[PurePosixPath], failures: list[str]
) -> None:
    """historical_migration_files / historical_standalone_files name files
    that the record claims are, or became, part of this tree. Nothing else
    checks that claim, so a stale or invented row sits there indefinitely
    (forum 925: two CYW43455 licence-file rows that were never part of any
    tracked tree). This checks that each record's destination exists and is
    tracked, for every destination the same manifest's own current_tree
    policy declares as belonging inside this repository.

    A destination outside every allowed_prefix and allowed_root_file (for
    example "keywords.def", named by historical_selection as compiler data
    the historical export pulled in from outside this repository) is not
    claimed as part of THIS tree by the manifest's own boundary, so it is
    not something this check can call phantom; it is left alone rather than
    guessed at.

    This deliberately does NOT recompute and compare the recorded sha256
    values against current file content: historical_exported_utc marks the
    whole block as a record of one past export, and files named in it have
    legitimately changed since. A hash field here documents what the export
    produced, not what the file must still hash to.
    """
    entries = list(manifest.get("historical_migration_files", ())) + list(
        manifest.get("historical_standalone_files", ())
    )
    if not entries:
        failures.append(
            "PROVENANCE.json has no historical_migration_files/"
            "historical_standalone_files records to verify"
        )
        return

    policy = manifest.get("current_tree", {})
    allowed_prefixes = tuple(policy.get("allowed_prefixes", ()))
    allowed_root_files = set(policy.get("allowed_root_files", ()))

    for entry in entries:
        destination = entry.get("destination") if isinstance(entry, dict) else None
        if not destination:
            failures.append(
                f"a PROVENANCE.json history entry has no 'destination': {entry}"
            )
            continue
        try:
            relative = safe_relative(
                destination, "PROVENANCE.json historical file record"
            )
        except RuntimeError as error:
            failures.append(str(error))
            continue
        name = relative.as_posix()
        if name not in allowed_root_files and not name.startswith(allowed_prefixes):
            continue
        if relative not in selected:
            failures.append(
                f"PROVENANCE.json lists '{relative.as_posix()}' as a provenance "
                "record destination inside this repository's own declared "
                "tree, and it is not part of the tracked tree"
            )


def parse_sha256sums(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip("\n")
        if not line.strip():
            continue
        match = SHA256SUMS_LINE_RE.match(line)
        if not match:
            raise RuntimeError(
                f"{path}:{line_number}: not a recognisable sha256sum line: {raw!r}"
            )
        digest, _mode, name = match.groups()
        entries.append((digest.lower(), name))
    return entries


def resolve_checksum_target(sums_relative: PurePosixPath, name: str) -> PurePosixPath:
    base_dir = ROOT.joinpath(*sums_relative.parts).parent
    candidate = (base_dir / name.replace("\\", "/")).resolve()
    root_resolved = ROOT.resolve()
    try:
        relative = candidate.relative_to(root_resolved)
    except ValueError as error:
        raise RuntimeError(
            f"{sums_relative.as_posix()}: checksum target escapes the "
            f"repository: {name}"
        ) from error
    return PurePosixPath(relative.as_posix())


def check_board_checksums(selected: set[PurePosixPath], failures: list[str]) -> None:
    """CHECKSUM_FILES_TO_VERIFY is walked and each one's lines are proven
    against the files they name: a tampered file or a stale checksum both
    fail here. A board that tells its operator to add further files from
    elsewhere in the repository (forum 926: the Pi 4's radio firmware) must
    also checksum those files, checked against REQUIRED_ADDITIONAL_CHECKSUMS
    so a missing row cannot silently return.
    """
    sums_files = sorted(
        (
            path
            for path in selected
            if path.as_posix() in CHECKSUM_FILES_TO_VERIFY
        ),
        key=lambda item: item.as_posix(),
    )
    missing = CHECKSUM_FILES_TO_VERIFY - {path.as_posix() for path in sums_files}
    for name in sorted(missing):
        failures.append(f"{name}: is not part of the tracked tree")
    if not sums_files:
        return

    for sums_path in sums_files:
        full = ROOT.joinpath(*sums_path.parts)
        try:
            entries = parse_sha256sums(full)
        except RuntimeError as error:
            failures.append(str(error))
            continue
        if not entries:
            failures.append(f"{sums_path.as_posix()}: has no checksum lines")
            continue

        covered: set[PurePosixPath] = set()
        for digest, name in entries:
            try:
                target = resolve_checksum_target(sums_path, name)
            except RuntimeError as error:
                failures.append(str(error))
                continue
            covered.add(target)
            target_path = ROOT.joinpath(*target.parts)
            if not target_path.is_file():
                failures.append(
                    f"{sums_path.as_posix()}: checksummed file is missing: {name}"
                )
                continue
            actual = hashlib.sha256(target_path.read_bytes()).hexdigest()
            if actual != digest:
                failures.append(
                    f"{sums_path.as_posix()}: checksum for {name} does not match "
                    f"its contents (listed {digest}, actual {actual})"
                )

        for required_name in REQUIRED_ADDITIONAL_CHECKSUMS.get(
            sums_path.as_posix(), frozenset()
        ):
            try:
                required_target = resolve_checksum_target(sums_path, required_name)
            except RuntimeError as error:
                failures.append(str(error))
                continue
            if required_target not in covered:
                failures.append(
                    f"{sums_path.as_posix()}: does not checksum a file its own "
                    f"board README requires an operator to add: {required_name}"
                )


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
        "--for-publication",
        action="store_true",
        help="also require the recorded publication review to be cleared",
    )
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
    review = manifest.get("publication_review", {})
    if not isinstance(review, dict):
        review = {}
    review_status = review.get("status", "unrecorded")
    if args.for_publication and review_status != "cleared":
        failures.append(
            "publication review is not cleared: "
            + str(review.get("reason", "no completed review is recorded"))
        )
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

    check_provenance_history(manifest, selected, failures)
    check_board_checksums(selected, failures)

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
        f"include closures complete ({counts}); file boundaries checked and "
        "required notice files present; provenance history destinations and "
        "every SHA256SUMS checksum verified against the tracked tree."
    )
    print(
        f"Publication review: {review_status}. Packaging checks do not determine "
        "license compatibility or grant publication authority."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
