#!/usr/bin/env python3
"""Desk gate for the Pi 3 loader-only replacement.

Builds throwaway boot volumes in a temporary directory and drives
`pi3_loader_replace.main()` over them.  Nothing here touches a real card, a
real disk or a board: the point is to prove that the one operation which needs
the card out of the Pi refuses every wrong card, keeps a way back, and leaves
the A/B transaction byte-identical.

The pinned-firmware contract is the one check this gate stubs, because the
official Broadcom boot binaries are not in this repository and their hashes
cannot be forged.  That is not a hole in the proof: one case replaces the stub
with a refusal and requires the tool to stop, which proves the tool consults the
contract, and the contract itself is already gated by `pi3_boot_stage.py`.

    python tools/pi3_loader_replace_check.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pi3_loader_replace as replace  # noqa: E402
from pi3_ab_provision import REQUIRED_FIRMWARE, SLOT_BYTES, ProvisionError  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "build" / "pi3" / "recovery" / "kernel8.img"
LOADER_PMF = ROOT / "build" / "pi3" / "recovery" / "kernel8.img.pmf"
PINNED_CONFIG = ROOT / "RaspberryPi3" / "Boot" / "config.txt"

checks = 0


def check(condition: bool, what: str) -> None:
    global checks
    checks += 1
    if not condition:
        raise SystemExit(f"FAIL: {what}")


def sparse(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.truncate(size)


def make_card(where: Path, outgoing: bytes) -> Path:
    root = where / "card"
    root.mkdir(parents=True)
    for name in REQUIRED_FIRMWARE:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "config.txt":
            target.write_bytes(PINNED_CONFIG.read_bytes())
        else:
            target.write_bytes(b"pinned firmware stand-in for " + name.encode())
    (root / "kernel8.img").write_bytes(outgoing)
    sparse(root / "ANVILA.BIN", SLOT_BYTES)
    sparse(root / "ANVILB.BIN", SLOT_BYTES)
    (root / "P3CTRLA.BIN").write_bytes(bytes(512))
    (root / "P3CTRLB.BIN").write_bytes(bytes(512))
    (root / "P3UPDATE.JSON").write_text(
        json.dumps(
            {
                "format": "Anvil Pi3 A/B provision 2",
                "activeSlot": "B",
                "generation": 5,
                "loaderSha256": hashlib.sha256(outgoing).hexdigest(),
                "files": {"kernel8.img": {"bytes": len(outgoing), "sha256": "stale"}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    return root


def snapshot(root: Path) -> dict:
    state = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return state


def run(root: Path, backup: Path, *, acknowledge: bool = True, pmf: Path | None = None):
    argv = [
        "pi3_loader_replace.py",
        "--card-root",
        str(root),
        "--loader",
        str(LOADER),
        "--loader-pmf",
        str(pmf or LOADER_PMF),
        "--backup",
        str(backup),
    ]
    if acknowledge:
        argv.append("--yes-replace-kernel8")
    saved = sys.argv
    sys.argv = argv
    try:
        return replace.main()
    finally:
        sys.argv = saved


def expect_refusal(root: Path, backup: Path, fragment: str, **kwargs) -> None:
    before = snapshot(root)
    try:
        run(root, backup, **kwargs)
    except ProvisionError as exc:
        check(fragment in str(exc), f"refusal names {fragment!r}; got {exc}")
    else:
        raise SystemExit(f"FAIL: expected a refusal mentioning {fragment!r}")
    check(snapshot(root) == before, f"card is untouched after the {fragment!r} refusal")


def main() -> int:
    if not LOADER.is_file() or not LOADER_PMF.is_file():
        raise SystemExit(
            "build/pi3/recovery/kernel8.img and its .pmf sidecar must exist; "
            "run tools/build.py pi3-loader first"
        )
    loader = LOADER.read_bytes()
    loader_sha = hashlib.sha256(loader).hexdigest()
    outgoing = b"an older and deliberately different loader\n" * 64
    outgoing_sha = hashlib.sha256(outgoing).hexdigest()

    stubbed = []

    def allow(root, image, sha256):
        stubbed.append(sha256)

    def refuse(root, image, sha256):
        raise ProvisionError("Pi 3 pinned boot contract refused: stand-in refusal")

    original = replace.check_boot_contract

    with tempfile.TemporaryDirectory(prefix="pi3-loader-replace-") as temporary:
        area = Path(temporary)

        # 1. The pinned boot contract is consulted, and a refusal stops everything.
        replace.check_boot_contract = refuse
        root = make_card(area / "contract", outgoing)
        expect_refusal(root, area / "contract" / "backup.img", "pinned boot contract")
        check(
            not (area / "contract" / "backup.img").exists(),
            "no backup is written when the boot contract refuses",
        )

        replace.check_boot_contract = allow

        # 2. The acknowledgement is mandatory.
        root = make_card(area / "unacked", outgoing)
        expect_refusal(
            root,
            area / "unacked" / "backup.img",
            "was not acknowledged",
            acknowledge=False,
        )

        # 3. A directory that is not the prepared boot volume is refused.
        bare = area / "bare"
        bare.mkdir()
        (bare / "kernel8.img").write_bytes(outgoing)
        try:
            run(bare, area / "bare-backup.img")
        except ProvisionError as exc:
            check(
                "not the prepared Pi 3 boot volume" in str(exc),
                f"a bare directory is refused; got {exc}",
            )
        else:
            raise SystemExit("FAIL: a bare directory was accepted as a card")

        # 4. A card with no A/B slot files is refused before anything is written.
        root = make_card(area / "noslots", outgoing)
        (root / "ANVILB.BIN").unlink()
        expect_refusal(root, area / "noslots" / "backup.img", "ANVILB.BIN is missing")

        # 5. A slot of the wrong size is refused.
        root = make_card(area / "shortslot", outgoing)
        sparse(root / "ANVILA.BIN", SLOT_BYTES - 512)
        expect_refusal(root, area / "shortslot" / "backup.img", "slot layout")

        # 6. The sidecar must actually describe this loader.
        root = make_card(area / "badpmf", outgoing)
        wrong = area / "wrong.pmf"
        wrong.write_bytes(b"not a PMFBOOT sidecar")
        expect_refusal(
            root, area / "badpmf" / "backup.img", "loader refused", pmf=wrong
        )

        # 7. The happy path.
        root = make_card(area / "good", outgoing)
        before = snapshot(root)
        backup = area / "good" / "kept" / "KERNEL8.IMG.outgoing"
        check(run(root, backup) == 0, "the replacement succeeds on a prepared card")
        check(stubbed and stubbed[-1] == loader_sha, "the contract saw the new loader")
        check(backup.is_file(), "the outgoing loader is kept")
        check(
            hashlib.sha256(backup.read_bytes()).hexdigest() == outgoing_sha,
            "the kept copy is the exact outgoing loader",
        )
        after = snapshot(root)
        check(
            after["kernel8.img"] == loader_sha,
            "the card now carries the new loader byte for byte",
        )
        moved = {name for name in after if after[name] != before.get(name)}
        check(
            moved == {"kernel8.img", "P3UPDATE.JSON"},
            f"only the loader and its record changed; {sorted(moved)} did",
        )
        for name in ("ANVILA.BIN", "ANVILB.BIN", "P3CTRLA.BIN", "P3CTRLB.BIN"):
            check(after[name] == before[name], f"{name} survived the loader swap")
        manifest = json.loads((root / "P3UPDATE.JSON").read_text(encoding="utf-8"))
        check(
            manifest["loaderSha256"] == loader_sha
            and manifest["loaderReplacedFromSha256"] == outgoing_sha,
            "the card's record names the loader now on it and the one before",
        )
        check(
            manifest["activeSlot"] == "B" and manifest["generation"] == 5,
            "the recorded A/B selection is not rewritten by a loader swap",
        )
        check(
            manifest["files"]["kernel8.img"]["sha256"] == loader_sha,
            "the stale per-file record is corrected",
        )

        # 8. A second run refuses rather than overwriting the only way back.
        (root / "kernel8.img").write_bytes(outgoing)
        expect_refusal(root, backup, "backup path already exists")

        # 9. Replacing a loader with itself writes nothing at all.
        root = make_card(area / "same", loader)
        before = snapshot(root)
        check(
            run(root, area / "same" / "backup.img") == 0,
            "an identical loader is accepted as a no-op",
        )
        check(snapshot(root) == before, "the no-op card is byte-identical")
        check(
            not (area / "same" / "backup.img").exists(),
            "a no-op keeps no backup",
        )

    replace.check_boot_contract = original
    print(
        f"pi3_loader_replace_check PASS {checks} checks; "
        "temporary volumes only, no card, disk or board touched"
    )
    print(f"Loader under test: {len(loader)} bytes; SHA256 {loader_sha.upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
