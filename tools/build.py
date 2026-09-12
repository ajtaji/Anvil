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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_count  # noqa: E402
from pi3_slot import wrap_monitor  # noqa: E402
from pi3_slot_pack import atomic_write  # noqa: E402


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
}
TARGET_ALIASES = {"pi3": ("pi3-loader", "pi3-updater")}


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

    ONE MECHANISM, AND IT IS tools/build_count.py. This tool used to pass
    the compiler's own `--bump-build` and let it raise the marker in the file
    it had been handed. That counted the builds made this way and missed
    every build made any other way: a gate compiles the whole monitor from
    a temporary copy, so the compiler's bump landed on a file in a
    temporary directory and the real board file never moved. Ten monitor
    builds a gate run went unrecorded, and the ruling that followed was
    "gate builds do count... I want real build tracking, not estimated".
    The flag is therefore NOT passed here any more - record_build() below
    raises the real board file, stamps the date and time, and writes the
    ledger line, and it is the only thing in this repository that does.
    Asking for both would bump twice for one build and take two different
    locks over one file.

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

    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [
        compiler, "--compile",
        spec["source"].as_posix(),
        "-t",
        spec.get("target", target),
        *spec["args"],
        "-o",
        str(output),
    ]
    print(f"Building {target}: {spec['source']} -> {spec['output']}")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode:
        raise SystemExit(
            f"The {target} build failed with exit code {completed.returncode}."
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit(
            f"The {target} compiler reported success but did not write "
            f"{spec['output']}."
        )
    print(f"Built {spec['output']} ({output.stat().st_size} bytes).")

    slot_output = spec.get("slot_output")
    if slot_output is not None:
        pmf = Path(str(output) + ".pmf")
        if not pmf.is_file():
            raise SystemExit(f"Pi 3 updater PMF sidecar is missing: {pmf}")
        slot, metadata = wrap_monitor(pmf.read_bytes())
        slot_path = ROOT / slot_output
        atomic_write(slot_path, slot)
        atomic_write(
            Path(str(slot_path) + ".json"),
            (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("ascii"),
        )
        print(
            f"Packed {slot_output} ({len(slot)} bytes, SHA-256 "
            f"{metadata['slotSha256']})."
        )

    # AFTER a successful build, never before: the image exists, so the build
    # happened, so it counts. A target with no board file of its own (the ARM
    # stub) answers counted=False and nothing moves.
    counted = build_count.record_build(source, spec.get("count_target", spec.get("target", target)), output,
                                       by="tools/build.py", compiler=compiler)
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
