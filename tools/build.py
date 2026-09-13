#!/usr/bin/env python3
"""Build Anvil targets with the PureMetal application in command-line mode.

The editor and the compiler are one program: `PureMetalForge.exe --compile`
builds without opening a window. Point at it with --compiler or PMF_COMPILER.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_count  # noqa: E402
from pi3_slot import wrap_monitor  # noqa: E402
from pi3_slot_pack import atomic_write  # noqa: E402
from rockpi4c_image import wrap as wrap_rockpi4c_image  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "pi4": {
        "source": Path("RaspberryPi4/Board/board.pi4"),
        "output": Path("build/pi4/anvil.img"),
        "args": [],
    },
    "unoq": {
        "source": Path("ArduinoQ/Board/board.unoq"),
        "output": Path("build/unoq/anvil.img"),
        "args": ["--entry-returns"],
    },
    "pi3-loader": {
        "source": Path("RaspberryPi3/Board/loader.pi3"),
        "output": Path("build/pi3/kernel8.img"),
        "target": "pi3",
        "count_target": "pi3-loader",
        "args": [],
    },
    "pi3-updater": {
        "source": Path("RaspberryPi3/Board/updater.pi3"),
        "output": Path("build/pi3/anvil.img"),
        "slot_output": Path("build/pi3/anvil-slot.img"),
        "target": "pi3",
        "count_target": "pi3-updater",
        "args": [],
    },
    "pi3-diagnostic": {
        "source": Path("RaspberryPi3/Board/board.pi3"),
        "output": Path("build/pi3-diagnostic/diagnostic.img"),
        "target": "pi3",
        "count_target": "pi3",
        "args": ["--load-addr", "0x80000", "--stack-addr", "0x200000"],
    },
    "armstub": {
        "source": Path("RaspberryPi4/Board/armstub8.asm"),
        "output": Path("build/pi4/armstub8.bin"),
        "target": "pi4",
        "args": ["--armstub"],
    },
    "rockpi4c": {
        "source": Path("RockPi4C/Board/board.rockpi4c"),
        "output": Path("build/rockpi4c/anvil-flat.img"),
        "image_output": Path("build/rockpi4c/Image"),
        "args": ["--load-addr", "0x02000040", "--bss-addr", "0x02800000",
                 "--stack-addr", "0x03000000"],
    },
}
TARGET_ALIASES = {"pi3": ("pi3-loader", "pi3-updater")}


class PublishedArtifacts:
    """A reversible, same-volume publication of one compiler result set."""

    def __init__(self, pairs: list[tuple[Path, Path]], token: str) -> None:
        self.pairs = pairs
        self.token = token
        self.backups: dict[Path, Path] = {}
        self.published: list[Path] = []

    def publish(self) -> None:
        try:
            for staged, final in self.pairs:
                final.parent.mkdir(parents=True, exist_ok=True)
                if final.exists():
                    backup = final.with_name(f".{final.name}.build-backup-{self.token}")
                    os.replace(final, backup)
                    self.backups[final] = backup
                os.replace(staged, final)
                self.published.append(final)
        except BaseException:
            self.rollback()
            raise

    def rollback(self) -> None:
        for final in reversed(self.published):
            try:
                final.unlink()
            except FileNotFoundError:
                pass
        self.published.clear()
        for final, backup in self.backups.items():
            if backup.exists():
                os.replace(backup, final)
        self.backups.clear()

    def finalize(self) -> None:
        for backup in self.backups.values():
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
        self.backups.clear()


def _stage_output(output: Path, token: str) -> Path:
    """A unique compiler destination beside the eventual atomic destination."""
    output.parent.mkdir(parents=True, exist_ok=True)
    return output.with_name(f".{output.name}.build-stage-{token}")


def _compile_and_publish(compiler: str, target: str, source: Path,
                         output: Path, spec: dict) -> PublishedArtifacts:
    """Compile to private names, validate/pack, then reversibly publish."""
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    staged_output = _stage_output(output, token)
    staged_slot = None
    staged_slot_json = None
    staged_image = None
    staged_image_json = None
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [
        compiler, "--compile", spec["source"].as_posix(), "-t",
        spec.get("target", target), *spec["args"], "-o", str(staged_output),
    ]
    print(f"Building {target}: {spec['source']} -> {spec['output']}")
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if completed.returncode:
            raise SystemExit(
                f"The {target} build failed with exit code {completed.returncode}. "
                f"Its build identity and prior artifacts were preserved."
            )
        if not staged_output.is_file() or staged_output.stat().st_size == 0:
            raise SystemExit(
                f"The {target} compiler reported success but did not write a usable "
                f"{spec['output']}. Its build identity and prior artifacts were preserved."
            )

        # Every ordinary A64 compiler result has a PMF sidecar. Treat its
        # absence as an incomplete artifact, before either file is published.
        staged_pmf = Path(str(staged_output) + ".pmf")
        if "--armstub" not in spec["args"] and not staged_pmf.is_file():
            raise SystemExit(
                f"The {target} compiler wrote an image without its PMF container. "
                f"Nothing was published and the build number was not consumed."
            )

        slot_output = spec.get("slot_output")
        if slot_output is not None:
            slot, metadata = wrap_monitor(staged_pmf.read_bytes())
            slot_path = ROOT / slot_output
            staged_slot = _stage_output(slot_path, token)
            staged_slot_json = Path(str(staged_slot) + ".json")
            atomic_write(staged_slot, slot)
            atomic_write(
                staged_slot_json,
                (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("ascii"),
            )

        image_output = spec.get("image_output")
        if image_output is not None:
            wrapped, metadata = wrap_rockpi4c_image(staged_output.read_bytes())
            image_path = ROOT / image_output
            staged_image = _stage_output(image_path, token)
            staged_image_json = Path(str(staged_image) + ".json")
            atomic_write(staged_image, wrapped)
            atomic_write(
                staged_image_json,
                (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("ascii"),
            )

        compiler_files = sorted(
            (path for path in staged_output.parent.glob(staged_output.name + "*")
             if path.is_file()),
            key=lambda path: (path != staged_output, path.name),
        )
        pairs = [
            (path, output.with_name(output.name + path.name[len(staged_output.name):]))
            for path in compiler_files
        ]
        if staged_slot is not None and staged_slot_json is not None:
            slot_path = ROOT / spec["slot_output"]
            pairs.extend(((staged_slot, slot_path),
                          (staged_slot_json, Path(str(slot_path) + ".json"))))
        if staged_image is not None and staged_image_json is not None:
            image_path = ROOT / spec["image_output"]
            pairs.extend(((staged_image, image_path),
                          (staged_image_json, Path(str(image_path) + ".json"))))
        publication = PublishedArtifacts(pairs, token)
        publication.publish()
        print(f"Built {spec['output']} ({output.stat().st_size} bytes).")
        if staged_slot is not None:
            print(
                f"Packed {spec['slot_output']} ({(ROOT / spec['slot_output']).stat().st_size} "
                f"bytes)."
            )
        if staged_image is not None:
            print(f"Wrapped {spec['image_output']} ({(ROOT / spec['image_output']).stat().st_size} bytes).")
        return publication
    finally:
        # A failed compiler or packer may leave a partial private set. It is
        # never a build product and has no reason to survive the refusal.
        for path in staged_output.parent.glob(staged_output.name + "*"):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        for path in (staged_slot, staged_slot_json, staged_image, staged_image_json):
            if path is not None and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass


# The one application is both the editor and the compiler. On Windows it is
# PureMetalForge.exe; the Linux build of the same sources answers to
# PureMetalForge.linux, and a plain PureMetalForge is what an installed copy
# is often called. All three are the same program.
COMPILER_NAMES = ("PureMetalForge.exe", "PureMetalForge.linux", "PureMetalForge")

# THE RETIRED CONSOLE COMPILER. Ruled 2026-09-11: "the standard ide now
# replaces pmfc. no more using pmfc." It is gone from the toolchain, and the
# reason to REFUSE it by name rather than quietly run it is that an old binary
# left on a bench still compiles - it just compiles with a frontend nobody is
# fixing any more, and every result made with it would read as evidence about
# the compiler that ships. A stale path in a script or an environment variable
# is exactly how that happens, so the path says so out loud.
RETIRED_COMPILER_STEMS = ("pmfc",)


def refuse_retired(path: Path) -> None:
    stem = path.stem.lower()
    if any(stem == retired or stem.startswith(retired + "_") or
           stem.startswith(retired + ".") for retired in RETIRED_COMPILER_STEMS):
        raise SystemExit(
            f"{path} is the retired console compiler. It was replaced on "
            "2026-09-11 by the one application, which compiles from the "
            "command line: pass --compiler <PureMetalForge.exe> or set "
            "PMF_COMPILER to it. Anvil does not build with pmfc any more, and "
            "an image built with it is not evidence about the compiler that "
            "ships."
        )


def find_compiler(explicit: str | None) -> str:
    """Resolve the one PureMetal application that also compiles."""
    requested = explicit or os.environ.get("PMF_COMPILER")
    if requested:
        candidate = Path(requested).expanduser()
        if candidate.is_file():
            resolved_path = candidate.resolve()
            refuse_retired(resolved_path)
            return str(resolved_path)
        resolved = shutil.which(requested)
        if resolved:
            refuse_retired(Path(resolved))
            return resolved
        raise SystemExit(
            f"The requested PureMetal compiler was not found: {requested}. "
            "Check --compiler or PMF_COMPILER."
        )

    for name in COMPILER_NAMES:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise SystemExit(
        "PureMetal compiler not found. Put PureMetalForge on PATH, set "
        "PMF_COMPILER, or pass --compiler /path/to/PureMetalForge.exe. The "
        "same application is the IDE and the command-line compiler; --compile "
        "selects the build."
    )


def build(compiler: str, target: str) -> None:
    """Build one target.

    EVERY MONITOR BUILD RAISES THE BOARD'S BUILD NUMBER. Ruled 2026-09-11,
    after three images in one night all announced themselves as build 41
    and nothing on the board could say which one was running: `version`
    exists so a person watching a board can tell the images apart without
    hashing anything, and that only works if the number moves with every
    build.

    ONE MECHANISM, AND IT IS tools/build_count.py. It reserves the new
    identity under the global build lock BEFORE the compiler reads the board
    file, and keeps the lock through staged artifact publication and ledger
    append. The former after-compile bump made source say build 8 while the
    first Pi 3 loader and updater truthfully printed build 7. A failed compile,
    missing sidecar, publication failure or ledger failure restores the exact
    prior source, ledger and published artifact set.

    THERE IS NO WAY TO BUILD WITHOUT COUNTING. `--no-bump` is gone: a
    build made to verify something is still a build of the monitor, and
    the number moving is how anyone can tell later that it happened.
    """
    spec = TARGETS[target]
    source = ROOT / spec["source"]
    output = ROOT / spec["output"]
    if not source.is_file():
        raise SystemExit(f"Target source is missing: {source.relative_to(ROOT)}")
    output.parent.mkdir(parents=True, exist_ok=True)

    count_target = spec.get("count_target", spec.get("target", target))
    if build_count.board_for(source, count_target, ROOT) is None:
        publication = _compile_and_publish(compiler, target, source, output, spec)
        publication.finalize()
        return

    with build_count.build_identity(
        source, count_target, compiler=compiler, by="tools/build.py", root=ROOT
    ) as identity:
        publication = _compile_and_publish(compiler, target, source, output, spec)
        # Publication happened reversibly. If hashing or ledger append fails,
        # build_identity invokes this rollback while it still owns the lock.
        identity.register_publication(publication.rollback, publication.finalize)
        counted = identity.complete(output)
    print(f"  {counted.message}")


def staged_compiler(compiler: str, directory: Path) -> str:
    """Stage the executable with this repository's board profiles.

    The current compiler resolves Boards/*.board relative to its executable,
    outside the otherwise-pinned PMF_ROOT search. A temporary staging folder
    makes that dependency explicit without checking a compiler binary in.
    """
    source = Path(compiler).resolve()
    staged = directory / source.name
    shutil.copy2(source, staged)
    board_source = ROOT / "Boards"
    if board_source.is_dir():
        shutil.copytree(board_source, directory / "Boards")
    return str(staged)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        choices=("all", *TARGET_ALIASES, *TARGETS),
        nargs="?",
        default="all",
    )
    parser.add_argument("--compiler",
                        default=os.environ.get("PMF_COMPILER"),
                        help="path or command name of PureMetalForge (or set "
                             "PMF_COMPILER); it is run with --compile")
    args = parser.parse_args()

    compiler = find_compiler(args.compiler)
    # Experimental boot firmware is an explicit build, never an implicit
    # part of the ordinary monitor pair. Building does not install it.
    if args.target == "all":
        selected = ("pi4", "unoq")
    else:
        selected = TARGET_ALIASES.get(args.target, (args.target,))
    with tempfile.TemporaryDirectory(prefix="anvil-compiler-") as temporary:
        isolated_compiler = staged_compiler(compiler, Path(temporary))
        for target in selected:
            build(isolated_compiler, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
