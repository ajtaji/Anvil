#!/usr/bin/env python3
"""Shared, safe resolution of the PureMetal compiler executable.

Every Anvil tool that takes --compiler / PMF_COMPILER should resolve it
through resolve_compiler() here rather than taking the path verbatim with
its own inline argparse. Taking the path verbatim - no existence check, no
rejection of a stale or retired build - is exactly the "--compile opened
the IDE window" defect: a checker ran a stale PureMetalForge.exe copy left
in a scratch directory, and that copy's headless argument detection
predated the guard the tracked build now carries, so an argument list that
is safe on every current build opened the GUI on that one. See the general
Bug tracker topic for the incident.

This mirrors tools/build.py's find_compiler()/refuse_retired() (existence
check, refuse the retired console compiler) and adds the "current" check
that file did not have: a resolved path that is not the compiler
repository's own tracked release binary is refused unless the caller opts
in. There is no queryable content stamp for a built PureMetalForge.exe -
its build stamp is compiled into the binary and shown in its own title bar
and About box, not on any command line - so "current" falls back to
identity with the one tracked path rather than a hash or a date, either of
which a stale copy could share by chance.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

RETIRED_COMPILER_STEMS = ("pmfc",)

# The one PureMetalForge.exe every Anvil tool builds and gates against:
# the compiler repository's own tracked release binary. A copy anywhere
# else - left in _work/, tmp/, or any other scratch or working directory -
# is untracked and may be stale.
TRACKED_COMPILER = Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)

# Set this to use a compiler that is not the tracked build - a scratch
# build carrying a fix under test, for instance. Off by default so the
# untracked case must be a deliberate choice, not a leftover --compiler
# value nobody re-checked.
OVERRIDE_ENV = "PMF_ALLOW_UNTRACKED_COMPILER"


def refuse_retired(path: Path) -> None:
    stem = path.stem.lower()
    if any(stem == retired or stem.startswith(retired + "_") or
           stem.startswith(retired + ".") for retired in RETIRED_COMPILER_STEMS):
        raise SystemExit(
            f"{path} is the retired console compiler. It was replaced on "
            "2026-09-11 by the one application, which compiles from the "
            "command line: pass --compiler <PureMetalForge.exe> or set "
            "PMF_COMPILER to it. An image built with it is not evidence "
            "about the compiler that ships."
        )


def refuse_untracked(path: Path) -> None:
    """Refuse a resolved compiler path that is not the tracked release
    binary, unless PMF_ALLOW_UNTRACKED_COMPILER is set. This is the check
    a stale copy under _work/ or tmp/ fails even though it exists and is
    not pmfc: it can still be weeks out of date, missing a guard the
    tracked binary already carries.
    """
    if os.environ.get(OVERRIDE_ENV):
        return
    same = False
    try:
        if TRACKED_COMPILER.is_file():
            same = path.samefile(TRACKED_COMPILER)
    except OSError:
        same = False
    if not same and path != TRACKED_COMPILER.resolve():
        raise SystemExit(
            f"{path} is not the compiler repository's tracked build "
            f"({TRACKED_COMPILER}) and may be a stale copy left in a "
            "scratch or working directory - exactly the shape of the "
            "\"--compile opened the IDE window\" defect. Point --compiler "
            f"/ PMF_COMPILER at the tracked executable, or set "
            f"{OVERRIDE_ENV}=1 to use this one anyway."
        )


def resolve_compiler(explicit: str | None) -> str:
    """Resolve the one PureMetal application that also compiles: exists,
    is not the retired console compiler, and is the tracked build unless
    overridden. Prints the resolved path so a run's log always shows which
    binary actually compiled it.
    """
    requested = explicit or os.environ.get("PMF_COMPILER")
    if not requested:
        raise SystemExit(
            "No compiler was named. Pass --compiler with the path to "
            "PureMetalForge.exe, or set PMF_COMPILER."
        )
    candidate = Path(requested).expanduser()
    if candidate.is_file():
        resolved_path = candidate.resolve()
    else:
        found = shutil.which(requested)
        if not found:
            raise SystemExit(
                f"The requested PureMetal compiler was not found: {requested}. "
                "Check --compiler or PMF_COMPILER."
            )
        resolved_path = Path(found).resolve()
    refuse_retired(resolved_path)
    refuse_untracked(resolved_path)
    print(f"using compiler: {resolved_path}")
    return str(resolved_path)
