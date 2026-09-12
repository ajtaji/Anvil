#!/usr/bin/env python3
"""EVERY ANVIL BUILD COUNTS. This module is the one place that counts one.

THE RULING, 2026-09-11: "from now on if you build anvil the build number
needs to be increased", and when it turned out that gate fixtures had been
building the whole monitor uncounted, "gate builds do count" and "I want real
build tracking, not estimated". `version` on the board prints #ANVIL_BUILD so
a person watching a board can tell one image from another without hashing
anything. That only works if the number moves for EVERY build of the monitor -
the one the flasher makes, and the ten a gate run makes from temporary copies.

WHAT WAS WRONG BEFORE THIS FILE. tools/build.py asked the compiler to bump
(the compiler's own `--bump-build`), so it raised the marker in THE FILE IT WAS
GIVEN. A gate compiles the monitor from a temporary export with a staged
compiler, so the file it was given was a copy in a temporary directory that is
deleted seconds later. The real board file never moved and the count was not
real - it was the count of the builds that happened to be made one particular
way. Ten monitor builds a gate run went unrecorded.

WHAT THIS MODULE OWNS, and it is a single sentence: "a board file was built".
Hand it the source path that was compiled (the real board file or any copy of
it), the target, the artifact the compiler produced and the name of the tool
that asked, and it

  1. identifies WHICH REAL BOARD FILE in this repository that compile was a
     build of - RaspberryPi4/Board/board.pi4 for pi4, ArduinoQ/Board/board.unoq
     for unoq, or RaspberryPi3/Board/board.pi3 for the experimental Pi 3;
  2. raises that file's `; pmf:build` marker by exactly one and stamps the
     `; pmf:builddate` and `; pmf:buildtime` siblings beside it;
  3. honours `; pmf:build off` - a frozen number does not move, and the build
     is still recorded, because a build that happened is evidence whether or
     not the number was allowed to follow it;
  4. appends one line to the ledger at build/BUILDS.log.

ONE MECHANISM, NOT TWO. `--bump-build` is NOT passed by anything in tools/ any
more, including tools/build.py. Every counted build in this repository goes
through record_build() in this file and through nothing else. Two bumpers -
the compiler raising the file it was handed while this module raises the file
that file came from - would double-count the ordinary build and still miss the
gate builds, and they would take two different locks over one file, which is
the lost-update shape this module exists to refuse. The compiler's own bumper
is untouched and is still what the IDE's build action uses; this repository
simply does not ask for it.

`--no-bump` IS GONE. The ruling is that every build counts, and a flag whose
whole purpose is to make a build not count contradicts it. There is no
verification build in this repository that compiles a board file and must not
be counted: a build made to check something is still a build of the monitor,
and the number moving is how anyone can later tell that it happened.

THE MARKER CONTRACT is the compiler's, not this file's invention. It is
defined in BuildNumber.pbi in the compiler tree and reimplemented here byte for
byte: a line is marked when the FIRST word of its comment, found outside any
string literal, is `pmf:build`, `pmf:builddate` or `pmf:buildtime`; the code
half must be `#NAME = <plain decimal whole number>` and nothing else; a
comment-only line is never a marker, because a marker marks a constant; the
second word may be `on` or `off` and any other bare word is a typo that is
refused by name rather than read as `on`. The PMF-BLD-nnn codes below are the
compiler's codes and mean what they mean there - one vocabulary for one
contract, so a refusal from the IDE and a refusal from a gate are the same
refusal.

BYTE FOR BYTE. The file is read as raw bytes and only the digits of a value
are replaced. The encoding, the byte-order mark, the line endings, the spacing
and the comment come back exactly as they went in, so `git diff` shows the
three lines whose numbers changed and nothing else.

ALL THREE LINES LAND AT ONCE. The compiler writes the number, then the date,
then the time, as three separate writes, and says so: the number goes first so
a failure to write the date cannot leave a file whose date moved and whose
number did not. This module splices all three in memory and writes the result
through one temporary file and one os.replace(), which is atomic on both hosts
this repository builds on. Either all three moved or none did, and a reader -
the compiler, in another worker's gate run - never sees a half-written board
file.

TWO WORKERS RUN GATES AT ONCE. Every read-modify-write of a board file and
every ledger append happens while holding build/BUILDS.lock, so two concurrent
builds of the same target count TWO: 56 -> 57 -> 58, never 56 -> 57 twice.

ONE COMPILE IS COUNTED ONCE. Each call fingerprints the compile by the
artifact it produced - its absolute path, its size, its modification time in
nanoseconds and its sha256 - and that fingerprint goes in the ledger line. A
second call naming the same artifact, unchanged, is the same compile arriving
twice and is recorded as already counted rather than bumped again. Two real
builds that happen to produce identical bytes still count twice, because they
are written at different times to different paths: the fingerprint is the
compile, not the image.

THE LEDGER LIVES IN build/, WHICH IS GITIGNORED, AND THAT IS DELIBERATE. The
durable, shareable count is the marker line in the board file, and that IS
committed - it travels with the source, shows up in a diff and is what the
image announces. The ledger is the local evidence behind it: what this machine
built, when, out of which temporary directory, and what the bytes hashed to.
Tracked, it would conflict on every concurrent gate run between two workers,
and it would carry one machine's temp paths into everybody else's clone.
build/ rather than _work/ because the artifacts these lines hash are already
in build/, so the evidence sits beside what it is evidence of; _work/ is lane
scratch that gets cleared.

THE COMPILER THAT MADE IT IS PART OF THE RECORD. `compiler=` carries the sha256 of
the executable that produced the image. The compiler is rebuilt on this bench
while gates are running - it was rebuilt in the middle of the first sweep this
mechanism ever ran - so "build 58 of board.pi4" is only half an identity: the
other half is which compiler emitted it. Two images with the same build number
and different compiler hashes is exactly the confusion the build number exists to
end, and it is not recoverable after the fact. A counted build with no compiler
named is refused rather than written down half-known.

THE LEDGER LINE, one per counted build:

  2026-09-11T21:33:07Z target=pi4 build=57 stamp=20260911-213307
  board=RaspberryPi4/Board/board.pi4 source=<the path that was compiled>
  image=<the artifact> sha256=<64 hex> compiler=<64 hex> by=<tool>
  compile=<16 hex>

written on ONE line. The time at the front is UTC so that two workers' lines
sort against each other; the stamp is the local date and time written into the
board file's sibling markers, which is what the board prints and what the
compiler has always written there.

THE CODES. PMF-BLD-nnn are the COMPILER's codes for the marker contract and
mean here exactly what they mean there. What this module asks for on top of
that contract - a named compiler - is Anvil's own requirement, so it carries an
ANVIL-BLD code. One code never means two things.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

# THE ONLY TWO FILES IN THIS REPOSITORY THAT HAVE A BUILD NUMBER. Each board
# file is its own project and counts its own builds; the shared core in
# Anvil/Core carries no marker, because a library is built into many projects
# and a number bumped by all of them counts nothing (the compiler refuses that
# by name, PMF-BLD-003).
BOARDS = {
    "pi3": Path("RaspberryPi3/Board/board.pi3"),
    "pi3-loader": Path("RaspberryPi3/Board/loader.pi3"),
    "pi3-updater": Path("RaspberryPi3/Board/updater.pi3"),
    "pi4": Path("RaspberryPi4/Board/board.pi4"),
    "unoq": Path("ArduinoQ/Board/board.unoq"),
}

LEDGER_NAME = Path("build/BUILDS.log")
LOCK_NAME = Path("build/BUILDS.lock")

# A lock this old belonged to a process that died holding it. Five minutes is
# far longer than the longest monitor compile on this bench and short enough
# that a crashed worker does not wedge the next gate run.
LOCK_STALE_SECONDS = 300.0
LOCK_TIMEOUT_SECONDS = 180.0

# The constant's ceiling: constants are stored in a signed 64-bit integer, so
# this is the type's limit and not a number chosen to look big.
MAX_BUILD = 9223372036854775807

MARKERS = {
    "pmf:build": "number",
    "pmf:builddate": "date",
    "pmf:buildtime": "time",
}
KIND_WORD = {"number": "build-number", "date": "build-date", "time": "build-time"}
MARKER_WORD = {"number": "pmf:build", "date": "pmf:builddate", "time": "pmf:buildtime"}


class BuildCountError(Exception):
    """A refusal that names its code and says what state the file is in.

    Errors here are full sentences carrying the numeric code (the 2026-09-03
    rule): what failed, what the code means, what was and was not changed, and
    the first thing to check.
    """


class Site:
    """One marked line, with the byte offsets that let one field be replaced."""

    __slots__ = ("kind", "line", "name", "raw", "value", "valid", "enabled",
                 "switch", "bad_switch", "text", "value_start", "value_len")

    def __init__(self) -> None:
        self.kind = None
        self.line = 0
        self.name = ""
        self.raw = ""
        self.value = 0
        self.valid = False
        self.enabled = True
        self.switch = ""
        self.bad_switch = ""
        self.text = ""
        self.value_start = 0
        self.value_len = 0


class Result:
    """What record_build() answers with. Nothing here is a bare flag."""

    __slots__ = ("counted", "already", "frozen", "target", "board", "value",
                 "new_value", "sha256", "image", "line", "message")

    def __init__(self, **kw) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"Result(counted={self.counted}, already={self.already}, "
                f"frozen={self.frozen}, target={self.target}, "
                f"{self.value}->{self.new_value})")


# ---------------------------------------------------------------- the scanner
def _comment_pos(text: str) -> int:
    """Index of the comment character found OUTSIDE a string literal, or -1.

    `PrintN("; pmf:build")` is a program printing text, not a marked line, and
    a scanner that cannot tell the difference rewrites somebody's string.
    """
    in_string = False
    for index, char in enumerate(text):
        if char == '"':
            in_string = not in_string
        elif char == ";" and not in_string:
            return index
    return -1


def _is_whole_number(text: str) -> bool:
    """A plain decimal whole number as a person would write one.

    DECIMAL ONLY, on purpose. `$10` and `%1010` are bit patterns written by
    somebody thinking in bits; a build number is a quantity that gets
    incremented, so a marker on one of those is refused rather than guessed at.
    """
    if not text:
        return False
    body = text[1:] if text[0] in "+-" else text
    return bool(body) and body.isdigit() and body.isascii()


def _is_name_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def _scan_line(text: str, site: Site) -> str | None:
    """Return the marker kind on this line, or None. Offsets are into `text`.

    A line carrying a marker that is NOT a whole-number constant comes back
    with a kind and valid=False, so the caller refuses it BY NAME instead of
    silently ignoring it: a marker that quietly does nothing is the worst of
    the three outcomes.
    """
    comment = _comment_pos(text)
    if comment < 0:
        return None
    # A COMMENT-ONLY LINE IS NEVER A MARKER, and that is not a technicality: a
    # marker marks a constant, so there has to be a constant on the line for it
    # to mark. Without this rule every line of prose that shows a marker would
    # be one, and the feature could not be written about in its own tree.
    if not text[:comment].strip():
        return None

    index = comment + 1
    while index < len(text) and text[index] in " \t":
        index += 1
    start = index
    while index < len(text) and text[index] not in " \t":
        index += 1
    kind = MARKERS.get(text[start:index].lower())
    if kind is None:
        return None

    site.kind = kind
    site.text = text.strip()
    site.enabled = True
    site.switch = ""
    site.bad_switch = ""

    # The optional on/off switch is the SECOND word. Prose after the marker is
    # allowed and means nothing ("; pmf:build - raised by the IDE"); a bare
    # WORD is not prose, and `; pmf:build offf` is a typo that would silently
    # leave bumping on, so it is refused by name.
    while index < len(text) and text[index] in " \t":
        index += 1
    start = index
    while index < len(text) and text[index] not in " \t":
        index += 1
    word = text[start:index]
    if word:
        lowered = word.lower()
        if lowered == "on":
            site.switch = word
        elif lowered == "off":
            site.switch = word
            site.enabled = False
        elif word.isascii() and word.isalpha():
            site.bad_switch = word

    # The code half: `#NAME = <sign><digits>` and nothing else.
    code = text[:comment]
    position = 0
    while position < len(code) and code[position] in " \t":
        position += 1
    if position >= len(code) or code[position] != "#":
        return kind
    name_start = position
    position += 1
    while position < len(code) and _is_name_char(code[position]):
        position += 1
    if position == name_start + 1:
        return kind
    name = code[name_start:position]

    while position < len(code) and code[position] in " \t":
        position += 1
    if position >= len(code) or code[position] != "=":
        return kind
    position += 1
    while position < len(code) and code[position] in " \t":
        position += 1
    value_start = position
    while position < len(code) and code[position] not in " \t":
        position += 1
    literal = code[value_start:position]
    while position < len(code) and code[position] in " \t":
        position += 1
    if position < len(code):          # something else before the comment
        return kind
    if not _is_whole_number(literal):
        return kind

    site.name = name
    site.raw = literal
    site.value = int(literal)
    site.value_start = value_start
    site.value_len = len(literal)
    site.valid = True
    return kind


def scan(data: bytes) -> list[Site]:
    """Every marked line in a file's raw bytes, with absolute byte offsets.

    Lines are walked as bytes and decoded latin-1, so one byte in is one
    character out and character N of a decoded line is byte N of the file.
    Multi-byte UTF-8 in a comment survives untouched because it is never
    re-encoded - only digits are spliced back.
    """
    sites: list[Site] = []
    if not data:
        return sites

    position = 0
    # A UTF-8 byte-order mark is three bytes of file that are not three
    # characters of source. Stepped over here, once; the bytes stay in the file
    # because nothing after this point rewrites anything but digits.
    if data[:3] == b"\xef\xbb\xbf":
        position = 3

    line_no = 0
    total = len(data)
    while position < total:
        start = position
        end = data.find(b"\n", position)
        if end < 0:
            end = total
            position = total
        else:
            position = end + 1
        # The CR of a CRLF is part of the line's bytes but never part of its
        # text; left in, it would sit inside the value of a line that ends with
        # its number.
        text_end = end
        if text_end > start and data[text_end - 1:text_end] == b"\r":
            text_end -= 1
        line_no += 1
        text = data[start:text_end].decode("latin-1")
        if ";" not in text:
            continue
        site = Site()
        if _scan_line(text, site) is None:
            continue
        site.line = line_no
        if site.valid:
            site.value_start += start          # make the offsets absolute
        sites.append(site)
    return sites


def read_sites(path: Path) -> tuple[bytes, list[Site]]:
    """Load a file and refuse, by code, anything decidable from the file alone."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise BuildCountError(
            f"PMF-BLD-008: the file {path} could not be read, so this project's "
            f"build number could not be looked at ({error}). Nothing was changed. "
            f"Check that the path is right and that the file has not been moved, "
            f"renamed or deleted since it was last built."
        ) from error

    sites = scan(data)
    for kind in ("number", "date", "time"):
        same = [site for site in sites if site.kind == kind]
        if len(same) > 1:
            raise BuildCountError(
                f"PMF-BLD-002: the file {path.name} carries {len(same)} "
                f"{KIND_WORD[kind]} markers, on lines "
                f"{' and '.join(str(site.line) for site in same[:2])}, and a project "
                f"has exactly one - with two of them nothing can say which one the "
                f"program prints. Nothing was changed and no build was recorded. "
                f"Delete the '; {MARKER_WORD[kind]}' comment from all but one of them."
            )

    for site in sites:
        if site.bad_switch:
            raise BuildCountError(
                f"PMF-BLD-009: the word '{site.bad_switch}' after the "
                f"{MARKER_WORD[site.kind]} marker on line {site.line} of {path.name} "
                f"is neither 'on' nor 'off', and those are the only two words that "
                f"switch bumping for a project. Nothing was changed and no build was "
                f"recorded, because a misspelt 'off' that quietly means 'on' would "
                f"raise a number somebody had asked to freeze. Write "
                f"'; {MARKER_WORD[site.kind]} off' exactly, or remove the word."
            )
        if not site.valid:
            raise BuildCountError(
                f"PMF-BLD-001: the {KIND_WORD[site.kind]} marker on line {site.line} "
                f"of {path.name} is not on a whole-number constant - the line reads "
                f'"{site.text}". A marked line must be a constant assigned a plain '
                f'decimal whole number, as in "#ANVIL_BUILD = 1        ; '
                f'{MARKER_WORD[site.kind]}". Nothing was changed and no build was '
                f"recorded. Check for a hexadecimal ($) or binary (%) value, a "
                f"fraction, an expression, or a marker left on a line that is not a "
                f"constant declaration."
            )
    return data, sites


# ----------------------------------------------------------------- the writer
def _splice(data: bytes, start: int, length: int, text: str) -> bytes:
    return data[:start] + text.encode("ascii") + data[start + length:]


def _write_atomic(path: Path, data: bytes) -> None:
    """One temporary file in the same directory, then one os.replace().

    A reader - the compiler, in another worker's gate run - never sees a
    half-written board file, and a crash between the two leaves the old file
    whole rather than a truncated one.
    """
    temporary = path.with_name(f"{path.name}.build_count.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    except OSError as error:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise BuildCountError(
            f"PMF-BLD-004: the build succeeded but the build number in {path.name} "
            f"could not be raised ({error}). Nothing in it was changed and the "
            f"program that was just built still carries the number it had. Check "
            f"whether the file is read-only, is open in another program that locks "
            f"it, or sits on a drive you cannot write to."
        ) from error


@contextlib.contextmanager
def _locked(lock: Path):
    """Hold build/BUILDS.lock for one whole read-modify-write-and-append.

    Two workers may run gates at the same time, and the bump is a read, an add
    and a write of the same file. Outside a lock the second reader would read
    56 while the first had not yet written 57, and one of the two builds would
    vanish - the lost update this lock exists to refuse.
    """
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, f"{os.getpid()} {time.time():.3f}\n".encode("ascii"))
            os.close(handle)
            break
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                continue
            if age > LOCK_STALE_SECONDS:
                # The holder died. Breaking it is safe because every writer
                # re-reads the board file after taking the lock.
                with contextlib.suppress(OSError):
                    lock.unlink()
                continue
            if time.monotonic() > deadline:
                raise BuildCountError(
                    f"PMF-BLD-004: the build succeeded but its build could not be "
                    f"counted: {lock} was held by another build for more than "
                    f"{LOCK_TIMEOUT_SECONDS:.0f} seconds. No board file was changed "
                    f"and no ledger line was written. Check whether another gate run "
                    f"is still going, and delete that lock file if nothing is."
                )
            time.sleep(0.005 + random.random() * 0.02)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


# -------------------------------------------------------------- identification
def board_for(source, target: str | None = None, root: Path = ROOT) -> Path | None:
    """Which REAL board file was this compile a build of? None if it was not one.

    A gate compiles the monitor from a temporary copy, so the path it hands the
    compiler is not the path that has to move. Identity is the board file's own
    name: each entry in BOARDS has its own unique board filename, and
    a file called that, compiled for that target, is that monitor - whether it
    sits in the tree or in a temporary export of it. Everything else a gate
    compiles is a fixture: a few lifted procedures around a probe, with no
    build number anywhere in it and nothing to count.
    """
    name = Path(source).name.lower()
    for board_target, relative in BOARDS.items():
        if name != relative.name.lower():
            continue
        if target is not None and target != board_target:
            # board.pi4 built for something other than pi4 is not the Pi 4
            # monitor; saying so beats counting a build of a different thing.
            continue
        return root / relative
    return None


def _artifact(image) -> Path:
    """The file the compiler actually produced for this build.

    `-o x.img` writes x.img for an ordinary build and x.img.asm when the caller
    asked for assembly with -S, and some gates want only the listing. Either is
    the product of one compile of the monitor; the ledger records which one it
    hashed so a line can be checked later.
    """
    path = Path(image)
    if path.is_file():
        return path
    listing = Path(str(path) + ".asm")
    if listing.is_file():
        return listing
    raise BuildCountError(
        f"PMF-BLD-004: a monitor build was reported as successful but neither "
        f"{path} nor {listing} exists, so there is no image to hash and the build "
        f"was not counted. No board file was changed. Check that the compile really "
        f"did write its output before the count was asked for."
    )


def _fingerprint(artifact: Path, digest: str) -> str:
    """This compile, not this image.

    Two builds of an unchanged tree produce identical bytes and are still two
    builds, so the image hash alone cannot be the identity. The artifact's path,
    size and modification time in nanoseconds make each compile distinct, and
    including the digest means a rewritten file with a preserved timestamp is
    still seen as different.
    """
    stat = artifact.stat()
    material = f"{artifact.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{digest}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# The compiler is a few megabytes and a gate can count several builds in one
# run, so its digest is remembered per (path, size, mtime). A rebuild changes
# the timestamp, so a compiler replaced mid-run is hashed again.
_COMPILER_DIGESTS: dict[tuple, str] = {}


def compiler_digest(compiler) -> str:
    """The sha256 of the executable that produced the image.

    A gate stages a COPY of the compiler beside this repository's board
    profiles, so the
    path varies from run to run and the bytes do not: the digest is what
    identifies the compiler, and it is the same for the copy and the original.
    """
    path = Path(compiler)
    if not path.is_file():
        raise BuildCountError(
            f"ANVIL-BLD-001: the build was made with {path}, which is not a file that "
            f"can be read, so the compiler that produced the image cannot be named and "
            f"the build was not recorded. No board file was changed. Pass the path of "
            f"the compiler that was actually run - a staged copy is fine, it hashes the "
            f"same."
        )
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _COMPILER_DIGESTS:
        _COMPILER_DIGESTS[key] = _sha256(path)
    return _COMPILER_DIGESTS[key]


def _caller() -> str:
    argv0 = Path(sys.argv[0] or "unknown").name
    return f"tools/{argv0}" if argv0.endswith(".py") else argv0


# ------------------------------------------------------------------- the count
def record_build(source, target: str, image, by: str | None = None,
                 compiler=None, root: Path = ROOT, ledger: Path | None = None) -> Result:
    """Count one successful build of a board file. Call it AFTER the compile.

    `source` is the path that was handed to the compiler - the real board file
    or a temporary copy of it. `target` is a key in BOARDS. `image` is what the
    compile produced. `by` names the tool doing the asking, and defaults to the
    script that is running. `compiler` is the executable that was run - required
    for a
    build that counts, because which compiler emitted an image is half of what
    identifies it, and this bench rebuilds the compiler while gates are running.

    A compile of anything that is not a board file answers counted=False and
    writes nothing: a fixture has no build number, and a ledger line for one
    would be a build of Anvil that never happened.

    A FAILED BUILD IS NEVER COUNTED, and this function cannot check that for
    you - it is called after a compile the caller has already proven succeeded.
    """
    root = Path(root)
    board = board_for(source, target, root)
    if board is None:
        return Result(counted=False, already=False, frozen=False, target=target,
                      board=None, value=None, new_value=None, sha256=None,
                      image=None, line=None,
                      message=f"{Path(source).name} is not a board file; nothing to count.")

    if compiler is None:
        raise BuildCountError(
            f"ANVIL-BLD-001: a build of {board.name} was reported but the compiler that "
            f"made it was not named, so the ledger line would say which build it is and "
            f"not what built it. Nothing was changed and no build was recorded. Pass "
            f"compiler=<the compiler that was run> to record_build; the compiler is rebuilt "
            f"on this bench while gates are running, so two images can share a build "
            f"number and not share a compiler."
        )
    artifact = _artifact(image)
    digest = _sha256(artifact)
    built_by = compiler_digest(compiler)
    fingerprint = _fingerprint(artifact, digest)
    who = by or _caller()
    ledger_path = Path(ledger) if ledger else root / LEDGER_NAME
    lock_path = root / LOCK_NAME

    with _locked(lock_path):
        if _already_counted(ledger_path, fingerprint):
            return Result(counted=False, already=True, frozen=False, target=target,
                          board=board, value=None, new_value=None, sha256=digest,
                          image=artifact, line=None,
                          message=(f"this compile ({fingerprint}) is already in "
                                   f"{ledger_path.name}; counted once, not twice."))

        data, sites = read_sites(board)
        number = next((site for site in sites if site.kind == "number"), None)
        if number is None:
            raise BuildCountError(
                f"PMF-BLD-006: {board} was built but carries no build-number marker, "
                f"so the build could not be counted and the image it produced cannot "
                f"say which build it is. No ledger line was written. Add a line like "
                f'"#ANVIL_BUILD = 1        ; pmf:build" to that board file - every '
                f"Anvil board file has one and CmdVersion prints it."
            )

        # The local date and time, matching what the compiler has always written
        # into these two siblings and what the board prints back. The ledger's
        # own timestamp is UTC, so two workers' lines sort against each other.
        now = time.localtime()
        stamp_date = time.strftime("%Y%m%d", now)
        stamp_time = time.strftime("%H%M%S", now)

        if not number.enabled:
            # `; pmf:build off` freezes the number for a release. The build
            # still happened, so it still goes in the ledger - the evidence is
            # the point, and a frozen stretch with no lines would read as a
            # stretch when nobody built anything.
            line = _ledger_line(target, number.value, stamp_date, stamp_time,
                                board, source, artifact, digest, built_by, who,
                                fingerprint, frozen=True, root=root)
            _append(ledger_path, line)
            return Result(counted=False, already=False, frozen=True, target=target,
                          board=board, value=number.value, new_value=number.value,
                          sha256=digest, image=artifact, line=line,
                          message=(f"the build number in {board.name} is switched off "
                                   f"(the marker says 'off'), so {number.name} stays at "
                                   f"{number.value}; the build was recorded."))

        if number.value >= MAX_BUILD:
            raise BuildCountError(
                f"PMF-BLD-005: the build number in {board.name} is {number.value}, "
                f"which is the largest whole number a constant in this language can "
                f"hold, so raising it by one would overflow and wrap to a negative "
                f"build number. The build succeeded and the file was not changed. Set "
                f"the build number back to a small value by editing that one line."
            )

        new_value = number.value + 1

        # All three lines are spliced in memory and written once. The number
        # first, then each sibling re-scanned against the buffer as it now
        # stands, because splicing a longer or shorter literal moves every
        # offset after it.
        data = _splice(data, number.value_start, number.value_len, str(new_value))
        for kind, text in (("date", stamp_date), ("time", stamp_time)):
            site = next((s for s in scan(data) if s.kind == kind and s.valid), None)
            if site is not None:
                data = _splice(data, site.value_start, site.value_len, text)

        _write_atomic(board, data)
        line = _ledger_line(target, new_value, stamp_date, stamp_time, board, source,
                            artifact, digest, built_by, who, fingerprint,
                            frozen=False, root=root)
        _append(ledger_path, line)

    return Result(counted=True, already=False, frozen=False, target=target,
                  board=board, value=number.value, new_value=new_value,
                  sha256=digest, image=artifact, line=line,
                  message=(f"{number.name} raised from {number.value} to {new_value} in "
                           f"{board.name} after a successful build; build date set to "
                           f"{stamp_date} and build time to {stamp_time}."))


# ------------------------------------------------------------------ the ledger
def _relative(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


def _ledger_line(target: str, build: int, stamp_date: str, stamp_time: str,
                 board: Path, source, artifact: Path, digest: str, built_by: str,
                 who: str, fingerprint: str, frozen: bool, root: Path) -> str:
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fields = [
        when,
        f"target={target}",
        f"build={build}",
        f"stamp={stamp_date}-{stamp_time}",
        f"board={_relative(board, root)}",
        f"source={_relative(source, root)}",
        f"image={_relative(artifact, root)}",
        f"sha256={digest}",
        f"compiler={built_by}",
        f"by={who}",
        f"compile={fingerprint}",
    ]
    if frozen:
        # Said out loud on the line itself: this build happened and the number
        # deliberately did not move.
        fields.append("frozen=yes")
    return " ".join(fields)


def _append(ledger: Path, line: str) -> None:
    """Append one line. Called only while the lock is held."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def _already_counted(ledger: Path, fingerprint: str) -> bool:
    if not ledger.is_file():
        return False
    needle = f"compile={fingerprint}"
    with ledger.open("r", encoding="utf-8", errors="replace") as handle:
        return any(needle in line for line in handle)


# --------------------------------------------------------------------- reading
def current(target: str, root: Path = ROOT) -> int:
    """The build number a board file holds right now - the NEXT build's number."""
    board = root / BOARDS[target]
    _, sites = read_sites(board)
    site = next((s for s in sites if s.kind == "number"), None)
    if site is None:
        raise BuildCountError(
            f"PMF-BLD-006: there is no build-number marker in {board}, so nothing "
            f"can say which build its image would be."
        )
    return site.value


def main() -> int:
    """`python tools/build_count.py` prints what each board file stands at."""
    for target in BOARDS:
        print(f"{target}: {current(target)}  ({BOARDS[target].as_posix()})")
    ledger = ROOT / LEDGER_NAME
    if ledger.is_file():
        lines = ledger.read_text(encoding="utf-8").splitlines()
        print(f"ledger: {LEDGER_NAME.as_posix()} - {len(lines)} recorded builds")
    else:
        print(f"ledger: {LEDGER_NAME.as_posix()} - not written yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
