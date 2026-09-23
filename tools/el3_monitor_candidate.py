#!/usr/bin/env python3
"""Build an isolated, source-manifested Pi 4 desk candidate; never deploy it.

The ordinary build/pi4 output may belong to another active lane. This tool
uses a new directory, freezes the include closure and compiler, records the
normal build ledger, and retains the exact sources beside the candidate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

import build as anvil_build
import build_count
from pmf_compiler import resolve_compiler
import verify_export

ROOT = Path(__file__).resolve().parents[1]
ENTRY = PurePosixPath("RaspberryPi4/Board/board.pi4")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="new directory; existing paths are refused")
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    paths = verify_export.closure(ENTRY)
    paths.update(PurePosixPath(p.relative_to(ROOT).as_posix())
                 for p in (ROOT / "Boards").glob("*.board"))
    # Target definitions are runtime compiler inputs, not source includes.
    paths.update(PurePosixPath(p.relative_to(ROOT).as_posix())
                 for p in (ROOT / "RaspberryPi4").rglob("*.def"))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / "source"
    manifest = {}
    for relative in sorted(paths):
        src, dst = ROOT / relative, snapshot / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest[str(relative)] = digest(dst)
    # Detect edits while the multi-file snapshot itself was being copied.
    if any(digest(ROOT / p) != sha for p, sha in manifest.items()):
        raise SystemExit("Sources changed during snapshot; this candidate was not compiled.")
    host = out / "compiler"
    host.mkdir()
    staged = Path(anvil_build.staged_compiler(str(compiler), host))
    compiler_sha = digest(staged)
    image = out / "anvil-el3-desk.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(snapshot)
    command = [str(staged), "--compile", str(ENTRY), "-t", "pi4",
               "-o", str(image), "-s"]
    print(f"Frozen {len(manifest)} source/input files; building {image}.", flush=True)
    print("Compilation output will be retained in compile.log. No board access is performed.", flush=True)
    result = subprocess.run(command, cwd=snapshot, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / "compile.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode or not image.is_file() or not image.stat().st_size:
        raise SystemExit(f"Candidate compile failed ({result.returncode}); see {out / 'compile.log'}")
    counted = build_count.record_build(snapshot / ENTRY, "pi4", image,
        by="tools/el3_monitor_candidate.py", compiler=staged)
    record = {"status": "desk-only-not-deployed", "sources": manifest,
              "compiler_sha256": compiler_sha, "image_sha256": digest(image),
              "bytes": image.stat().st_size, "ledger": counted.message}
    symbol = Path(str(image) + ".sym")
    if symbol.is_file():
        record["symbols_sha256"] = digest(symbol)
    (out / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in record.items() if k != "sources"}, indent=2))
    print("Source closure:", len(manifest), "files. No deployment was attempted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
