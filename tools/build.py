#!/usr/bin/env python3
"""Build Anvil targets with an external PureMetal command-line compiler."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


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
}


def find_compiler(explicit: str | None) -> str:
    requested = explicit or os.environ.get("PMFC")
    if requested:
        candidate = Path(requested).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        resolved = shutil.which(requested)
        if resolved:
            return resolved
        raise SystemExit(
            f"The requested PureMetal compiler was not found: {requested}. "
            "Check --pmfc or PMFC."
        )

    for name in ("pmfc", "pmfc.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise SystemExit(
        "PureMetal compiler not found. Put pmfc on PATH, set PMFC, or pass "
        "--pmfc /path/to/pmfc."
    )


def build(compiler: str, target: str) -> None:
    spec = TARGETS[target]
    source = ROOT / spec["source"]
    output = ROOT / spec["output"]
    if not source.is_file():
        raise SystemExit(f"Target source is missing: {source.relative_to(ROOT)}")
    output.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [
        compiler,
        spec["source"].as_posix(),
        "-t",
        target,
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
    parser.add_argument("target", choices=("all", *TARGETS), nargs="?", default="all")
    parser.add_argument("--pmfc", help="path or command name for the external compiler")
    args = parser.parse_args()

    compiler = find_compiler(args.pmfc)
    selected = TARGETS if args.target == "all" else (args.target,)
    with tempfile.TemporaryDirectory(prefix="anvil-pmfc-") as temporary:
        isolated_compiler = staged_compiler(compiler, Path(temporary))
        for target in selected:
            build(isolated_compiler, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
