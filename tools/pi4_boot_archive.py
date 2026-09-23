#!/usr/bin/env python3
"""Plan and verify host-side archival of optional Pi 4 boot files.

This tool operates on ordinary directories only. It never talks to a board or
mounts a volume. A plan is explicit and reviewed by the caller; dry-run is the
default and --apply is required before any source is removed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

MANDATORY = {
    "start4.elf", "fixup4.dat", "config.txt", "bcm2711-rpi-4-b.dtb",
    "kernel8.img", "armstub8.bin", "armstub8.BIN", "settings.txt",
    "modules.txt", "thermal.mod", "brcmfw.bin", "brcmnv.txt", "brcmclm.blb",
}


def fail(msg: str) -> None:
    raise SystemExit(f"pi4_boot_archive: {msg}")


def inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_path(root: Path, value: str, label: str, *, existing: bool = False) -> Path:
    if not value or Path(value).is_absolute():
        fail(f"{label} must be a relative path")
    if ".." in Path(value).parts or Path(value).drive:
        fail(f"{label} contains a parent or drive component")
    raw = root / Path(value)
    current = root
    for part in Path(value).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            fail(f"{label} traverses a link: {value}")
    resolved = raw.resolve(strict=False)
    if not inside(root.resolve(), resolved):
        fail(f"{label} escapes its explicit root: {value}")
    cur = root.resolve()
    rel = resolved.relative_to(cur)
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            fail(f"{label} traverses a symlink: {value}")
    if existing and not resolved.exists():
        fail(f"{label} does not exist: {value}")
    return resolved


def regular(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        fail(f"{label} is not a regular non-symlink file: {path.name}")


def digest(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as src:
        while True:
            block = src.read(1024 * 1024)
            if not block:
                break
            h.update(block)
            size += len(block)
    return size, h.hexdigest()


def config_refs(boot: Path) -> set[str]:
    cfg = boot / "config.txt"
    if not cfg.exists():
        return set()
    regular(cfg, "config.txt")
    refs: set[str] = set()
    for raw in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split(";", 1)[0].split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if key.lower() in {"kernel", "device_tree", "armstub", "initramfs", "include"}:
            token = value.split()[0].strip('"') if value else ""
            if token:
                refs.add(Path(token).name.lower())
        elif key.lower() in {"dtoverlay", "overlay_prefix"}:
            token = value.split(",", 1)[0].strip()
            if token:
                refs.add((token if token.lower().endswith(".dtbo") else token + ".dtbo").lower())
    return refs


def protected(boot: Path) -> set[str]:
    names = {x.lower() for x in MANDATORY}
    names.update(config_refs(boot))
    return names


def load_plan(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        fail("plan JSON must be a regular file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid plan JSON: {exc}")
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        fail("plan JSON must contain a non-empty entries array")
    out = []
    for i, item in enumerate(entries):
        if (not isinstance(item, dict) or not isinstance(item.get("source"), str)
                or not isinstance(item.get("destination"), str)
                or item.get("optional") is not True):
            fail(f"entry {i} needs string source/destination and optional=true")
        out.append(item)
    return out


def copy_verified(source: Path, dest: Path, backup: Path | None) -> tuple[int, str]:
    size, sha = digest(source)
    for target in (dest, backup):
        if target is None:
            continue
        if target.exists() or target.is_symlink():
            regular(target, "existing destination")
            got = digest(target)
            if got != (size, sha):
                fail(f"refusing unequal existing destination: {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmpname = tempfile.mkstemp(prefix=".pi4-archive-", dir=target.parent)
            os.close(fd)
            tmp = Path(tmpname)
            try:
                shutil.copyfile(source, tmp)
                with tmp.open("r+b") as written:
                    written.flush()
                    os.fsync(written.fileno())
                if digest(tmp) != (size, sha):
                    fail(f"readback hash mismatch: {target}")
                tmp.replace(target)
                if digest(target) != (size, sha):
                    fail(f"final readback hash mismatch: {target}")
            finally:
                tmp.unlink(missing_ok=True)
    return size, sha


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--boot-root", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--plan-json", type=Path, required=True)
    ap.add_argument("--backup-dir", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="copy, verify, and remove sources")
    args = ap.parse_args()
    boot, data, plan, backup = (p.resolve() for p in (args.boot_root, args.data_root, args.plan_json, args.backup_dir))
    if not boot.is_dir() or not data.is_dir():
        fail("boot and data roots must already be directories")
    if plan.is_symlink() or not plan.is_file():
        fail("plan JSON must already be a regular file")
    if boot == data or inside(boot, data) or inside(data, boot):
        fail("boot and data roots must be distinct and disjoint")
    if inside(boot, backup) or inside(data, backup):
        fail("backup must be outside both volume roots")
    entries = load_plan(plan)
    protected_names = protected(boot)
    seen = set()
    destinations = set()
    rows = []
    for index, item in enumerate(entries):
        src = safe_path(boot, item["source"], f"entry {index} source", existing=True)
        dst = safe_path(data, item["destination"], f"entry {index} destination")
        regular(src, f"entry {index} source")
        if src.name.lower() in protected_names:
            fail(f"entry {index} attempts to archive protected boot file: {src.name}")
        if src in seen or src == dst:
            fail(f"entry {index} duplicates or aliases another source")
        seen.add(src)
        if dst in destinations:
            fail("duplicate destination in plan")
        destinations.add(dst)
        if dst.exists() or dst.is_symlink():
            regular(dst, f"entry {index} destination")
        backup_target = backup / src.name
        backup_target = safe_path(backup, src.name, f"entry {index} backup")
        if backup_target.exists() or backup_target.is_symlink():
            regular(backup_target, f"entry {index} backup")
        size, sha = digest(src)
        rows.append((src, dst, backup_target, size, sha, item.get("reason", "")))
    active = boot / "kernel8.img"
    if not active.exists():
        fail("active kernel8.img is missing")
    regular(active, "active kernel8.img")
    active_backup = safe_path(backup, "kernel8.img", "active kernel backup")
    if active_backup.exists() or active_backup.is_symlink():
        regular(active_backup, "active kernel backup")
    print(json.dumps({"mode": "apply" if args.apply else "survey", "protected": sorted(protected_names),
                      "entries": [{"source": str(s), "destination": str(d), "bytes": n, "sha256": h,
                                   "reason": reason} for s, d, _, n, h, reason in rows]}, indent=2))
    if not args.apply:
        return 0
    copy_verified(active, active_backup, None)
    for src, dst, backup_target, size, sha, _ in rows:
        copy_verified(src, backup_target, None)
        copy_verified(src, dst, None)
        if digest(src) != (size, sha):
            fail(f"source changed during copy: {src.name}")
        src.unlink()
        print(f"removed {src.name} after verified copies ({size} bytes, {sha})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
