#!/usr/bin/env python3
"""Keep the provenance inventory honest.

Two records describe where Anvil's source came from: `PROVENANCE.json`'s
`third_party` block, which is machine-readable, and `docs/PROVENANCE_INVENTORY.md`,
which a person reads. This script fails if they disagree with each other or with
the source tree.

It answers three questions, and it is deliberately not clever about any of them.

  1. IS EVERY PAIR CLASSIFIED TRUTHFULLY AND SUPPORTED?
     Most implementation references are `consulted`: behavior was read and
     implemented independently. The Raspberry Pi armstub adaptations are the
     explicit exception: their source declares them as translations and their
     BSD-3-Clause notices are retained. `derived` and `verbatim` remain
     refusals for all other sources. Every pair must cite its source; a
     licensed adaptation must additionally retain its named license and
     acknowledgment.

  2. DOES ANY SOURCE FILE CITE AN UPSTREAM THE INVENTORY DOES NOT LIST?
     Every tracked source file is re-scanned with the citation patterns stored
     in `PROVENANCE.json`. A file that names U-Boot, Linux, Mesa, BearSSL or any
     other pinned upstream, and is not listed against it, is a failure. This is
     the check that matters over time: a citation added in six months' work is
     caught the first time this runs, instead of being found during a
     publication review.

  3. DO THE TWO DOCUMENTS AGREE?
     Every row of the inventory table must correspond to an entry in the JSON,
     and every JSON entry must have a row. A table that drifts from the data it
     describes is worse than no table, because it is read and believed.

WHAT IT DOES NOT DO, SAID OUT LOUD. It finds unlisted CITATIONS, not uncited
copies. It enforces the ruling on what the inventory RECORDS; it cannot look at
a procedure and tell you how it was written. A block that was copied and
committed with no comment is invisible to this script and to every other check
in this repository, and the only thing that catches it is a person reading the
code. Nor does it decide license compatibility: it reports what
`PROVENANCE.json` records, and that record is an engineering reading, not a
legal determination.

Usage:
    python3 tools/provenance_inventory_check.py
    python3 tools/provenance_inventory_check.py --list-original

Exit status is 0 when every check passes and 1 when any fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "PROVENANCE.json"
INVENTORY = ROOT / "docs" / "PROVENANCE_INVENTORY.md"
NOTICES = ROOT / "docs" / "THIRD_PARTY_NOTICES.md"

SOURCE_SUFFIXES = (".pi4", ".pbi", ".unoq", ".asm", ".def")

CONSULTED = "consulted"
LICENSED_ADAPTATION = "licensed-adaptation"
LICENSED_ADAPTATIONS = {
    ("RaspberryPi3/Board/armstub8.asm", "rpi-armstub8"),
    ("RaspberryPi4/Board/armstub8.asm", "rpi-armstub8"),
}
REFUSED_CLASSES = ("derived", "verbatim")
REFUSAL = (
    "a copied or derived block is not permitted in this tree; restate it or "
    "remove it"
)

# A table row: | `path` | class | source-id | license | obligation |
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([a-z-]+)\s*\|\s*([A-Za-z0-9._-]+)\s*\|")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []
        self.passed = 0

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def ok(self, count: int = 1) -> None:
        self.passed += count


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return [p.strip() for p in out if p.strip()]


def tracked_sources() -> list[str]:
    """Every Git-tracked source file, or every file on disk if Git is absent."""
    try:
        paths = _git("ls-files")
    except (OSError, subprocess.CalledProcessError):
        paths = [
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts
        ]
    return sorted(p for p in paths if p.endswith(SOURCE_SUFFIXES))


def untracked_sources() -> list[str]:
    """Source files that are not ignored and not yet tracked.

    These are another lane's work in progress. A citation in one of them is
    reported as a note, never as a failure: this gate exists to stop an
    unlisted derivation from being PUBLISHED, and nothing untracked is. It says
    so early so the row can be written while the work is fresh, rather than
    during the next publication review.
    """
    try:
        paths = _git("ls-files", "--others", "--exclude-standard")
    except (OSError, subprocess.CalledProcessError):
        return []
    return sorted(p for p in paths if p.endswith(SOURCE_SUFFIXES))


def anchor_of(notice_ref: str) -> str:
    """`docs/THIRD_PARTY_NOTICES.md#some-heading` -> `some-heading`."""
    return notice_ref.split("#", 1)[1] if "#" in notice_ref else ""


def heading_anchors(text: str) -> set[str]:
    """GitHub-style anchors for every Markdown heading in `text`."""
    anchors = set()
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        title = line.lstrip("#").strip().lower()
        slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-")
        anchors.add(slug)
    return anchors


def check_classes(third_party: dict, report: Report) -> None:
    """1. Every pair is a permitted class, and every consulted pair cites."""
    sources = third_party["sources"]
    classifications = third_party.get("classifications", {})
    notices_text = NOTICES.read_text(encoding="utf-8") if NOTICES.exists() else ""
    if not notices_text:
        report.fail(
            f"references-consulted file is missing: {NOTICES.relative_to(ROOT)}"
        )
        return
    anchors = heading_anchors(notices_text)

    cited_pairs: list[tuple[str, str, str]] = []
    for path, entry in third_party["classified_files"].items():
        for src, cls in entry.items():
            if cls in REFUSED_CLASSES:
                report.fail(
                    f"{path}: classified '{cls}' against '{src}'. {REFUSAL}. It was "
                    f"confirmed on 2026-09-10 that no third-party code was used; the "
                    f"references were read for how the hardware behaves, so the only "
                    f"class this tree carries against an implementation is "
                    f"'{CONSULTED}', except for explicitly licensed adaptations."
                )
            elif cls not in classifications:
                report.fail(
                    f"{path}: classified '{cls}' against '{src}', which is not one of "
                    f"the classes PROVENANCE.json defines: {sorted(classifications)}"
                )
            elif cls in (CONSULTED, LICENSED_ADAPTATION):
                if cls == LICENSED_ADAPTATION and (path, src) not in LICENSED_ADAPTATIONS:
                    report.fail(f"{path}: licensed-adaptation is reserved for the two Raspberry Pi armstubs")
                cited_pairs.append((path, src, cls))

    if not cited_pairs:
        report.fail("no consulted pairs are recorded; that cannot be right")
        return

    for path, src, cls in cited_pairs:
        meta = sources.get(src)
        if meta is None:
            report.fail(f"{path}: consulted an unknown source id '{src}'")
            continue

        # Both relationships need citations. An adaptation also needs the
        # retained license text and an anchored acknowledgment in the notices.
        pattern = meta.get("citation_pattern")
        if not pattern:
            report.fail(
                f"{path}: source '{src}' has no citation_pattern, so the citation "
                f"this consulted pair rests on cannot be checked"
            )
            continue
        try:
            cited = re.search(
                pattern, (ROOT / path).read_text(encoding="utf-8", errors="replace"),
                re.IGNORECASE,
            )
        except (OSError, re.error) as error:
            report.fail(f"{path}: cannot check the citation of '{src}': {error}")
            continue
        if not cited:
            report.fail(
                f"{path}: classified {CONSULTED} against '{src}' and cites nothing "
                f"of it. A consulted pair must cite the source the fact came from."
            )
            continue

        text = meta.get("license_text")
        ref = meta.get("acknowledgment")
        if text and not (ROOT / text).exists():
            report.fail(
                f"{path}: source '{src}' names retained text '{text}', which is not "
                f"on disk"
            )
            continue
        if cls == LICENSED_ADAPTATION and not text:
            report.fail(f"{path}: licensed adaptation has no retained license text")
            continue
        if cls == LICENSED_ADAPTATION and not ref:
            report.fail(f"{path}: licensed adaptation has no acknowledgment reference")
            continue
        if ref:
            anchor = anchor_of(ref)
            if anchor and anchor not in anchors:
                report.fail(
                    f"{path}: source '{src}' points at acknowledgment section "
                    f"'{ref}', and docs/THIRD_PARTY_NOTICES.md has no such heading"
                )
                continue
        report.ok()

    consulted_pairs = [(path, src) for path, src, cls in cited_pairs if cls == CONSULTED]
    adapted_pairs = [(path, src) for path, src, cls in cited_pairs if cls == LICENSED_ADAPTATION]
    by_source = sorted({src for _, src, _ in cited_pairs})
    report.note(
        f"{len(consulted_pairs)} consulted pair(s) across {len(by_source)} source(s): "
        f"{', '.join(by_source)}; {len(adapted_pairs)} licensed adaptation(s) retain "
        f"their license text and notice."
    )


def check_citations(third_party: dict, report: Report) -> tuple[list[str], list[str]]:
    """2. Every citation in the tree must be listed in the inventory."""
    sources = third_party["sources"]
    listed = third_party["classified_files"]
    patterns = {}
    for src, meta in sources.items():
        pattern = meta.get("citation_pattern")
        if not pattern:
            report.fail(f"source '{src}' has no citation_pattern; it cannot be checked")
            continue
        try:
            patterns[src] = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            report.fail(f"source '{src}' has an unusable citation_pattern: {error}")

    files = tracked_sources()
    if not files:
        report.fail("no source files were found to scan")
        return [], []

    uncited = []
    for path in files:
        try:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            report.fail(f"{path}: cannot read: {error}")
            continue
        found = sorted(src for src, rx in patterns.items() if rx.search(text))
        entry = listed.get(path, {})
        if not found:
            uncited.append(path)
            if entry:
                report.fail(
                    f"{path}: the inventory lists {sorted(entry)} but the file cites "
                    f"none of them any more. Remove the stale row, or restore the citation."
                )
            continue
        for src in found:
            if src not in entry:
                report.fail(
                    f"{path}: cites '{src}' and the inventory does not list it. "
                    f"Classify it in PROVENANCE.json third_party.classified_files and "
                    f"add its row to docs/PROVENANCE_INVENTORY.md."
                )
            else:
                report.ok()
        for src in entry:
            if src not in found:
                report.fail(
                    f"{path}: the inventory lists '{src}' but the file no longer cites it"
                )
    for path in listed:
        if path not in files:
            report.fail(f"{path}: listed in the inventory but is not a tracked source file")

    for path in untracked_sources():
        try:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = sorted(src for src, rx in patterns.items() if rx.search(text))
        if found:
            report.note(
                f"{path} is untracked work in progress and already cites "
                f"{found}. Classify it before it is committed."
            )
    return files, uncited


def check_device_tree_pattern_selftest(third_party: dict, report: Report) -> None:
    """Self-test (forum 967): a device-tree citation is attributed by the
    vendor file it actually names, never by a generic '*.dtsi' wildcard.

    linux-dt-bcm2711's citation_pattern used to include a bare
    `[A-Za-z0-9_.-]*\\.dtsi\\b` alternative, so ANY vendor's device-tree
    filename counted as a citation of the Raspberry Pi 4's Broadcom device
    tree. That miscounted RockPi4C/Lib/dma_pl330.pbi, gpu_probe.pbi and
    hdmi.pbi (which cite Rockchip's rk3399.dtsi/rk3399-base.dtsi) and
    ArduinoQ/Board/hwtimer_q.unoq (which cites Qualcomm's agatti.dtsi). This
    runs every time so that wildcard cannot come back unnoticed.
    """
    sources = third_party["sources"]
    bcm = sources.get("linux-dt-bcm2711", {})
    pattern = bcm.get("citation_pattern")
    if not pattern:
        report.fail("linux-dt-bcm2711 has no citation_pattern to self-test")
        return
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as error:
        report.fail(f"linux-dt-bcm2711 citation_pattern is unusable: {error}")
        return

    must_not_match = {
        "rk3399.dtsi": "a Rockchip RK3399 device tree, not Broadcom's",
        "rk3399-base.dtsi": "a Rockchip RK3399 device tree, not Broadcom's",
        "agatti.dtsi": "a Qualcomm QCM2290 device tree, not Broadcom's",
        "sm6115.dtsi": "a Qualcomm SM6115 device tree, not Broadcom's",
    }
    for text, why in must_not_match.items():
        if rx.search(text):
            report.fail(
                f"self-test: linux-dt-bcm2711's citation_pattern matches '{text}', which "
                f"names {why}. The forum 967 generic-*.dtsi wildcard bug is back."
            )
        else:
            report.ok()

    must_match = {
        "bcm2711.dtsi": "the Raspberry Pi 4 device tree",
        "bcm2711-rpi-4-b.dts": "the Raspberry Pi 4 board device tree",
        "bcm283x-rpi-smsc9514.dtsi": "the Raspberry Pi 3 USB device-tree fragment",
        "bcm2837.dtsi": "the Raspberry Pi 3 device tree",
    }
    for text, why in must_match.items():
        if not rx.search(text):
            report.fail(
                f"self-test: linux-dt-bcm2711's citation_pattern no longer matches "
                f"'{text}' ({why}). Tightening the pattern must not lose a real citation."
            )
        else:
            report.ok()


def check_document(third_party: dict, report: Report) -> None:
    """3. The Markdown table and the JSON must describe the same tree."""
    if not INVENTORY.exists():
        report.fail(f"inventory document is missing: {INVENTORY.relative_to(ROOT)}")
        return
    text = INVENTORY.read_text(encoding="utf-8")

    rows: dict[tuple[str, str], str] = {}
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match:
            path, cls, src = match.group(1), match.group(2), match.group(3)
            rows[(path, src)] = cls

    expected = {
        (path, src): cls
        for path, entry in third_party["classified_files"].items()
        for src, cls in entry.items()
    }

    for key, cls in expected.items():
        if key not in rows:
            report.fail(f"{key[0]}: no inventory row for source '{key[1]}'")
        elif rows[key] != cls:
            report.fail(
                f"{key[0]} / {key[1]}: PROVENANCE.json says '{cls}', the inventory "
                f"table says '{rows[key]}'"
            )
        else:
            report.ok()
    for key in rows:
        if key not in expected:
            report.fail(
                f"{key[0]}: inventory row names source '{key[1]}' with no entry in "
                f"PROVENANCE.json"
            )

    for name in ("The 2026-09-10 confirmation, and what it means", "Proven versus reasoned"):
        if name not in text:
            report.fail(f"the inventory no longer contains its '{name}' section")
        else:
            report.ok()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list-original",
        action="store_true",
        help="also print every source file that carries no third-party citation",
    )
    args = parser.parse_args()

    report = Report()

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Provenance inventory check failed: cannot read PROVENANCE.json: {error}")
        return 1

    third_party = manifest.get("third_party")
    if not third_party:
        print(
            "Provenance inventory check failed: PROVENANCE.json has no third_party "
            "block. The inventory lives there; see docs/PROVENANCE_INVENTORY.md."
        )
        return 1
    for key in ("sources", "classified_files", "inventory"):
        if key not in third_party:
            report.fail(f"PROVENANCE.json third_party is missing '{key}'")

    if report.failures:
        for failure in report.failures:
            print(f"  - {failure}")
        return 1

    check_classes(third_party, report)
    files, uncited = check_citations(third_party, report)
    check_document(third_party, report)
    check_device_tree_pattern_selftest(third_party, report)

    review = manifest.get("publication_review", {})
    held = review.get("status") == "held"

    print(
        f"Scanned {len(files)} tracked source files: "
        f"{len(third_party['classified_files'])} carry a citation, {len(uncited)} carry none."
    )
    counts: dict[str, int] = {}
    for entry in third_party["classified_files"].values():
        for cls in entry.values():
            counts[cls] = counts.get(cls, 0) + 1
    print("Classified pairs: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    if args.list_original:
        print("\nSource files with no third-party citation:")
        for path in uncited:
            print(f"  {path}")

    if report.notes:
        print()
        for note in report.notes:
            print(f"  note: {note}")

    print()
    if report.failures:
        print("Provenance inventory check FAILED:")
        for failure in report.failures:
            print(f"  - {failure}")
        return 1

    print(f"Provenance inventory check passed: {report.passed} checks.")
    if held:
        print(
            "Publication review: held. This check proves the inventory and the "
            "acknowledgments agree with the source tree, and that nothing in it is "
            "recorded as unlicensed derivation. It does not grant publication authority: "
            "publishing is a separate, explicit instruction."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
