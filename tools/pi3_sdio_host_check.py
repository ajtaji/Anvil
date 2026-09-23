#!/usr/bin/env python3
"""Emitted-code gate for the Pi 3 SDHCI/SDIO transport.

Uses a register-level model around the real compiled Pi3Sdio* procedures. The
model accepts only aligned 32-bit accesses to the Arasan SDHCI window and the
specific GPIO34..39 mux/pull registers used by the Pi 3 Wi-Fi wiring. It does
not model a real radio, board-profile power/reset, or RF behavior.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base

ROOT = base.ROOT
PROBE = ROOT / "RaspberryPi3" / "Tests" / "sdio_gate.pi3"
SDHCI = 0x3F300000
GPIO = 0x3F200000
CLK = 0x2C
ARG = 0x08
CMD = 0x0C
RESP0 = 0x10
BUFFER = 0x20
PRESENT = 0x24
CONTROL0 = 0x28
CONTROL1 = 0x2C
INT_STATUS = 0x30
INT_ENABLE = 0x34
SIG_ENABLE = 0x38
CAPS0 = 0x40
HOSTVER = 0xFC
INT_RESPONSE = 0x1
INT_DATA_END = 0x2
INT_SPACE = 0x10
INT_DATA = 0x20
INT_ERROR_MASK = 0xFFFF8000
RESET_ALL = 0x01000000
RESET_CMD = 0x02000000
RESET_DATA = 0x04000000
CLK_STABLE = 2
CLK_CARD_EN = 4
R5_BAD = 0xCB00


def compile_gate(compiler: Path) -> tuple[Path, dict[str, int], bytes, tempfile.TemporaryDirectory]:
    temp = tempfile.TemporaryDirectory(prefix="pi3-sdio-host-")
    # Caller owns the TemporaryDirectory lifetime through returned Path.parent.
    work = Path(temp.name)
    image = work / "pi3_sdio_gate.img"
    env = dict(os.environ, PMF_ROOT=str(ROOT))
    result = subprocess.run(
        [str(compiler), "--compile", PROBE.relative_to(ROOT).as_posix(),
         "-t", "pi3", "--entry-returns", "--load-addr", hex(base.LOAD),
         "--stack-addr", hex(base.STACK), "-s", "-o", str(image)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    if result.returncode or not image.is_file() or "pmfc: OK" not in result.stdout:
        temp.cleanup()
        raise AssertionError("Pi3 SDIO gate compile failed:\n" + result.stdout + result.stderr)
    symbols: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            symbols[name.strip().lower()] = int(value.strip(), 0)
    return image, symbols, image.read_bytes(), temp


def _procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$", source)
    if not match:
        raise AssertionError(f"missing production procedure {name}")
    return match.group(0)


def _compile_mailbox_gate(compiler: Path):
    mmu = (ROOT / "RaspberryPi3" / "Lib" / "mmu.pi3").read_text(encoding="utf-8")
    mailbox = (ROOT / "RaspberryPi3" / "Lib" / "mailbox.pbi").read_text(encoding="utf-8")
    constants = []
    for name in ("MMU3_NC_MAX", "MMU3_TABLE_BASE", "MMU3_ATTR_NC", "MMU3_PERIPH_BASE"):
        found = re.search(rf"(?m)^#{name}\s*=\s*[^\r\n]+", mmu)
        if not found:
            raise AssertionError(f"missing MMU constant {name}")
        constants.append(found.group(0))
    globals_ = []
    for declaration in (
        "Global Dim mmu3_nc_lo.i[#MMU3_NC_MAX]",
        "Global Dim mmu3_nc_hi.i[#MMU3_NC_MAX]",
        "Global mmu3_ncN.i",
        "Global mmu3_nc_ready.i",
    ):
        if declaration not in mmu:
            raise AssertionError(f"missing NC state declaration: {declaration}")
        globals_.append(declaration)
    procs = [
        _procedure(mmu, "MmuCurrentEl"), _procedure(mmu, "MmuAtEl3"),
        _procedure(mmu, "MmuSctlrEl2"), _procedure(mmu, "MmuSctlrEl3"),
        _procedure(mmu, "MmuSctlr"),
        _procedure(mmu, "MmuDescriptorL2Low"), _procedure(mmu, "MmuAddNc"),
        _procedure(mmu, "MmuNcCount"), _procedure(mmu, "MmuIsNcRange"),
        _procedure(mailbox, "Pi3MailboxContextState"),
        _procedure(mailbox, "Pi3MailboxContext"),
        _procedure(mailbox, "Pi3MailboxBufferContext"),
    ]
    harness = r'''Global gate_case.i
Global gate_lo.i
Global gate_hi.i
Global gate_bytes.i
Procedure.i Main()
  Select gate_case
    Case 1 : ProcedureReturn Pi3MailboxContextState()
    Case 2 : ProcedureReturn Pi3MailboxContext()
    Case 3 : ProcedureReturn Pi3MailboxBufferContext(gate_lo, gate_bytes)
    Case 4 : MmuAddNc(gate_lo, gate_hi) : ProcedureReturn MmuNcCount()
    Case 5 : ProcedureReturn MmuNcCount()
  EndSelect
  ProcedureReturn 0
EndProcedure
'''
    source = "\n".join(constants + globals_ + procs) + "\n" + harness
    temp = tempfile.TemporaryDirectory(prefix="pi3-mailbox-nc-")
    work = Path(temp.name)
    src = work / "mailbox_nc_gate.pi3"
    image = work / "mailbox_nc_gate.img"
    src.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [str(compiler), "--compile", str(src), "-t", "pi3", "--entry-returns",
         "--load-addr", hex(base.LOAD), "--stack-addr", hex(base.STACK),
         "-s", "-o", str(image)], cwd=ROOT, capture_output=True, text=True,
        check=False)
    if result.returncode or not image.is_file() or "pmfc: OK" not in result.stdout:
        temp.cleanup()
        raise AssertionError("mailbox/NC emitted gate compile failed:\n" +
                             result.stdout + result.stderr)
    symbols = base.parse_symbols(image)
    return image, symbols, image.read_bytes(), temp


def _mailbox_case(cpu, symbols, case: int, lo: int = 0x01200000,
                  hi: int = 0x01200FFF, nbytes: int = 256) -> int:
    for name, value in (("gate_case", case), ("gate_lo", lo),
                        ("gate_hi", hi), ("gate_bytes", nbytes)):
        addr = symbols["global_" + name]
        cpu.raw_store(addr, value, 8)
    cpu.pc = base.LOAD + symbols["main"]
    cpu.x[30] = base.RETURN_PC
    for _ in range(250_000):
        if cpu.pc == base.RETURN_PC:
            value = cpu.x[0]
            return value - (1 << 64) if value & (1 << 63) else value
        cpu.step()
    raise AssertionError(f"mailbox/NC emitted case {case} did not return")


def mailbox_nc_checks(compiler: Path) -> int:
    image, sym, blob, temp = _compile_mailbox_gate(compiler)
    checks = 0
    mpidr = 0xD51800A0
    sctlr2 = 0xD51C1000
    sctlr3 = 0xD51E1000

    def fresh(el: int = 3, sctlr: int = 0, core: int = 0):
        cpu = base.load_interp(base.INTERP).A64()
        cpu.memory = {base.LOAD + i: b for i, b in enumerate(blob)}
        cpu.sp = base.STACK
        cpu.enable_system_registers(el=el, preset={mpidr: core,
            sctlr2: sctlr, sctlr3: sctlr})
        return cpu

    cold = fresh()
    assert _mailbox_case(cold, sym, 1) == 1
    assert _mailbox_case(cold, sym, 2) == 1
    assert _mailbox_case(cold, sym, 3, nbytes=8) == 1
    checks += 3

    for el, sctlr, core in ((3, 0, 1), (2, 5, 0), (3, 1, 0), (3, 4, 0)):
        bad = fresh(el, sctlr, core)
        assert _mailbox_case(bad, sym, 1) == 0, (el, sctlr, core)
        assert _mailbox_case(bad, sym, 2) == 0, (el, sctlr, core)
        assert _mailbox_case(bad, sym, 3) == 0, (el, sctlr, core)
        checks += 3

    cached = fresh(3, 5)
    lo, hi = 0x01200000, 0x01200FFF
    assert _mailbox_case(cached, sym, 2) == 0  # cold-only API stays closed
    assert _mailbox_case(cached, sym, 3, lo, hi, 256) == 0  # no NC mapping yet
    assert _mailbox_case(cached, sym, 4, lo, hi) == 1  # real MmuAddNc
    assert _mailbox_case(cached, sym, 5) == 1
    # Seed the actual L2 low descriptor read by MmuIsNcRange, then freeze the
    # pre-MMU range set as MmuUp does on the production path.
    table = 0x01F10000
    block = lo & ~0x1FFFFF
    slot = block >> 21
    cached.raw_store(table + 4096 + slot * 8, block | 0x70D, 8)
    cached.raw_store(sym["global_mmu3_nc_ready"], 1, 8)
    assert _mailbox_case(cached, sym, 3, lo + 16, hi, 64) == 1
    assert _mailbox_case(cached, sym, 3, hi - 7, hi, 16) == 0
    assert _mailbox_case(cached, sym, 3, lo - 1, hi, 16) == 0
    assert _mailbox_case(cached, sym, 4, 0x01400000, 0x01400FFF) == 1
    assert _mailbox_case(cached, sym, 5) == 1  # additions are frozen after MmuUp
    assert _mailbox_case(cached, sym, 3, lo + 16, hi, 64) == 1
    checks += 10

    wrong_descriptor = fresh(3, 5)
    assert _mailbox_case(wrong_descriptor, sym, 4, lo, hi) == 1
    wrong_descriptor.raw_store(table + 4096 + slot * 8, block | 0x705, 8)
    wrong_descriptor.raw_store(sym["global_mmu3_nc_ready"], 1, 8)
    assert _mailbox_case(wrong_descriptor, sym, 3, lo + 16, hi, 64) == 0
    wrong_descriptor.raw_store(table + 4096 + slot * 8, block | 0x70D, 8)
    assert _mailbox_case(wrong_descriptor, sym, 3, 0x3F000000, 0x3F000FFF, 16) == 0
    checks += 3
    temp.cleanup()
    return checks


def _compile_gpio_state_gate(compiler: Path):
    mailbox = (ROOT / "RaspberryPi3" / "Lib" / "mailbox.pbi").read_text(encoding="utf-8")
    declarations = [
        "Global Dim pi3_property.l[16]",
        "Global pi3_mailbox_outstanding.i",
        "Global gate_reply_word.i",
        "Global gate_reply_tag.i",
        "Global gate_reply_capacity.i",
        "Global gate_reply_gpio.i",
        "Global gate_overall_ok.i",
        "Global gate_calls.i",
    ]
    for declaration in declarations[:2]:
        if declaration not in mailbox:
            raise AssertionError(f"missing production mailbox state declaration: {declaration}")
    procedure = _procedure(mailbox, "Pi3FirmwareGpioSetState")
    harness = r'''Global gate_gpio.i
Global gate_state.i
Procedure.i Pi3MailboxCall(buffer.i, bytes.i)
  gate_calls = gate_calls + 1
  If bytes <> 32 : ProcedureReturn 0 : EndIf
  PokeL(buffer + 4, Bool(gate_overall_ok <> 0) * $80000000)
  PokeL(buffer + 8, gate_reply_tag)
  PokeL(buffer + 12, gate_reply_capacity)
  PokeL(buffer + 16, gate_reply_word)
  PokeL(buffer + 20, gate_reply_gpio)
  ProcedureReturn gate_overall_ok
EndProcedure
Procedure.i Main()
  ProcedureReturn Pi3FirmwareGpioSetState(gate_gpio, gate_state)
EndProcedure
'''
    source = "\n".join(declarations) + "\n" + procedure + "\n" + harness
    temp = tempfile.TemporaryDirectory(prefix="pi3-gpio-state-")
    work = Path(temp.name)
    src = work / "gpio_state_gate.pi3"
    image = work / "gpio_state_gate.img"
    src.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [str(compiler), "--compile", str(src), "-t", "pi3", "--entry-returns",
         "--load-addr", hex(base.LOAD), "--stack-addr", hex(base.STACK),
         "-s", "-o", str(image)], cwd=ROOT, capture_output=True, text=True,
        check=False)
    if result.returncode or not image.is_file() or "pmfc: OK" not in result.stdout:
        temp.cleanup()
        raise AssertionError("GPIO state emitted gate compile failed:\n" +
                             result.stdout + result.stderr)
    return image, base.parse_symbols(image), image.read_bytes(), temp


def _gpio_state_case(cpu, symbols, *, gpio=129, state=0, outstanding=0,
                     overall=1, tag=0x38041, capacity=8,
                     reply=8, returned_gpio=0) -> tuple[int, int]:
    values = {
        "gate_gpio": gpio, "gate_state": state,
        "pi3_mailbox_outstanding": outstanding,
        "gate_overall_ok": overall, "gate_reply_tag": tag,
        "gate_reply_capacity": capacity, "gate_reply_word": reply,
        "gate_reply_gpio": returned_gpio, "gate_calls": 0,
    }
    for name, value in values.items():
        address = symbols["global_" + name]
        cpu.store(address, value, 8)
    cpu.pc = base.LOAD + symbols["main"]
    cpu.x[30] = base.RETURN_PC
    for _ in range(100_000):
        if cpu.pc == base.RETURN_PC:
            result = cpu.x[0]
            if result & (1 << 63):
                result -= 1 << 64
            return result, cpu.load(symbols["global_gate_calls"], 8)
        cpu.step()
    raise AssertionError("Pi3FirmwareGpioSetState emitted gate did not return")


def gpio_state_reply_checks(compiler: Path) -> int:
    image, sym, blob, temp = _compile_gpio_state_gate(compiler)
    a64 = base.load_interp(base.INTERP)

    def run(**kwargs) -> tuple[int, int]:
        cpu = a64.A64()
        cpu.memory = {base.LOAD + i: b for i, b in enumerate(blob)}
        cpu.sp = base.STACK
        cpu.enable_system_registers(el=3)
        return _gpio_state_case(cpu, sym, **kwargs)

    checks = 0
    # Firmware versions differ on whether the successful 8-byte tag response
    # length sets bit 31. Overall property success and the returned GPIO status
    # remain mandatory in both cases.
    assert run(reply=8) == (1, 1)
    assert run(reply=0x80000008) == (1, 1)
    checks += 2
    for kwargs in (
        {"overall": 0},
        {"tag": 0x38042},
        {"capacity": 4},
        {"reply": 0},
        {"reply": 0x80000000},
        {"reply": 0x80000010},
        {"returned_gpio": 129},
        {"gpio": 127},
        {"gpio": 136},
        {"state": 2},
        {"outstanding": 1},
    ):
        result, calls = run(**kwargs)
        assert result == 0, kwargs
        assert calls == (0 if kwargs.get("gpio", 129) not in range(128, 136) or
                         kwargs.get("state", 0) not in (0, 1) or
                         kwargs.get("outstanding", 0) != 0 else 1), (kwargs, calls)
        checks += 2
    temp.cleanup()
    return checks


def _compile_gpio_config_gate(compiler: Path):
    mailbox = (ROOT / "RaspberryPi3" / "Lib" / "mailbox.pbi").read_text(encoding="utf-8")
    declarations = [
        "Global Dim pi3_property.l[16]",
        "Global pi3_mailbox_outstanding.i",
    ]
    for declaration in declarations[:2]:
        if declaration not in mailbox:
            raise AssertionError(f"missing production mailbox state declaration: {declaration}")
    procedure = _procedure(mailbox, "Pi3FirmwareGpioConfigureOutput")
    harness = r'''Global gate_gpio.i
Global gate_state.i
Global gate_calls.i
Global gate_bad_call.i
Global gate_reply_form.i
Global Dim gate_log.l[16]
Procedure.i Pi3MailboxCall(buffer.i, bytes.i)
  Protected call.i
  Protected off.i
  call = gate_calls
  gate_calls = gate_calls + 1
  gate_log[call * 8] = bytes
  gate_log[call * 8 + 1] = PeekL(buffer + 8)
  gate_log[call * 8 + 2] = PeekL(buffer + 12)
  gate_log[call * 8 + 3] = PeekL(buffer + 20)
  gate_log[call * 8 + 4] = PeekL(buffer + 24)
  gate_log[call * 8 + 5] = PeekL(buffer + 28)
  gate_log[call * 8 + 6] = PeekL(buffer + 36)
  gate_log[call * 8 + 7] = PeekL(buffer + 40)
  If call = 0
    off = 0
    PokeL(buffer + 4, $80000000)
    PokeL(buffer + 8, $30043) : PokeL(buffer + 12, 20)
    PokeL(buffer + 16, 20) : PokeL(buffer + 20, Bool(gate_bad_call = 1))
    PokeL(buffer + 24, 1) : PokeL(buffer + 28, $A5)
    PokeL(buffer + 32, 0) : PokeL(buffer + 36, 1)
    PokeL(buffer + 40, 0)
  Else
    off = 1
    PokeL(buffer + 4, $80000000)
    PokeL(buffer + 8, $38043) : PokeL(buffer + 12, 24)
    PokeL(buffer + 16, 24) : PokeL(buffer + 20, Bool(gate_bad_call = 2))
  EndIf
  If gate_bad_call = 3 And call = 0 : PokeL(buffer + 4, 0) : EndIf
  If gate_bad_call = 4 And call = 0 : PokeL(buffer + 8, $30044) : EndIf
  If gate_bad_call = 5 And call = 0 : PokeL(buffer + 12, 16) : EndIf
  If gate_bad_call = 6 And call = 0 : PokeL(buffer + 16, 0) : EndIf
  If gate_bad_call = 7 And call = 1 : PokeL(buffer + 4, 0) : EndIf
  If gate_bad_call = 8 And call = 1 : PokeL(buffer + 8, $38044) : EndIf
  If gate_bad_call = 9 And call = 1 : PokeL(buffer + 12, 20) : EndIf
  If gate_bad_call = 10 And call = 1 : PokeL(buffer + 16, 0) : EndIf
  If gate_bad_call = 11 And call = 1 : PokeL(buffer + 20, 129) : EndIf
  If gate_reply_form = 1 : PokeL(buffer + 16, 20 + (off * 4)) : EndIf
  If gate_reply_form = 2 : PokeL(buffer + 16, $80000000 | (20 + (off * 4))) : EndIf
  If gate_bad_call = 12 And call = 1 : ProcedureReturn 0 : EndIf
  If gate_bad_call = 3 And call = 0 : ProcedureReturn 0 : EndIf
  If gate_bad_call = 7 And call = 1 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i Main()
  ProcedureReturn Pi3FirmwareGpioConfigureOutput(gate_gpio, gate_state)
EndProcedure
'''
    source = "\n".join(declarations) + "\n" + procedure + "\n" + harness
    temp = tempfile.TemporaryDirectory(prefix="pi3-gpio-config-")
    work = Path(temp.name)
    src = work / "gpio_config_gate.pi3"
    image = work / "gpio_config_gate.img"
    src.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [str(compiler), "--compile", str(src), "-t", "pi3", "--entry-returns",
         "--load-addr", hex(base.LOAD), "--stack-addr", hex(base.STACK),
         "-s", "-o", str(image)], cwd=ROOT, capture_output=True, text=True,
        check=False)
    if result.returncode or not image.is_file() or "pmfc: OK" not in result.stdout:
        temp.cleanup()
        raise AssertionError("GPIO config emitted gate compile failed:\n" + result.stdout + result.stderr)
    return image, base.parse_symbols(image), image.read_bytes(), temp


def gpio_config_reply_checks(compiler: Path) -> int:
    image, sym, blob, temp = _compile_gpio_config_gate(compiler)
    a64 = base.load_interp(base.INTERP)

    def run(*, bad=0, form=0, gpio=129, state=0, outstanding=0):
        cpu = a64.A64()
        cpu.memory = {base.LOAD + i: b for i, b in enumerate(blob)}
        cpu.sp = base.STACK
        cpu.enable_system_registers(el=3)
        for name, value in (("gate_gpio", gpio), ("gate_state", state),
                            ("gate_calls", 0), ("gate_bad_call", bad),
                            ("gate_reply_form", form),
                            ("pi3_mailbox_outstanding", outstanding)):
            cpu.store(sym["global_" + name], value, 8)
        cpu.pc = base.LOAD + sym["main"]
        cpu.x[30] = base.RETURN_PC
        for _ in range(100_000):
            if cpu.pc == base.RETURN_PC:
                return (cpu.x[0], cpu.load(sym["global_gate_calls"], 8),
                        [cpu.load(sym["global_gate_log"] + i * 4, 4) for i in range(16)])
            cpu.step()
        raise AssertionError("Pi3FirmwareGpioConfigureOutput emitted gate did not return")

    checks = 0
    for form in (0, 1, 2):
        result, calls, log = run(form=form)
        assert (result, calls) == (1, 2), (form, result, calls)
        # Independently assert exact request layouts, including preserved GET
        # polarity, output direction, state, and firmware channel buffer size.
        assert log[:8] == [44, 0x30043, 20, 129, 0, 0, 0, 0], log[:8]
        assert log[8:] == [48, 0x38043, 24, 129, 1, 0xA5, 0, 0], log[8:]
        checks += 5
    for bad in range(1, 13):
        result, calls, _ = run(bad=bad)
        assert result == 0, bad
        assert calls == (1 if bad in (1, 3, 4, 5, 6) else 2), (bad, calls)
        checks += 2
    for kwargs in ({"gpio": 127}, {"gpio": 136}, {"state": 2}, {"outstanding": 1}):
        result, calls, _ = run(**kwargs)
        assert (result, calls) == (0, 0), (kwargs, result, calls)
        checks += 1
    temp.cleanup()
    return checks


def _set_cis_pointer(host: Host, register: int, pointer: int) -> None:
    for i in range(3):
        host.cccr[(0, register + i)] = (pointer >> (8 * i)) & 0xFF


def _set_manfid(host: Host, pointer: int, vendor: int, device: int) -> None:
    host.cis_bytes.update({
        pointer: 0x20, pointer + 1: 4,
        pointer + 2: vendor & 0xFF, pointer + 3: (vendor >> 8) & 0xFF,
        pointer + 4: device & 0xFF, pointer + 5: (device >> 8) & 0xFF,
    })


def _configure_discovery(host: Host, common: int, function1: int) -> None:
    host.set64("p3_sdio_card_selected", 1)
    host.set64("p3_sdio_functions", 1)
    host.cccr[(0, 0)] = 0x32
    host.cccr[(0, 8)] = 0x02
    _set_cis_pointer(host, 0x09, common)
    _set_cis_pointer(host, 0x109, function1)


def cis_checks(host_factory) -> int:
    checks = 0
    common, f1 = 0x1234, 0x2345
    expected_vendor, expected_device = 0x02D0, 0xA9A6

    # Common and function CIS are both fetched via function zero. Walk over
    # an unknown tuple, decode common MANFID, and inherit it when F1 omits one.
    absent = host_factory()
    _configure_discovery(absent, common, f1)
    absent.cis_bytes.update({common: 0x22, common + 1: 1, common + 2: 0xAA,
                             f1: 0xFF})
    _set_manfid(absent, common + 3, expected_vendor, expected_device)
    assert absent.call("pi3sdiodiscover") == 1
    assert absent.get64("p3_sdio_cis_vendor") == expected_vendor
    assert absent.get64("p3_sdio_cis_device") == expected_device
    assert absent.get64("p3_sdio_func1_vendor") == expected_vendor
    assert absent.get64("p3_sdio_func1_device") == expected_device
    assert absent.get64("p3_sdio_cccr_revision") == 0x32
    assert absent.get64("p3_sdio_cccr_capabilities") == 0x02
    assert absent.cis_accesses and all(fn == 0 for fn, _ in absent.cis_accesses)
    checks += 7

    # An explicit F1 MANFID overrides the common ID, and a 0xFF link length
    # terminates an otherwise unknown function tuple chain.
    explicit = host_factory()
    _configure_discovery(explicit, common, f1)
    _set_manfid(explicit, common, expected_vendor, expected_device)
    explicit.cis_bytes.update({f1: 0x22, f1 + 1: 0xFF})
    assert explicit.call("pi3sdiodiscover") == 1
    assert explicit.get64("p3_sdio_func1_vendor") == expected_vendor
    assert explicit.get64("p3_sdio_func1_device") == expected_device
    assert (0, f1 + 2) not in explicit.cis_accesses
    checks += 3

    explicit_f1 = host_factory()
    _configure_discovery(explicit_f1, common, f1)
    _set_manfid(explicit_f1, common, expected_vendor, expected_device)
    _set_manfid(explicit_f1, f1, 0x1234, 0x5678)
    assert explicit_f1.call("pi3sdiodiscover") == 1
    assert explicit_f1.get64("p3_sdio_func1_vendor") == 0x1234
    assert explicit_f1.get64("p3_sdio_func1_device") == 0x5678
    checks += 3

    malformed = host_factory()
    edge = 0x1FFFE
    _configure_discovery(malformed, edge, f1)
    malformed.cccr[(0, 0x09)] = edge & 0xFF
    malformed.cccr[(0, 0x0A)] = (edge >> 8) & 0xFF
    malformed.cccr[(0, 0x0B)] = (edge >> 16) & 0xFF
    malformed.cis_bytes[edge] = 0x22
    malformed.cis_bytes[edge + 1] = 4
    assert malformed.call("pi3sdiodiscover") == 0
    assert malformed.get64("p3_sdio_cis_vendor") == 0
    checks += 2

    bus_error = host_factory("cis-r5-error")
    _configure_discovery(bus_error, common, f1)
    _set_manfid(bus_error, common, expected_vendor, expected_device)
    bus_error.cis_error_addr = common + 2
    assert bus_error.call("pi3sdiodiscover") == 0
    assert bus_error.get64("p3_sdio_last_r5") & R5_BAD
    assert bus_error.get64("p3_sdio_func1_vendor") == 0
    checks += 3
    return checks


class Host:
    def __init__(self, a64, image: Path, symbols: dict[str, int], code: bytes,
                 scenario: str = "ready") -> None:
        self.cpu = a64.A64()
        self.cpu.memory = {base.LOAD + i: b for i, b in enumerate(code)}
        self.memload = self.cpu.load
        self.memstore = self.cpu.store
        self.cpu.load = self.load
        self.cpu.store = self.store
        self.cpu.sp = base.STACK
        self.cpu.enable_system_registers(el=3, preset={0xD51BE000: 19_200_000})
        self.cpu.cntpct_per_instruction = 256
        self.image = image
        self.sym = symbols
        self.scenario = scenario
        self.regs: dict[int, int] = {HOSTVER: (0x00040000 if scenario == "hostver-unsupported"
                                                else 0x00020000),
                                     CAPS0: 0x00200000}
        self.status = 0
        self.argument = 0
        self.command = -1
        self.response = 0
        self.cccr: dict[tuple[int, int], int] = {(0, 7): 0, (0, 8): 0x02}
        self.cis_bytes: dict[int, int] = {}
        self.cis_accesses: list[tuple[int, int]] = []
        self.cis_error_addr = -1
        self.cmd5_retries = 0
        self.cmd53_fifo_index = 0
        self.cmd53_data: list[int] = []
        self.cmd53_write = False
        self.cmd53_transfers: list[tuple[int, int, int, int]] = []
        self.cmd53_args: list[int] = []
        self.cmd53_host_block_words: list[int] = []
        self.sdhci_reads: list[int] = []
        self.sdhci_writes: list[tuple[int, int]] = []
        self.gpio_writes: list[tuple[int, int]] = []
        self.forbidden_writes: list[tuple[int, int, int]] = []
        self.timeline: list[tuple[str, int, int, int, int]] = []
        self.command_timeline: list[tuple[int, int, int]] = []
        self.data_events = True
        self.present_state = 0
        self.control1 = 0
        self.clock_stable = True
        self.fail_mode = scenario
        self.steps = 0

    def load(self, address: int, size: int) -> int:
        if SDHCI <= address < SDHCI + 0x100:
            if size != 4 or address & 3:
                raise AssertionError(f"SDHCI access must be aligned 32-bit: {address:08X}/{size}")
            off = address - SDHCI
            self.sdhci_reads.append(off)
            if off == INT_STATUS:
                event = 0
                if self.command >= 0x35:
                    if self.data_events:
                        event |= INT_SPACE if self.cmd53_write else INT_DATA
                        event |= INT_DATA_END
                return (self.status | event) & 0xFFFFFFFF
            if off == PRESENT:
                return self.present_state
            if off == CONTROL1:
                return self.control1
            if off == RESP0:
                return self.response
            if off == BUFFER:
                value = (0xA55A0000 + self.cmd53_fifo_index) & 0xFFFFFFFF
                self.cmd53_fifo_index += 1
                return value
            return self.regs.get(off, 0)
        if GPIO <= address < GPIO + 0x100:
            if size != 4 or address & 3:
                raise AssertionError("Pi3 GPIO access must be aligned 32-bit")
            return self.regs.get(0x10000 + address - GPIO, 0)
        return self.memload(address, size)

    def store(self, address: int, value: int, size: int) -> None:
        if SDHCI <= address < SDHCI + 0x100:
            if size != 4 or address & 3:
                raise AssertionError(f"SDHCI access must be aligned 32-bit: {address:08X}/{size}")
            value &= 0xFFFFFFFF
            off = address - SDHCI
            self.sdhci_writes.append((off, value))
            if off in (CONTROL0, CONTROL1, CMD):
                cmd_index = ((value >> 24) & 0x3F) if off == CMD else -1
                self.timeline.append(("sdhci", off, value, self.cpu.cntpct,
                                      cmd_index))
            if off == INT_STATUS:
                self.status &= ~value
            elif off == ARG:
                self.argument = value
            elif off == CONTROL1:
                if value & (RESET_ALL | RESET_CMD | RESET_DATA):
                    self.control1 = value & ~(RESET_ALL | RESET_CMD | RESET_DATA | CLK_STABLE)
                elif value & 1:
                    self.control1 = value | (CLK_STABLE if self.clock_stable else 0)
                else:
                    self.control1 = value
            elif off == CMD:
                self.command = (value >> 24) & 0x3F
                self.command_timeline.append((self.command, self.argument,
                                              self.cpu.cntpct))
                self.status = 0
                self.cmd53_fifo_index = 0
                self._command(value)
            elif off == 0x04:
                self.cmd53_host_block_words.append(value)
                self.regs[off] = value
            elif off == BUFFER:
                self.cmd53_data.append(value)
            else:
                self.regs[off] = value
            return
        if GPIO <= address < GPIO + 0x100:
            if size != 4 or address & 3:
                raise AssertionError("Pi3 GPIO access must be aligned 32-bit")
            value &= 0xFFFFFFFF
            off = address - GPIO
            self.gpio_writes.append((off, value))
            if off not in (0x0C, 0x94, 0x9C):
                self.forbidden_writes.append((address, value, size))
            self.regs[0x10000 + off] = value
            return
        if 0x3F000000 <= address < 0x40000000:
            self.forbidden_writes.append((address, value, size))
            return
        self.memstore(address, value, size)

    def _command(self, cmdword: int) -> None:
        cmd = self.command
        arg = self.argument
        if cmd == 5:
            if self.scenario == "cmd5-silent":
                return
            if self.scenario == "cmd5-timeout":
                # BCM2837 SDHCI reports the summary error bit together with
                # command-timeout detail (as captured on the real Pi 3).
                self.status = 0x00018000
                return
            if self.scenario == "cmd5-crc":
                self.status = 0x00028000
                return
            if arg == 0:
                self.response = 0x10000000 | 0x00300000
            else:
                self.cmd5_retries += 1
                self.response = 0x10000000 | 0x00300000
                if self.scenario != "cmd5-never-ready" and self.cmd5_retries >= 2:
                    self.response |= 0x80000000
        elif cmd == 3:
            self.response = 0x12340000
        elif cmd == 52:
            write = (arg & 0x80000000) != 0
            fn = (arg >> 28) & 7
            addr = (arg >> 9) & 0x1FFFF
            val = arg & 0xFF
            if self.scenario == "r5-error" and addr == 7:
                self.response = 0x00000800
            elif (self.scenario == "cis-r5-error" and
                  addr == self.cis_error_addr):
                self.response = 0x00000800
            elif write:
                self.cccr[(fn, addr)] = val
                self.response = val
            else:
                self.cis_accesses.append((fn, addr))
                self.response = self.cis_bytes.get(addr,
                                                   self.cccr.get((fn, addr), 0))
        elif cmd == 53:
            fn = (arg >> 28) & 7
            write = (arg & 0x80000000) != 0
            self.cmd53_write = write
            block_mode = bool(arg & 0x08000000)
            incr = bool(arg & 0x04000000)
            addr = (arg >> 9) & 0x1FFFF
            count = arg & 0x1FF
            self.cmd53_transfers.append((fn, int(write), int(block_mode), count))
            self.cmd53_args.append(arg)
            self.response = 0x00000000
            self.data_events = self.scenario != "cmd53-data-timeout"
        elif cmd == 7:
            self.response = 0x00008000 if self.scenario == "cmd7-r1-error" else 0
            self.status = INT_RESPONSE | INT_DATA_END
            return
        else:
            self.response = 0
        self.status |= INT_RESPONSE

    def set64(self, symbol: str, value: int) -> None:
        addr = self.sym["global_" + symbol.lower()]
        for i in range(8):
            self.cpu.memory[addr + i] = (value >> (i * 8)) & 0xFF

    def get64(self, symbol: str) -> int:
        addr = self.sym["global_" + symbol.lower()]
        return sum(self.cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))

    def call(self, name: str, *args: int, limit: int = 2_000_000) -> int:
        self.cpu.pc = base.LOAD + self.sym[name.lower()]
        self.cpu.x[30] = base.RETURN_PC
        for i, value in enumerate(args):
            self.cpu.x[i] = value
        pcs: Counter[int] = Counter()
        recent: deque[int] = deque(maxlen=16)
        expired_samples: list[tuple[int, int, int]] = []
        for _ in range(limit):
            if self.cpu.pc == base.RETURN_PC:
                self.steps += 1
                value = self.cpu.x[0]
                return value - (1 << 64) if value & (1 << 63) else value
            pcs[self.cpu.pc] += 1
            recent.append(self.cpu.pc)
            if self.cpu.pc == base.LOAD + 0x298 and len(expired_samples) < 12:
                expired_samples.append((self.cpu.cntpct, self.cpu.x[12], self.cpu.x[13]))
            self.cpu.step()
            self.steps += 1
        pc = self.cpu.pc
        code_symbols = sorted((value, key) for key, value in self.sym.items()
                              if not key.startswith("global_") and value < 0x100000)
        preceding = [(value, key) for value, key in code_symbols if base.LOAD + value <= pc]
        near = preceding[-1] if preceding else None
        raise AssertionError(
            f"unbounded emitted call: {name} scenario={self.scenario}; "
            f"pc=0x{pc:08X} x0..x3={[hex(x) for x in self.cpu.x[:4]]} "
            f"x9..x13={[hex(x) for x in self.cpu.x[9:14]]} "
            f"sp=0x{self.cpu.sp:08X} cmd={self.command} arg=0x{self.argument:08X} "
            f"status=0x{self.status:08X} ctl1=0x{self.control1:08X} "
            f"ticks={self.cpu.cntpct} steps={self.steps} near={near} "
            f"last_writes={self.sdhci_writes[-12:]} last_reads={self.sdhci_reads[-12:]} "
            f"top_pcs={pcs.most_common(8)} recent={[hex(x) for x in recent]} "
            f"expired_cmp={expired_samples}"
        )


def sdio_power_sequence_checks(host_factory) -> int:
    checks = 0
    min_delay_ticks = (10_000 * 19_200_000) // 1_000_000

    def init(host: Host, wired: int, failure: int = 0) -> int:
        gate_addr = host.sym["global_p3_sdio_gate_words"]
        host.cpu.store(gate_addr + 133 * 4, wired, 4)
        host.cpu.store(gate_addr + 134 * 4, failure, 4)
        host.cpu.store(gate_addr + 135 * 4, 11, 4)
        return host.call("main")

    wired = host_factory()
    gate = wired.sym["global_p3_sdio_gate_words"]
    assert init(wired, 1) == 1
    reset_count = wired.cpu.load(gate + 120 * 4, 4)
    reset_asserted = wired.cpu.load(gate + 121 * 4, 4)
    asserted_tick = wired.cpu.load(gate + 122 * 4, 4)
    reset_released = wired.cpu.load(gate + 123 * 4, 4)
    released_tick = wired.cpu.load(gate + 124 * 4, 4)
    assert (reset_count, reset_asserted, reset_released) == (2, 1, 0)

    power = next(t for kind, off, val, t, cmd in wired.timeline
                 if off == CONTROL0 and (val & 0xF00) == 0xF00)
    card_clock = next(t for kind, off, val, t, cmd in wired.timeline
                      if off == CONTROL1 and (val & CLK_CARD_EN) != 0)
    cmd0 = next(t for kind, off, val, t, cmd in wired.timeline
                if off == CMD and cmd == 0)
    command_prefix = [cmd for cmd, _, _ in wired.command_timeline[:8]]
    assert command_prefix == [52, 52, 0, 5, 5, 5, 3, 7], command_prefix
    assert wired.get64("p3_sdio_reset_status") == 1
    assert wired.get64("p3_sdio_go_idle_status") == 1
    reset_card = wired.command_timeline[:2]
    assert reset_card[0][1] == (0x06 << 9)
    assert reset_card[1][1] == (0x80000000 | (0x06 << 9) | 8)
    go_idle = wired.command_timeline[2]
    assert go_idle[2] - card_clock >= 3 * min_delay_ticks // 10
    assert asserted_tick <= power
    assert released_tick - power >= min_delay_ticks
    assert released_tick <= card_clock
    assert cmd0 - card_clock >= min_delay_ticks
    checks += 7

    # An unwired board (Pi 3A+) skips reset callbacks but retains power-up and
    # clock-settle delays before the first command.
    unwired = host_factory()
    ugate = unwired.sym["global_p3_sdio_gate_words"]
    assert init(unwired, 0) == 1
    assert unwired.cpu.load(ugate + 120 * 4, 4) == 0
    upower = next(t for _, off, val, t, _ in unwired.timeline
                  if off == CONTROL0 and (val & 0xF00) == 0xF00)
    uclock = next(t for _, off, val, t, _ in unwired.timeline
                  if off == CONTROL1 and (val & CLK_CARD_EN) != 0)
    ucmd0 = next(t for _, off, val, t, cmd in unwired.timeline
                 if off == CMD and cmd == 0)
    assert uclock - upower >= min_delay_ticks
    assert ucmd0 - uclock >= min_delay_ticks
    checks += 4

    # Callback failures are fail-closed at the right boundary: no host power
    # write after assertion fails, and no clock/CMD traffic after release fails.
    assert_failed = host_factory()
    agate = assert_failed.sym["global_p3_sdio_gate_words"]
    assert init(assert_failed, 1, 1) == 0
    assert assert_failed.get64("p3_sdio_error") == 22
    assert assert_failed.cpu.load(agate + 120 * 4, 4) == 1
    assert not any(off == CONTROL0 and (val & 0xF00) == 0xF00
                   for off, val in assert_failed.sdhci_writes)
    assert not any(off == CMD for off, _ in assert_failed.sdhci_writes)
    checks += 4

    release_failed = host_factory()
    rgate = release_failed.sym["global_p3_sdio_gate_words"]
    assert init(release_failed, 1, 2) == 0
    assert release_failed.get64("p3_sdio_error") == 23
    assert release_failed.cpu.load(rgate + 120 * 4, 4) == 2
    assert any(off == CONTROL0 and (val & 0xF00) == 0xF00
               for off, val in release_failed.sdhci_writes)
    assert not any(off == CONTROL1 and (val & CLK_CARD_EN) != 0
                   for off, val in release_failed.sdhci_writes)
    assert not any(off == CMD for off, _ in release_failed.sdhci_writes)
    checks += 6
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args()
    image, sym, blob, temp = compile_gate(args.compiler.resolve())
    a64 = base.load_interp(base.INTERP)
    checks = 0

    def fresh(mode: str = "ready") -> Host:
        return Host(a64, image, sym, blob, mode)

    # The emitted timer wrappers themselves are under test: both MRS values
    # must survive the helper return path and feed bounded waits correctly.
    timer = fresh()
    assert timer.call("pi3sdiotickhz") == 19_200_000
    tick0 = timer.call("pi3sdioticks")
    tick1 = timer.call("pi3sdioticks")
    assert tick1 > tick0 >= 0
    checks += 2

    # Normal init uses CMD0, the CMD5 probe+ready negotiation, CMD3/RCA,
    # CMD7 busy release, and a CCCR bus-width update. It may touch only the
    # Pi3 SDHCI block and GPIO34..39 setup registers.
    h = fresh()
    init_result = h.call("pi3sdioinit", 250_000_000, 4)
    assert init_result == 1, (init_result, h.get64("p3_sdio_error"),
                              h.get64("p3_sdio_last_command"),
                              h.get64("p3_sdio_last_interrupt"),
                              h.get64("p3_sdio_last_present"), h.sdhci_writes[-8:])
    checks += 1
    assert h.get64("p3_sdio_ready") == 1 and h.get64("p3_sdio_rca") == 0x1234
    assert h.get64("p3_sdio_bus_width") == 4 and h.get64("p3_sdio_functions") == 1
    checks += 3
    assert [cmd for off, cmd in h.sdhci_writes if off == CMD and (cmd >> 24) & 0x3F == 5]
    assert all(0 <= off < 0x100 for off in h.sdhci_reads)
    assert not h.forbidden_writes, f"non-SDHCI/pin48 write observed: {h.forbidden_writes[:3]}"
    assert any(off == 0x0C for off, _ in h.gpio_writes)
    assert not any(off == 0x10 for off, _ in h.gpio_writes), "GPIO FSEL4/pins48-53 were touched"
    checks += 4

    # The complete HOSTVER specification byte is validated; unsupported
    # future versions are refused before touching SDHCI control registers.
    future = fresh("hostver-unsupported")
    assert future.call("pi3sdioinit", 250_000_000, 4) == 0
    assert future.get64("p3_sdio_error") == 10
    assert not future.sdhci_writes
    checks += 3

    # SDHCI clock divider uses the injected source clock and never requests a
    # faster card clock. At 250MHz the SDHCI v3 divider formula is ceil(src/2*target).
    h.set64("p3_sdio_clock_hz", 250_000_000)
    h.set64("p3_sdio_host_version", 2)
    assert h.call("pi3sdiosetclock", 400_000) == 1
    assert h.get64("p3_sdio_clock_now") == 250_000_000 // (2 * 313)
    ctl_words = [v for off, v in h.sdhci_writes if off == CONTROL1]
    assert ctl_words and (ctl_words[-1] & CLK_CARD_EN) and ((ctl_words[-1] >> 8) & 0xFF) == 0x39
    assert ((ctl_words[-1] >> 6) & 3) == 1, "SDHCI v3 divider high bits were lost"
    checks += 3

    # A too-slow request cannot be silently clamped to a faster clock than
    # requested. It must fail before changing the live divider.
    old_writes = len(h.sdhci_writes)
    old_clock = h.get64("p3_sdio_clock_now")
    assert h.call("pi3sdiosetclock", 1) == 0
    assert len(h.sdhci_writes) == old_writes and h.get64("p3_sdio_clock_now") == old_clock
    checks += 2

    # SDHCI v2 uses power-of-two real divisors, while v3 encodes even real
    # divisors. The v2 path must stay at or below the requested frequency.
    v2 = fresh()
    v2.set64("p3_sdio_clock_hz", 250_000_000)
    v2.set64("p3_sdio_host_version", 1)
    assert v2.call("pi3sdiosetclock", 1_000_000) == 1
    assert v2.get64("p3_sdio_clock_now") == 250_000_000 // 256
    v2word = [v for off, v in v2.sdhci_writes if off == CONTROL1][-1]
    assert ((v2word >> 8) & 0xFF) == 0x80
    checks += 3

    # CMD5's absence, transport error, and a card that never sets OCR busy
    # all fail within their documented deadlines; they do not publish ready.
    for mode, want_error in (("cmd5-timeout", 6), ("cmd5-crc", 6),
                             ("cmd5-never-ready", 16), ("cmd5-silent", 5)):
        t = fresh(mode)
        assert t.call("pi3sdioinit", 250_000_000, 4) == 0, mode
        assert t.get64("p3_sdio_ready") == 0, mode
        assert t.get64("p3_sdio_error") == want_error, (mode, t.get64("p3_sdio_error"))
        if mode == "cmd5-timeout":
            assert sum(1 for cmd, _, _ in t.command_timeline if cmd == 5) == 4
            checks += 1
        if mode in ("cmd5-timeout", "cmd5-crc"):
            assert t.get64("p3_sdio_last_interrupt") & INT_ERROR_MASK
            assert t.get64("p3_sdio_last_command") == 5
            assert t.get64("p3_sdio_last_interrupt") == (
                0x00018000 if mode == "cmd5-timeout" else 0x00028000)
            reset_masks = [v & (RESET_CMD | RESET_DATA)
                           for off, v in t.sdhci_writes
                           if off == CONTROL1 and v & (RESET_CMD | RESET_DATA)]
            assert reset_masks[-2:] == [RESET_CMD, RESET_DATA], reset_masks
        assert not t.forbidden_writes, mode
        checks += 6 if mode in ("cmd5-timeout", "cmd5-crc") else 3

    # A successful transport response can still carry an invalid R1 status;
    # CMD7 must refuse selection rather than mark the card selected.
    bad_r1 = fresh("cmd7-r1-error")
    assert bad_r1.call("pi3sdioinit", 250_000_000, 4) == 0
    assert bad_r1.get64("p3_sdio_error") == 19
    assert bad_r1.get64("p3_sdio_card_selected") == 0
    assert bad_r1.command_timeline[-1][0] == 7
    checks += 4

    # An inhibited command line is bounded and causes no command-register
    # write. Clock-stability timeout also refuses instead of enabling SDCLK.
    blocked = fresh()
    blocked.present_state = 1
    writes = len(blocked.sdhci_writes)
    assert blocked.call("pi3sdiowaitidle", 0) == 0
    assert blocked.get64("p3_sdio_error") == 4
    assert blocked.get64("p3_sdio_last_present") == 1
    assert blocked.get64("p3_sdio_last_interrupt") == 0
    assert blocked.get64("p3_sdio_fault_latched") == 1
    assert not any(off == CMD for off, _ in blocked.sdhci_writes[writes:])
    assert any(off == CONTROL1 and value & RESET_CMD
               for off, value in blocked.sdhci_writes[writes:])
    assert blocked.control1 & RESET_CMD == 0
    unstable = fresh()
    unstable.clock_stable = False
    unstable.set64("p3_sdio_clock_hz", 250_000_000)
    unstable.set64("p3_sdio_host_version", 2)
    assert unstable.call("pi3sdiosetclock", 400_000) == 0
    assert unstable.get64("p3_sdio_error") == 3
    assert not any(v & CLK_CARD_EN for off, v in unstable.sdhci_writes if off == CONTROL1)
    checks += 4

    # R5 validation rejects the card's error bit; malformed arguments are
    # refused before ARG1/CMD writes. A subsequent good direct read still works.
    r = fresh("r5-error")
    r.set64("p3_sdio_card_selected", 1)
    assert r.call("pi3sdiocmd52read", 0, 7) == -1
    assert r.get64("p3_sdio_last_r5") & R5_BAD
    before = len(r.sdhci_writes)
    assert r.call("pi3sdiocmd52read", 8, 7) == -1
    assert r.call("pi3sdiocmd52read", 0, 0x20000) == -1
    assert len(r.sdhci_writes) == before
    r.scenario = "ready"
    assert r.call("pi3sdiocmd52read", 0, 8) == 2
    checks += 5

    cis_count = cis_checks(fresh)

    # CMD53 PIO read/write exercise count packing, single host-block setup,
    # FIFO word count, and caller-buffer guards. Length/address/alignment
    # refusals must not issue a command or touch memory.
    d = fresh()
    d.set64("p3_sdio_ready", 1)
    buf = sym["global_p3_sdio_gate_words"]
    d.cpu.store(buf, 0x11223344, 4)
    d.cpu.store(buf + 64, 0x55667788, 4)
    assert d.call("pi3sdiocmd53read", 1, 0x200, buf + 4, 12, 1) == 1
    assert [d.cpu.load(buf + 4 + n * 4, 4) for n in range(3)] == [0xA55A0000+n for n in range(3)]
    assert d.cpu.load(buf, 4) == 0x11223344 and d.cpu.load(buf + 64, 4) == 0x55667788
    assert d.cmd53_transfers[-1] == (1, 0, 0, 12)
    blksz = [v for off, v in d.sdhci_writes if off == 4]
    assert blksz and blksz[-1] == 0x0001000C
    checks += 4
    d.cmd53_data.clear()
    for i in range(3): d.cpu.store(buf + 4 + i*4, 0xCAFE0000+i, 4)
    assert d.call("pi3sdiocmd53write", 1, 0x300, buf + 4, 12, 0) == 1
    assert d.cmd53_data == [0xCAFE0000, 0xCAFE0001, 0xCAFE0002]
    assert d.cmd53_transfers[-1] == (1, 1, 0, 12)
    checks += 2

    # Byte-mode supports 512 bytes by encoding CMD53 count zero. The host
    # still programs one 512-byte block; the SDIO CMD53 block-mode bit stays
    # clear (multi-block operation is not part of this API).
    after = buf + 4 + 512
    d.cpu.store(after, 0xDEADBEEF, 4)
    assert d.call("pi3sdiocmd53read", 1, 0x100, buf + 4, 512, 0) == 1
    assert d.cmd53_transfers[-1] == (1, 0, 0, 0)
    assert (d.cmd53_args[-1] & 0x1FF) == 0 and (d.cmd53_args[-1] & 0x08000000) == 0
    assert d.cmd53_host_block_words[-1] == 0x00010200
    assert d.cpu.load(after, 4) == 0xDEADBEEF
    checks += 4

    # 508 is the largest ordinary nonzero 9-bit byte count before the
    # special 512-as-zero encoding.
    assert d.call("pi3sdiocmd53read", 1, 0x120, buf + 4, 508, 1) == 1
    assert d.cmd53_transfers[-1] == (1, 0, 0, 508)
    assert (d.cmd53_args[-1] & 0x1FF) == 508
    assert d.cmd53_host_block_words[-1] == 0x000101FC
    checks += 4
    writes_before = len(d.sdhci_writes)
    sentinel = [d.cpu.load(buf + 4 + i*4, 4) for i in range(3)]
    for args_bad in ((1, 0x200, buf + 2, 12, 1),
                     (1, 0x200, buf + 4, 0, 1),
                     (1, 0x200, buf + 4, 6, 1),
                     (1, 0x200, buf + 4, 516, 1),
                     (1, 0x20000, buf + 4, 12, 1)):
        assert d.call("pi3sdiocmd53read", *args_bad) == 0
    assert d.call("pi3sdiocmd53read", 1, 0x1FFF8, buf + 4, 16, 1) == 0
    assert len(d.sdhci_writes) == writes_before
    assert [d.cpu.load(buf + 4 + i*4, 4) for i in range(3)] == sentinel
    checks += 7

    # No DATA_AVAIL/SPACE event reaches the bounded poll deadline, returning
    # an error without mutating the destination buffer.
    t = fresh("cmd53-data-timeout")
    t.set64("p3_sdio_ready", 1)
    before = t.cpu.load(buf + 4, 4)
    assert t.call("pi3sdiocmd53read", 1, 0x100, buf + 4, 4, 0) == 0
    assert t.cpu.load(buf + 4, 4) == before
    assert t.get64("p3_sdio_error") != 0
    checks += 3

    sequence_count = sdio_power_sequence_checks(fresh)

    print(f"PASS: Pi3 SDIO emitted host gate ({checks} assertions; 32-bit SDHCI, CMD5/CMD52/CMD53, GPIO isolation)")
    print(f"PASS: Pi3 SDIO power sequencing gate ({sequence_count} assertions; reset/power/clock order and 10 ms settle bounds)")
    print(f"PASS: Pi3 CIS discovery gate ({cis_count} assertions; F0 tuple reads, MANFID, termination, bounds, R5 errors)")
    temp.cleanup()
    nc_checks = mailbox_nc_checks(args.compiler.resolve())
    print(f"PASS: Pi3 mailbox/NC emitted gate ({nc_checks} assertions; real EL3 context and MMU span helpers)")
    gpio_reply_checks = gpio_state_reply_checks(args.compiler.resolve())
    print(f"PASS: Pi3 firmware GPIO reply gate ({gpio_reply_checks} assertions; both valid tag-length forms and strict overall/tag/payload checks)")
    gpio_config_checks = gpio_config_reply_checks(args.compiler.resolve())
    print(f"PASS: Pi3 firmware GPIO configure gate ({gpio_config_checks} assertions; exact GET/SET payloads, polarity preservation, and fail-closed replies)")


def power_sequence_only(compiler: Path) -> int:
    image, sym, blob, temp = compile_gate(compiler.resolve())
    a64 = base.load_interp(base.INTERP)

    def fresh(mode: str = "ready") -> Host:
        return Host(a64, image, sym, blob, mode)

    try:
        return sdio_power_sequence_checks(fresh)
    finally:
        temp.cleanup()


if __name__ == "__main__":
    main()
