#!/usr/bin/env python3
r"""a64_diag_build_check.py - every diagnostic that is meant to build, BUILDS.

      python tools/a64/a64_diag_build_check.py --compiler PureMetalForge.exe
      python tools/a64/a64_diag_build_check.py --q
      python tools/a64/a64_diag_build_check.py --negative
      python tools/a64/a64_diag_build_check.py --jobs 8 --keep _work/diag_build

WHY THIS GATE EXISTS, AND WHY IT IS NOT ONE MORE BEHAVIOURAL CHECK

Every other check in this directory proves that some code does the right
thing. This one proves something much duller and, on the evidence, much
easier to lose: that the programs in RaspberryPi4/Examples/Diagnostics
BUILD AT ALL.

On 2026-09-02 the settings store moved behind the HwFile* seam. Two Wi-Fi
diagnostics had their include line repointed at the new path and nothing
else added, stopped compiling that afternoon, and were not built again for
three days, because nothing in the tree built them. The monitor image and
the images each behavioural gate builds for itself all stayed green, since
they come from files that were right. A whole directory of programs can rot
while every gate is green, and the only thing that notices is a person who
happens to build one by hand.

The same thing happened again when these diagnostics moved into this
repository: six of them no longer compiled because RaspberryPi4/Lib/pcie.pi4
had grown a call into the mailbox library, which a main program must include
ahead of it. Nothing had built them since.

WHAT IT DOES

Compiles every *.pi4 directly inside RaspberryPi4/Examples/Diagnostics (and,
with --q, every *.unoq directly inside ArduinoQ/Examples/Diagnostics) with
the PureMetal application in command-line mode, on a pool of worker threads,
and fails if any one of them is not "pmfc: OK" with a non-empty image.
Nothing is executed and no hardware is touched: this is a compile gate and
says so.

Each Pi 4 program is compiled with the load address, stack address and
switches its own header documents (the first `--load-addr`, `--stack-addr`,
`--bss-addr`, `--entry-returns` and `--wants-services` in its opening comment),
because that is the build the file tells a reader to run. A header that
names none gets the compiler's defaults. UNO Q programs are compiled
`-t unoq --entry-returns` at the addresses tools/build_unoq_*.sh use.

WHAT IT DELIBERATELY DOES NOT BUILD, AND HOW THAT STAYS HONEST

A NotBuilding/ directory beside the programs holds diagnostics that are
known not to compile against this tree, each with a sentence in
NotBuilding/README.md saying what it needs. They are not built. They are
not forgotten either: the gate fails if a file in NotBuilding/ has no row
in that README, or a row names a file that is not there, so a diagnostic
cannot be parked there silently and a row cannot outlive its file.

THE COMPILER AND THE ROOT ARE PINNED

The tree under test is the one this file lives in, and PMF_ROOT is set to
it for every compile, so includes can only resolve against this checkout.
The compiler is found exactly as tools/build.py finds it (--compiler, then
PMF_COMPILER, then PATH) and staged with this tree's Boards/ profiles, and
the retired console compiler is refused by name.

THE NEGATIVE CONTROL

--negative plants defects and requires red. Every defect is planted in a
COPY written to a temporary directory; no file in the tree is ever edited.

  1. THE REAL OMISSION. A copy of pi4PcieProbe.pi4 with its mailbox include
     removed must fail, and the compiler's message must name
     MailboxNotifyVl805Reset. That is byte for byte the defect this gate
     found when the diagnostics moved here.
  2. A STRUCTURAL DEFECT. A copy of pi4Hang.pi4 with its EndProcedure
     removed must fail. Without this, control 1 alone would still pass if
     the gate had quietly narrowed to one error string.
  3. THE UNPLANTED ORIGINALS must both build in the same run, so a red on
     the copies is a red about the defect and not about the compiler.
  4. THE PARKING RULE. A NotBuilding/ listing with one row removed must be
     reported, so the README check is seen to bite.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402  (find_compiler and staged_compiler)

PI4_DIAGS = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics"
Q_DIAGS = ROOT / "ArduinoQ" / "Examples" / "Diagnostics"
NOT_BUILDING = "NotBuilding"

Q_FLAGS = ["--load-addr", "0x70000000", "--stack-addr", "0x68000000",
           "--entry-returns"]
HEADER_LINES = 120
VALUE_FLAGS = ("--load-addr", "--stack-addr", "--bss-addr")
SWITCHES = ("--entry-returns", "--wants-services")
README_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)


def header_flags(source: pathlib.Path) -> list[str]:
    """The build switches the program's own opening comment documents."""
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    head = "\n".join(line for line in lines[:HEADER_LINES]
                     if line.lstrip().startswith(";"))
    flags: list[str] = []
    for flag in VALUE_FLAGS:
        match = re.search(re.escape(flag) + r"\s+(0x[0-9A-Fa-f]+|\$[0-9A-Fa-f]+|\d+)", head)
        if match:
            flags += [flag, match.group(1)]
    for switch in SWITCHES:
        if re.search(re.escape(switch) + r"(?![\w-])", head):
            flags.append(switch)
    return flags


def target_for(source: pathlib.Path) -> tuple[str, list[str]]:
    if source.suffix == ".unoq":
        return "unoq", list(Q_FLAGS)
    return "pi4", header_flags(source)


def sources(include_q: bool) -> list[pathlib.Path]:
    found = sorted(PI4_DIAGS.glob("*.pi4"), key=lambda p: p.name.lower())
    if include_q:
        found += sorted(Q_DIAGS.glob("*.unoq"), key=lambda p: p.name.lower())
    return found


def build_one(compiler: str, source: pathlib.Path, outdir: pathlib.Path,
              display: str | None = None) -> tuple[str, bool, str, float]:
    """Compile one source. Returns (name, ok, full output when red, seconds)."""
    target, flags = target_for(source)
    try:
        rel = source.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(source)
    name = display or rel
    # NAMED BY THE WHOLE RELATIVE PATH, so two programs with one stem in two
    # directories cannot write the same image from two threads.
    image = outdir / (re.sub(r"[\\/:]+", "__", name) + ".img")
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    started = time.monotonic()
    completed = subprocess.run(
        [compiler, "--compile", rel, "-t", target, *flags, "-o", str(image)],
        cwd=ROOT, env=env, text=True, errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    seconds = time.monotonic() - started
    output = completed.stdout or ""
    ok = (completed.returncode == 0 and "pmfc: OK" in output
          and image.is_file() and image.stat().st_size > 0)
    return name, ok, "" if ok else output.strip(), seconds


def run_sweep(compiler: str, items: list[tuple[pathlib.Path, str | None]],
              outdir: pathlib.Path, jobs: int) -> list[tuple[str, bool, str, float]]:
    outdir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda item: build_one(compiler, item[0], outdir, item[1]),
                             items))


def parking_problems(directory: pathlib.Path, readme_text: str | None = None) -> list[str]:
    """Every NotBuilding/ program has a README row and every row a program."""
    parked = directory / NOT_BUILDING
    if not parked.is_dir():
        return []
    readme = parked / "README.md"
    if readme_text is None:
        if not readme.is_file():
            return [f"{parked.relative_to(ROOT).as_posix()} has no README.md saying "
                    "why its programs do not build."]
        readme_text = readme.read_text(encoding="utf-8")
    rows = set(README_ROW.findall(readme_text)) - {"File"}
    files = {p.name for p in parked.iterdir()
             if p.is_file() and p.suffix in (".pi4", ".unoq")}
    rel = parked.relative_to(ROOT).as_posix()
    problems = [f"{rel}/{name} is parked without a README row saying what it needs."
                for name in sorted(files - rows)]
    problems += [f"{rel}/README.md has a row for {name}, which is not in that directory."
                 for name in sorted(rows - files)]
    return problems


def report(results) -> int:
    bad = [r for r in results if not r[1]]
    for name, ok, detail, _seconds in results:
        if not ok:
            print(f"\nFAIL  {name}")
            for line in detail.splitlines():
                print(f"      {line}")
    return len(bad)


# ----------------------------------------------------------------------
#  The negative controls. Every plant is in a temporary copy.
# ----------------------------------------------------------------------

def _planted_copy(source: pathlib.Path, before: str, after: str,
                  into: pathlib.Path) -> pathlib.Path:
    raw = source.read_bytes().decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in raw else "\n"
    before_nl = before.replace("\n", newline)
    if before_nl not in raw:
        raise SystemExit(f"The negative control cannot plant its defect, because "
                         f"{source.relative_to(ROOT).as_posix()} no longer contains "
                         f"the text it removes.")
    copy = into / source.name
    copy.write_bytes(raw.replace(before_nl, after.replace("\n", newline), 1).encode("utf-8"))
    return copy


def negative_control(compiler: str, jobs: int, workdir: pathlib.Path) -> int:
    fails = 0
    plants = workdir / "planted"
    plants.mkdir(parents=True, exist_ok=True)
    pcie = PI4_DIAGS / "pi4PcieProbe.pi4"
    hang = PI4_DIAGS / "pi4Hang.pi4"
    omission = _planted_copy(pcie, 'XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"\n', "", plants)
    structural = _planted_copy(hang, "  ProcedureReturn 0\nEndProcedure\n",
                               "  ProcedureReturn 0\n", plants)
    results = run_sweep(compiler, [(omission, "planted/pi4PcieProbe.pi4"),
                                   (structural, "planted/pi4Hang.pi4"),
                                   (pcie, None), (hang, None)],
                        workdir / "images", jobs)
    by_name = {r[0]: r for r in results}

    print("\n[neg 1] a copy of pi4PcieProbe.pi4 without its mailbox include")
    _name, ok, detail, _ = by_name["planted/pi4PcieProbe.pi4"]
    if ok:
        print("  Red was expected and the build was green, so this gate does not bite.")
        fails += 1
    elif "MailboxNotifyVl805Reset" not in detail:
        print("  The build failed, but the message never names MailboxNotifyVl805Reset:")
        print("   ", detail.replace("\n", "\n    "))
        fails += 1
    else:
        print("  The build failed, as required, and the message names MailboxNotifyVl805Reset.")

    print("\n[neg 2] a copy of pi4Hang.pi4 with its EndProcedure removed")
    _name, ok, detail, _ = by_name["planted/pi4Hang.pi4"]
    if ok:
        print("  Red was expected and an unclosed procedure compiled clean.")
        fails += 1
    else:
        tail = [line for line in detail.splitlines() if line.strip()]
        print("  The build failed, as required:", tail[-2] if len(tail) > 1 else "")

    print("\n[neg 3] the unplanted originals, in the same run")
    for source in (pcie, hang):
        rel = source.relative_to(ROOT).as_posix()
        if by_name[rel][1]:
            print(f"  {rel} built, so the reds above are about the planted defects.")
        else:
            print(f"  {rel} did not build unplanted, so the controls above prove nothing.")
            fails += 1

    print("\n[neg 4] a NotBuilding/ README with one row removed")
    readme = PI4_DIAGS / NOT_BUILDING / "README.md"
    if not readme.is_file():
        print("  There is no NotBuilding/README.md to plant a defect in.")
        fails += 1
    else:
        text = readme.read_text(encoding="utf-8")
        rows = [m for m in re.finditer(r"^\|\s*`[^`]+`.*\n", text, re.M)
                if not m.group(0).startswith("| File")]
        if not rows:
            print("  NotBuilding/README.md has no rows to remove.")
            fails += 1
        else:
            planted = text[:rows[0].start()] + text[rows[0].end():]
            problems = parking_problems(PI4_DIAGS, planted)
            if problems:
                print("  Reported, as required:", problems[0])
            else:
                print("  A parked program without a README row was not reported.")
                fails += 1
    return fails


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                        help="path or command name of PureMetalForge (or set PMF_COMPILER); "
                             "it is run with --compile")
    parser.add_argument("--jobs", type=int, default=min(16, os.cpu_count() or 4),
                        help="compiles run at once (default: the core count, at most 16)")
    parser.add_argument("--q", action="store_true",
                        help="also build ArduinoQ/Examples/Diagnostics")
    parser.add_argument("--negative", action="store_true",
                        help="run the negative controls instead of the sweep")
    parser.add_argument("--keep", default=None, metavar="DIR",
                        help="write the images to DIR and keep them")
    args = parser.parse_args()

    print(f"[gate] tree under test: {ROOT}", file=sys.stderr)
    compiler = build.find_compiler(args.compiler)
    with tempfile.TemporaryDirectory(prefix="anvil-diag-build-") as temporary:
        workdir = pathlib.Path(temporary)
        (workdir / "compiler").mkdir()
        staged = build.staged_compiler(compiler, workdir / "compiler")
        if args.negative:
            fails = negative_control(staged, args.jobs, workdir)
            print()
            if fails:
                print(f"NEGATIVE CONTROL FAILED ({fails} problem(s)). This gate cannot be trusted.")
                return 1
            print("NEGATIVE CONTROL PASSED. The gate goes red on every planted defect.")
            return 0

        srcs = sources(args.q)
        if not srcs:
            raise SystemExit(f"No diagnostics were found under {PI4_DIAGS}.")
        outdir = pathlib.Path(args.keep).resolve() if args.keep else workdir / "images"
        print(f"[gate] {len(srcs)} sources, {args.jobs} at once")
        started = time.monotonic()
        results = run_sweep(staged, [(s, None) for s in srcs], outdir, args.jobs)
        bad = report(results)
        seconds = time.monotonic() - started

    problems = parking_problems(PI4_DIAGS) + (parking_problems(Q_DIAGS) if args.q else [])
    for problem in problems:
        print(f"\nFAIL  {problem}")

    for directory in (PI4_DIAGS, Q_DIAGS) if args.q else (PI4_DIAGS,):
        parked = directory / NOT_BUILDING
        if parked.is_dir():
            count = sum(1 for p in parked.iterdir() if p.suffix in (".pi4", ".unoq"))
            print(f"[gate] {count} program(s) in {parked.relative_to(ROOT).as_posix()} "
                  "are not built; its README says why.")
    built = len(results) - bad
    print(f"\n{built}/{len(results)} built, {bad} failed, {seconds:.1f}s wall")
    if bad or problems:
        print("DIAG BUILD GATE FAILED")
        return 1
    print("DIAG BUILD GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
