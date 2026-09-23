#!/usr/bin/env python3
"""board_model_run.py - one command from a model run's manifest to its WAV.

    python tools/board_model_run.py <manifest.json> --console-ip <board>
        --lease-file <BOARD-SHARE.md> --lane "<lane name>"

WHY THIS EXISTS. A model run on the board used to be eight separate steps
driven by hand, one tool call each: upload the weights, upload
the noise, `coretest status`, board_run.py, `coretest status`, the readbacks,
the WAV conversion, the score. Every hand-off between two of them cost tens of
seconds to minutes, and the weights went up again every time even when the
same bytes were already in the board's memory. On 2026-09-16 a payload had
returned on the board's own screen and the WAV still did not exist minutes
later. The ruling: "write better tools that dont waste so much time".

So ONE invocation does all of it, with nothing in between:

  1. take the board lease        the live-holder callout and a ledger row in
                                 the shared-board file, re-read to confirm
  2. `version`, `map`, `coretest status`, `cache` (turned on if it was off)
  3. for each asset              `sha256sum <addr> <len>` of what is ALREADY
                                 in memory. Equal to the manifest's digest:
                                 "resident", no upload. Otherwise `net recv`,
                                 the file over TCP, and the board's own length
                                 and SHA-256 of the memory it landed in
  4. the payload                 `net recv` to its stage address, verified
  5. `deadman <s>`, `last run`, `boot mem <stage>`
  6. the moment it returns       `readback` of the regions a WAV is made
                                 from, in the SAME console connection, with
                                 no pause; `sha256sum` on the board where the
                                 manifest asks for it
  7. the WAVs, then ONE line     "WAV ready: <paths>"
  8. `readback` of every other region, `deadman off`, `coretest status`
  9. put the cache back, release the lease with a ledger row
 10. the compare command, if the manifest has one - after the WAV line,
     never before it, and never while holding the board

The lease is released in a `finally`: on success, on a failure, and after an
exception or Ctrl-C. Its row says what the board was left doing.

THE CONSOLE CODE IS board_run.py's, imported: NetConsole (with its keepalive),
the echo-anchored command reader, the upload stream, the return and
exception parsers and `ask_after_silence`. The bytes off the board come from
anvil_readback.read_range. Nothing is re-implemented here and nothing runs as
a subprocess with a connection of its own.

THE MANIFEST, a JSON object. Paths are relative to "base"; "base" is relative
to the manifest's own folder, and --base replaces it.

    {
      "format":  "anvil-board-model-run 1",
      "name":    "kitten-rosie",
      "text":    "what the model is asked to say (for the record, optional)",
      "base":    "kitten-nano-0.8",
      "out":     "pi4-rosie/board-model-run",
      "payload": {"file": "pi4-rosie/kitten-rosie.img.pmf",
                  "sha256": "<optional: refuse any other file>",
                  "stage": "0x03000000",
                  "expect_x0": "0",
                  "timeout_seconds": 900},
      "deadman_seconds": 15,
      "assets":  [{"name": "weights", "file": "pi4/kitten.pmw",
                   "address": "0x40000000", "sha256": "<64 hex>"}],
      "results": [{"name": "wave", "address": "0x57000000", "bytes": 2382400,
                   "board_sha256": true,
                   "sha256": "<optional: the digest it must have>"}],
      "post":    {"wav": [{"from": "wave", "rate": 24000,
                           "file": "kitten-rosie.wav"}],
                  "compare": ["{python}", "score.py", "--wave", "{result.wave}"]}
    }

Addresses and sizes are numbers or strings ("0x40000000", "$40000000",
"2382400"). "stage" may be left out, and the board's `map` then decides.
"compare" is an argument list; `{python}` is this interpreter, `{base}` the
base folder, `{out}` the run folder, `{result.NAME}` a region's file and
`{wav.NAME}` the WAV made from region NAME. Unknown keys are refused, so a
misspelt key cannot silently mean "not asked for".

EACH RUN GETS ITS OWN FOLDER, <out>/<YYYYMMDD-HHMMSS>, holding every region as
<name>.bin (or .f32 when a WAV is made from it), the WAVs, <name>.json (the
run record, rewritten after every step, with the timings) and <name>.txt (the
console transcript). A record without a `finished` field is one whose process
was killed at the `stage` it names.

    --console-ip A    the board's UDP console (required)
    --console-port N  5555 unless somebody has changed it
    --board-ip A      where uploads are streamed to. Defaults to --console-ip
    --port N          the board's one-shot TCP listener port. Default 5001
    --base DIR        replaces the manifest's "base"
    --out DIR         replaces the manifest's "out"
    --lease-file F    the shared-board file (BOARD-SHARE.md) to take the lease in
    --lane NAME       who is taking it, as the ledger should name them
    --no-lease        a board nobody else uses; no lease file is read or written
    --lease-wait S    how long to wait for the board to be FREE. Default 3600
    --ask-seconds S   after a missing return line, how long to wait for the
                      board to answer before calling the payload still
                      running. Default 60

THE EXIT CODES

    0   the payload returned what was expected, every region verified, the
        WAVs are on disk and the compare command (if any) passed
    1   the run started and failed; the run record says where
    2   nothing was sent to the board: a bad manifest, a file that does not
        match it, no lease, or no prompt

>>  NEVER WRAP THIS TOOL IN AN OUTER `timeout`, AND NEVER PIPE IT THROUGH
>>  `tail` WHILE IT RUNS. Its bounds are its own and each one ends in a
    sentence. An outer kill loses the record's ending AND leaves the lease
    held; a pager shows nothing until the end. docs/BOARD_RUN.md says why.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from array import array
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_run as br                                    # noqa: E402
from anvil_readback import ReadbackError, read_range      # noqa: E402

FORMAT = "anvil-board-model-run 1"
DEFAULT_LEASE_WAIT = 3600.0
# How often the lease file is looked at while somebody else holds the board.
# It is a file on a disk, and a file has no event to wait on that works the
# same on every platform and through a synced vault, so this is a poll - of
# the file's size and time, which costs nothing.
LEASE_POLL_SECONDS = 1.0
# THE SECOND LOOK AFTER WRITING A LEASE. Two lanes that both read FREE and
# both write land within the time it takes an editor or a sync to save; the
# first re-read happens at once and this one catches a write that was already
# on its way.
LEASE_CONFIRM_SECONDS = 2.0
# SHA-256 on this part is 4,041 KB/s with the caches on (measured, see
# pi4_upload.py). The bound below allows a quarter of that plus half a minute;
# the caches are always on by the time a digest is asked for.
HASH_FLOOR_BYTES_PER_SECOND = 1_000_000

CACHE_RE = re.compile(r"(?m)^The D-cache and MMU are (ON|OFF)\b")
SHA256SUM_RE = re.compile(r"The sha256sum is ([0-9a-f]{64})")
CORETEST_RE = re.compile(
    r"coretest started=(\d+) stopped=(\d+) runs=(\d+) nonce=(\d+) error=(\d+)")
BUILD_RE = re.compile(r"build (\d+)")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """The manifest cannot be run as written. Always a full sentence."""


class RunFailed(RuntimeError):
    """A board step failed. Always a full sentence; nothing is retried."""


def say(clock: float, text: str) -> None:
    print(f"[{time.monotonic() - clock:7.1f} s] {text}")


# =====================================================================
#  THE MANIFEST
# =====================================================================
def number(value, what: str) -> int:
    if isinstance(value, bool):
        raise ManifestError(f"{what} is true or false, and it has to be a number.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            if text.startswith("$"):
                return int(text[1:], 16)
            return int(text, 0)
        except ValueError:
            pass
    raise ManifestError(
        f"{what} is {value!r}, which is not a number. Write it as a number, or as "
        "a string like \"0x40000000\", \"$40000000\" or \"2382400\".")


def only_keys(obj: dict, allowed: set[str], required: set[str], where: str) -> None:
    if not isinstance(obj, dict):
        raise ManifestError(f"{where} has to be a JSON object, and it is not.")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ManifestError(
            f"{where} has the key(s) {', '.join(unknown)}, which this tool does not "
            f"know. The keys it reads there are {', '.join(sorted(allowed))}. A "
            "misspelt key is refused rather than ignored, because an ignored key "
            "reads as \"not asked for\".")
    missing = sorted(required - set(obj))
    if missing:
        raise ManifestError(f"{where} has no {', '.join(missing)}, and it needs one.")


def digest_of(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def load_manifest(path: Path, base_override: str | None,
                  out_override: str | None) -> dict:
    """Read, check and resolve a manifest. Nothing here touches a board."""
    if not path.is_file():
        raise ManifestError(f"there is no manifest at {path}.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path} is not valid JSON: {error}.") from error
    only_keys(raw, {"format", "name", "text", "base", "out", "payload",
                    "deadman_seconds", "assets", "results", "post"},
              {"format", "name", "payload", "results"}, "the manifest")
    if raw["format"] != FORMAT:
        raise ManifestError(
            f"the manifest says its format is {raw['format']!r}, and this tool reads "
            f"{FORMAT!r}. Check that the manifest was written for this tool.")
    name = str(raw["name"])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ManifestError(
            f"the manifest's name {name!r} is used as a file name, so it may hold "
            "only letters, digits, dot, underscore and hyphen.")

    here = path.resolve().parent
    base = Path(base_override).resolve() if base_override else (here / raw.get("base", ".")).resolve()
    if not base.is_dir():
        raise ManifestError(
            f"the base folder {base} does not exist. It is the manifest's \"base\" "
            "resolved against the manifest's own folder; give --base to point at "
            "where the files are.")
    out = Path(out_override).resolve() if out_override else (base / raw.get("out", "board-model-run")).resolve()

    payload = raw["payload"]
    only_keys(payload, {"file", "sha256", "stage", "expect_x0", "timeout_seconds"},
              {"file"}, "the manifest's payload")
    payload_path = base / payload["file"]
    if not payload_path.is_file():
        raise ManifestError(f"the payload {payload_path} does not exist.")
    payload_data = payload_path.read_bytes()
    if not payload_data:
        raise ManifestError(f"the payload {payload_path} is empty.")
    payload_sha = hashlib.sha256(payload_data).hexdigest()
    if "sha256" in payload and payload["sha256"].lower() != payload_sha:
        raise ManifestError(
            f"the payload {payload_path} has sha256 {payload_sha}, and the manifest "
            f"says it must be {payload['sha256'].lower()}. It was rebuilt since the "
            "manifest was written, or this is the wrong file.")
    expect_x0 = number(payload.get("expect_x0", 0), "the payload's expect_x0")
    if not 0 <= expect_x0 < 1 << 64:
        raise ManifestError("the payload's expect_x0 has to fit in 64 unsigned bits.")
    timeout = float(payload.get("timeout_seconds", br.DEFAULT_TIMEOUT))
    if timeout <= 0:
        raise ManifestError("the payload's timeout_seconds has to be more than zero.")

    deadman = number(raw.get("deadman_seconds", 0), "deadman_seconds")
    if deadman and not 1 <= deadman <= br.MAX_DEADMAN_SECONDS:
        raise ManifestError(
            f"deadman_seconds is {deadman}, and the board's deadman can be armed for "
            f"1 to {br.MAX_DEADMAN_SECONDS} whole seconds: its counter is 20 bits at "
            "65536 ticks a second. Use 0 for no deadman.")

    assets = []
    names: set[str] = set()
    for index, asset in enumerate(raw.get("assets", [])):
        where = f"asset {index + 1}"
        only_keys(asset, {"name", "file", "address", "sha256"},
                  {"name", "file", "address", "sha256"}, where)
        file = base / asset["file"]
        if not file.is_file():
            raise ManifestError(f"{where} ({asset['name']}) names {file}, which does not exist.")
        want = asset["sha256"].lower()
        if not HEX64_RE.match(want):
            raise ManifestError(f"{where} ({asset['name']}) has a sha256 that is not 64 hex digits.")
        have = digest_of(file)
        if have != want:
            raise ManifestError(
                f"{where} ({asset['name']}): {file} has sha256 {have}, and the manifest "
                f"says {want}. Either the file changed or the manifest is stale; this "
                "tool will not decide which, and nothing was sent.")
        if asset["name"] in names:
            raise ManifestError(f"two assets are called {asset['name']!r}.")
        names.add(asset["name"])
        assets.append({"name": asset["name"], "path": file,
                       "address": number(asset["address"], f"{where}'s address"),
                       "bytes": file.stat().st_size, "sha256": want})

    results = []
    names = set()
    for index, region in enumerate(raw["results"]):
        where = f"result region {index + 1}"
        only_keys(region, {"name", "address", "bytes", "board_sha256", "sha256"},
                  {"name", "address", "bytes"}, where)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(region["name"])):
            raise ManifestError(
                f"{where}'s name {region['name']!r} is used as a file name and a "
                "placeholder, so it may hold only letters, digits, underscore and hyphen.")
        if region["name"] in names:
            raise ManifestError(f"two result regions are called {region['name']!r}.")
        names.add(region["name"])
        size = number(region["bytes"], f"{where}'s bytes")
        if size <= 0:
            raise ManifestError(f"{where} ({region['name']}) reads {size} bytes; give at least one.")
        expected = region.get("sha256")
        if expected is not None and not HEX64_RE.match(expected.lower()):
            raise ManifestError(f"{where} ({region['name']}) has a sha256 that is not 64 hex digits.")
        results.append({"name": region["name"],
                        "address": number(region["address"], f"{where}'s address"),
                        "bytes": size,
                        "board_sha256": bool(region.get("board_sha256", False)),
                        "sha256": expected.lower() if expected else None})
    if not results:
        raise ManifestError("the manifest reads back no result regions, so a run would produce nothing.")

    post = raw.get("post", {})
    only_keys(post, {"wav", "compare"}, set(), "the manifest's post")
    wavs = []
    for index, wav in enumerate(post.get("wav", [])):
        where = f"post wav {index + 1}"
        only_keys(wav, {"from", "rate", "file"}, {"from", "rate", "file"}, where)
        source = next((r for r in results if r["name"] == wav["from"]), None)
        if source is None:
            raise ManifestError(f"{where} converts {wav['from']!r}, and no result region has that name.")
        if source["bytes"] % 4:
            raise ManifestError(
                f"{where} converts {wav['from']!r}, which is {source['bytes']} bytes - not a "
                "whole number of FLOAT32 samples.")
        rate = number(wav["rate"], f"{where}'s rate")
        if not 1 <= rate <= 768000:
            raise ManifestError(f"{where}'s rate {rate} is not a sample rate.")
        if Path(wav["file"]).name != wav["file"]:
            raise ManifestError(f"{where}'s file {wav['file']!r} has to be a bare file name; it is written into the run folder.")
        wavs.append({"from": wav["from"], "rate": rate, "file": wav["file"]})
    compare = post.get("compare")
    if compare is not None and (not isinstance(compare, list) or not compare
                                or not all(isinstance(item, str) for item in compare)):
        raise ManifestError("post compare has to be a non-empty list of strings: the command and its arguments.")

    return {
        "path": path.resolve(), "name": name, "text": raw.get("text", ""),
        "base": base, "out": out,
        "payload": {"path": payload_path, "data": payload_data, "sha256": payload_sha,
                    "stage": (number(payload["stage"], "the payload's stage")
                              if "stage" in payload else None),
                    "expect_x0": expect_x0, "timeout": timeout},
        "deadman": deadman, "assets": assets, "results": results,
        "wavs": wavs, "compare": compare,
    }


# =====================================================================
#  THE LEASE
# =====================================================================
LEDGER_HEADING = "## Transfer ledger"
CALLOUT_HEAD = "> [!important] Live holder"


def cell(text: str) -> str:
    """A table cell: no pipes, no line breaks."""
    return " ".join(str(text).replace("|", "/").split())


class LeaseError(RuntimeError):
    """The lease could not be taken. Nothing was sent to the board."""


class BoardLease:
    """The shared-board file's live-holder callout and transfer ledger.

    THE PROTOCOL IS THE FILE'S OWN (Raspberry Pi 4/BOARD-SHARE.md): the board
    is free when the ledger's last row hands it to FREE; a lane takes it by
    rewriting the callout and appending a row, then re-reads the file to
    confirm the row it wrote is still the last one; it releases with a row
    the moment its sequence ends. This class does exactly that, and nothing
    else in the file is touched.
    """

    def __init__(self, path: Path, lane: str, run_id: str):
        self.path = path
        self.lane = lane
        self.run_id = run_id
        self.take_row: str | None = None
        self.held = False

    # ---- reading ----------------------------------------------------------
    def read(self) -> str:
        # newline="" so a CRLF file stays CRLF when it is written back.
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def stamp(self) -> tuple[int, int]:
        info = self.path.stat()
        return info.st_size, info.st_mtime_ns

    @staticmethod
    def rows(text: str) -> list[tuple[int, list[str]]]:
        lines = text.split("\n")
        try:
            start = next(i for i, line in enumerate(lines) if line.strip() == LEDGER_HEADING)
        except StopIteration:
            raise LeaseError(
                "the lease file has no \"## Transfer ledger\" heading, so there is no "
                "ledger to read the board's holder from. Check that --lease-file is the "
                "shared-board file.") from None
        found = []
        for index in range(start + 1, len(lines)):
            line = lines[index].rstrip("\r")
            if line.startswith("## "):
                break
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cells = [piece.strip() for piece in line.strip().strip("|").split("|")]
            if cells and cells[0].lower().startswith("time"):
                continue
            found.append((index, cells))
        if not found:
            raise LeaseError("the lease file's ledger has no rows, so its holder cannot be read.")
        return found

    @staticmethod
    def holder(text: str) -> str | None:
        """None when the board is FREE, else who the last row hands it to."""
        _index, cells = BoardLease.rows(text)[-1]
        to = cells[2] if len(cells) > 2 else ""
        if to.replace("*", "").strip().upper().startswith("FREE"):
            return None
        return to.replace("*", "").strip() or "somebody the last row does not name"

    # ---- writing ----------------------------------------------------------
    @staticmethod
    def newline(text: str) -> str:
        return "\r\n" if "\r\n" in text else "\n"

    def with_row(self, text: str, row: str) -> str:
        nl = self.newline(text)
        lines = text.split(nl)
        last_index, _cells = self.rows(text.replace("\r\n", "\n"))[-1]
        lines.insert(last_index + 1, row)
        return nl.join(lines)

    def with_callout(self, text: str, body: str) -> str:
        nl = self.newline(text)
        lines = text.split(nl)
        try:
            head = next(i for i, line in enumerate(lines) if line.startswith(CALLOUT_HEAD))
        except StopIteration:
            raise LeaseError(
                "the lease file has no \"> [!important] Live holder\" callout to write "
                "the holder into. Check that --lease-file is the shared-board file.") from None
        end = head + 1
        while end < len(lines) and lines[end].startswith(">"):
            end += 1
        return nl.join(lines[:head + 1] + ["> " + body] + lines[end:])

    def write(self, text: str) -> None:
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    @staticmethod
    def now() -> str:
        return time.strftime("%Y-%m-%d %H:%M")

    # ---- the two operations -------------------------------------------------
    def take(self, plan: str, clock: float, bound: float) -> float:
        """Wait for FREE, take the lease, confirm it. Returns seconds waited."""
        began = time.monotonic()
        last_seen = None
        last_note = began
        while True:
            text = self.read()
            flat = text.replace("\r\n", "\n")
            holder = self.holder(flat)
            if holder is not None:
                if holder != last_seen:
                    say(clock, f"lease: the board is held by {holder}; waiting for its release row.")
                    last_seen = holder
                    last_note = time.monotonic()
                elif time.monotonic() - last_note >= 60.0:
                    say(clock, f"lease: still held by {holder} "
                               f"({time.monotonic() - began:.0f} s so far).")
                    last_note = time.monotonic()
                if time.monotonic() - began >= bound:
                    raise LeaseError(
                        f"the board was still held by {holder} after {bound:.0f} s of "
                        "waiting (--lease-wait), so this run did not take it and sent "
                        "nothing. Run again when that lane has released it.")
                stamp = self.stamp()
                while self.stamp() == stamp and time.monotonic() - began < bound:
                    time.sleep(LEASE_POLL_SECONDS)
                continue

            hhmm = self.now()
            self.take_row = (
                f"| {hhmm} | FREE | **{cell(self.lane)}** | {cell('as the previous row left it - confirmed by this run' + chr(39) + 's `version` before anything else is sent')} "
                f"| {cell(plan)} (tools/board_model_run.py run {self.run_id}) |")
            callout = (f"**{cell(self.lane)} - taken {hhmm[-5:]} from FREE for ONE "
                       f"sequence (tools/board_model_run.py run {self.run_id}):** {cell(plan)}")
            new = self.with_callout(self.with_row(text, self.take_row), callout)
            if self.read() != text:
                continue                 # somebody wrote between the read and now
            self.write(new)
            if self.confirmed():
                self.held = True
                waited = time.monotonic() - began
                say(clock, f"lease: taken ({waited:.1f} s waiting), confirmed by two re-reads.")
                return waited
            # ANOTHER LEASE LANDED. Say so in the ledger if this row is still in
            # it, so nobody reads it as a live holder, and wait again.
            text = self.read()
            if self.take_row in text:
                withdraw = (f"| {self.now()} | **{cell(self.lane)}** | unchanged - the other lease stands "
                            f"| not contacted by this run | NONE. COLLISION, WITHDRAWN: another lease landed "
                            f"within seconds of this one (run {self.run_id}); nothing was sent to the board |")
                self.write(self.with_row(text, withdraw))
            say(clock, "lease: another lease landed at the same moment, so this run "
                       "withdrew its row and sent nothing; waiting for that lease's release row.")
            self.take_row = None
            last_seen = None

    def confirmed(self) -> bool:
        for delay in (0.0, LEASE_CONFIRM_SECONDS):
            if delay:
                time.sleep(delay)
            text = self.read().replace("\r\n", "\n")
            last_index, _cells = self.rows(text)[-1]
            if text.split("\n")[last_index] != self.take_row:
                return False
            callout = next((line for line in text.split("\n") if line.startswith("> **")
                            and f"run {self.run_id}" in line), None)
            if callout is None:
                return False
        return True

    def release(self, state: str, work: str, clock: float) -> None:
        if not self.held:
            return
        row = f"| {self.now()} | **{cell(self.lane)}** | FREE | {cell(state)} | {cell(work)} |"
        for _attempt in range(3):
            text = self.read()
            flat = text.replace("\r\n", "\n")
            mine = any(line.startswith("> **") and f"run {self.run_id}" in line
                       for line in flat.split("\n"))
            new = self.with_row(text, row)
            if mine:
                new = self.with_callout(
                    new, f"**FREE** - released {self.now()[-5:]} by {cell(self.lane)} "
                         f"(tools/board_model_run.py run {self.run_id}). {cell(state)}")
            self.write(new)
            if row in self.read():
                self.held = False
                say(clock, "lease: released with a ledger row.")
                return
        raise LeaseError(
            "the release row could not be kept in the lease file after three writes - "
            "something else is rewriting it. The board is NOT marked free; append the "
            f"release row by hand: {row}")


# =====================================================================
#  THE BOARD
# =====================================================================
def command(console: br.NetConsole, line: str, seconds: float = 10.0) -> str:
    """One monitor command through its prompt; a refusal becomes RunFailed."""
    reply = console.command(line, seconds)
    refused = br.board_refusal(reply, line)
    if refused:
        raise RunFailed(f"the board refused `{line}`, and said:\n{br.indent(refused)}")
    return reply


def board_sha256(console: br.NetConsole, address: int, size: int) -> tuple[str, float]:
    line = f"sha256sum {address:X} {size:X}"
    began = time.monotonic()
    reply = command(console, line, 30.0 + size / HASH_FLOOR_BYTES_PER_SECOND)
    found = SHA256SUM_RE.search(reply)
    if not found:
        raise RunFailed(
            f"the board answered `{line}` without a digest, so nothing about that range "
            f"is known. It said:\n{br.indent(br.command_body(reply, line))}")
    return found.group(1), time.monotonic() - began


def upload(console: br.NetConsole, board_ip: str, port: int, address: int,
           data: bytes, want: str, label: str) -> dict:
    """`net recv`, the bytes over TCP, and the board's verdict on its memory."""
    line = f"net recv {port} {address:X}"
    console.settle(quiet=0.3, cap=3.0)
    console.send(line)
    listen, why = console.read_until_or_prompt(line, ["for ONE connection"], 15)
    if why != "needle":
        reason = br.refusal_reason(listen, line)
        raise RunFailed(
            f"the board did not arm a listener for {label}, so nothing was sent. " +
            (f"It said:\n{br.indent(reason)}" if reason else
             "It gave no reason within 15 s; the reply is in the transcript."))
    began = time.monotonic()
    br.stream_file(board_ip, port, data)
    verdict, _why = console.read_until_or_prompt(
        line, [br.RECV_SHA_RE], 30.0 + len(data) / 40000.0, seen=listen)
    got_len, got_ms, got_sha = br.parse_recv_verdict(listen + verdict)
    seconds = time.monotonic() - began
    if got_len is None or got_sha is None:
        raise RunFailed(
            f"the board never printed a length and a digest for {label}, so that "
            "upload has no verdict at all - which is not the same as a good one.")
    if got_len != len(data) or got_sha != want:
        raise RunFailed(
            f"THE UPLOAD OF {label} DID NOT VERIFY: this host sent {len(data)} bytes with "
            f"sha256 {want} and the board holds {got_len} bytes with sha256 {got_sha}.")
    return {"bytes": got_len, "board_ms": got_ms, "seconds": round(seconds, 3)}


def cache_on(console: br.NetConsole) -> bool:
    """Caches on for the digests. Returns True if this call turned them on."""
    states = CACHE_RE.findall(command(console, "cache", 10))
    if len(states) != 1:
        raise RunFailed("the board did not report one unambiguous cache state, so no digest was asked for.")
    if states[0] == "ON":
        return False
    command(console, "cache on", 15)
    if CACHE_RE.findall(command(console, "cache", 10)) != ["ON"]:
        raise RunFailed("the board's caches are still OFF after `cache on`; nothing was uploaded.")
    return True


def coretest(console: br.NetConsole) -> dict:
    reply = command(console, "coretest status", 10)
    found = CORETEST_RE.search(reply)
    line = next((l for l in reply.replace("\r", "").split("\n") if l.startswith("coretest started")), "")
    if not found:
        return {"line": br.command_body(reply, "coretest status")}
    started, stopped, runs, nonce, error = (int(v) for v in found.groups())
    return {"line": line.strip(), "started": started, "stopped": stopped,
            "runs": runs, "nonce": nonce, "error": error}


# =====================================================================
#  THE OUTPUTS
# =====================================================================
def write_wav(raw: bytes, rate: int, path: Path) -> dict:
    """16-bit PCM mono. Clamped to [-1, +1], x32767, rounded half away from
    zero - the same conversion as the ONNX repository's f32_to_wav.py, with
    every clamped sample counted."""
    samples = array("f")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    bad = sum(1 for v in samples if v != v or v in (float("inf"), float("-inf")))
    if bad:
        raise RunFailed(
            f"{bad} of the {len(samples)} samples read back are NaN or infinite, so no WAV "
            f"was written to {path}. The payload's output is not a clean waveform.")
    clamped = sum(1 for v in samples if v > 1.0 or v < -1.0)
    pcm = array("h", [32767 if v >= 1.0 else -32767 if v <= -1.0 else
                      int(v * 32767.0 + 0.5) if v >= 0.0 else int(v * 32767.0 - 0.5)
                      for v in samples])
    if sys.byteorder != "little":
        pcm.byteswap()
    data = pcm.tobytes()
    fmt = (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + rate.to_bytes(4, "little") + \
        (rate * 2).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    riff = (b"RIFF" + (4 + 8 + len(fmt) + 8 + len(data)).to_bytes(4, "little") + b"WAVE" +
            b"fmt " + len(fmt).to_bytes(4, "little") + fmt +
            b"data" + len(data).to_bytes(4, "little") + data)
    path.write_bytes(riff)
    return {"file": str(path), "bytes": len(riff), "sha256": hashlib.sha256(riff).hexdigest(),
            "samples": len(samples), "rate": rate, "seconds": len(samples) / rate,
            "clamped": clamped}


# =====================================================================
#  THE RUN
# =====================================================================
def run(options: argparse.Namespace, console_factory=None) -> int:
    clock = time.monotonic()
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(line_buffering=True)
        except (ValueError, OSError):
            pass

    try:
        manifest = load_manifest(Path(options.manifest), options.base, options.out)
    except ManifestError as error:
        print(f"!! the manifest cannot be run: {error} Nothing was sent to the board.")
        return 2
    name = manifest["name"]
    payload = manifest["payload"]
    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = manifest["out"] / run_id
    board_ip = options.board_ip or options.console_ip
    say(clock, f"{name}: manifest {manifest['path']}")
    say(clock, f"  payload {payload['path'].name}, {len(payload['data'])} bytes, sha256 {payload['sha256']}")
    for asset in manifest["assets"]:
        say(clock, f"  asset {asset['name']}: {asset['bytes']} bytes -> {asset['address']:08X}, sha256 equal to the manifest")

    lease = None
    if not options.no_lease:
        if not options.lease_file or not options.lane:
            print("!! a shared board needs --lease-file and --lane, so this run can take the "
                  "lease itself; give --no-lease only for a board nobody else uses. Nothing "
                  "was sent to the board.")
            return 2
        lease_path = Path(options.lease_file)
        if not lease_path.is_file():
            print(f"!! there is no lease file at {lease_path}. Nothing was sent to the board.")
            return 2
        lease = BoardLease(lease_path, options.lane, run_id)

    plan = (f"RAM-only model run `{name}`: `version`, `coretest status`, a `sha256sum` resident check of "
            f"{len(manifest['assets'])} asset(s) with an upload only of those not resident, one returning "
            f"payload `{payload['path'].name}` ({len(payload['data'])} B) staged at "
            f"{'$%08X' % payload['stage'] if payload['stage'] is not None else 'the map address'}"
            f"{', deadman %d s' % manifest['deadman'] if manifest['deadman'] else ''}, "
            f"`readback` of {len(manifest['results'])} region(s), `deadman off`, `coretest status`. "
            "No reset, no flash, NO STICK WRITE")

    timings: dict = {"assets": {}, "regions": {}}
    record: dict = {
        "tool": "tools/board_model_run.py", "manifest": str(manifest["path"]),
        "name": name, "run_id": run_id, "text": manifest["text"],
        "console": f"{options.console_ip}:{options.console_port}",
        "payload": {"file": str(payload["path"]), "bytes": len(payload["data"]),
                    "sha256": payload["sha256"], "expect_x0": f"{payload['expect_x0']:016X}"},
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": "starting",
        "timings": timings, "assets": {}, "regions": {}, "wavs": [],
    }
    failures: list[str] = []
    journal = None
    console = None
    turned_cache_on = False
    deadman_armed = False
    deadman_off = False
    board_busy = False          # the payload may still hold the processor
    answered = False            # the board's prompt came back at least once
    returned_at = None
    wav_line_at = None
    exit_code = 1
    uploads = resident = 0

    try:
        if lease is not None:
            try:
                timings["lease_wait_seconds"] = round(lease.take(plan, clock, options.lease_wait), 3)
            except LeaseError as error:
                print(f"!! {error}")
                return 2

        started = time.monotonic()
        console = (console_factory or br.NetConsole)(options.console_ip, options.console_port)
        if not console.at_prompt(timeout=30.0):
            print(f"!! no Anvil prompt answered on {console.name} within 30 s, so nothing was "
                  "sent. Is the board powered, on this network, and is this its console?")
            exit_code = 2
            return 2
        answered = True
        out_dir.mkdir(parents=True, exist_ok=True)
        journal = br.RunJournal(out_dir, name, record, console)

        version = command(console, "version", 10)
        record["version"] = (br.command_body(version, "version").splitlines() or [""])[0]
        board_map = command(console, "map", 12)
        stage = payload["stage"] if payload["stage"] is not None else br.parse_stage_address(board_map)
        extent = br.parse_image_extent(board_map)
        if stage is None:
            raise RunFailed("the board's `map` gave no staging address and the manifest has no payload stage.")
        if extent:
            regions = [("the payload", stage, len(payload["data"]))] + \
                      [(f"asset {a['name']}", a["address"], a["bytes"]) for a in manifest["assets"]]
            for label, lo, size in regions:
                if lo <= extent[1] and lo + size - 1 >= extent[0]:
                    raise RunFailed(
                        f"{label} at {lo:08X} ({size} bytes) would land on the running monitor "
                        f"({extent[0]:08X}..{extent[1]:08X}); nothing was sent.")
        record["stage_addr"] = f"{stage:08X}"
        record["coretest_before"] = coretest(console)
        say(clock, f"board: {record['version']}; {record['coretest_before'].get('line', '')}")
        timings["connect_seconds"] = round(time.monotonic() - started, 3)
        turned_cache_on = cache_on(console)
        record["cache_turned_on"] = turned_cache_on
        journal.step("board identified")

        # ---- the assets: resident, or uploaded -------------------------------
        for asset in manifest["assets"]:
            label = f"asset {asset['name']}"
            say(clock, f"{label}: asking the board for sha256sum {asset['address']:X} {asset['bytes']:X}")
            have, check_seconds = board_sha256(console, asset["address"], asset["bytes"])
            entry = {"address": f"{asset['address']:08X}", "bytes": asset["bytes"],
                     "sha256": asset["sha256"], "board_before": have,
                     "check_seconds": round(check_seconds, 3)}
            if have == asset["sha256"]:
                entry["action"] = "resident"
                resident += 1
                say(clock, f"{label}: resident - the board's digest of {asset['address']:08X} equals the "
                           f"manifest's ({check_seconds:.1f} s), no upload")
            else:
                say(clock, f"{label}: not resident ({check_seconds:.1f} s); uploading {asset['bytes']} bytes")
                data = asset["path"].read_bytes()
                if hashlib.sha256(data).hexdigest() != asset["sha256"]:
                    raise RunFailed(f"{asset['path']} changed on disk during this run; nothing more was sent.")
                result = upload(console, board_ip, options.port, asset["address"], data,
                                asset["sha256"], label)
                entry.update(action="uploaded", upload=result)
                uploads += 1
                say(clock, f"{label}: uploaded and verified by the board's sha256 in {result['seconds']:.1f} s")
            record["assets"][asset["name"]] = entry
            timings["assets"][asset["name"]] = {
                "action": entry["action"], "check_seconds": entry["check_seconds"],
                "upload_seconds": entry.get("upload", {}).get("seconds", 0.0)}
            journal.step(f"asset {asset['name']}")

        # ---- the payload -------------------------------------------------------
        began = time.monotonic()
        result = upload(console, board_ip, options.port, stage, payload["data"],
                        payload["sha256"], "the payload")
        timings["payload_upload_seconds"] = round(time.monotonic() - began, 3)
        say(clock, f"payload: {len(payload['data'])} bytes at {stage:08X}, verified ({result['seconds']:.2f} s)")
        journal.step("payload verified")

        if manifest["deadman"]:
            command(console, f"deadman {manifest['deadman']}", 10)
            deadman_armed = True
        before_run = br.parse_last_run(console.command("last run", 10))
        record["last_run_before"] = before_run

        line = f"boot mem {stage:X}"
        console.settle(quiet=0.3, cap=3.0)
        datagrams = len(console.accepted_datagrams)
        journal.step("boot")
        say(clock, f"run: `{line}`" + (f", deadman {manifest['deadman']} s" if deadman_armed else "") +
            f"; waiting up to {payload['timeout']:.0f} s for the return line")
        board_busy = True
        booted = time.monotonic()
        console.send(line)
        body, why = console.read_until_or_prompt(line, [br.RETURN_RE, br.FATAL_MARKER], payload["timeout"])
        timings["run_seconds"] = round(time.monotonic() - booted, 3)
        x0 = br.parse_return_x0(body)
        if why == "prompt" and not br.has_fatal_marker(body):
            board_busy = False
            reason = br.refusal_reason(body, line)
            raise RunFailed("the board REFUSED TO ENTER THE PAYLOAD and nothing ran. " +
                            (f"It said:\n{br.indent(reason)}" if reason else "It gave no reason."))
        if br.has_fatal_marker(body):
            br.capture_fatal_exception(console, body, datagrams, manifest["deadman"], record, failures)
            board_busy = False
            journal.step("processor exception")
            raise RunFailed("the payload stopped at a processor exception; the record holds its fields.")
        if x0 is None:
            journal.step("asking the board")
            ask = SimpleNamespace(timeout=payload["timeout"], ask_seconds=options.ask_seconds,
                                  deadman=manifest["deadman"], no_shot=True)
            outcome, x0 = br.ask_after_silence(console, ask, record, failures, before_run, 0)
            if x0 is None:
                board_busy = outcome in ("still running", "unresolved silence")
                journal.step(outcome)
                raise RunFailed(f"the payload's outcome is: {outcome}.")
            record["return_line_lost"] = True
            timings["run_seconds"] = round(time.monotonic() - booted, 3)
        board_busy = False
        returned_at = time.monotonic()
        record["x0"] = f"{x0:016X}"
        if x0 != payload["expect_x0"]:
            failures.append(f"the payload returned x0 = {x0:016X}, and the manifest expects "
                            f"{payload['expect_x0']:016X}. The regions are still read back as evidence; "
                            "no WAV is made from a failed run.")
        say(clock, f"returned: x0 = {x0:016X} after {timings['run_seconds']:.1f} s; reading back now")
        journal.step("return")

        # ---- readback, at once, same connection ------------------------------
        # THE REGIONS A WAV IS MADE FROM COME FIRST, and the WAV and its line
        # follow the moment they are verified; the other regions, `deadman off`
        # and `coretest status` come after the line. The deadman stays armed
        # for that second or two at the prompt, where the monitor services it.
        raw: dict[str, bytes] = {}
        wav_sources = {w["from"] for w in manifest["wavs"]}
        ordered = ([r for r in manifest["results"] if r["name"] in wav_sources] +
                   [r for r in manifest["results"] if r["name"] not in wav_sources])
        began_all = time.monotonic()
        for region in ordered:
            began = time.monotonic()
            try:
                data, stats = read_range(console, region["address"], region["bytes"], progress=None)
            except ReadbackError as error:
                raise RunFailed(f"region {region['name']} could not be read back: {error}") from error
            digest = hashlib.sha256(data).hexdigest()
            entry = {"address": f"{region['address']:08X}", "bytes": len(data), "sha256": digest,
                     "crc32_verified": True, "retries": stats["retries"]}
            if region["board_sha256"]:
                board_digest, _s = board_sha256(console, region["address"], region["bytes"])
                entry["board_sha256"] = board_digest
                if board_digest != digest:
                    raise RunFailed(
                        f"region {region['name']}: the bytes read back have sha256 {digest} and the "
                        f"board's own digest of the range is {board_digest}. Nothing was accepted.")
            if region["sha256"] and region["sha256"] != digest:
                failures.append(f"region {region['name']} has sha256 {digest}, and the manifest says "
                                f"it must be {region['sha256']}.")
            suffix = ".f32" if region["name"] in wav_sources else ".bin"
            path = out_dir / f"{region['name']}{suffix}"
            path.write_bytes(data)
            entry["file"] = str(path)
            entry["seconds"] = round(time.monotonic() - began, 3)
            raw[region["name"]] = data
            record["regions"][region["name"]] = entry
            timings["regions"][region["name"]] = entry["seconds"]
            say(clock, f"readback {region['name']}: {len(data)} bytes from {region['address']:08X} in "
                       f"{entry['seconds']:.2f} s, crc32" +
                       (" and board sha256 equal" if region["board_sha256"] else "") + " verified")
            if wav_line_at is None and wav_sources and wav_sources <= set(raw):
                if not failures:
                    for wav in manifest["wavs"]:
                        record["wavs"].append(write_wav(raw[wav["from"]], wav["rate"], out_dir / wav["file"]))
                    wav_line_at = time.monotonic()
                    timings["returned_to_wav_line_seconds"] = round(wav_line_at - returned_at, 3)
                    print("WAV ready: " + ", ".join(w["file"] for w in record["wavs"]) +
                          f"  ({timings['returned_to_wav_line_seconds']:.1f} s after the payload returned)")
                    journal.step("wav")
                else:
                    wav_line_at = -1.0       # a failed run makes no WAV
        timings["readback_seconds"] = round(time.monotonic() - began_all, 3)
        journal.step("readback")

        if deadman_armed:
            reply = command(console, "deadman off", 10)
            if "is off" not in reply:
                raise RunFailed("the board did not confirm `deadman off`; the deadman may still be armed.")
            deadman_off = True
        record["coretest_after"] = coretest(console)
        journal.step("deadman off")

        journal.step("outputs")
        exit_code = 0 if not failures else 1

    except RunFailed as error:
        failures.append(str(error))
        exit_code = 1
    except (br.StreamError, OSError) as error:
        failures.append(f"the run stopped on a console or network error: {error}")
        exit_code = 1
    except KeyboardInterrupt:
        failures.append("the run was interrupted from the keyboard.")
        exit_code = 1
    finally:
        # ---- leave the board as found, then release it ----------------------
        if console is not None and journal is not None and not board_busy:
            try:
                if deadman_armed and not deadman_off:
                    reply = console.command("deadman off", 10)
                    deadman_off = "is off" in reply
                if turned_cache_on:
                    console.command("cache off", 15)
                    record["cache_restored_off"] = True
            except (br.StreamError, OSError) as error:
                failures.append(f"putting the board back as found failed: {error}")
        if console is not None:
            console.close()
        if lease is not None and lease.held:
            build = BUILD_RE.search(record.get("version", ""))
            state = (((f"build {build.group(1) if build else '?'} at "
                       + ("NOT at the prompt - the payload may still be running" if board_busy
                          else f"real `pmf>`, `{options.console_ip}`"))
                      if answered else
                      f"NO PROMPT answered on `{options.console_ip}` within 30 s; nothing was sent")
                     + f"; deadman {'OFF (confirmed)' if deadman_off or not deadman_armed else 'MAY STILL BE ARMED'}"
                     + (f"; {record['coretest_after']['line']}" if record.get("coretest_after", {}).get("line") else "")
                     + "; no listener")
            work = (f"NONE. RAM-only as declared: run {run_id}, assets resident {resident} / uploaded {uploads}, "
                    f"payload `{payload['path'].name}` "
                    + (f"x0={record['x0']} after {timings.get('run_seconds', 0):.1f} s" if "x0" in record
                       else "did not return a verdict")
                    + (f", {len(record['regions'])} region(s) read back" if record["regions"] else "")
                    + (f"; FAILED: {failures[0][:200]}" if failures else "")
                    + ". No reset, no flash, no boot-medium write")
            try:
                lease.release(state, work, clock)
            except (LeaseError, OSError) as error:
                print(f"!! {error}")
                exit_code = 1
        if journal is not None:
            timings["total_seconds"] = round(time.monotonic() - clock, 3)
            record["failures"] = failures
            record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            journal.flush()

    # ---- after the board: the compare command -------------------------------
    if exit_code == 0 and manifest["compare"]:
        values = {"{python}": sys.executable, "{base}": str(manifest["base"]), "{out}": str(out_dir)}
        for region in manifest["results"]:
            values[f"{{result.{region['name']}}}"] = record["regions"][region["name"]]["file"]
        for wav, made in zip(manifest["wavs"], record["wavs"]):
            values[f"{{wav.{wav['from']}}}"] = made["file"]
        argv = []
        for item in manifest["compare"]:
            for key, value in values.items():
                item = item.replace(key, value)
            argv.append(item)
        say(clock, "compare: " + " ".join(argv))
        began = time.monotonic()
        try:
            done = subprocess.run(argv, cwd=str(manifest["base"]))
            code = done.returncode
        except OSError as error:
            code = None
            failures.append(f"the compare command could not be started: {error}")
        timings["compare_seconds"] = round(time.monotonic() - began, 3)
        record["compare"] = {"argv": argv, "exit": code}
        if code != 0:
            failures.append(f"the compare command exited {code}; the WAVs are on disk and unaffected.")
            exit_code = 1
        timings["total_seconds"] = round(time.monotonic() - clock, 3)
        record["failures"] = failures
        (out_dir / f"{name}.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    if journal is not None:
        say(clock, f"record: {out_dir / (name + '.json')}")
        say(clock, "timings: " + json.dumps(timings, sort_keys=True))
    if failures:
        print("!! THIS RUN FAILED:")
        for entry in failures:
            print(f"   {entry}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", help="the run's manifest (JSON)")
    parser.add_argument("--console-ip", dest="console_ip", required=True)
    parser.add_argument("--console-port", dest="console_port", type=int,
                        default=br.DEFAULT_CONSOLE_PORT)
    parser.add_argument("--board-ip", dest="board_ip", default=None)
    parser.add_argument("--port", type=int, default=br.DEFAULT_RECV_PORT)
    parser.add_argument("--base", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--lease-file", dest="lease_file", default=None)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--no-lease", dest="no_lease", action="store_true")
    parser.add_argument("--lease-wait", dest="lease_wait", type=float, default=DEFAULT_LEASE_WAIT)
    parser.add_argument("--ask-seconds", dest="ask_seconds", type=float,
                        default=br.DEFAULT_ASK_SECONDS)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
