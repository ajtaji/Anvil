#!/usr/bin/env python3
"""Isolated proof for the four public dead-fragment-interface invariants.

The monolithic pipeline checker has a broad mutation table and historically
mutated production files in place.  This focused runner never does that.  It
freezes every compiler/checker input into a private snapshot, copies that
snapshot into a private work root, and applies one byte-surgical mutation to
the private copy.  Each mutant is then run as an ordinary pipeline baseline:
only the checker's normal, returned semantic ``FAIL (`` result with a
``[dead-io]`` property can reject it.  Compile failures, timeouts, interpreter
exceptions and hash drift abort this runner and cannot be counted as kills.

Without --run this performs preparation/source checks only.  The four builds
must not be started until the monolithic pipeline gate is frozen and green.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402
CHECKER_REL = pathlib.Path("tools/vulkan_pipeline_check.py")
SNAPSHOT_ITEMS = (
    pathlib.Path("Anvil"),
    pathlib.Path("RaspberryPi4"),
    pathlib.Path("Boards"),
    pathlib.Path("tools"),
    pathlib.Path("keywords.def"),
)
MUTANTS = (
    (
        "the V3D target includes a dead decorated fragment input",
        pathlib.Path("Anvil/Graphics/Vulkan/vk_v3d_shader.pi4"),
        r"If *variable\storageClass = #ANVIL_IR_STORAGE_INPUT And avkqIrLive[*variable\sourceId] <> 0",
        r"If *variable\storageClass = #ANVIL_IR_STORAGE_INPUT",
        ("[dead-io] real typed-IR V3D compilation succeeds",),
    ),
    (
        "the V3D target includes a dead decorated fragment output",
        pathlib.Path("Anvil/Graphics/Vulkan/vk_v3d_shader.pi4"),
        r"ElseIf *variable\storageClass = #ANVIL_IR_STORAGE_OUTPUT And *variable\sourceId = outputVariableId",
        r"ElseIf *variable\storageClass = #ANVIL_IR_STORAGE_OUTPUT",
        ("[dead-io] real typed-IR V3D compilation succeeds",),
    ),
    (
        "the fragment summary includes a dead decorated input",
        pathlib.Path("Anvil/Graphics/Vulkan/vk_pipeline.pbi"),
        r"If *v\storageClass = #ANVIL_IR_STORAGE_INPUT And avkShIrLive[*v\sourceId] <> 0",
        r"If *v\storageClass = #ANVIL_IR_STORAGE_INPUT",
        ("[dead-io] public pipeline ignores the dead input and output",),
    ),
    (
        "the fragment summary includes a dead decorated output",
        pathlib.Path("Anvil/Graphics/Vulkan/vk_pipeline.pbi"),
        r"ElseIf *v\storageClass = #ANVIL_IR_STORAGE_OUTPUT And *v\sourceId = outputVariableId",
        r"ElseIf *v\storageClass = #ANVIL_IR_STORAGE_OUTPUT",
        ("[dead-io] retained fragment summary has only the Store output",),
    ),
)


@contextlib.contextmanager
def checker_lock():
    """Share the monolithic checker's lock only while freezing shared input."""
    lock_path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def input_files(root: pathlib.Path) -> list[pathlib.Path]:
    files = []
    for rel in SNAPSHOT_ITEMS:
        item = root / rel
        if item.is_file():
            files.append(item)
            continue
        for path in item.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".img", ".tmp"):
                continue
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def input_manifest(root: pathlib.Path) -> str:
    """Hash paths and file digests with unambiguous length framing."""
    h = hashlib.sha256()
    for path in input_files(root):
        name = path.relative_to(root).as_posix().encode("utf-8")
        digest = bytes.fromhex(sha256(path))
        h.update(struct.pack("<I", len(name)))
        h.update(name)
        h.update(digest)
    return h.hexdigest()


def locate_compiler(value: str | None) -> pathlib.Path:
    """Resolve through the shared, validating resolver (tools/pmf_compiler.py)
    when a compiler was named (value or PMF_COMPILER); otherwise fall back
    to the compiler repository's own tree, unchanged (forum 977)."""
    requested = value or os.environ.get("PMF_COMPILER")
    if requested:
        return pathlib.Path(_pmf_resolve_compiler(requested))
    fallback = pathlib.Path(
        r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
    )
    if fallback.is_file():
        return fallback.resolve()
    raise RuntimeError("PureMetalForge.exe was not found; pass --compiler")


def copy_item(source: pathlib.Path, destination: pathlib.Path) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.img", "*.tmp"),
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def freeze_inputs(snapshot: pathlib.Path) -> str:
    for rel in SNAPSHOT_ITEMS:
        source = ROOT / rel
        if not source.exists():
            raise RuntimeError(f"required snapshot input is missing: {source}")
        copy_item(source, snapshot / rel)
    return input_manifest(snapshot)


def assert_shared_unchanged(expected: str) -> None:
    actual = input_manifest(ROOT)
    if actual != expected:
        raise RuntimeError(f"complete shared input manifest changed: {actual} != {expected}")


def assert_snapshot(snapshot: pathlib.Path, expected: str) -> None:
    actual = input_manifest(snapshot)
    if actual != expected:
        raise RuntimeError(f"frozen snapshot drifted: {actual} != {expected}")


def mutate_private(path: pathlib.Path, fixed: str, broken: str) -> None:
    original = path.read_bytes()
    fixed_bytes = fixed.encode("utf-8")
    broken_bytes = broken.encode("utf-8")
    hits = original.count(fixed_bytes)
    if hits != 1:
        raise RuntimeError(f"{path}: mutation anchor has {hits} hits, expected exactly one")
    at = original.index(fixed_bytes)
    mutant = original[:at] + broken_bytes + original[at + len(fixed_bytes):]
    if mutant[:at] != original[:at] or mutant[at + len(broken_bytes):] != original[at + len(fixed_bytes):]:
        raise RuntimeError(f"{path}: non-anchor bytes changed")
    path.write_bytes(mutant)


def run_checker(work: pathlib.Path, compiler: pathlib.Path, step_limit: int,
                timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ANVIL_VK_PIPELINE_STEP_LIMIT"] = str(step_limit)
    command = [sys.executable, "-u", str(CHECKER_REL), "--compiler", str(compiler)]
    return subprocess.run(
        command,
        cwd=work,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )


def require_green(run: subprocess.CompletedProcess[str], expected_line: str) -> None:
    pass_lines = [line for line in run.stdout.splitlines()
                  if line.startswith("vulkan_pipeline_check: PASS -")]
    if run.returncode != 0 or pass_lines != [expected_line]:
        raise RuntimeError("frozen baseline was not green:\n" + run.stdout)


def require_semantic_kill(name: str, expected: tuple[str, ...],
                          run: subprocess.CompletedProcess[str]) -> str:
    if run.returncode != 1 or "vulkan_pipeline_check: FAIL (" not in run.stdout:
        raise RuntimeError(f"{name}: infrastructure/non-semantic result:\n{run.stdout}")
    proof = next((line.strip() for line in run.stdout.splitlines()
                  if any(label in line for label in expected)), "")
    if not proof:
        raise RuntimeError(f"{name}: failed without a dead-IO property:\n{run.stdout}")
    return proof


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--run", action="store_true",
                        help="execute baseline and four mutants after the monolith is frozen green")
    parser.add_argument("--expected-pass-line",
                        help="exact frozen monolithic PASS line; required with --run")
    parser.add_argument("--step-limit", type=int, default=200_000_000)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.run and not args.expected_pass_line:
        parser.error("--run requires --expected-pass-line from the frozen green monolith")

    compiler = locate_compiler(args.compiler)
    compiler_hash = sha256(compiler)
    shared_manifest = None
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_dead_io_snapshot_"))
    try:
        with checker_lock():
            shared_manifest = input_manifest(ROOT)
            manifest = freeze_inputs(snapshot)
            if manifest != shared_manifest or input_manifest(ROOT) != shared_manifest:
                raise RuntimeError("shared inputs changed while the frozen snapshot was copied")
        for name, rel, fixed, _broken, _expected in MUTANTS:
            hits = (snapshot / rel).read_bytes().count(fixed.encode("utf-8"))
            if hits != 1:
                raise RuntimeError(f"{name}: frozen anchor has {hits} hits")

        print(f"vulkan_pipeline_dead_io_check: compiler={compiler} sha256={compiler_hash}")
        print(f"vulkan_pipeline_dead_io_check: frozen-input-manifest={manifest}")
        print("vulkan_pipeline_dead_io_check: 4/4 anchors unique and byte-surgical")
        if not args.run:
            print("vulkan_pipeline_dead_io_check: READY - no compiler/checker executed")
            return 0

        def isolated_run(mutant=None):
            work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_dead_io_work_"))
            try:
                copy_item(snapshot, work)
                if mutant is not None:
                    _name, rel, fixed, broken, _expected = mutant
                    mutate_private(work / rel, fixed, broken)
                return run_checker(work, compiler, args.step_limit, args.timeout_seconds)
            finally:
                shutil.rmtree(work, ignore_errors=True)

        baseline = isolated_run()
        require_green(baseline, args.expected_pass_line)
        print(args.expected_pass_line)

        for mutant in MUTANTS:
            name, _rel, _fixed, _broken, expected = mutant
            run = isolated_run(mutant)
            proof = require_semantic_kill(name, expected, run)
            print(f"  RED {name} - {proof}")
            assert_snapshot(snapshot, manifest)
            if sha256(compiler) != compiler_hash:
                raise RuntimeError("compiler changed during isolated proof")
            assert_shared_unchanged(shared_manifest)

        print("vulkan_pipeline_dead_io_check: all 4 mutations rejected")
        return 0
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)
        if compiler.exists() and sha256(compiler) != compiler_hash:
            raise RuntimeError("compiler changed before isolated proof cleanup")
        if shared_manifest is not None:
            assert_shared_unchanged(shared_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
