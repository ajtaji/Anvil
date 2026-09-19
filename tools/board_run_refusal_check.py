#!/usr/bin/env python3
"""Desk-only proof that a board_run that goes wrong SAYS SO, and says it now.

WHAT THIS IS ABOUT. On 2026-09-16 a lane ran

    timeout 600 python tools/board_run.py ... --deadman 15 ... 2>&1 | tail -30

twice, about ten minutes each, and got no output at all, an empty run
directory, and a shell status of zero. Nothing about that told anybody
anything, including whether the board had ever been sent a byte. Three
defects in this tool lined up with one habit in the caller:

  (a) the board REFUSED to enter the payload - its load address was inside
      the monitor - and printed a sentence and its prompt within
      milliseconds. A refusal is not the line the run was waiting for, so
      the tool sat out the whole 600-second default at a board that had
      been idle since the first one of them;
  (b) the outer `timeout` then killed the process where it stood, and the
      record and the transcript were written only in a finally, so nothing
      at all was on disk; and
  (c) stdout was block-buffered because it was going into a pipe, so every
      line the tool HAD printed died in the buffer with the process. `tail`
      then reported its own exit status, which was zero.

Each of the three is fixed at its source in tools/board_run.py and each has
a case here. None of them needs a board: a refusal is a scripted console, a
hard kill is an exception raised inside a step, and nobody listening on the
port is a socket that answers a datagram with a reset.

    python tools/board_run_refusal_check.py

WHY THE CONSOLE IS SCRIPTED AT THE SOCKET AND NOT AT THE CLASS. The thing
being proved here is the decision "the prompt came back and the line I was
waiting for did not", and that decision is made of echo handling, prompt
anchoring and datagram reassembly. A fake that replaced NetConsole would
have skipped all three and proved only that the fake agrees with itself. So
these cases drive the REAL NetConsole over a socket that answers like a
monitor: it echoes what it is given, prints its reply, and prints `pmf> `.

WHY NOBODY LISTENING IS SCRIPTED TOO. Pointing the tool at a closed port on
this machine is exactly the bench case, and it is platform-dependent: an
unconnected UDP socket on Windows is handed the ICMP unreachable as
WinError 10054 on the next receive, while on Linux it is not handed
anything and the receive simply times out. A check that passed on one and
hung on the other would be worth less than no check, so the reset is
scripted at the socket and the seam that must catch it is the real one.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import socket
import sys
import tempfile
import time


HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "board_run"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "anvil_board_run_refusal", HERE / "board_run.py")
    if spec is None or spec.loader is None:
        raise SystemExit("board_run_refusal_check: cannot load board_run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require(ok: bool, text: str) -> None:
    if not ok:
        raise SystemExit("board_run_refusal_check: FAIL - " + text)


# ---------------------------------------------------------------------
#  The board's own refusals, copied from the monitor's sources so that a
#  reworded one is caught by the check that reads them rather than by a
#  bench run six weeks later.
#
#  RaspberryPi4/Board/cache.pi4, the four-core refusal:
FOUR_CORE_REFUSAL = (
    "!! resident secondary cores own this monitor until restart, so no\r\n"
    "   payload was entered. Restart Anvil before run, go or boot mem.\r\n")
#  Anvil/Core/bootfile_cmd.pbi, the dirty-transfer refusal:
DIRTY_TRANSFER_REFUSAL = (
    "!! the last transfer did not arrive cleanly, so nothing was booted.\r\n"
    "   What is in memory is part of an image and part of whatever was\r\n"
    "   there before. The hash below would have caught it, and catching it\r\n"
    "   here says something more useful about why. Send it again.\r\n")

RETURN_LINE = ("The payload returned to the monitor. Its x0 register held "
               "0000000000000000\r\n")


class MonitorSocket:
    """A socket that answers like the monitor on the other end of a console.

    It echoes the line it is given, prints whatever that command answers
    with, and prints a prompt - in that order, which is the order that makes
    a bare `pmf>` needle useless and the echo the only honest anchor.

    Replies are handed back one datagram at a time, and a reply longer than
    `chunk` is split across several, because that is what a UDP console
    does and it is where a decoder that assumed whole lines would break.
    """

    def __init__(self, peer, answers, chunk=64):
        self.peer = peer
        self.answers = answers
        self.chunk = chunk
        self.queue: list[bytes] = []
        self.lines: list[str] = []
        self.closed = False
        self.on_send = None

    # -- the socket surface NetConsole uses ---------------------------
    def settimeout(self, _seconds):
        pass

    def bind(self, _address):
        pass

    def close(self):
        self.closed = True

    def sendto(self, data, _address):
        line = data.decode("utf-8", "replace").rstrip("\r\n")
        self.lines.append(line)
        if self.on_send is not None:
            self.on_send(line)
        if line == "":
            self._queue("\r\npmf> ")
            return len(data)
        answer = self.answers(line)
        if answer is None:
            self._queue(f"{line}\r\n? the monitor does not know that word.\r\npmf> ")
        else:
            self._queue(line + "\r\n" + answer)
        return len(data)

    def recvfrom(self, _size):
        if not self.queue:
            raise socket.timeout()
        return self.queue.pop(0), self.peer

    # -- fragmentation -------------------------------------------------
    def _queue(self, text):
        raw = text.encode()
        for at in range(0, len(raw), self.chunk):
            self.queue.append(raw[at:at + self.chunk])


class ResetSocket:
    """A socket whose next receive is told nobody is listening.

    This is what a UDP console with nothing behind it looks like from here:
    the datagram goes out, the far host answers with an ICMP
    port-unreachable, and the operating system reports it on the NEXT
    receive as a connection reset - which is a strange thing to be told
    about a protocol with no connections, and was an even stranger thing to
    be shown as a traceback.
    """

    def __init__(self):
        self.closed = False

    def settimeout(self, _seconds):
        pass

    def bind(self, _address):
        pass

    def close(self):
        self.closed = True

    def sendto(self, data, _address):
        return len(data)

    def recvfrom(self, _size):
        raise ConnectionResetError(
            10054, "An existing connection was forcibly closed by the remote host")


GOOD_DEADMAN = ("The deadman watchdog is armed for 15 seconds.\r\n"
                "  It covers the NEXT payload only. It is armed immediately "
                "before the\r\n  jump and stopped immediately after.\r\n")


def board_answers(payload_bytes: int, digest: str, boot_answer: str,
                  deadman_reply: str | None = None):
    """One monitor's replies, as a function from command line to text."""
    shot_status = (FIXTURES / "shot_status.txt").read_text(encoding="ascii")
    shot_stream = (FIXTURES / "shot_return.txt").read_text(encoding="ascii")

    def answer(line: str):
        if line == "version":
            return "Anvil build 145\r\npmf> "
        if line == "map":
            return ("  stage a file at 00500000\r\n"
                    "  this image 00200000 to 004FFFFF\r\npmf> ")
        if line == "shot status":
            return shot_status.replace("\n", "\r\n") + "pmf> "
        if line.startswith("net recv"):
            return ("  Listening on port 5001 for ONE connection.\r\n"
                    f"Received {payload_bytes} bytes from 192.0.2.20 to "
                    "00500000 in 3 ms.\r\n"
                    f"  sha256 {digest}\r\npmf> ")
        if line.startswith("deadman"):
            return (GOOD_DEADMAN if deadman_reply is None else deadman_reply) + "pmf> "
        if line.startswith("boot mem"):
            return boot_answer
        if line == "shot":
            return shot_stream.replace("\n", "\r\n") + "pmf> "
        return None

    return answer


def args_for(payload, out, **extra):
    args = argparse.Namespace(
        payload=str(payload), console_ip="192.0.2.10", console_port=5555,
        board_ip=None, port=5001, addr=None, out=str(out), name="proof",
        tier=None, deadman=15, trace=None, timeout=600.0, shot_timeout=5.0,
        settle=0.05, twin=False, no_shot=False, expect_x0="0",
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def drive(tool, payload, out, boot_answer, on_send=None,
          deadman_reply=None, **extra):
    """Run the tool against one scripted monitor. Returns rc, output, socket."""
    data = payload.read_bytes()
    answers = board_answers(len(data), hashlib.sha256(data).hexdigest(),
                            boot_answer, deadman_reply)
    holder = {}

    def bound(_ip):
        sock = MonitorSocket(("192.0.2.10", 5555), answers)
        sock.on_send = on_send
        holder["sock"] = sock
        return sock

    old_bound, old_stream = tool.NetConsole._bound_socket, tool.stream_file
    tool.NetConsole._bound_socket = staticmethod(bound)
    tool.stream_file = lambda *_a, **_k: 0.002
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            rc = tool.run(args_for(payload, out, **extra))
    finally:
        tool.NetConsole._bound_socket = old_bound
        tool.stream_file = old_stream
    return rc, printed.getvalue(), holder["sock"]


# =====================================================================
#  (0) The decision itself, as pure text
# =====================================================================
def anchor_checks(tool) -> int:
    """The echo is the anchor, and this is why a bare prompt is not.

    The reply to any command OPENS with the prompt the command was typed
    at. A tool that stopped at the first `pmf>` would decide that every
    command had finished before it started - which is the opposite failure
    to the one being fixed and just as silent.
    """
    line = "boot mem 500000 shot"

    # The echo arrives on the prompt's own line, which is what a terminal
    # echo does. Nothing that follows `pmf>` on that line is a finished
    # command, and the expression must not say it is.
    same_line = "pmf> " + line + "\r\n"
    require(tool.PROMPT_RE.search(same_line.replace("\r", "")) is None,
            "a prompt with a command echoed after it on the same line was "
            "read as a command that had finished")

    # And the harder spelling: the prompt on a line of its own, with the
    # echo after it. Here the expression DOES match, and the only thing
    # keeping the step from ending before it began is the echo anchor.
    own_line = "pmf> \r\n" + line + "\r\n"
    require(tool.PROMPT_RE.search(own_line.replace("\r", "")) is not None,
            "the opening prompt is not matched at all, so this case is vacuous")
    echoed = tool.echo_pattern(line).search(own_line.replace("\r", ""))
    require(echoed is not None, "the echoed command line was not found")
    require(tool.PROMPT_RE.search(own_line.replace("\r", ""), echoed.end()) is None,
            "the prompt the command was TYPED at was read as the prompt that "
            "ENDS it, which would end every step before it began")

    whole = same_line + FOUR_CORE_REFUSAL + "pmf> "
    echoed = tool.echo_pattern(line).search(whole.replace("\r", ""))
    require(tool.PROMPT_RE.search(whole.replace("\r", ""), echoed.end()) is not None,
            "the prompt after a refusal was not recognised")
    reason = tool.refusal_reason(whole, line)
    require(reason.splitlines()[0].startswith("!! resident secondary cores"),
            f"the board's own refusal was not quoted back: {reason!r}")
    require("Restart Anvil" in reason,
            "the refusal's second line was dropped, so the quote is half a "
            "sentence")
    require(tool.refusal_reason(same_line + "pmf> ", line) == "",
            "a refusal with no text was reported as having some")

    # The payload's own output is NOT read for refusal markers: it prints
    # what it likes and a run must never fail over that.
    noisy = (same_line + "!! my payload says this and it is fine\r\n"
             + RETURN_LINE + "pmf> ")
    require(tool.parse_return_x0(noisy) == 0,
            "a payload that printed !! lost its return line")

    require(tool.board_refusal(
        "deadman 99\r\n!! a number of seconds cannot be negative, so nothing\r\n"
        "pmf> ", "deadman 99").startswith("!!"),
        "a monitor refusal of deadman was not seen")
    require(tool.board_refusal(
        "deadman 15\r\nThe deadman watchdog is armed for 15 seconds.\r\npmf> ",
        "deadman 15") == "",
        "an armed deadman was read as a refusal")
    require(tool.deadman_armed_seconds(
        "deadman 15\r\n" + GOOD_DEADMAN + "pmf> ", "deadman 15", 15) == 15,
        "the actual next-payload arm confirmation was not accepted")
    require(tool.deadman_armed_seconds(
        "deadman 15\r\nThe deadman watchdog is armed for 15 seconds.\r\npmf> ",
        "deadman 15", 15) is None,
        "a bare success-looking sentence without next-payload scope was accepted")
    require(tool.deadman_armed_seconds(
        "deadman 15\r\nThe deadman watchdog is armed for 14 seconds.\r\n"
        "  It covers the NEXT payload only.\r\npmf> ", "deadman 15", 15) is None,
        "a clamped/incorrect timeout was accepted")
    require(tool.argument_parser().parse_args(["payload.pmf"]).deadman == 15,
            "the command-line default is not the 15-second deadman")
    return 14


# =====================================================================
#  (i) A refusal is answered at once, in the board's own words
# =====================================================================
def refusal_checks(tool, root) -> int:
    payload = root / "payload.pmf"
    payload.write_bytes(b"ANVILPAYLOAD")
    checks = 0

    # A prompt is not proof the one-shot watchdog armed. Exercise missing,
    # explicit refusal, and mismatched-effective-timeout replies through the
    # real run path, then prove none reaches `boot mem`.
    for index, reply in enumerate((
        "",
        "!! the watchdog is unavailable, so nothing was changed.\r\n",
        "The deadman watchdog is armed for 14 seconds.\r\n"
        "  It covers the NEXT payload only.\r\n",
    )):
        out = root / f"deadman-not-confirmed-{index}"
        rc, printed, sock = drive(tool, payload, out, RETURN_LINE + "pmf> ",
                                  deadman_reply=reply)
        record = json.loads((out / "proof.json").read_text(encoding="utf-8"))
        require(rc == 1 and record["stage"] == "deadman refused",
                f"ambiguous deadman reply {index} did not fail at the arm gate")
        require("affirmatively confirm" in printed,
                f"ambiguous deadman reply {index} was not reported clearly")
        require(not any(line.startswith("boot mem ") for line in sock.lines),
                f"ambiguous deadman reply {index} still booted the payload")
        checks += 3

    # Zero is not an opt-out. It fails before opening a console or writing a
    # run directory, while an omitted CLI value defaults to the safe maximum.
    zero_out = root / "deadman-zero"
    zero_text = io.StringIO()
    with contextlib.redirect_stdout(zero_text):
        rc = tool.run(args_for(payload, zero_out, deadman=0))
    require(rc == 2 and not zero_out.exists() and "--deadman" in zero_text.getvalue(),
            "explicit deadman zero was not refused before any run")
    require(tool.DEFAULT_DEADMAN_SECONDS == 15,
            "the default deadman is not the board-supported 15-second maximum")
    checks += 2

    for index, (label, refusal, quoted) in enumerate((
        ("four cores own the board", FOUR_CORE_REFUSAL,
         "resident secondary cores own this monitor until restart"),
        ("the transfer was dirty", DIRTY_TRANSFER_REFUSAL,
         "the last transfer did not arrive cleanly"),
    )):
        out = root / f"refused-{index}"
        started = time.monotonic()
        rc, printed, _sock = drive(
            tool, payload, out, refusal + "pmf> ")
        took = time.monotonic() - started

        require(rc == 1, f"{label}: a refused boot returned {rc}, not 1")
        # THE NUMBER THAT MATTERS. --timeout is 600 s in these cases, the
        # same as the bench run. A refusal that is recognised costs the
        # round trip and nothing else.
        require(took < 3.0,
                f"{label}: a refused boot took {took:.1f} s with --timeout "
                "600 - the refusal was not recognised and the bound was "
                "waited out, which is the whole defect")
        require(quoted in printed,
                f"{label}: the board's own words are not in the output")
        require("REFUSED TO ENTER THE PAYLOAD" in printed,
                f"{label}: the output does not say the payload never ran")
        record = json.loads((out / "proof.json").read_text(encoding="utf-8"))
        require(record["stage"] == "boot refused",
                f"{label}: stage is {record['stage']!r}, not 'boot refused'")
        require(quoted in record["boot_refusal"],
                f"{label}: the record does not carry the board's reason")
        require(record["x0"] is None,
                f"{label}: a refused boot recorded a return value")
        require((out / "proof.txt").read_text(encoding="utf-8").strip() != "",
                f"{label}: the transcript is empty")
        # NOTHING IS ASKED OF THE BOARD AFTER A REFUSAL. There is no new
        # capture to read and no trace to dump, and streaming the previous
        # run's picture back is how a refused run acquires a screenshot.
        require(not (out / "proof.png").exists(),
                f"{label}: a refused run produced a picture")
        require(not (out / "proof.shot.txt").exists(),
                f"{label}: a refused run streamed a picture")
        checks += 10

    # A REFUSAL WITH NOTHING SAID IS STILL A REFUSAL. The tool must not need
    # the board to explain itself before it will believe the prompt.
    out = root / "refused-silently"
    rc, printed, _sock = drive(tool, payload, out, "pmf> ")
    record = json.loads((out / "proof.json").read_text(encoding="utf-8"))
    require(rc == 1 and record["stage"] == "boot refused",
            "a silent refusal was not recognised")
    require("no reason at all" in printed,
            "a silent refusal did not say that the board gave no reason")
    checks += 2

    # AND THE CONTROL: the same machinery must let a real run through.
    out = root / "returned"
    started = time.monotonic()
    rc, printed, sock = drive(tool, payload, out, RETURN_LINE + "pmf> ")
    record = json.loads((out / "proof.json").read_text(encoding="utf-8"))
    require(rc == 0, f"a payload that returned 0 failed: {printed}")
    require(record["stage"] == "picture" and record["x0"] == "0000000000000000",
            f"a good run recorded stage {record['stage']!r}")
    require((out / "proof.png").is_file(), "a good run wrote no picture")
    require("finished" in record,
            "a completed run carries no finished timestamp, so nothing "
            "distinguishes it from one that was killed")
    require(time.monotonic() - started < 10.0,
            "a good run no longer completes promptly")
    # It really did go through the whole ladder, in order.
    require([line for line in sock.lines if line][:4]
            == ["version", "map", "shot status", "net recv 5001 500000"],
            f"the run did not follow its own ladder: {sock.lines}")
    checks += 6
    return checks


# =====================================================================
#  (ii) A run that is killed leaves a directory that says where
# =====================================================================
def killed_checks(tool, root) -> int:
    """A hard kill is simulated by raising inside a step.

    KeyboardInterrupt, deliberately: it is not a StreamError, so the tool
    cannot catch and tidy it, and it therefore models the only ending this
    tool does not control. What is asserted is NOT that the finally still
    writes - it always did - but that the record was ALREADY on disk, with
    the right stage, at the instant the step was interrupted. That is the
    difference between the empty directory of 2026-09-16 and a directory
    that answers the question.
    """
    payload = root / "payload.pmf"
    payload.write_bytes(b"ANVILPAYLOAD")
    checks = 0

    for label, kill_at, expected_stage in (
        ("at the listener", "net recv", "map"),
        ("at the transfer verdict", "boot mem", "boot"),
    ):
        out = root / ("killed-" + kill_at.split()[0])
        seen = {}

        def on_send(line, out=out, seen=seen, kill_at=kill_at):
            if not line.startswith(kill_at):
                return
            # Read what is on disk AT THIS INSTANT - before any finally.
            seen["json"] = (out / "proof.json").read_text(encoding="utf-8")
            seen["txt"] = (out / "proof.txt").read_text(encoding="utf-8")
            raise KeyboardInterrupt("the outer timeout fired")

        try:
            drive(tool, payload, out, RETURN_LINE + "pmf> ", on_send=on_send)
        except KeyboardInterrupt:
            pass
        else:
            require(False, f"{label}: the simulated kill did not happen")

        require("json" in seen, f"{label}: no record was on disk mid-run")
        record = json.loads(seen["json"])
        require(record["stage"] == expected_stage,
                f"{label}: mid-run stage was {record['stage']!r}, expected "
                f"{expected_stage!r}")
        require("finished" not in record,
                f"{label}: a killed run claims to have finished")
        require(record["payload_sha256"] == hashlib.sha256(
            payload.read_bytes()).hexdigest(),
            f"{label}: the mid-run record does not identify the payload")
        require(seen["txt"].strip() != "",
                f"{label}: the transcript was empty mid-run, so a kill would "
                "still have left nothing to read")
        require((out / "proof.json").is_file() and (out / "proof.txt").is_file(),
                f"{label}: the run directory is not there afterwards")
        checks += 6

    # AND THE OTHER HALF OF THE SAME RULE: a run that never started leaves
    # NOTHING - so an empty directory cannot be produced by this tool and a
    # directory is therefore evidence that a board was spoken to.
    for label, extra in (
        ("an address inside the monitor", {"addr": "200000"}),
        ("a deadman the board cannot honour", {"deadman": 900}),
    ):
        out = root / ("never-started-" + label.split()[-1])
        if "deadman" in extra:
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                rc = tool.run(args_for(payload, out, **extra))
            text = printed.getvalue()
        else:
            rc, text, _sock = drive(tool, payload, out,
                                    RETURN_LINE + "pmf> ", **extra)
        require(rc == 2, f"{label}: exited {rc}, not 2")
        require(not out.exists(),
                f"{label}: a run that never started left a directory behind")
        require(text.strip() != "" and "!!" in text,
                f"{label}: a run that never started said nothing")
        checks += 3
    return checks


# =====================================================================
#  (iii) Nobody listening on the port is a sentence, not a traceback
# =====================================================================
def unreachable_checks(tool, root) -> int:
    payload = root / "payload.pmf"
    payload.write_bytes(b"ANVILPAYLOAD")
    out = root / "unreachable"

    old_bound = tool.NetConsole._bound_socket
    tool.NetConsole._bound_socket = staticmethod(lambda _ip: ResetSocket())
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            rc = tool.run(args_for(payload, out, console_ip="127.0.0.1",
                                   console_port=5599))
    except ConnectionResetError:
        require(False, "the reset escaped as a traceback, which is the defect")
    finally:
        tool.NetConsole._bound_socket = old_bound
    text = printed.getvalue()

    require(rc == 2, f"nobody listening exited {rc}, not 2")
    require("127.0.0.1:5599" in text,
            "the sentence does not name the address and the port that were "
            f"tried: {text!r}")
    require("10054" in text,
            "the operating system's own number was dropped, so the sentence "
            "cannot be matched against what the OS says")
    require("nothing is listening" in text,
            "the sentence does not say what is actually wrong")
    require("Traceback" not in text, "a traceback was printed")
    require(not out.exists(),
            "a console that was never reached still left a directory")

    # The seam is the receive, and it is named. A blanket except would also
    # have swallowed this, which is why it is not one.
    console = object.__new__(tool.NetConsole)
    console.addr = ("127.0.0.1", 5599)
    console.name = "127.0.0.1:5599"
    console.sock = ResetSocket()
    console.transcript = []
    console.accepted_datagrams = []
    try:
        console.read_until(["pmf>"], 0.05)
    except tool.ConsoleUnreachable as error:
        require("127.0.0.1:5599" in str(error),
                "the console's own exception does not name the console")
    else:
        require(False, "the receive seam did not raise ConsoleUnreachable")
    require(issubclass(tool.ConsoleUnreachable, tool.StreamError),
            "ConsoleUnreachable is outside the tool's own error family, so "
            "the run loop would not treat it as an ending")
    return 8


def main() -> int:
    tool = load_tool()
    checks = 0
    checks += anchor_checks(tool)
    with tempfile.TemporaryDirectory(prefix="board-run-refusal-check-") as raw:
        root = pathlib.Path(raw)
        checks += refusal_checks(tool, root)
        checks += killed_checks(tool, root)
        checks += unreachable_checks(tool, root)
    print(f"board_run_refusal_check: PASS - {checks} causal assertions; no board")
    print("  a refused boot ends in the round trip, not in --timeout;")
    print("  a killed run leaves a record that names the stage it died at;")
    print("  an unlistened console is a sentence naming the address and port.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
