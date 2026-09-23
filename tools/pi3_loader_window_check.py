#!/usr/bin/env python3
"""Desk gate for the Pi 3 immutable loader's whole pre-branch watchdog window."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as a64_base
import pi3_gate_build
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = ROOT / "RaspberryPi3/Board/loader.pi3"
UPDATER = ROOT / "RaspberryPi3/Board/updater.pi3"
MONITOR = ROOT / "RaspberryPi3/Board/board.pi3"
AB = ROOT / "RaspberryPi3/Lib/update_ab.pbi"
WATCHDOG = ROOT / "RaspberryPi3/Lib/update_watchdog.pbi"
SUPPORT = ROOT / "RaspberryPi3/Board/update_boot_support.pbi"
TRANSPORT = ROOT / "RaspberryPi3/Lib/update_transport.pbi"
PRIMITIVES = ROOT / "RaspberryPi3/Board/pi3_boot_primitives.pbi"

# Operator transcript for the one card trip. Binary frames are represented by
# the transport's textual boundaries; the frame ACKs are checked by the host
# gate, not guessed here.
EXPECTED_RECOVERY_TRANSCRIPT = (
    "U: serial recovery; F: older confirmed slot; auto boot in 3 seconds",
    "R0: serial recovery on the UART at 115200 8N1.",
    "mount",
    "mounted; update and status commands are now available",
    "update status -> received 0 error 0 slot B generation 5 pending none",
    "update begin <length> <sha256> -> rdy 0",
    "binary P3A1 ACKs -> staged <length>",
    "update commit -> committed slot A generation 6",
    "reset -> candidate C0 entry -> running generation confirmed",
)


def procedure(text: str, name: str) -> str:
    match = re.search(
        rf"Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)EndProcedure",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("missing procedure " + name)
    return match.group(1)


def ordered(text: str, needles: tuple[str, ...]) -> None:
    at = -1
    for needle in needles:
        found = text.find(needle, at + 1)
        if found < 0:
            raise ValueError("missing or out-of-order loader boundary: " + needle)
        at = found


def recovery_transport_contract(transport: str) -> None:
    """Keep the recovery transcript backed by the actual dispatcher branches."""
    mount = transport[transport.find('If pi3ut_Match("mount")'):transport.find('If pi3ut_Match("reset")')]
    if "pi3_ut_mount_registered = 0" not in mount or "pi3_ut_mount_owner()" not in mount:
        raise ValueError("recovery mount command lost its registered owner")
    status = transport[transport.find('If pi3ut_Match("status")'):transport.find('If pi3ut_Match("abort")')]
    if "pi3ut_Status()" not in status:
        raise ValueError("recovery status command lost its A/B record report")
    commit = transport[transport.find('If pi3ut_Match("commit")'):transport.find('If pi3ut_Match("begin")')]
    if "Pi3UpdateCommitFrom(#PI3_UPDATE_SOURCE_SERIAL)" not in commit or '"committed slot "' not in commit:
        raise ValueError("serial commit branch lost its owner or result")
    begin = transport[transport.find('If pi3ut_Match("begin")'):transport.find('Procedure Pi3UpdateServe()')]
    ordered(begin, (
        "Pi3UpdateBeginFrom(#PI3_UPDATE_SOURCE_SERIAL",
        "pi3ut_ReceiveFrames(total)",
        'pi3ut_WriteText("staged ")',
    ))


def shared_primitive_contract(board: str, support: str, primitives: str) -> None:
    """Ensure identical boot helpers have one definition and both owners include it."""
    if 'XIncludeFile "RaspberryPi3/Board/pi3_boot_primitives.pbi"' not in board:
        raise ValueError("monitor does not include shared Pi3 boot primitives")
    if 'XIncludeFile "RaspberryPi3/Board/pi3_boot_primitives.pbi"' not in support:
        raise ValueError("loader/updater support does not include shared Pi3 boot primitives")
    for name in ("Pi3Park", "Pi3ReadBe32", "Pi3BootMaxCoreClock"):
        if len(re.findall(rf"Procedure(?:\.i)?\s+{name}\s*\(", primitives, re.IGNORECASE)) != 1:
            raise ValueError("shared primitive does not have one definition: " + name)
        if re.search(rf"Procedure(?:\.i)?\s+{name}\s*\(", board, re.IGNORECASE):
            raise ValueError("monitor still duplicates shared primitive: " + name)
        if re.search(rf"Procedure(?:\.i)?\s+{name}\s*\(", support, re.IGNORECASE):
            raise ValueError("loader/updater support still duplicates shared primitive: " + name)


def watchdog_progress_cases() -> int:
    """Small seam model: completed units may refresh early ownership once."""
    class Deadline:
        def __init__(self):
            self.early = False
            self.trial = False
            self.last = 0
            self.deadline = 0

        def arm_early(self, now):
            if self.early or self.trial:
                return False
            self.early = True; self.last = 0; self.deadline = now + 15
            return True

        def completed(self, token, now):
            if not self.early or self.trial or now < self.last or token <= self.last:
                return False
            self.last = token; self.deadline = now + 15
            return True

        def stop_early(self):
            if not self.early or self.trial:
                return False
            self.early = False
            return True

        def arm_trial(self, now):
            if not self.early or self.trial:
                return False
            self.early = False; self.trial = True; self.last = 0
            self.deadline = now + 15
            return True

        def expired(self, now):
            return now >= self.deadline

    cases = 0
    d = Deadline(); assert d.arm_early(0); cases += 1
    assert d.completed(1, 1); cases += 1
    assert not d.completed(1, 2); cases += 1       # repeated token refused
    assert not d.completed(0, 3); cases += 1       # no backwards progress
    assert d.expired(17); cases += 1               # stalled I/O gets no feed
    assert d.stop_early(); cases += 1
    d = Deadline(); assert d.arm_early(0); assert d.completed(1, 1)
    assert d.arm_trial(2); cases += 1              # fresh trial deadline
    assert not d.arm_trial(3); cases += 1           # only one trial arm
    assert not d.completed(2, 4); cases += 1        # no post-branch feed
    assert not d.expired(16); cases += 1            # fresh trial deadline is live
    d = Deadline(); assert d.arm_early(0); assert d.stop_early(); cases += 1
    assert d.stop_early() is False; cases += 1       # cleanup cannot repeat
    return cases


def contract(loader: str, updater: str, ab: str, watchdog: str, support: str) -> None:
    main = procedure(loader, "Main")
    # 938: the recovery choice is made BEFORE the card is touched. It used to be
    # offered only after the cold mount returned, so a card the mount could not
    # get through locked the board out entirely.
    ordered(main, (
        "Pi3UpdateBootBegin(1)",
        'Pi3Say("U: serial recovery; F: older confirmed slot; auto boot in 3 seconds")',
        "Pi3UartRead()",
        "Pi3BootStorage(1)",
    ))
    if "Pi3UpdateBootStart(" in main:
        raise ValueError("the loader runs the whole cold sequence again, so its "
                         "window is back behind storage")
    recovery = main[main.find("If recovery <> 0"):main.find("If Pi3BootStorage(1) = 0")]
    if "Pi3UpdateRegisterMount(@Pi3LoaderMount)" not in recovery:
        raise ValueError("recovery is served with no way to mount the card later")
    if "Pi3UpdateServe()" not in recovery:
        raise ValueError("recovery no longer serves the prompt")
    if recovery.find("Pi3UpdateServe()") < recovery.find("Pi3UpdateRegisterMount"):
        raise ValueError("recovery serves before its mount owner is registered")
    if "NOT mounted" not in recovery or "power-cycle" not in recovery:
        raise ValueError("the recovery state does not say on screen what it is, "
                         "so a static screen is all an operator gets")
    ordered(main, (
        'Pi3Say("L0: arm 15-second pre-branch watchdog")',
        "Pi3UpdateBootProgressHandler(@Pi3LoaderBootProgress)",
        "Pi3UpdateWatchdogArmWindow()",
        "Pi3UpdateLoad",
        'Pi3Say("L5: write handoff identity")',
        "Pi3UpdatePrepareHandoff",
        'Pi3Say("L6: start fresh trial watchdog; branch to payload")',
        "Pi3BootWorkEnd()",
        "Pi3UpdateWatchdogBeginTrial()",
        "Pi3UpdateEnter()",
    ))
    if "Pi3UpdateWatchdogArm()" in main:
        raise ValueError("loader feeds/restarts watchdog after slot load")
    boot_start = procedure(support, "Pi3UpdateBootStart")
    if "ProcedureReturn Pi3BootStorage(display)" not in boot_start:
        raise ValueError("cold loader no longer enters the covered storage owner")
    storage = procedure(support, "Pi3BootStorage")
    ordered(storage, (
        'Pi3Say("E0: arm early 15-second storage watchdog")',
        "Pi3UpdateWatchdogArmEarly()",
        'Pi3Say("E1: set stock ARM 1200000000 Hz and CORE 400000000 Hz")',
        "Pi3BootSetStockClocks()",
        "Pi3BootMaxCoreClock()",
        "Pi3BootStockArmActual()",
        "Pi3BootStockCoreActual()",
        'Pi3Say("E2: stock clocks requested and read back; SD clock ceiling ready")',
        'Pi3Say("E3: initialize native SDHOST")',
        "Pi3SdInit(",
        'Pi3Say("E4: native SDHOST ready")',
        'Pi3Say("E5: mount and verify A/B volume")',
        "Pi3UpdateMount()",
        "Pi3UpdateWatchdogStopEarly()",
        'Pi3Say("E6: early storage watchdog stopped")',
    ))
    if storage.count("Pi3UpdateWatchdogArmEarly()") != 1 or storage.count("Pi3UpdateWatchdogStopEarly()") != 1:
        raise ValueError("early storage watchdog must have one owner and one cleanup")
    progress = procedure(loader, "Pi3LoaderBootProgress")
    for phase in range(1, 5):
        if f"Case {phase}" not in progress or f'L{phase}:' not in progress:
            raise ValueError(f"loader lost serial/LED phase L{phase}")
    if "Pi3StatusLed(phase & 1)" not in progress:
        raise ValueError("loader lost persistent LED phase state")
    ab_load = procedure(ab, "Pi3UpdateLoad")
    ab_place = procedure(ab, "pi3UpPlace")
    for phase, body in ((1, ab_load), (2, ab_load), (3, ab_place), (4, ab_place)):
        if f"BootProgress({phase})" not in body:
            raise ValueError(f"A/B owner lost phase {phase} at its blocking boundary")
    ordered(ab_load, (
        "Pi3UpBootProgress(1)",
        "pi3UpVerifySlot(slot)",
        "Pi3UpBootProgress(2)",
        "pi3UpState(slot, #PI3_UPDATE_TRIED)",
    ))
    ordered(ab_place, (
        "pi3UpBootProgress(3)",
        "pi3UpVerifySlot(slot)",
        "pi3UpBootProgress(4)",
        "While offset<bytes",
        "take=bytes-offset",
        "If take>4096",
        "For n=offset To offset+take-1",
        "Pi3UpdateWorkProgress(take)",
    ))
    progress_dispatch = procedure(ab, "pi3UpBootProgress")
    if "ProcedureReturn pi3_up_boot_progress()" not in progress_dispatch:
        raise ValueError("A/B owner lost the registered progress callback dispatch")
    window = procedure(watchdog, "Pi3UpdateWatchdogArmWindow")
    executable = "\n".join(line.split(";", 1)[0] for line in window.splitlines())
    if re.search(r"\b(for|next|while|wend|repeat|until)\b", executable, re.IGNORECASE):
        raise ValueError("pre-branch watchdog owner hides a wait loop")
    if window.count("$5A0F0000") != 1 or window.count("p3uwWrite($3F10001C") != 1:
        raise ValueError("pre-branch watchdog must be armed exactly once")
    early = procedure(watchdog, "Pi3UpdateWatchdogArmEarly")
    early_stop = procedure(watchdog, "Pi3UpdateWatchdogStopEarly")
    for label, body in (("early arm", early), ("early stop", early_stop)):
        executable = "\n".join(line.split(";", 1)[0] for line in body.splitlines())
        if re.search(r"\b(for|next|while|wend|repeat|until)\b", executable, re.IGNORECASE):
            raise ValueError(label + " hides a wait loop")
    if early.count("$5A0F0000") != 1 or early.count("p3uwWrite($3F10001C") != 1:
        raise ValueError("early storage watchdog must be armed exactly once")
    if early_stop.count("p3uwWrite($3F10001C,$5A000102)") != 1:
        raise ValueError("early storage watchdog has no positive stop")
    arm = procedure(watchdog, "Pi3UpdateWatchdogArm")
    if "pi3_update_watchdog_window_owned" not in arm or "ProcedureReturn (p3uwRead($3F10001C) & $30)=$20" not in arm:
        raise ValueError("post-load ownership check can feed the existing window")
    if "Pi3UpdateWatchdog" in progress:
        raise ValueError("loader phase callback must observe progress, never feed a watchdog")
    # Exception vectors must exist BEFORE anything that can fault, which on this
    # boot chain is everything after the port. Until they did, a synchronous
    # abort and a wedge were the same silence on the wire.
    begin = procedure(support, "Pi3UpdateBootBegin")
    ordered(begin, (
        "Pi3UartInit(",
        "Pi3InstallFaultVectors()",
        "Pi3LoaderBootMemory()",
    ))
    if "Pi3BootStorage" in begin:
        raise ValueError("the begin phase touches storage, so the window it "
                         "exists to precede is back behind the card")
    whole = procedure(support, "Pi3UpdateBootStart")
    if whole.find("Pi3UpdateBootBegin(display)") > whole.find("Pi3BootStorage(display)"):
        raise ValueError("the candidate's cold sequence runs storage before the "
                         "port, vectors and memory are up")
    installer = procedure(support, "Pi3InstallFaultVectors")
    if "ExceptionSetReporter(@Pi3FaultReport)" not in installer or "ExceptionInstall()" not in installer:
        raise ValueError("the fault installer no longer registers a reporter or installs vectors")
    report = procedure(support, "Pi3FaultReport")
    for register in ("ExceptionSlot()", "ExceptionEsr()", "ExceptionElr()",
                     "ExceptionFar()", "ExceptionSpsr()"):
        if register not in report:
            raise ValueError("the fault report no longer prints " + register)
    if "Pi3Say" in report:
        raise ValueError("the fault report draws to the framebuffer, which may be "
                         "exactly what faulted; it must write only to the port")
    up_main = procedure(updater, "Main")
    if up_main.find('pi3ut_WriteLine("C0: candidate Main entered")') < 0:
        raise ValueError("candidate has no earliest source-level entry evidence")
    if up_main.find('pi3ut_WriteLine("C0: candidate Main entered")') > up_main.find("Pi3UpdateBootStart(0)"):
        raise ValueError("candidate entry evidence occurs after a blocking boot call")


def compile_image(compiler: pathlib.Path, source: pathlib.Path, output: pathlib.Path) -> None:
    """Compile one board image, counted: a gate build is still a build."""
    def run() -> None:
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(
            [str(compiler), "--compile", str(source.relative_to(ROOT)).replace("\\", "/"),
             "-t", "pi3", "-o", str(output), "-s"],
            cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if result.returncode or not output.is_file():
            raise SystemExit("Pi3 loader window compile failed:\n" + result.stdout)

    pi3_gate_build.compile_counted(
        run, source, output, compiler=compiler,
        by="tools/pi3_loader_window_check.py", root=ROOT,
    )


def emitted_storage_cases(loader_image: pathlib.Path) -> int:
    """Run the real storage coordinator; hardware owners are explicit hooks."""
    load_address = 0x80000
    sym = a64_base.parse_symbols(loader_image)
    blob = loader_image.read_bytes()
    module = a64_base.load_interp(a64_base.INTERP)
    # Pi3BootCurrentCoreClock and Pi3SayClockGap are hardware owners like the
    # rest: one is a firmware property call, the other writes to the port. They
    # are hooked rather than executed so this gate keeps answering for every
    # board value it depends on, in one place, next to the claims it makes.
    hooks = tuple(name.lower() for name in (
        "Pi3Say", "Pi3UpdateWatchdogArmEarly", "Pi3BootWorkBegin", "Pi3BootWorkEnd",
        "Pi3UpdateMountProgressHandler", "Pi3BootSetStockClocks",
        "Pi3BootMaxCoreClock", "Pi3BootStockArmActual", "Pi3BootStockCoreActual",
        "Pi3BootStockClockIsMeasured", "Pi3BootCurrentCoreClock", "Pi3SayClockGap", "Pi3FaultHex",
        "Pi3SdInit", "Pi3UpdateConfigure", "Pi3UpdateMount",
        "Pi3UpdateWatchdogStopEarly",
    ))

    def run(overrides: dict[str, int]) -> tuple[int, list[str]]:
        cpu = module.A64()
        cpu.memory = {load_address + i: value for i, value in enumerate(blob)}
        cpu.sp = 0x200000
        cpu.pc = load_address + sym["pi3bootstorage"]
        cpu.x[0] = 1
        cpu.x[30] = a64_base.RETURN_PC
        addresses = {load_address + sym[name]: name for name in hooks}
        events: list[str] = []

        def text_at(address: int) -> str:
            data = bytearray()
            for index in range(256):
                value = cpu.memory.get(address + index, 0)
                if value == 0:
                    break
                data.append(value)
            return data.decode("ascii")

        for _ in range(500000):
            if cpu.pc == a64_base.RETURN_PC:
                return cpu.x[0], events
            name = addresses.get(cpu.pc)
            if name:
                if name == "pi3say":
                    events.append("say:" + text_at(cpu.x[0]))
                    result = 1
                elif name == "pi3faulthex":
                    events.append("faulthex:" + text_at(cpu.x[0]))
                    result = overrides.get(name, 1)
                else:
                    events.append(name)
                    result = overrides.get(name, 1)
                    if name == "pi3bootmaxcoreclock" and name not in overrides:
                        result = 500000000
                    # Same as the maximum unless a case says otherwise, so the
                    # ordinary path reports no clock gap and the marker sequence
                    # stays the one the boundaries below are written against.
                    if name == "pi3bootcurrentcoreclock" and name not in overrides:
                        result = 500000000
                cpu.x[0] = result
                cpu.pc = cpu.x[30]
            else:
                cpu.step()
        raise AssertionError("Pi3BootStorage did not return")

    result, events = run({})
    expected = [
        "say:E0: arm early 15-second storage watchdog",
        "pi3updatewatchdogarmearly",
        "pi3bootworkbegin",
        "say:E1: set stock ARM 1200000000 Hz and CORE 400000000 Hz",
        "pi3bootsetstockclocks",
        "pi3bootmaxcoreclock",
        "pi3bootstockclockismeasured",
        "pi3bootstockarmactual",
        "faulthex:ARM measured Hz ",
        "pi3bootstockcoreactual",
        "faulthex:CORE measured Hz ",
        "say:E2: stock clocks requested and read back; SD clock ceiling ready",
        # Read once, between E2 and E3, and reported only when it differs from
        # the rate the divisor assumed. Here they agree, so no E2a line.
        "pi3bootcurrentcoreclock",
        "say:E3: initialize native SDHOST",
        "pi3sdinit",
        "say:E4: native SDHOST ready",
        "pi3updateconfigure",
        "say:E5: mount and verify A/B volume",
        "pi3updatemountprogresshandler",
        "pi3updatemount",
        "pi3updatemountprogresshandler",
        "pi3bootworkend",
        "pi3updatewatchdogstopearly",
        "say:E6: early storage watchdog stopped",
    ]
    if result != 1 or events != expected:
        raise AssertionError((result, events))
    result, events = run({"pi3bootstockclockismeasured": 0})
    if result != 1 or "faulthex:ARM configured Hz " not in events or "faulthex:CORE configured Hz " not in events:
        raise AssertionError(("configured clock labels not reported", events))
    # A core clock that differs from the assumed one must be SAID, not silently
    # tolerated: a card clock well under the 25 MHz asked for is the difference
    # between a mount that fits a watchdog and one that does not.
    result, events = run({"pi3bootcurrentcoreclock": 250000000})
    if result != 1 or "pi3sayclockgap" not in events:
        raise AssertionError(("clock gap not reported", events))
    result, events = run({"pi3bootcurrentcoreclock": 0})
    if result != 1 or not any(e.startswith("say:E2a") for e in events):
        raise AssertionError(("unreadable core clock not reported", events))
    for owner, value in (("pi3updatewatchdogarmearly", 0),
                         ("pi3bootsetstockclocks", 0),
                         ("pi3bootmaxcoreclock", 0), ("pi3sdinit", 0)):
        result, events = run({owner: value})
        if result != 0:
            raise AssertionError((owner, "refusal returned success"))
        armed = events.count("pi3updatewatchdogarmearly")
        stopped = events.count("pi3updatewatchdogstopearly")
        if owner == "pi3updatewatchdogarmearly":
            if armed != 1 or stopped != 0:
                raise AssertionError((owner, events))
        elif armed != 1 or stopped != 1:
            raise AssertionError((owner, events))
    return 6


def emitted_updater_cases(updater_image: pathlib.Path) -> int:
    """Check symbols in an already-built updater image without compiling it."""
    if not updater_image.is_file() or updater_image.stat().st_size < 1:
        raise SystemExit("missing updater image: " + str(updater_image))
    symbols = a64_base.parse_symbols(updater_image)
    required = ("main", "pi3updatemount", "pi3updatecommitfrom")
    missing = [name for name in required if name not in symbols]
    if missing:
        raise SystemExit("updater image missing symbols: " + ", ".join(missing))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER") or
                        r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
    parser.add_argument("--source-only", action="store_true",
                        help="run source contracts and mutants without compiling")
    parser.add_argument("--loader-image", type=pathlib.Path,
                        help="use an already-built loader image; requires --updater-image")
    parser.add_argument("--updater-image", type=pathlib.Path,
                        help="use an already-built updater image; requires --loader-image")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if (args.loader_image is None) != (args.updater_image is None):
        parser.error("--loader-image and --updater-image must be supplied together")
    if args.source_only and (args.loader_image is not None or args.updater_image is not None):
        parser.error("--source-only cannot be combined with prebuilt images")
    compiler = pathlib.Path(args.compiler).resolve()
    if not args.source_only and args.loader_image is None and not compiler.is_file():
        raise SystemExit("missing unified compiler: " + str(compiler))
    originals = tuple(path.read_text(encoding="utf-8") for path in (LOADER, UPDATER, AB, WATCHDOG, SUPPORT))
    transport = TRANSPORT.read_text(encoding="utf-8")
    primitives = PRIMITIVES.read_text(encoding="utf-8")
    monitor = MONITOR.read_text(encoding="utf-8")
    contract(*originals)
    progress_cases = watchdog_progress_cases()
    recovery_transport_contract(transport)
    shared_primitive_contract(monitor, originals[4], primitives)
    mutants = (
        (originals[0].replace("If Pi3UpdateWatchdogArmWindow()=0", "If Pi3UpdateWatchdogArm()=0", 1), *originals[1:]),
        (originals[0].replace("Pi3UpdateBootProgressHandler(@Pi3LoaderBootProgress)", "Pi3NoBootProgress()", 1), *originals[1:]),
        (originals[0].replace('Pi3Say("L5: write handoff identity")', 'Pi3Say("stage missing")', 1), *originals[1:]),
        (originals[0], originals[1].replace('pi3ut_WriteLine("C0: candidate Main entered")', "", 1), originals[2], originals[3], originals[4]),
        (originals[0], originals[1], originals[2].replace("Pi3UpBootProgress(2)", "Pi3UpBootProgress(1)", 1), originals[3], originals[4]),
        (originals[0], originals[1], originals[2], originals[3].replace("$5A0F0000", "$5A0E0000", 1), originals[4]),
        (*originals[:4], originals[4].replace("Pi3UpdateWatchdogArmEarly()=0", "Pi3NoBootProgress()=0", 1)),
        (*originals[:4], originals[4].replace('Pi3Say("E3: initialize native SDHOST")', 'Pi3Say("missing")', 1)),
        (*originals[:4], originals[4].replace("Pi3UpdateWatchdogStopEarly()=0", "Pi3NoBootProgress()=0", 1)),
        # 937: the vectors must be installed, and installed early.
        (*originals[:4], originals[4].replace("If Pi3InstallFaultVectors() = 0", "If 1 = 0", 1)),
        (*originals[:4], originals[4].replace("ExceptionSetReporter(@Pi3FaultReport)", "", 1)),
        (*originals[:4], originals[4].replace("Pi3FaultHex(\"  ESR  \", ExceptionEsr())", "", 1)),
        # 938: the window must not go back behind storage, and recovery must
        # keep both its mount owner and its explanation of itself.
        (originals[0].replace("If Pi3UpdateBootBegin(1) = 0", "If Pi3UpdateBootStart(1) = 0", 1), *originals[1:]),
        (originals[0].replace("Pi3UpdateRegisterMount(@Pi3LoaderMount)", "Pi3NoMountOwner()", 1), *originals[1:]),
        (originals[0].replace("The card is NOT mounted", "The card is fine", 1), *originals[1:]),
    )
    for index, mutant in enumerate(mutants, 1):
        try:
            contract(*mutant)
        except ValueError:
            continue
        raise SystemExit(f"Pi3 loader window mutant {index} survived")
    if args.source_only:
        print("PASS: source-only mode; no compiler or emitted image checks")
        print(f"PASS: {progress_cases} watchdog progress seam cases (mock hardware model)")
        print(f"PASS: {len(mutants)} hostile structural mutants rejected")
        return 0
    if args.loader_image is not None:
        loader_image = args.loader_image.resolve()
        updater_image = args.updater_image.resolve()
        emitted_cases = emitted_storage_cases(loader_image)
        updater_cases = emitted_updater_cases(updater_image)
        print("PASS: static watchdog ownership and L0-L6/C0 source contract (no hardware claim)")
        print("PASS: static recovery transcript mount/status/begin/commit boundaries (no hardware claim)")
        print("PASS: shared Pi3 boot primitive ownership is unique")
        print(f"PASS: {emitted_cases} emitted early-storage success/refusal cases (interpreter hooks, no silicon claim)")
        print(f"PASS: {progress_cases} watchdog progress seam cases (mock hardware model)")
        print(f"PASS: {updater_cases} emitted updater symbol checks (prebuilt image; no compile/count)")
        print(f"PASS: {len(mutants)} hostile structural mutants rejected")
        print(f"Loader: {loader_image.stat().st_size} bytes; SHA256 {hashlib.sha256(loader_image.read_bytes()).hexdigest().upper()}")
        print(f"Updater: {updater_image.stat().st_size} bytes; SHA256 {hashlib.sha256(updater_image.read_bytes()).hexdigest().upper()}")
        return 0
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-loader-window-") as temp_name:
        temp = pathlib.Path(temp_name)
        loader_image = temp / "kernel8.img"
        updater_image = temp / "updater.img"
        compile_image(compiler, LOADER, loader_image)
        compile_image(compiler, UPDATER, updater_image)
        emitted_cases = emitted_storage_cases(loader_image)
        print("PASS: static watchdog ownership and L0-L6/C0 source contract (no hardware claim)")
        print("PASS: static recovery transcript mount/status/begin/commit boundaries (no hardware claim)")
        print("PASS: shared Pi3 boot primitive ownership is unique")
        print(f"PASS: {emitted_cases} emitted early-storage success/refusal cases (interpreter hooks, no silicon claim)")
        print("Expected recovery transcript:")
        for line in EXPECTED_RECOVERY_TRANSCRIPT:
            print("  " + line)
        print(f"PASS: {len(mutants)} hostile structural mutants rejected")
        print(f"Loader: {loader_image.stat().st_size} bytes; SHA256 {hashlib.sha256(loader_image.read_bytes()).hexdigest().upper()}")
        print(f"Updater: {updater_image.stat().st_size} bytes; SHA256 {hashlib.sha256(updater_image.read_bytes()).hexdigest().upper()}")
        print(f"Compiler SHA256: {hashlib.sha256(compiler.read_bytes()).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
