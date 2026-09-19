#!/usr/bin/env python3
"""Replace only the immutable kernel8.img loader on a prepared Pi 3 boot card.

Provisioning recreates both monitor slots and both control records, which
discards whichever slot is currently confirmed and restarts the generation
count at 1.  That is the right tool for a card that has never been prepared and
the wrong one for a card whose running monitor is healthy: the loader is the
only part that cannot be replaced over the serial or Ethernet A/B transports,
so replacing it is the only reason to take the card out of the board at all.

This tool therefore writes exactly one file.  Both slot images, both control
records and every firmware file are read and hashed before the write and hashed
again afterwards, and any difference is reported as a failure, so the confirmed
A/B state that survives the swap is proven to have survived rather than assumed.
The outgoing loader is copied to a named backup on the PC first, so the previous
boot chain can always be put back.

    python tools/pi3_loader_replace.py --card-root X:\\ \
        --loader build/pi3/kernel8.img \
        --backup _work/pi3-loader-backup/KERNEL8.IMG.outgoing \
        --yes-replace-kernel8

The board still performs the final FAT-contiguity and image-hash checks itself;
a host readback proves the bytes landed, not that the loader will accept them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from pi3_provision import (
    LOADER_MAX,
    REQUIRED_FIRMWARE,
    SLOT_BYTES,
    ProvisionError,
    check_boot_contract,
    check_card_root,
    sha256,
    write_atomic,
)
from pi3_slot import SlotError, validate_loader_pmf


# Every file the loader-only replacement must leave byte-identical.  The slot
# images and control records carry the A/B transaction; the firmware files carry
# the pinned boot contract.  kernel8.img is deliberately absent: it is the one
# file this tool is allowed to change.
PRESERVED = ("ANVILA.BIN", "ANVILB.BIN", "P3CTRLA.BIN", "P3CTRLB.BIN") + REQUIRED_FIRMWARE

EXPECTED_SIZES = {
    "ANVILA.BIN": SLOT_BYTES,
    "ANVILB.BIN": SLOT_BYTES,
    "P3CTRLA.BIN": 512,
    "P3CTRLB.BIN": 512,
}


def survey(root: Path) -> dict[str, tuple[int, str]]:
    """Size and digest of every file the replacement must not touch."""
    state: dict[str, tuple[int, str]] = {}
    for name in PRESERVED:
        path = root / name
        if not path.is_file():
            raise ProvisionError(
                "this card has not been provisioned for A/B booting; "
                f"the required file {name} is missing, so a loader-only "
                "replacement would leave it unbootable"
            )
        size = path.stat().st_size
        expected = EXPECTED_SIZES.get(name)
        if expected is not None and size != expected:
            raise ProvisionError(
                f"{name} is {size} bytes and the A/B layout requires exactly "
                f"{expected}; refusing to replace the loader over a card whose "
                "slot layout is not the one the loader expects"
            )
        state[name] = (size, sha256(path))
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-root", required=True, type=Path)
    parser.add_argument("--loader", required=True, type=Path)
    parser.add_argument(
        "--loader-pmf",
        type=Path,
        help="compiler PMFBOOT v2 sidecar (default: <loader>.pmf)",
    )
    parser.add_argument(
        "--backup",
        required=True,
        type=Path,
        help="file on the PC to copy the outgoing kernel8.img to; it must not "
        "already exist, so a second run cannot overwrite the only way back",
    )
    parser.add_argument(
        "--yes-replace-kernel8",
        action="store_true",
        help="required acknowledgement that the immutable loader will change",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.yes_replace_kernel8:
        raise ProvisionError(
            "kernel8.img replacement was not acknowledged; add "
            "--yes-replace-kernel8 after checking --card-root"
        )
    check_card_root(args.card_root)
    root = args.card_root.resolve()

    loader_pmf_path = args.loader_pmf or Path(str(args.loader) + ".pmf")
    if not args.loader.is_file() or not loader_pmf_path.is_file():
        raise ProvisionError(
            "the loader and its PMF sidecar must both be existing files"
        )
    loader = args.loader.read_bytes()
    loader_pmf = loader_pmf_path.read_bytes()
    if not loader or len(loader) > LOADER_MAX:
        raise ProvisionError(
            f"loader must contain 1..{LOADER_MAX} bytes; got {len(loader)}"
        )
    try:
        loader_metadata = validate_loader_pmf(loader_pmf, loader)
    except SlotError as exc:
        raise ProvisionError(f"loader refused: {exc}") from exc

    loader_sha256 = hashlib.sha256(loader).hexdigest()
    check_boot_contract(root, args.loader, loader_sha256)

    target = root / "kernel8.img"
    if not target.is_file():
        raise ProvisionError(
            "this card has no kernel8.img, so it has never been provisioned; "
            "use pi3_provision.py for a first installation"
        )
    outgoing = target.read_bytes()
    outgoing_sha256 = hashlib.sha256(outgoing).hexdigest()
    if outgoing_sha256 == loader_sha256:
        print(
            "the card already carries this exact loader "
            f"({len(outgoing)} bytes, sha256 {outgoing_sha256}); nothing to do"
        )
        return 0

    before = survey(root)

    if args.backup.exists():
        raise ProvisionError(
            f"the backup path already exists: {args.backup}; name a new file so "
            "an earlier outgoing loader cannot be overwritten"
        )
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    args.backup.write_bytes(outgoing)
    if sha256(args.backup) != outgoing_sha256:
        raise ProvisionError("the outgoing loader did not copy to the backup intact")
    print(
        f"outgoing loader kept at {args.backup} "
        f"({len(outgoing)} bytes, sha256 {outgoing_sha256})"
    )

    free = shutil.disk_usage(root).free
    # The replacement is written beside the original before os.replace, so the
    # card briefly holds both.
    if free < len(loader) + 1024 * 1024:
        raise ProvisionError(
            f"the card has {free} bytes free and the replacement needs "
            f"{len(loader)} plus headroom; free space before replacing the loader"
        )

    print(f"writing {target} ({len(loader)} bytes, sha256 {loader_sha256})")
    # write_atomic flushes and fsyncs the replacement before renaming it over
    # the old loader, so the readback below reads the medium, not a cache.
    write_atomic(target, [loader])

    written = target.stat().st_size
    if written != len(loader):
        raise ProvisionError(
            f"readback size mismatch for kernel8.img: {written} != {len(loader)}"
        )
    readback = sha256(target)
    if readback != loader_sha256:
        raise ProvisionError(
            f"readback hash mismatch for kernel8.img: {readback} != {loader_sha256}; "
            f"restore it from {args.backup} before powering the board"
        )

    after = survey(root)
    changed = sorted(name for name in before if before[name] != after[name])
    if changed:
        raise ProvisionError(
            "the loader replacement changed files it must not touch: "
            + ", ".join(changed)
        )
    print(f"all {len(before)} slot, control and firmware files are unchanged")

    manifest_path = root / "P3UPDATE.JSON"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProvisionError(
                f"the card's P3UPDATE.JSON could not be read back: {exc}; the new "
                "loader is in place but its record on the card is now stale"
            ) from exc
        manifest["loaderSha256"] = loader_sha256
        manifest["loaderPmfSha256"] = hashlib.sha256(loader_pmf).hexdigest()
        manifest["loaderMetadata"] = loader_metadata
        manifest["loaderReplacedFromSha256"] = outgoing_sha256
        files = manifest.get("files")
        if isinstance(files, dict) and isinstance(files.get("kernel8.img"), dict):
            files["kernel8.img"] = {"bytes": len(loader), "sha256": loader_sha256}
        write_atomic(
            manifest_path,
            [json.dumps(manifest, indent=2, sort_keys=True).encode("ascii") + b"\n"],
        )
        print(f"updated {manifest_path} to record the loader now on the card")

    print(
        "loader replaced; the slots and control records are untouched, so the "
        "confirmed monitor still boots. Board contiguity/hash acceptance remains."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisionError as exc:
        print(f"!! {exc}", file=sys.stderr)
        raise SystemExit(1)
