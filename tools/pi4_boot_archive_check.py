#!/usr/bin/env python3
"""Temporary-directory regression checks for pi4_boot_archive.py."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pi4_boot_archive.py"


def sha(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def run(boot: Path, data: Path, plan: Path, backup: Path, apply: bool = False):
    cmd = [sys.executable, str(TOOL), "--boot-root", str(boot),
           "--data-root", str(data), "--plan-json", str(plan),
           "--backup-dir", str(backup)]
    if apply:
        cmd.append("--apply")
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def setup(root: Path):
    boot, data, backup = root / "boot", root / "data", root / "backup"
    boot.mkdir(); data.mkdir()
    # The tool must protect the active kernel while never reading settings.
    (boot / "kernel8.img").write_bytes(b"active-kernel")
    (boot / "config.txt").write_text("kernel=kernel8.img\ndtoverlay=disable-bt\n", encoding="utf-8")
    (boot / "disable-bt.dtbo").write_bytes(b"overlay")
    (boot / "S24TIME.BAK").write_bytes(b"archived")
    plan = root / "plan.json"
    plan.write_text(json.dumps({"entries": [{
        "source": "S24TIME.BAK", "destination": "recovery/S24TIME.BAK",
        "optional": True, "reason": "reviewed optional archive"
    }]}), encoding="utf-8")
    return boot, data, backup, plan


def expect_fail(result, label):
    if result.returncode == 0:
        raise AssertionError(f"{label}: unsafe plan unexpectedly succeeded")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pi4-boot-archive-check-") as tmp:
        root = Path(tmp)
        boot, data, backup, plan = setup(root)

        # Survey is the default and leaves sources untouched.
        result = run(boot, data, plan, backup)
        if result.returncode or (boot / "S24TIME.BAK").read_bytes() != b"archived":
            raise AssertionError("survey changed or rejected a valid plan")

        # Valid apply verifies destination and backup before removing source.
        result = run(boot, data, plan, backup, True)
        if result.returncode or (boot / "S24TIME.BAK").exists():
            raise AssertionError("valid archive did not remove the verified source")
        if sha(data / "recovery/S24TIME.BAK") != sha(backup / "S24TIME.BAK"):
            raise AssertionError("archived copy and backup differ")
        if sha(backup / "kernel8.img") != sha(boot / "kernel8.img"):
            raise AssertionError("active kernel backup is missing or differs")
        print("PASS valid survey/apply, destination readback, source removal, kernel backup")

        # Protected active file refusal.
        p = root / "protected.json"
        p.write_text(json.dumps({"entries": [{"source": "kernel8.img",
                                                "destination": "kernel8.img",
                                                "optional": True}]}))
        expect_fail(run(boot, data, p, root / "backup-protected"), "active file")
        if not (boot / "kernel8.img").exists():
            raise AssertionError("protected active file was removed")
        print("PASS active-file refusal")

        # Parent traversal and root alias/disjoint-root checks.
        for name, source, destination in (
            ("source traversal", "../outside", "x"),
            ("destination traversal", "kernel8.img", "../outside"),
        ):
            p = root / f"{name.replace(' ', '-')}.json"
            p.write_text(json.dumps({"entries": [{"source": source,
                                                   "destination": destination,
                                                   "optional": True}]}))
            expect_fail(run(boot, data, p, root / f"backup-{name}"), name)
        p = root / "alias.json"
        p.write_text(json.dumps({"entries": [{"source": "S24TIME.BAK",
                                               "destination": "x", "optional": True}]}))
        expect_fail(run(boot, boot / "nested-data", p, root / "backup-alias"), "root alias")
        print("PASS traversal and root-alias refusal")

        # Unequal destination must fail while preserving source and destination.
        (boot / "S24TIME.BAK").write_bytes(b"again")
        (data / "recovery").mkdir(exist_ok=True)
        (data / "recovery/S24TIME.BAK").write_bytes(b"wrong")
        p = root / "unequal.json"
        p.write_text(json.dumps({"entries": [{"source": "S24TIME.BAK",
                                                "destination": "recovery/S24TIME.BAK",
                                                "optional": True}]}))
        expect_fail(run(boot, data, p, root / "backup-unequal", True), "unequal destination")
        if not (boot / "S24TIME.BAK").exists() or (data / "recovery/S24TIME.BAK").read_bytes() != b"wrong":
            raise AssertionError("unequal destination changed source or destination")
        print("PASS unequal-destination refusal preserves source")

        # A symlink source and destination are both refused when the platform permits links.
        try:
            (boot / "linked.BAK").symlink_to(boot / "kernel8.img")
        except (OSError, NotImplementedError):
            print("SKIP symlink checks: host denied symlink creation")
        else:
            p = root / "source-link.json"
            p.write_text(json.dumps({"entries": [{"source": "linked.BAK",
                                                   "destination": "linked", "optional": True}]}))
            expect_fail(run(boot, data, p, root / "backup-link"), "symlink source")
            (data / "linked").symlink_to(boot / "kernel8.img")
            p.write_text(json.dumps({"entries": [{"source": "S24TIME.BAK",
                                                   "destination": "linked", "optional": True}]}))
            expect_fail(run(boot, data, p, root / "backup-link-dest"), "symlink destination")
            print("PASS source/destination symlink refusal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
