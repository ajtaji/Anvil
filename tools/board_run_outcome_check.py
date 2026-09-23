#!/usr/bin/env python3
"""Desk-only proof that a missing return line is asked about, not believed.

WHAT THIS IS ABOUT. On 2026-09-16 three long payloads on the Pi 4 - two to
five minutes of silent compute each - finished and returned, and
tools/board_run.py said "the payload never returned inside N s" about every
one. Each result had to be dug out of board memory by hand.

The cause was measured on the board the same day, and it is on the host: the
PC's stateful firewall forgets a UDP flow it has seen no traffic on, and the
board's reply after a long silence is dropped on the way in. A `sleep 120`
reply at the prompt arrived; `sleep 150` and `sleep 300` replies did not; the
same `sleep 300` arrived under an interpreter the firewall allows on the
cable's own network profile, and arrived under the other one once the host
sent an empty datagram every 20 seconds.

So there are two fixes and this checks both:

  (i)  THE KEEPALIVE. Every wait in NetConsole sends an empty datagram when
       nothing has gone to the board for KEEPALIVE_SECONDS. Proved against a
       scripted board behind a scripted firewall that drops any datagram
       arriving later than its flow timeout after the host last sent: with
       the keepalive the return line arrives; without it the line is lost.

  (ii) THE QUESTION. When no return line arrives inside --timeout, the tool
       asks the board (`last run`, the monitor's run record) and says which
       of five things happened, each as a sentence and a record stage:
       returned with x0 and the line lost; still running; reset by the
       deadman; stopped at a processor exception; never entered. A monitor
       without `last run` is not guessed at: its capture on return is used
       when it moved, and otherwise the outcome is NOT KNOWN - never "never
       returned".

Every scenario drives the REAL board_run.run() over a socket that answers like
the monitor, so the echo handling, the prompt anchoring, the datagram
reassembly and the keepalive are all the shipped code. Six mutants of
board_run.py - one per decision - are loaded and each must fail a scenario.
One of them is the needle: the scripted board splits every reply at 64 bytes,
and a wait for the WORDS of the return line stopped with its sixteen digits
still in the next datagram - found by this check on its first run.

    python tools/board_run_outcome_check.py
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

FLOW_TIMEOUT = 0.35       # the modelled firewall, seconds
KEEPALIVE = 0.1           # the keepalive used in these cases, seconds
PAYLOAD_SECONDS = 1.2     # a "long" silent payload, several flow timeouts
REBOOT_SECONDS = 0.8      # a deadman reset and the boot after it

RETURN_TEXT = ("The payload came back, so the deadman watchdog has been stopped.\r\n"
               "The payload returned to the monitor. Its x0 register held "
               "{x0:016X},\r\nwhich is whatever it chose to return.\r\npmf> ")
BOOT_TEXT = ("Starting the payload at 00700000. Control leaves the monitor now, and\r\n"
             "anything printed below this line came from the payload, not from Anvil.\r\n")


def load_tool(source: str | None = None, label: str = "real"):
    name = f"anvil_board_run_outcome_{label}"
    if source is None:
        spec = importlib.util.spec_from_file_location(name, HERE / "board_run.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader=None))
    module.__file__ = str(HERE / "board_run.py")
    sys.modules[name] = module
    exec(compile(source, f"board_run[{label}]", "exec"), module.__dict__)
    return module


class Failed(Exception):
    pass


def require(ok: bool, text: str) -> None:
    if not ok:
        raise Failed(text)


def lastrun_line(rec: dict) -> str:
    ms = 0xFFFFFFFFFFFFFFFF if rec.get("ms") is None else rec["ms"]
    return (f"LASTRUN {rec['run']:08X} {rec['state']:02X} {int(rec['restarted']):02X} "
            f"{rec['deadman']:02X} {rec['x0']:016X} {rec['addr']:016X} {ms:016X} "
            f"{rec.get('esr', 0):016X} {rec.get('pc', 0):016X} {rec.get('far', 0):016X}")


class SilentBoard:
    """A monitor on the far side of a stateful firewall.

    Datagrams from the board are queued with a release time. When one is
    released, the modelled firewall delivers it only if the host has sent
    something to the board within FLOW_TIMEOUT before that moment; otherwise
    it is gone, exactly as on the bench. The host's own sends - an empty
    keepalive included - refresh the flow. An empty datagram is no
    keystrokes to the monitor, so it is otherwise ignored.

    While a payload holds the processor the board answers nothing at all.
    """

    def __init__(self, payload_bytes: int, digest: str, ending: str,
                 old_monitor: bool = False):
        self.peer = ("192.0.2.10", 5555)
        self.ending = ending
        self.old = old_monitor
        self.queue: list[tuple[float, bytes]] = []
        self.lines: list[str] = []
        self.keepalives_seen = 0
        self.link_down_from = 0.0
        self.link_down_until = 0.0
        self.refused_sends = 0
        self.typed_while_busy: list[str] = []
        self.dropped = 0
        self.last_host = time.monotonic()
        self.busy_from = None
        self.busy_until = 0.0
        self.payload_bytes = payload_bytes
        self.digest = digest
        self.seq = 2
        self.shot_x0 = 0
        # The run record as the previous run left it: run 7, returned 0.
        self.rec = {"run": 7, "state": 2, "restarted": False, "deadman": 15,
                    "x0": 0, "addr": 0x700000, "ms": 4000}

    # ---- the socket surface NetConsole uses ----------------------------
    def settimeout(self, _s):
        pass

    def bind(self, _a):
        pass

    def close(self):
        pass

    def sendto(self, data, _addr):
        now = time.monotonic()
        if self.link_down_until and self.link_down_from <= now < self.link_down_until:
            # The board is resetting: the PC's own address on the cable is gone.
            self.refused_sends += 1
            raise OSError(22, "The requested address is not valid in its context", None, 10049)
        self.last_host = now
        if data == b"":
            self.keepalives_seen += 1
            return 0
        line = data.decode("utf-8", "replace").rstrip("\r\n")
        self.lines.append(line)
        if self.busy_from is not None and now < self.busy_until:
            self.typed_while_busy.append(line)
            return len(data)             # the payload has the processor
        self._settle(now)
        self._answer(line, now)
        return len(data)

    def recvfrom(self, _size):
        now = time.monotonic()
        self._settle(now)
        while self.queue and self.queue[0][0] <= now:
            released, data = self.queue.pop(0)
            if released - self.last_host > FLOW_TIMEOUT and released > self.last_host:
                self.dropped += 1
                continue
            return data, self.peer
        time.sleep(0.01)
        raise socket.timeout()

    # ---- the monitor ---------------------------------------------------
    def _say(self, text: str, at: float, chunk: int = 64) -> None:
        raw = text.encode()
        for i in range(0, len(raw), chunk):
            self.queue.append((at, raw[i:i + chunk]))
        self.queue.sort(key=lambda item: item[0])

    def _settle(self, now: float) -> None:
        """Apply what the payload's ending did, once its time has come."""
        if self.busy_from is None or now < self.busy_until:
            return
        self.busy_from = None

    def _answer(self, line: str, now: float) -> None:
        if line == "":
            self._say("\r\npmf> ", now)
            return
        if line == "version":
            self._say("version\r\nAnvil build 152\r\npmf> ", now)
        elif line == "map":
            self._say("map\r\n  stage a file at 00500000\r\n"
                      "  this image 00200000 to 004FFFFF\r\npmf> ", now)
        elif line == "shot status":
            self._say("shot status\r\nThe capture area holds picture number "
                      f"{self.seq}, 1280 by 800 as the\r\nconsole saw it, taken by "
                      "this monitor as a payload returned (its x0 was "
                      f"{self.shot_x0:016X})\r\npmf> ", now)
        elif line.startswith("net recv"):
            self._say(f"{line}\r\n  Listening on port 5001 for ONE connection.\r\n"
                      f"Received {self.payload_bytes} bytes from 192.0.2.20 to "
                      f"00500000 in 3 ms.\r\n  sha256 {self.digest}\r\npmf> ", now)
        elif line.startswith("deadman"):
            self._say(f"{line}\r\nThe deadman watchdog is armed for 15 seconds.\r\n"
                      "  It covers the NEXT payload only. It is armed immediately before the\r\n"
                      "  jump and stopped immediately after.\r\npmf> ", now)
        elif line == "last run":
            if self.old:
                self._say("last run\r\n? unknown command - type help. (last)\r\npmf> ", now)
            else:
                self._say("last run\r\n" + lastrun_line(self.rec) +
                          "\r\nRun 7 entered the payload.\r\npmf> ", now)
        elif line.startswith("boot mem"):
            self._boot(line, now)
        elif line == "shot":
            stream = (FIXTURES / "shot_return.txt").read_text(encoding="ascii")
            self._say("shot\r\n" + stream.replace("\n", "\r\n") + "pmf> ", now,
                      chunk=1024)
        else:
            self._say(f"{line}\r\n? the monitor does not know that word.\r\npmf> ", now)

    def _boot(self, line: str, now: float) -> None:
        if self.ending == "never":
            # Refused, and the refusal itself lost on the way: the case in
            # which only the run number can say nothing was entered.
            self.queue.append((now + 10 * FLOW_TIMEOUT, b"!! refused\r\npmf> "))
            self.last_host = now - 100.0
            return
        self._say(line + "\r\n" + BOOT_TEXT, now)
        self.rec = {"run": 8, "state": 1, "restarted": False, "deadman": 15,
                    "x0": 0, "addr": 0x700000, "ms": None}
        self.busy_from = now
        end = now + PAYLOAD_SECONDS
        if self.ending == "return":
            self.busy_until = end
            self.rec.update(state=2, x0=0, ms=int(PAYLOAD_SECONDS * 1000))
            self.seq = 3
            self.shot_x0 = 0
            self._say(RETURN_TEXT.format(x0=0), end)
        elif self.ending == "still":
            self.busy_until = end + 3600.0
        elif self.ending == "deadman":
            # A longer boot here, so the tool's question starts while the
            # board is still down. Measured on the bench board: the reset
            # takes the cable down and the PC's address with it, so sends are
            # refused until the link is back.
            self.busy_until = end + REBOOT_SECONDS + 1.5
            self.rec.update(restarted=True)
            self.link_down_from = end
            self.link_down_until = end + REBOOT_SECONDS + 1.5
        elif self.ending == "exception":
            self.busy_until = end + REBOOT_SECONDS
            self.rec.update(state=3, restarted=True, esr=0x96000004,
                            pc=0x701234, far=0xFFFFFFFFFFF00000)
        elif self.ending == "unknown":
            self.busy_until = end
            self._say(RETURN_TEXT.format(x0=0), end)
        else:
            raise AssertionError(self.ending)


def args_for(payload, out, **extra):
    args = argparse.Namespace(
        payload=str(payload), console_ip="192.0.2.10", console_port=5555,
        board_ip=None, port=5001, addr=None, out=str(out), name="proof",
        tier=None, deadman=15, trace=None, timeout=2.0, shot_timeout=5.0,
        settle=0.05, twin=False, no_shot=False, expect_x0="0",
        ask_seconds=2.5,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def drive(tool, root, name, ending, keepalive=KEEPALIVE, old=False, **extra):
    root.mkdir(parents=True, exist_ok=True)
    payload = root / "payload.pmf"
    payload.write_bytes(b"ANVILPAYLOAD-OUTCOME")
    data = payload.read_bytes()
    board = SilentBoard(len(data), hashlib.sha256(data).hexdigest(), ending, old)
    out = root / name
    saved = (tool.NetConsole._bound_socket, tool.stream_file,
             tool.NetConsole.keepalive_seconds)
    tool.NetConsole._bound_socket = staticmethod(lambda _ip: board)
    tool.stream_file = lambda *_a, **_k: 0.002
    tool.NetConsole.keepalive_seconds = keepalive
    printed = io.StringIO()
    started = time.monotonic()
    try:
        with contextlib.redirect_stdout(printed):
            rc = tool.run(args_for(payload, out, **extra))
    finally:
        (tool.NetConsole._bound_socket, tool.stream_file,
         tool.NetConsole.keepalive_seconds) = saved
    took = time.monotonic() - started
    record = json.loads((out / "proof.json").read_text(encoding="utf-8"))
    return rc, printed.getvalue(), record, board, took


def scenarios(tool, root) -> int:
    checks = 0

    def never_says_never(text, record, label):
        joined = text + json.dumps(record)
        require("never returned" not in joined,
                f"{label}: the old sentence 'never returned' is still printed")

    # ---- (i) the keepalive keeps the line ---------------------------------
    rc, text, record, board, _ = drive(tool, root, "keep", "return")
    require(board.keepalives_seen >= 3,
            f"keepalive: only {board.keepalives_seen} empty datagrams went out "
            "across a silence several flow timeouts long")
    require(board.dropped == 0, f"keepalive: {board.dropped} board datagrams were "
            "dropped by the modelled firewall with the keepalive running")
    require(rc == 0 and record["stage"] == "picture",
            f"keepalive: rc {rc}, stage {record['stage']}: {text}")
    require("return_line_lost" not in record and record["x0"] == "0" * 16,
            "keepalive: the return line did not arrive although the flow was kept")
    require(board.typed_while_busy == [],
            f"keepalive: {board.typed_while_busy!r} was typed at a running payload; "
            "a keepalive must be an empty datagram, which the monitor reads as nothing")
    never_says_never(text, record, "keepalive")
    checks += 6

    # ---- (ii) returned, line lost -----------------------------------------
    rc, text, record, board, _ = drive(tool, root, "lost", "return", keepalive=3600.0)
    require(board.dropped > 0,
            "line lost: the modelled firewall dropped nothing, so the case is vacuous")
    require(rc == 0, f"line lost: a payload the board says returned 0 failed: {text}")
    require(record.get("return_line_lost") is True and record["x0"] == "0" * 16,
            "line lost: the record does not carry x0 and the lost line")
    require(record["outcome"]["kind"] == "returned, line lost"
            and record["outcome"]["evidence"] == "run record",
            f"line lost: outcome {record.get('outcome')}")
    require("RETURNED" in text and "lost on the way" in text,
            "line lost: the sentence does not say it returned and the line was lost")
    require(record["stage"] == "picture" and (root / "lost" / "proof.png").is_file(),
            "line lost: the run did not go on to its picture")
    require(board.lines.count("last run") == 2,
            "line lost: the run number was not read before AND the record after")
    never_says_never(text, record, "line lost")
    checks += 8

    # ---- still running ----------------------------------------------------
    rc, text, record, board, took = drive(tool, root, "still", "still", keepalive=3600.0)
    require(rc == 1 and record["stage"] == "unresolved silence",
            f"still running: rc {rc}, stage {record['stage']}")
    require("does not prove either state" in text and "watchdog" in text,
            "silence was misreported as a watchdog reset or payload progress")
    require("last run" not in board.lines[-3:],
            "still running: a command was sent to a board that was not answering")
    require(not (root / "still" / "proof.shot.txt").exists(),
            "still running: a picture was asked of a board still running a payload")
    require(took >= 2.0 + 2.5 - 0.3,
            f"still running: gave up after {took:.1f} s, before --ask-seconds")
    never_says_never(text, record, "still running")
    checks += 6

    # ---- reset by the deadman --------------------------------------------
    rc, text, record, board, _ = drive(tool, root, "deadman", "deadman", keepalive=3600.0)
    require(rc == 1 and record["stage"] == "deadman reset",
            f"deadman: rc {rc}, stage {record['stage']}: {text}")
    require("THE DEADMAN RESET THE BOARD" in text, "deadman: sentence missing")
    require(record["outcome"]["run"] == 8, "deadman: the run is not named")
    require(not (root / "deadman" / "proof.shot.txt").exists(),
            "deadman: a picture was streamed after a reset")
    require(board.refused_sends > 0,
            "deadman: the PC address never went away, so the reset case is vacuous")
    never_says_never(text, record, "deadman")
    checks += 6

    # ---- stopped at a processor exception ---------------------------------
    rc, text, record, board, _ = drive(tool, root, "exception", "exception", keepalive=3600.0)
    require(rc == 1 and record["stage"] == "processor exception",
            f"exception: rc {rc}, stage {record['stage']}")
    require("STOPPED AT A PROCESSOR EXCEPTION" in text and "0000000000701234" in text,
            "exception: the sentence does not name the exception and its PC")
    require(record["outcome"]["esr"] == "0000000096000004",
            "exception: ESR not recorded")
    never_says_never(text, record, "exception")
    checks += 4

    # ---- never entered -----------------------------------------------------
    rc, text, record, board, _ = drive(tool, root, "never", "never", keepalive=3600.0)
    require(rc == 1 and record["stage"] == "never entered",
            f"never entered: rc {rc}, stage {record['stage']}: {text}")
    require("NEVER ENTERED THE PAYLOAD" in text and "run 7" in text,
            "never entered: the sentence does not say so by the run number")
    never_says_never(text, record, "never entered")
    checks += 3

    # ---- a monitor without `last run`, capture moved ------------------------
    rc, text, record, board, _ = drive(tool, root, "old-return", "return",
                                       keepalive=3600.0, old=True)
    require(rc == 0 and record["outcome"]["evidence"] == "capture on return",
            f"old monitor, returned: rc {rc}, outcome {record.get('outcome')}: {text}")
    require(record["last_run_before"] is None and record["last_run_after"] is None,
            "old monitor: a refused `last run` was read as a record")
    checks += 2

    # ---- a monitor without `last run`, nothing to go on ---------------------
    rc, text, record, board, _ = drive(tool, root, "old-unknown", "unknown",
                                       keepalive=3600.0, old=True)
    require(rc == 1 and record["stage"] == "outcome unknown",
            f"old monitor, unknown: rc {rc}, stage {record['stage']}: {text}")
    require("NOT KNOWN" in text and "NOT evidence that the payload never" in text,
            "old monitor, unknown: the sentence overclaims")
    checks += 2
    return checks


MUTANTS = (
    ("the keepalive is never sent",
     '            if self._sendto(b""):\n',
     '            if False:\n'),
    ("a missing line is believed again",
     "                outcome, x0 = ask_after_silence(\n"
     "                    console, args, record, failures, before_run, before)\n",
     "                outcome, x0 = \"payload never returned\", None\n"
     "                failures.append(\"the payload never returned\")\n"),
    ("the run number is not compared",
     "    if run_before is not None and after[\"run\"] == run_before and after[\"state\"] != LASTRUN_NONE:\n",
     "    if False:\n"),
    ("the return line is matched by its words, not by its value",
     "                line, [RETURN_RE, FATAL_MARKER], args.timeout)\n",
     "                line, [\"Its x0 register held\", FATAL_MARKER], args.timeout)\n"),
    ("a vanished PC address is a traceback again",
     "            if not self._address_gone(error):\n                raise\n            self._rebind()\n            return False\n",
     "            raise\n"),
    ("silence is taken for an answer at once",
     "    answered = console.at_prompt(timeout=args.ask_seconds)\n",
     "    answered = console.at_prompt(timeout=0.0)\n"),
)


def main() -> int:
    source = (HERE / "board_run.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="board-run-outcome-check-") as raw:
        root = pathlib.Path(raw)
        try:
            checks = scenarios(load_tool(), root / "real")
        except Failed as error:
            print(f"board_run_outcome_check: FAIL - {error}")
            return 1
        caught = []
        for index, (label, old, new) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"board_run_outcome_check: FAIL - the anchor for the mutant "
                      f"{label!r} appears {source.count(old)} times")
                return 1
            mutant = load_tool(source.replace(old, new, 1), f"m{index}")
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    scenarios(mutant, root / f"m{index}")
            except Failed as error:
                caught.append(f"{label}: {error}")
                continue
            except Exception as error:  # a traceback out of the tool is a failure too
                caught.append(f"{label}: the tool raised {type(error).__name__}: {error}")
                continue
            print(f"board_run_outcome_check: FAIL - the mutant {label!r} passed")
            return 1
    print(f"board_run_outcome_check: PASS - {checks} causal assertions over eight "
          f"scripted boards behind a modelled firewall; {len(caught)}/"
          f"{len(MUTANTS)} mutants caught; no board")
    for entry in caught:
        print("  caught: " + entry[:150])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
