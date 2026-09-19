#!/usr/bin/env python3
"""Install a reviewed direct-boot Pi 3 bundle on an already-mounted FAT root.

No disk is selected, partitioned, formatted, or cleaned. Every replaced file
is copied to a new, explicitly named backup directory before any card writes.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from pi3_boot_stage import validate_config


FORMAT = "Anvil Pi 3 direct boot bundle 1"
REQUIRED = {
    "bootcode.bin", "start.elf", "fixup.dat", "bcm2710-rpi-3-b.dtb",
    "overlays/disable-bt.dtbo", "LICENCE.broadcom", "config.txt", "README.txt",
    "firmware.json", "armstub8.bin", "kernel8.img",
    "RaspberryPi-armstub8-BSD-3-Clause.txt",
}


class ProvisionError(RuntimeError):
    pass


def validate_windows_card_root(card_root: str, volume_root: str, drive_type: int,
                               filesystem: str, system_drive: str,
                               *, confirmed: bool) -> None:
    """Admit only an explicitly confirmed removable FAT volume root on Windows."""
    norm = lambda value: ntpath.normcase(ntpath.normpath(value))
    card = norm(card_root)
    volume = norm(volume_root)
    system = norm(system_drive)
    if card != volume:
        raise ProvisionError("on Windows, --card-root must be the removable volume root")
    if card == system:
        raise ProvisionError("refusing to provision the Windows system drive")
    if not confirmed:
        raise ProvisionError("direct install requires --yes-replace-kernel8")
    if drive_type != 2:  # DRIVE_REMOVABLE
        raise ProvisionError("Windows --card-root must be a confirmed removable drive")
    if filesystem.upper() not in ("FAT", "FAT32"):
        raise ProvisionError("Windows --card-root must use FAT/FAT32, not " + filesystem)


def windows_volume_identity(root: str) -> tuple[int, str]:
    """Return the OS-reported drive type and filesystem for an existing root."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetDriveTypeW.restype = wintypes.UINT
    drive_type = int(kernel32.GetDriveTypeW(root))
    filesystem = ctypes.create_unicode_buffer(32)
    dword_p = ctypes.POINTER(wintypes.DWORD)
    kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, dword_p, dword_p,
        dword_p, wintypes.LPWSTR, wintypes.DWORD,
    ]
    kernel32.GetVolumeInformationW.restype = wintypes.BOOL
    if not kernel32.GetVolumeInformationW(root, None, 0, None, None, None,
                                           filesystem, len(filesystem)):
        error = ctypes.get_last_error()
        raise ProvisionError(f"cannot identify Windows card volume {root!r} (error {error})")
    return drive_type, filesystem.value


def windows_system_drive() -> str:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetWindowsDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel32.GetWindowsDirectoryW.restype = wintypes.UINT
    directory = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetWindowsDirectoryW(directory, len(directory))
    if length == 0 or length >= len(directory):
        raise ProvisionError("cannot identify the Windows system drive safely")
    return str(Path(directory.value).anchor)


def validate_windows_volume(card: Path, *, confirmed: bool) -> None:
    root = Path(card.anchor).resolve()
    system_root = Path(windows_system_drive()).resolve()
    drive_type, filesystem = windows_volume_identity(str(root))
    validate_windows_card_root(str(card), str(root), drive_type, filesystem,
                               str(system_root), confirmed=confirmed)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative(name: str) -> Path:
    pure = PurePosixPath(name)
    if (not name or pure.is_absolute() or "\\" in name or
            any(part in ("", ".", "..") for part in pure.parts)):
        raise ProvisionError(f"unsafe bundle path: {name!r}")
    return Path(*pure.parts)


def reject_link_components(root: Path, relative: Path, *, allow_missing: bool) -> Path:
    """Resolve an intended child while rejecting symlinks/junctions in its path."""
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink():
                raise ProvisionError(f"refusing a symlink/junction path: {cursor}")
            if not cursor.resolve().is_relative_to(root.resolve()):
                raise ProvisionError(f"path escapes its named root: {cursor}")
        elif not allow_missing:
            raise ProvisionError(f"required path is missing: {cursor}")
    return cursor


def load_bundle(bundle: Path, expected_manifest_sha256: str) -> tuple[dict, list[tuple[str, Path, str]]]:
    if not bundle.is_dir() or bundle.is_symlink():
        raise ProvisionError("--bundle must name an ordinary staging directory")
    manifest = bundle / "SHA256.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise ProvisionError("bundle SHA256.json is missing or is not a regular file")
    if sha256(manifest) != expected_manifest_sha256.lower():
        raise ProvisionError("bundle manifest differs from the reviewed SHA-256")
    try:
        record = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvisionError(f"cannot read bundle manifest: {exc}") from exc
    if record.get("format") != FORMAT:
        raise ProvisionError("unsupported direct-boot bundle format")
    files = record.get("files")
    if not isinstance(files, dict) or set(files) != REQUIRED:
        raise ProvisionError("bundle manifest has an unexpected file set")
    normalized: set[str] = set()
    operations: list[tuple[str, Path, str]] = []
    for name, item in files.items():
        relative = safe_relative(name)
        key = name.casefold()
        if key in normalized:
            raise ProvisionError(f"duplicate case-insensitive FAT destination: {name}")
        normalized.add(key)
        source = reject_link_components(bundle, relative, allow_missing=False)
        if not source.is_file():
            raise ProvisionError(f"bundle entry is not a regular file: {name}")
        expected_hash = item.get("sha256") if isinstance(item, dict) else None
        expected_bytes = item.get("bytes") if isinstance(item, dict) else None
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64 or
                not isinstance(expected_bytes, int) or expected_bytes < 0):
            raise ProvisionError(f"bad size/hash record for {name}")
        if source.stat().st_size != expected_bytes or sha256(source) != expected_hash.lower():
            raise ProvisionError(f"bundle file does not match manifest: {name}")
        operations.append((name, source, expected_hash.lower()))

    try:
        validate_config(bundle / "config.txt")
    except (OSError, ValueError) as exc:
        raise ProvisionError(f"direct-boot config refused: {exc}") from exc
    # Pin the image contract independently of the JSON labels.
    pmf = record.get("monitorPmf", {})
    expected_contract = {
        "loadAddress": 0x200000, "entryAddress": 0x200000,
        "bssAddress": 0x1100000, "stackAddress": 0x1F00000,
        "target": 2837,
    }
    if any(pmf.get(key) != value for key, value in expected_contract.items()):
        raise ProvisionError("bundle monitor PMF metadata violates the direct Pi 3 contract")
    if pmf.get("imageBytes") != files["kernel8.img"].get("bytes"):
        raise ProvisionError("bundle PMF image length differs from kernel8.img")
    return record, operations


def install(card_root: Path, bundle: Path, backup_dir: Path,
            manifest_sha256: str, *, yes_replace_kernel8: bool) -> dict:
    if not card_root.is_dir() or card_root.is_symlink():
        raise ProvisionError("--card-root must name an existing ordinary directory")
    card = card_root.resolve()
    if os.name == "nt":
        validate_windows_volume(card, confirmed=yes_replace_kernel8)
    elif card == Path(card.anchor).resolve():
        raise ProvisionError("refusing a filesystem root as the card root")
    bundle_root = bundle.resolve()
    if (card == bundle_root or card.is_relative_to(bundle_root) or
            bundle_root.is_relative_to(card)):
        raise ProvisionError("bundle source and card root must be disjoint")
    if not yes_replace_kernel8:
        raise ProvisionError("direct install requires --yes-replace-kernel8")
    if backup_dir.exists() or backup_dir.is_symlink():
        raise ProvisionError("backup directory must be new and must not already exist")
    backup = backup_dir.resolve()
    if backup == card or backup.is_relative_to(card) or card.is_relative_to(backup):
        raise ProvisionError("backup directory and card root must be disjoint")
    if (backup == bundle_root or backup.is_relative_to(bundle_root) or
            bundle_root.is_relative_to(backup)):
        raise ProvisionError("backup directory and bundle source must be disjoint")

    record, operations = load_bundle(bundle, manifest_sha256)
    # Validate the currently mounted root before making any backup or write.
    validate_config(bundle / "config.txt")
    required_existing = ("bootcode.bin", "start.elf", "fixup.dat", "bcm2710-rpi-3-b.dtb",
                         "overlays/disable-bt.dtbo", "LICENCE.broadcom", "config.txt")
    for name in required_existing:
        dest = reject_link_components(card, safe_relative(name), allow_missing=False)
        if not dest.is_file():
            raise ProvisionError(f"card root is missing required firmware file: {name}")
    if (card / "autoboot.txt").exists():
        raise ProvisionError("autoboot.txt is present; review and remove that alternate boot selector first")

    destinations: list[tuple[str, Path, Path, str]] = []
    for name, source, digest in operations:
        relative = safe_relative(name)
        dest = reject_link_components(card, relative, allow_missing=True)
        if dest.exists() and not dest.is_file():
            raise ProvisionError(f"destination is not a regular file: {dest}")
        destinations.append((name, source, dest, digest))

    # Back up all current files that will be changed before touching the card.
    # Prepare the exact backup set before starting mutations.
    changed = [(name, dest) for name, _, dest, digest in destinations
               if dest.is_file() and sha256(dest) != digest]
    backup.mkdir(parents=True, exist_ok=False)
    try:
        for name, dest in changed:
            saved = backup / safe_relative(name)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
            if sha256(saved) != sha256(dest):
                raise ProvisionError(f"backup verification failed: {name}")

        for name, source, dest, digest in destinations:
            if dest.is_file() and sha256(dest) == digest:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix="ANVIL-", dir=dest.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
                    shutil.copyfileobj(inp, out, 1024 * 1024)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temporary, dest)
            finally:
                if temporary.exists():
                    temporary.unlink()
            if sha256(dest) != digest:
                raise ProvisionError(f"card readback verification failed: {name}")
    except BaseException:
        # Preserve the backup and any completed writes for explicit recovery;
        # never attempt a broad automatic rollback on a FAT boot volume.
        raise

    summary = {
        "cardRoot": str(card),
        "backupDir": str(backup),
        "manifestSha256": manifest_sha256.lower(),
        "installed": {name: digest for name, _, _, digest in destinations},
        "changedBackups": [name for name, _ in changed],
        "monitorPmf": record["monitorPmf"],
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-root", required=True, type=Path,
                        help="explicit root of the already-mounted FAT boot volume")
    parser.add_argument("--bundle", required=True, type=Path,
                        help="new direct-boot staging directory from pi3_boot_stage.py")
    parser.add_argument("--manifest-sha256", required=True,
                        help="reviewed SHA-256 printed for bundle SHA256.json")
    parser.add_argument("--backup-dir", required=True, type=Path,
                        help="new directory outside the card for prior files")
    parser.add_argument("--yes-replace-kernel8", action="store_true",
                        help="acknowledge direct install replaces the firmware kernel image")
    args = parser.parse_args()
    result = install(args.card_root, args.bundle, args.backup_dir,
                     args.manifest_sha256, yes_replace_kernel8=args.yes_replace_kernel8)
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PASS: direct Pi 3 files installed and read back; no partition or format operation occurred")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisionError as error:
        raise SystemExit(f"REFUSED: {error}") from error
