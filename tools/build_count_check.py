#!/usr/bin/env python3
"""THE BUILD COUNT IS REAL. This gate is what says so.

The ruling of 2026-09-11 is that every build of the Anvil monitor raises the
board file's #ANVIL_BUILD, that gate builds count, and that the tracking is to
be real rather than estimated. tools/build_count.py is the one thing in this
repository that counts a build. This gate proves it counts, counts once, counts
under two workers at a time, refuses what it cannot count, and is actually
called by everything that compiles a board file.

WHAT IT PROVES, and every fixture runs on a TEMPORARY COPY of the board files.
The real board files are read for their starting contents and checked at the
end:

  raises by exactly one    a recorded build takes 56 to 57, not to 58 and not
                           to 56. The rest of the file comes back byte for
                           byte: one line changes and only its digits.
  stamps date and time     the two sibling markers carry today's date and this
                           build's time, so `version` can say when as well as
                           which.
  writes the ledger line   one line per counted build, carrying the sha256 of
                           the artifact the compile produced, the sha256 of the
                           compiler that produced it, the source that was
                           compiled, the tool that asked and the compile's own
                           fingerprint.
  names the compiler       a counted build with no compiler named is refused. The
                           compiler is rebuilt on this bench while gates are
                           running, so a build number alone is half an
                           identity; a staged copy hashes the same as
                           the original, which is what every gate runs.
  every caller's shape     the canonical builder owns one pre-compile identity
                           transaction around compile, reversible publication
                           and ledger commit. Older emitted-code gates that
                           compile the board directly still report their
                           successful artifact through record_build.
  honours `off`            `; pmf:build off` freezes the number, the build is
                           still recorded, and the line says frozen=yes.
  refuses a malformed
    marker                 a hexadecimal value, two markers in one file, a
                           misspelt 'off', a board file with no marker at all -
                           each refused by its own PMF-BLD code, with the file
                           left exactly as it was. A marker that quietly does
                           nothing is the failure the marker exists to prevent.
  two workers at once      six concurrent builds of one board file count six.
                           No lost update: the lock covers the whole
                           read-add-write and the ledger append with it.
  the lock really blocks    while the lock is held, a build in another process
                           waits for it, deterministically - not "usually, if
                           the timing is right".
  one compile counts once  the same artifact offered twice is one build.
  the wiring               the canonical builder calls build_identity before
                           its compiler helper, publishes reversibly, then
                           completes the ledger while that context is held.
                           Direct emitted-code gates call record_build after
                           their success guard. Nothing asks the compiler for
                           --bump-build and nothing offers a way around counting.

MUTANTS. Drop the lock, drop the date/time stamp, bump by two, stop recognising
a compile that was already counted, bump a frozen marker, ignore a malformed
one, leave the compiler out of the ledger line, allow a build that never names
its compiler - each mutation is applied to a copy of build_count.py, and the
check that owns that property must fail against it. A gate that passes against a
broken module proves nothing about the working one.

THE END-TO-END COMPILE. With PMF_COMPILER set, this gate also copies the repository
into a temporary directory and runs `tools/build.py pi4` there for real, then
checks that the temporary copy's board file went up by exactly one and that the
ledger line carries the sha256 of the image that was actually produced. THAT
BUILD THEN COUNTS AGAINST THE REAL board.pi4, because it is a build of the
monitor and this gate is not entitled to an exception to the rule it enforces.
It is a 70-second monitor build, so `--fast` skips it and says so out loud; the
other call sites are proven by the wiring check plus the per-caller shapes above
rather than by compiling the monitor five more times, which would cost six
minutes to learn what one compile and one static check already say.

EVERYTHING ELSE THIS GATE DOES IS ON A COPY, and the real board files are
checked at the end: they may differ only by the marked lines, only on pi4, and
only when the end-to-end compile actually ran.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_count as reference  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

REAL_BOARDS = tuple(ROOT / path for path in reference.BOARDS.values())

# Every place in tools/ that compiles a board file, with the target it compiles
# it for and the name it signs its ledger lines with. The wiring check below
# proves this table is the whole set and that each entry really calls
# record_build; the shape check drives record_build the way each one does.
CALLERS = (
    ("tools/build.py", "pi4"),
    ("tools/build.py", "unoq"),
    ("tools/memcmd_width_emitted_check.py", "pi4"),
    ("tools/memcmd_width_emitted_check.py", "unoq"),
    ("tools/payload_lifecycle_check.py", "pi4"),
    ("tools/dsi_diag_read_safety_check.py", "pi4"),
)


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)


# --------------------------------------------------------------- the fixtures
def temp_repo(where: Path) -> Path:
    """Two board files under a temporary root. The real ones are never written."""
    root = where / "repo"
    for board in reference.BOARDS.values():
        destination = root / board
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / board, destination)
    return root


# A STAND-IN FOR THE COMPILER. The ledger records the sha256 of the executable
# that produced the image, and these fixtures produce no image with a real
# compiler -
# so they name a file whose bytes are known, and the checks below assert the
# ledger carried that file's digest. What is proven is that the compiler's
# identity reaches the line, not that this file is a compiler.
COMPILER_BYTES = b"not a compiler - the fixtures need a file with known bytes"


def stand_in_compiler(where: Path) -> Path:
    path = where / "PureMetalForge.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_bytes(COMPILER_BYTES)
    return path


def artifact(where: Path, name: str, payload: bytes) -> Path:
    path = where / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def marker_line(board: Path, kind: str = "number") -> str:
    data = board.read_bytes()
    for site in reference.scan(data):
        if site.kind == kind:
            return site.text
    raise AssertionError(f"no {kind} marker in {board}")


def stamp_text(board: Path, kind: str) -> str:
    """The marker's value exactly as written - a time keeps its leading zero."""
    return marker_line(board, kind).split("=")[1].split(";")[0].strip()


def restamp(board: Path, date_text: str, time_text: str) -> None:
    """Write a date and time into a fixture copy, byte for byte, same width."""
    data = board.read_bytes()
    for kind, text in (("date", date_text), ("time", time_text)):
        site = next(s for s in reference.scan(data) if s.kind == kind and s.valid)
        assert len(text) == site.value_len, f"{kind} stamp width changed"
        data = data[:site.value_start] + text.encode("ascii") + data[site.value_start + site.value_len:]
    board.write_bytes(data)


def value_of(module, board: Path, kind: str = "number") -> int:
    for site in module.scan(board.read_bytes()):
        if site.kind == kind:
            return site.value
    raise AssertionError(f"no {kind} marker in {board}")


def ledger_lines(root: Path) -> list[str]:
    path = root / reference.LEDGER_NAME
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def field(line: str, name: str) -> str:
    for item in line.split(" "):
        if item.startswith(name + "="):
            return item[len(name) + 1:]
    raise AssertionError(f"the ledger line has no {name}= field: {line}")


# ------------------------------------------------------------------ the checks
def check_bump_by_one(module, c: Checks, where: Path) -> None:
    """One recorded build, one step, and the rest of the file untouched."""
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    before = board.read_bytes()
    start = value_of(module, board)

    image = artifact(where, "one/anvil.img", b"image-one")
    result = module.record_build("export/RaspberryPi4/Board/board.pi4", "pi4", image,
                                 by="tools/build.py", compiler=stand_in_compiler(where),
                                 root=root)
    c.yes(result.counted, "a build of board.pi4 was not counted")
    c.yes(result.value == start and result.new_value == start + 1,
          f"the build number went {result.value} -> {result.new_value}, not "
          f"{start} -> {start + 1}")
    c.yes(value_of(module, board) == start + 1,
          "the board file on disk does not hold the number that was reported")

    after = board.read_bytes()
    c.yes(len(before.splitlines()) == len(after.splitlines()),
          "the bump changed the number of lines in the board file")
    changed = [index for index, (old, new)
               in enumerate(zip(before.splitlines(), after.splitlines())) if old != new]
    c.yes(all(b"pmf:build" in after.splitlines()[index] for index in changed),
          "the bump rewrote a line that carries no build marker")
    c.yes(len(changed) <= 3,
          f"the bump rewrote {len(changed)} lines; only the number, the date and the "
          f"time may move")
    numbered = after.splitlines()[changed[0]].decode("latin-1")
    c.yes(numbered.replace(str(start + 1), str(start), 1) ==
          before.splitlines()[changed[0]].decode("latin-1"),
          "the marked line changed in more than its digits: " + numbered)


def check_stamps(module, c: Checks, where: Path) -> None:
    """The date and time siblings carry this build's date and time.

    The fixture is a copy of the real board file, which was itself stamped by
    the last real build - run this gate within two minutes of one and the copy
    already carries today's date and a time close enough to now to pass every
    assertion below without the build under test writing anything. So the copy
    is set back to a date and time no clock will ever read, and the checks then
    require both to have MOVED, not merely to look right.
    """
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    restamp(board, "20000101", "000000")
    c.yes(value_of(module, board, "date") == 20000101 and
          stamp_text(board, "time") == "000000",
          "the fixture board could not be set to a stale date and time")
    image = artifact(where, "stamp/anvil.img", b"image-stamp")
    result = module.record_build(board, "pi4", image, by="tools/build.py",
                                 compiler=stand_in_compiler(where), root=root)

    now = time.localtime()
    c.yes(value_of(module, board, "date") != 20000101,
          "the build left the stale date in the board file")
    c.yes(value_of(module, board, "date") == int(time.strftime("%Y%m%d", now)),
          "the build date marker does not carry today's date")
    stamped = stamp_text(board, "time")
    c.yes(stamped != "000000", "the build left the stale time in the board file")
    c.yes(len(stamped) == 6 and stamped.isdigit(),
          f"the build time marker is not six digits: {stamped!r}")
    c.yes(field(result.line, "stamp") ==
          f"{value_of(module, board, 'date')}-{stamped}",
          "the ledger line's stamp is not the date and time written into the board "
          f"file: {field(result.line, 'stamp')} on the line, "
          f"{value_of(module, board, 'date')}-{stamped} in the file")
    # HHMMSS keeps its leading zero: a time that silently loses a digit is worse
    # than no time at all, and int() would eat the zero out of an hour like 09.
    c.yes(abs(int(stamped[:2]) * 3600 + int(stamped[2:4]) * 60 + int(stamped[4:]) -
              (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec)) < 120,
          f"the build time marker is not this build's time: {stamped!r}")


def check_ledger(module, c: Checks, where: Path) -> None:
    """One line per counted build, carrying the hash of what was produced."""
    root = temp_repo(where)
    board = root / module.BOARDS["unoq"]
    start = value_of(module, board)
    payload = b"unoq-image-bytes"
    image = artifact(where, "ledger/anvil.img", payload)

    result = module.record_build("tmp/export/ArduinoQ/Board/board.unoq", "unoq", image,
                                 by="tools/build.py", compiler=stand_in_compiler(where),
                                 root=root)
    lines = ledger_lines(root)
    c.yes(len(lines) == 1, f"one counted build wrote {len(lines)} ledger lines")
    line = lines[0]
    c.yes(field(line, "target") == "unoq", "the ledger line names the wrong target")
    c.yes(field(line, "build") == str(start + 1),
          "the ledger line does not carry the new build number")
    c.yes(field(line, "board") == "ArduinoQ/Board/board.unoq",
          "the ledger line does not name the real board file that moved")
    c.yes(field(line, "sha256") == hashlib.sha256(payload).hexdigest(),
          "the ledger line does not carry the sha256 of the image that was produced")
    c.yes(field(line, "compiler") == hashlib.sha256(COMPILER_BYTES).hexdigest(),
          "the ledger line does not carry the sha256 of the compiler that made it. "
          "The compiler is rebuilt on this bench while gates run, so a build number "
          "without it is half an identity.")
    c.yes(field(line, "by") == "tools/build.py",
          "the ledger line does not name the tool that asked")
    c.yes(field(line, "compile") == result.line.split("compile=")[1],
          "the ledger line does not carry this compile's fingerprint")
    c.yes(line.startswith(time.strftime("%Y-%m-%dT", time.gmtime())) and line[19] == "Z",
          "the ledger line does not start with a UTC timestamp: " + line[:25])
    c.yes("frozen" not in line, "an ordinary counted build was recorded as frozen")


def check_every_caller(module, c: Checks, where: Path) -> None:
    """Every compile site in tools/ moves the number by one, its own way."""
    root = temp_repo(where)
    expected = {target: value_of(module, root / module.BOARDS[target])
                for target in module.BOARDS}
    for index, (tool, target) in enumerate(CALLERS):
        image = artifact(where, f"callers/{index}/anvil.img", f"image-{index}".encode())
        result = module.record_build(module.BOARDS[target], target, image,
                                     by=tool, compiler=stand_in_compiler(where),
                                     root=root)
        expected[target] += 1
        c.yes(result.counted and result.new_value == expected[target],
              f"{tool} building {target} did not raise the number by exactly one")
    for target, want in expected.items():
        c.yes(value_of(module, root / module.BOARDS[target]) == want,
              f"the {target} board file does not hold {want} after every caller ran")
    c.yes(len(ledger_lines(root)) == len(CALLERS),
          "the ledger does not hold one line per caller")


def check_listing_artifact(module, c: Checks, where: Path) -> None:
    """A gate that asked for assembly only is still a build, and is hashed."""
    root = temp_repo(where)
    requested = where / "listing" / "anvil.img"
    listing = artifact(where, "listing/anvil.img.asm", b"; emitted A64\n")
    result = module.record_build(module.BOARDS["pi4"], "pi4", requested,
                                 by="tools/payload_lifecycle_check.py",
                                 compiler=stand_in_compiler(where), root=root)
    c.yes(result.counted, "a -S build of the monitor was not counted")
    c.yes(Path(result.image) == listing,
          "the count hashed something other than the listing the compiler wrote")
    c.yes(field(ledger_lines(root)[0], "sha256") ==
          hashlib.sha256(listing.read_bytes()).hexdigest(),
          "the ledger line does not carry the sha256 of the listing")


def check_not_a_board(module, c: Checks, where: Path) -> None:
    """A fixture is not the monitor: nothing moves and nothing is written."""
    root = temp_repo(where)
    before = {target: value_of(module, root / module.BOARDS[target])
              for target in module.BOARDS}
    image = artifact(where, "fixture/gate.img", b"fixture")
    result = module.record_build(where / "early0.pi4", "pi4", image,
                                 by="tools/screen_early_cache_check.py",
                                 compiler=stand_in_compiler(where), root=root)
    c.yes(not result.counted and result.board is None,
          "a fixture compile was counted as a build of the monitor")
    c.yes(ledger_lines(root) == [], "a fixture compile wrote a ledger line")
    # board.pi4 compiled for the other part is not this part's monitor.
    result = module.record_build("RaspberryPi4/Board/board.pi4", "unoq", image,
                                 by="tools/build.py", compiler=stand_in_compiler(where),
                                 root=root)
    c.yes(not result.counted, "board.pi4 built for unoq was counted as a unoq build")
    for target, value in before.items():
        c.yes(value_of(module, root / module.BOARDS[target]) == value,
              f"the {target} board file moved for something that was not its build")


def check_frozen(module, c: Checks, where: Path) -> None:
    """`; pmf:build off` freezes the number; the build is still recorded."""
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    text = board.read_text(encoding="utf-8")
    frozen = text.replace("; pmf:build\n", "; pmf:build off\n", 1)
    c.yes(frozen != text, "the fixture could not be switched off - the marker has drifted")
    board.write_text(frozen, encoding="utf-8", newline="")
    start = value_of(module, board)

    image = artifact(where, "frozen/anvil.img", b"frozen-image")
    result = module.record_build(board, "pi4", image, by="tools/build.py",
                                 compiler=stand_in_compiler(where), root=root)
    c.yes(not result.counted and result.frozen,
          "a frozen board file was counted as a raised build number")
    c.yes(value_of(module, board) == start,
          "a frozen build number moved anyway")
    lines = ledger_lines(root)
    c.yes(len(lines) == 1 and "frozen=yes" in lines[0],
          "a frozen build was not recorded as a build that happened")
    c.yes(field(lines[0], "build") == str(start),
          "the frozen ledger line does not carry the number the image actually has")


def number_line(text: str) -> str:
    """The board file's own build-number line, whatever it currently reads.

    Written against the line rather than against a value: a fixture that says
    `replace "#ANVIL_BUILD = 56"` stops applying the first time the number
    moves, and then every refusal below is run against a perfectly good file
    and passes by proving nothing. That happened once, on the first sweep.
    """
    found = re.search(r"(?m)^#ANVIL_BUILD = -?\d+ *; pmf:build.*$", text)
    if found is None:
        raise AssertionError("the board file has no plain build-number line to mutate")
    return found.group(0)


def check_refusals(module, c: Checks, where: Path) -> None:
    """A marker that cannot be acted on is refused by name, and nothing moves."""
    cases = (
        ("a hexadecimal value", "PMF-BLD-001",
         lambda t, line: t.replace(line, "#ANVIL_BUILD = $38        ; pmf:build", 1)),
        ("an expression instead of a number", "PMF-BLD-001",
         lambda t, line: t.replace(line, "#ANVIL_BUILD = 55 + 1        ; pmf:build", 1)),
        ("two build-number markers", "PMF-BLD-002",
         lambda t, line: t.replace(
             line, line + "\n#ANVIL_BUILD_TOO = 1    ; pmf:build", 1)),
        ("a misspelt off", "PMF-BLD-009",
         lambda t, line: t.replace(line, line + " offf", 1)),
        ("no marker at all", "PMF-BLD-006",
         lambda t, line: t.replace(
             line, "; the build number used to be here", 1)),
    )
    for label, code, mutate in cases:
        root = temp_repo(where / label.replace(" ", "_"))
        board = root / module.BOARDS["pi4"]
        text = board.read_text(encoding="utf-8")
        line = number_line(text)
        original = mutate(text, line)
        c.yes(original != text,
              f"the {label} fixture did not change the marked line, so the refusal "
              f"below would be run against a perfectly good file")
        board.write_text(original, encoding="utf-8", newline="")
        before = board.read_bytes()
        image = artifact(where, f"refuse/{abs(hash(label))}/anvil.img", b"refused")
        try:
            module.record_build(board, "pi4", image, by="tools/build.py",
                                compiler=stand_in_compiler(where), root=root)
        except module.BuildCountError as error:
            c.yes(str(error).startswith(code),
                  f"{label} was refused as {str(error)[:12]}, not {code}")
            c.yes(len(str(error)) > 120 and str(error).rstrip().endswith("."),
                  f"the {label} refusal is not a full sentence: {error}")
        else:
            raise AssertionError(f"{label} was accepted; a build was counted against it")
        c.yes(board.read_bytes() == before, f"{label} changed the board file anyway")
        c.yes(ledger_lines(root) == [], f"{label} wrote a ledger line anyway")


def check_counted_once(module, c: Checks, where: Path) -> None:
    """The same compile offered twice is one build."""
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    start = value_of(module, board)
    image = artifact(where, "once/anvil.img", b"same-image")

    compiler = stand_in_compiler(where)
    first = module.record_build(board, "pi4", image, by="tools/build.py",
                                compiler=compiler, root=root)
    second = module.record_build(board, "pi4", image, by="tools/build.py",
                                 compiler=compiler, root=root)
    c.yes(first.counted, "the first offer of a compile was not counted")
    c.yes(not second.counted and second.already,
          "the same compile was counted a second time")
    c.yes(value_of(module, board) == start + 1,
          "one compile moved the build number twice")
    c.yes(len(ledger_lines(root)) == 1, "one compile wrote two ledger lines")

    # Two REAL builds that happen to produce identical bytes are two builds.
    again = artifact(where, "once/second/anvil.img", b"same-image")
    third = module.record_build(board, "pi4", again, by="tools/build.py",
                                compiler=compiler, root=root)
    c.yes(third.counted and third.new_value == start + 2,
          "a second build with identical output was mistaken for the first one")


def check_compiler_named(module, c: Checks, where: Path) -> None:
    """A counted build names the compiler that made it, or it is refused.

    Which compiler emitted an image is half of what identifies it, and the compiler
    is rebuilt on this bench while gates are running - it was rebuilt in the
    middle of the first sweep this mechanism ever ran. Writing the line without
    it would record a number and lose what the number is of.
    """
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    before = board.read_bytes()
    image = artifact(where, "unnamed/anvil.img", b"who-built-this")
    try:
        module.record_build(board, "pi4", image, by="tools/build.py", root=root)
    except module.BuildCountError as error:
        c.yes(str(error).startswith("ANVIL-BLD-001"),
              f"a build with no compiler named was refused as {str(error)[:14]}")
    else:
        raise AssertionError("a build was counted without naming the compiler that "
                             "made it")
    c.yes(board.read_bytes() == before, "the refused build moved the number anyway")
    c.yes(ledger_lines(root) == [], "the refused build wrote a ledger line anyway")

    missing = where / "gone" / "PureMetalForge.exe"
    try:
        module.record_build(board, "pi4", image, by="tools/build.py",
                            compiler=missing, root=root)
    except module.BuildCountError as error:
        c.yes(str(error).startswith("ANVIL-BLD-001"),
              "a compiler that cannot be read was not refused by name")
    else:
        raise AssertionError("a build named a compiler that does not exist and counted")

    # The digest is of the BYTES, so a staged copy under another name records
    # the same compiler - which is what every gate actually runs.
    original = stand_in_compiler(where)
    staged = where / "staged" / "PureMetalForge.exe"
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, staged)
    first = module.record_build(board, "pi4", image, by="tools/build.py",
                                compiler=original, root=root)
    second = module.record_build(board, "pi4",
                                 artifact(where, "unnamed/second.img", b"again"),
                                 by="tools/build.py", compiler=staged, root=root)
    c.yes(first.counted and second.counted, "a named build did not count")
    lines = ledger_lines(root)
    c.yes(field(lines[0], "compiler") == field(lines[1], "compiler"),
          "a staged copy of the compiler was recorded as a different compiler")


def _driver(where: Path) -> Path:
    """A worker that counts one build through the module under test."""
    path = where / "count_one.py"
    path.write_text(
        "import importlib.util, sys, time\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('bc_under_test', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "start = float(sys.argv[5])\n"
        "while time.time() < start:\n"
        "    time.sleep(0.001)\n"
        "result = module.record_build(sys.argv[6], sys.argv[3], Path(sys.argv[4]),\n"
        "                             by='tools/build_count_check.py',\n"
        "                             compiler=Path(sys.argv[7]), root=Path(sys.argv[2]))\n"
        "print(result.new_value)\n",
        encoding="utf-8", newline="")
    return path


def check_concurrent(module, c: Checks, where: Path) -> None:
    """Six builds at once count six. Two workers may run gates at the same time."""
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    start = value_of(module, board)
    driver = _driver(where)
    workers = 6
    begin = time.time() + 1.5
    running = []
    for index in range(workers):
        image = artifact(where, f"race/{index}/anvil.img", f"race-{index}".encode())
        running.append(subprocess.Popen(
            [sys.executable, str(driver), str(Path(module.__file__)), str(root), "pi4",
             str(image), f"{begin}", str(module.BOARDS["pi4"]),
             str(stand_in_compiler(where))],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    outputs = [process.communicate()[0] for process in running]
    for process, output in zip(running, outputs):
        c.yes(process.returncode == 0, "a concurrent build failed:\n" + output)

    c.yes(value_of(module, board) == start + workers,
          f"{workers} concurrent builds moved the number to "
          f"{value_of(module, board)}, not {start + workers} - an update was lost")
    reported = sorted(int(output.strip().splitlines()[-1]) for output in outputs)
    c.yes(reported == list(range(start + 1, start + workers + 1)),
          f"the concurrent builds did not each get their own number: {reported}")
    lines = ledger_lines(root)
    c.yes(len(lines) == workers, f"{workers} concurrent builds wrote {len(lines)} lines")
    c.yes(len({field(line, "compile") for line in lines}) == workers,
          "two concurrent builds share a compile fingerprint")
    c.yes(sorted(int(field(line, "build")) for line in lines) == reported,
          "the ledger and the board file disagree about which builds happened")


def check_lock_blocks(module, c: Checks, where: Path) -> None:
    """While the lock is held, a build in another process waits for it.

    Deterministic on purpose. Racing six workers and hoping to observe a lost
    update is how a mutation survives a gate on a quiet machine.
    """
    root = temp_repo(where)
    board = root / module.BOARDS["pi4"]
    start = value_of(module, board)
    driver = _driver(where)
    image = artifact(where, "blocked/anvil.img", b"blocked-image")

    with module._locked(root / module.LOCK_NAME):
        process = subprocess.Popen(
            [sys.executable, str(driver), str(Path(module.__file__)), str(root), "pi4",
             str(image), "0", str(module.BOARDS["pi4"]),
             str(stand_in_compiler(where))],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(2.0)
        finished = process.poll()
        held = value_of(module, board)
    output = process.communicate()[0]
    c.yes(finished is None,
          "a build counted itself while another process held the lock; two builds "
          "that overlap would read the same number and one of them would vanish")
    c.yes(held == start, "the board file moved while the lock was held elsewhere")
    c.yes(process.returncode == 0, "the waiting build failed once the lock was free:\n"
          + output)
    c.yes(value_of(module, board) == start + 1,
          "the build that waited for the lock did not count when it got it")


# ------------------------------------------------------------------ the wiring
def compiles_a_literal_board(text: str) -> bool:
    """Does a ``--compile`` argument resolve to a board entry-point path?

    Merely reading board.pi4 to check its include order does not build it. The
    former scan conflated that with passing the board to the compiler and began
    rejecting fixture-only emitted-code gates. This small resolver follows the
    ordinary Path/PurePosixPath, ``/``, str(), relative_to() and as_posix()
    shapes used by these tools, but only from the list that actually contains
    ``--compile``.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value

    def resolve(node, seen=()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.replace("\\", "/")
        if isinstance(node, ast.Name):
            if node.id == "ROOT":
                return ""
            if node.id in seen or node.id not in values:
                return None
            return resolve(values[node.id], (*seen, node.id))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left, right = resolve(node.left, seen), resolve(node.right, seen)
            if left is None or right is None:
                return None
            return "/".join(part.strip("/") for part in (left, right) if part)
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in {"str", "Path", "pathlib.Path", "PurePosixPath"} and node.args:
                return resolve(node.args[0], seen)
            if name.endswith((".as_posix", ".relative_to")):
                return resolve(node.func.value, seen)
        return None

    board_names = {path.name.lower() for path in reference.BOARDS.values()}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        for index, item in enumerate(node.elts[:-1]):
            if isinstance(item, ast.Constant) and item.value == "--compile":
                source = resolve(node.elts[index + 1])
                if source is not None and Path(source).name.lower() in board_names:
                    return True
    return False


def compiling_tools() -> list[Path]:
    """Every known counter caller plus newly discovered literal-board compile."""
    found = []
    for path in sorted(ROOT.joinpath("tools").rglob("*.py")):
        if "__pycache__" in path.parts or "_work" in path.parts:
            continue
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        accounted = name == "tools/build.py" or "build_count.record_build(" in text
        if "subprocess." not in text or not (accounted or compiles_a_literal_board(text)):
            continue
        found.append(path)
    return found


def check_wiring(c: Checks) -> None:
    """One module, with a transaction for builds and a recorder for old gates."""
    tools = compiling_tools()
    names = {path.relative_to(ROOT).as_posix() for path in tools}
    # The four that compile the monitor itself, by name: if the scan stops
    # seeing one of them the wiring proof below would pass by finding nothing.
    for known in {tool for tool, _ in CALLERS}:
        c.yes(known in names,
              f"{known} compiles a board file and the wiring scan no longer sees it")
    c.yes(len(tools) >= len({tool for tool, _ in CALLERS}),
          f"only {len(tools)} tools were found that compile and hold a board path; "
          f"the scan has stopped seeing them")
    for path in tools:
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        tree = ast.parse(text)
        if name == "tools/build.py":
            builds = [node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == "build"]
            c.yes(len(builds) == 1, "tools/build.py no longer has one build() owner")
            transactions = []
            for node in ast.walk(builds[0]):
                if not isinstance(node, ast.With):
                    continue
                for item in node.items:
                    expression = item.context_expr
                    if (isinstance(expression, ast.Call) and
                            ast.unparse(expression.func) == "build_count.build_identity"):
                        transactions.append(node)
            c.yes(len(transactions) == 1,
                  "tools/build.py does not hold exactly one build_identity transaction")
            calls = [node for node in ast.walk(transactions[0]) if isinstance(node, ast.Call)]
            compile_calls = [node for node in calls
                             if ast.unparse(node.func) == "_compile_and_publish"]
            register_calls = [node for node in calls
                              if ast.unparse(node.func).endswith(".register_publication")]
            complete_calls = [node for node in calls
                              if ast.unparse(node.func).endswith(".complete")]
            c.yes(len(compile_calls) == len(register_calls) == len(complete_calls) == 1,
                  "tools/build.py transaction does not compile, register rollback and complete once")
            c.yes(transactions[0].lineno < compile_calls[0].lineno <
                  register_calls[0].lineno < complete_calls[0].lineno,
                  "tools/build.py transaction order is not reserve, compile, rollback hook, complete")
            continue
        c.yes("build_count.record_build(" in text,
              f"{name} runs the compiler over a tree that holds a board file and never "
              f"asks build_count whether it just built the monitor. A build that is not "
              f"offered to the counter cannot be counted.")

        for function in [node for node in ast.walk(tree)
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            records = [node for node in calls
                       if ast.unparse(node.func) == "build_count.record_build"]
            runs = [node for node in calls
                    if ast.unparse(node.func).startswith("subprocess.")]
            if not records or not runs:
                continue
            records.sort(key=lambda node: node.lineno)
            runs.sort(key=lambda node: node.lineno)
            c.yes(len(records) == len(runs),
                  f"{name}: {function.name} has {len(runs)} compiler runs but "
                  f"{len(records)} artifact records")
            c.yes(all(run.lineno < record.lineno
                      for run, record in zip(runs, records)),
                  f"{name}: {function.name} records an artifact before its matching "
                  f"compiler run. A failed compile cannot consume a build number.")

    # ONE MECHANISM. The compiler's own bumper raises the file it was handed,
    # which for a gate is a copy in a temporary directory; asking for it as well
    # would bump twice for an ordinary build and still miss every gate build.
    for path in sorted(ROOT.joinpath("tools").rglob("*.py")):
        if "__pycache__" in path.parts or path.name == Path(__file__).name:
            continue
        # The flags as a program would pass them - a string constant, not the
        # word inside a comment or a docstring explaining why it is gone.
        try:
            constants = {node.value for node in ast.walk(ast.parse(path.read_text(
                encoding="utf-8")))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        except SyntaxError as error:
            raise AssertionError(f"{path.relative_to(ROOT).as_posix()}: {error}") from error
        name = path.relative_to(ROOT).as_posix()
        c.yes("--bump-build" not in constants,
              f"{name} still asks the compiler to bump. There is one mechanism and it "
              f"is tools/build_count.py; two would double-count an ordinary build, "
              f"still miss every gate build, and take two locks over one file.")
        c.yes("--no-bump" not in constants,
              f"{name} offers a way to build without counting. The ruling is that every "
              f"build counts: a build made to verify something is still a build of the "
              f"monitor, and the number moving is how anyone can tell it happened.")

    build_py = (ROOT / "tools/build.py").read_text(encoding="utf-8")
    c.yes("build_count.build_identity(" in build_py,
          "tools/build.py does not reserve the identity its compiler will embed")

    # The real board files must each carry exactly one enabled marker and both
    # siblings, or the numbers this repository reports are not numbers at all.
    for board in REAL_BOARDS:
        data, sites = reference.read_sites(board)
        kinds = [site.kind for site in sites]
        for kind in ("number", "date", "time"):
            c.yes(kinds.count(kind) == 1,
                  f"{board.name} does not carry exactly one {kind} marker")
        number = next(site for site in sites if site.kind == "number")
        c.yes(number.enabled,
              f"{board.name} has its build number switched off, so its builds are not "
              f"being counted; if that is a release freeze, say so where it can be seen")


# ------------------------------------------------------------------ end to end
def check_end_to_end(c: Checks, where: Path, compiler: str) -> str:
    """A real compile of the monitor, on a copy, raises the copy by exactly one.

    AND THEN IT COUNTS FOR REAL. The proof fixtures above are copies and must
    never touch the tree, but this one is not a fixture - it is the monitor,
    compiled end to end by the same tool that builds the image that gets
    flashed. Counting it only inside a directory that is deleted a second later
    would make this gate the one build in the repository that does not count,
    which is exactly the hole the 2026-09-11 ruling closed. So the copy's count
    proves the mechanism, and the same compile is then recorded against the real
    board file, signed by this gate.
    """
    root = where / "tree"
    root.mkdir(parents=True)
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.split("\n")
    for relative in [item.strip() for item in listed if item.strip()]:
        source = ROOT / relative
        if not source.is_file():
            continue
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    # tools/ is copied as it stands, not as it is committed: this gate proves the
    # mechanism that is about to be committed, not the one that already was.
    for tool in sorted(ROOT.joinpath("tools").glob("*.py")):
        shutil.copy2(tool, root / "tools" / tool.name)

    board = root / reference.BOARDS["pi4"]
    start = value_of(reference, board)
    completed = subprocess.run(
        [sys.executable, "tools/build.py", "pi4", "--compiler", compiler],
        cwd=root, capture_output=True, text=True)
    c.yes(completed.returncode == 0,
          "the end-to-end build failed:\n" + completed.stdout + completed.stderr)

    image = root / "build/pi4/anvil.img"
    c.yes(image.is_file(), "the end-to-end build wrote no image")
    c.yes(value_of(reference, board) == start + 1,
          f"a real compile through tools/build.py took the copy's build number to "
          f"{value_of(reference, board)}, not {start + 1}")
    lines = ledger_lines(root)
    c.yes(len(lines) == 1, f"a real compile wrote {len(lines)} ledger lines")
    c.yes(field(lines[0], "sha256") ==
          hashlib.sha256(image.read_bytes()).hexdigest(),
          "the ledger line does not carry the sha256 of the image that was built")
    c.yes(field(lines[0], "by") == "tools/build.py",
          "the ledger line does not name tools/build.py")
    c.yes(field(lines[0], "build") == str(start + 1),
          "the ledger line and the board file disagree about the build number")

    real = reference.record_build(board, "pi4", image,
                                  by="tools/build_count_check.py",
                                  compiler=compiler, root=ROOT)
    c.yes(real.counted,
          "the gate's own monitor build was not counted against the real board file")
    return (f"copy {board.name} {start} -> {start + 1}; real board.pi4 "
            f"{real.value} -> {real.new_value}; image "
            f"{field(lines[0], 'sha256')[:16]}..., {image.stat().st_size} bytes")


# --------------------------------------------------------------------- mutants
# Each mutation is applied to a copy of build_count.py, and the ONE check that
# owns that property must fail against it.
MUTANTS = (
    ("the lock is dropped", "check_lock_blocks",
     lambda text: text + "\n\n@contextlib.contextmanager\ndef _locked(lock):\n"
                         "    lock.parent.mkdir(parents=True, exist_ok=True)\n    yield\n"),
    ("the date and time stamp is dropped", "check_stamps",
     lambda text: text.replace(
         'for kind, text in (("date", stamp_date), ("time", stamp_time)):',
         'for kind, text in ():')),
    ("the number is bumped twice", "check_bump_by_one",
     lambda text: text.replace("new_value = number.value + 1",
                               "new_value = number.value + 2")),
    ("one compile is counted twice", "check_counted_once",
     lambda text: text.replace("if _already_counted(ledger_path, fingerprint):",
                               "if False:")),
    ("a frozen marker is bumped anyway", "check_frozen",
     lambda text: text.replace("if not number.enabled:", "if False:")),
    ("a malformed marker is ignored", "check_refusals",
     lambda text: text.replace("        if not site.valid:", "        if False:")),
    ("the compiler is left out of the ledger line", "check_ledger",
     lambda text: text.replace('        f"compiler={built_by}",' + chr(10), "")),
    ("a build may be counted without naming its compiler", "check_compiler_named",
     lambda text: text.replace("    if compiler is None:", "    if False:")),
)


def load(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CHECKS = (
    ("bump by one", check_bump_by_one),
    ("date and time stamped", check_stamps),
    ("ledger line", check_ledger),
    ("every caller", check_every_caller),
    ("assembly-only artifact", check_listing_artifact),
    ("a fixture is not the monitor", check_not_a_board),
    ("frozen", check_frozen),
    ("refusals", check_refusals),
    ("counted once", check_counted_once),
    ("the compiler is named", check_compiler_named),
    ("concurrent builds", check_concurrent),
    ("the lock blocks", check_lock_blocks),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--fast", action="store_true",
                        help="skip the real 70-second monitor compile")
    arguments = parser.parse_args(); arguments.compiler = _pmfpath.Path(resolve_compiler(arguments.compiler)) if arguments.compiler else arguments.compiler

    checks = Checks()
    # THE REAL BOARD FILES MOVE ONLY FOR A REAL BUILD, and it is checked rather
    # than promised. Every fixture in this gate works on a copy; the one thing
    # that may reach the tree is the count for the end-to-end compile, which is
    # a genuine build of the monitor and therefore counts. Anything else that
    # moved is this gate writing the tree by accident, which for a gate about
    # build numbers would be the worst possible defect.
    untouched = {board: board.read_bytes() for board in REAL_BOARDS}
    compiled_for_real = False
    end_to_end = "not run"
    try:
        with tempfile.TemporaryDirectory(prefix="anvil-build-count-") as name:
            where = Path(name)
            for label, check in CHECKS:
                check(reference, checks, where / label.replace(" ", "_"))
            check_wiring(checks)

            source = (ROOT / "tools/build_count.py").read_text(encoding="utf-8")
            for index, (label, owner, mutate) in enumerate(MUTANTS):
                mutated = mutate(source)
                checks.yes(mutated != source, f"mutation did not apply: {label}")
                path = where / f"mutant{index}" / "build_count.py"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(mutated, encoding="utf-8", newline="")
                module = load(path, f"anvil_build_count_mutant{index}")
                check = next(function for _, function in CHECKS
                             if function.__name__ == owner)
                try:
                    check(module, Checks(), where / f"mutant{index}" / "work")
                except (AssertionError, module.BuildCountError, TypeError):
                    print(f"  rejected: {label}")
                else:
                    raise AssertionError(f"mutation survived: {label}")
                checks.count += 1

            if arguments.fast or not arguments.compiler:
                end_to_end = ("skipped - pass --compiler (or set PMF_COMPILER) without --fast to "
                              "compile the monitor once, on a copy")
            else:
                compiled_for_real = True
                end_to_end = check_end_to_end(checks, where / "endtoend", arguments.compiler)
    except (AssertionError, OSError, subprocess.SubprocessError,
            reference.BuildCountError) as error:
        print(f"build_count_check: FAIL after {checks.count} checks: {error}")
        return 1
    finally:
        for board, data in untouched.items():
            now = board.read_bytes()
            if now == data:
                continue
            expected = board.name == "board.pi4" and compiled_for_real
            moved = [index for index, (old, new)
                     in enumerate(zip(data.splitlines(), now.splitlines())) if old != new]
            if not expected or not moved or not all(
                    b"pmf:build" in now.splitlines()[index] for index in moved):
                print(f"build_count_check: FAIL - this gate wrote the real {board.name} "
                      f"outside the one build it actually made")
                return 1

    print(f"build_count_check: PASS - {checks.count} checks, "
          f"{len(MUTANTS)} mutations rejected")
    print(f"  end-to-end compile: {end_to_end}")
    print("  every fixture ran on a copy; the real board files moved only for the one "
          "monitor build this gate actually made. No board was contacted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
