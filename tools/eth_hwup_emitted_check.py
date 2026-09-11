#!/usr/bin/env python3
"""Execute emitted Ethernet bring-up policy with modeled hardware seams.

This desk gate executes the real A64 ``eth_HwUp`` and ``eth_HwUpLocal``
procedures.  GENET operations, printing, and firmware reset are explicit
models; the gate therefore proves monitor control flow and state publication,
not physical DMA idle, PHY behaviour, or a successful reset.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import tempfile

import dsi_diag_read_safety_check as emitted


MASK = (1 << 64) - 1
GENET_WORDS = (0xFD580808, 0xFD585044, 0xFD583044)
GENET_ENABLE = dict(zip(GENET_WORDS, (3, 1, 1)))
GENET_RETAINED = dict(zip(GENET_WORDS, (0x10000, 0x20000, 0x40000)))
MODELED_MAC = bytes.fromhex("02 17 28 39 4a 5b")
RX_BASE = 0x08100000
RX_BYTES = 524288
LINK_MS = 5000

PROCEDURES = ("eth_hwup", "eth_hwuplocal", "ethpayloadstopchecked")
HOOK_NAMES = (
    "uartwritestr", "uartwrite", "printnl", "printdec", "uartdrain",
    "safetytofirmware",
    "ethwhygenet", "ethwhynet", "genetstarted", "genetphylinkup",
    "genetstop", "ethmacfetch", "genetprobe", "genetsetmac",
    "genetsetrxregion", "genetstart", "geneterror", "netmacset",
    "netdefaults", "netarpflush", "netsetmac",
)
GLOBAL_NAMES = ("gethup", "gethmac", "genet_started")


class FirmwareExit(Exception):
    """The modeled nonreturning firmware-reset boundary was reached."""


def must_refuse(action, diagnostic: str) -> None:
    try:
        action()
    except (AssertionError, FileNotFoundError) as error:
        if diagnostic not in str(error):
            raise AssertionError(
                f"unexpected refusal: {error}; wanted {diagnostic}") from error
    else:
        raise AssertionError("negative acceptance control survived: " + diagnostic)


def admit(image: Path, image_hash: str | None = None,
          symbols_hash: str | None = None) -> tuple[dict[str, int], bytes]:
    if not image.is_file():
        raise AssertionError("required image is missing")
    sidecar = Path(str(image) + ".sym")
    if not sidecar.is_file():
        raise AssertionError("required symbol sidecar is missing")
    blob = image.read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    actual_symbols = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    if image_hash is not None and actual != image_hash.lower():
        raise AssertionError("image digest does not match the admitted artifact")
    if symbols_hash is not None and actual_symbols != symbols_hash.lower():
        raise AssertionError("symbol digest does not match the admitted sidecar")

    sym = emitted.parse_symbols(image)
    required = ("__image_start__", "__image_end__", "__bss_start__",
                "__bss_end__") + PROCEDURES + HOOK_NAMES + tuple(
                    "global_" + name for name in GLOBAL_NAMES)
    missing = [name for name in required if name not in sym]
    if missing:
        raise AssertionError("required symbols missing: " + ", ".join(missing))
    if sym["__image_start__"] != 0 or sym["__image_end__"] != len(blob):
        raise AssertionError("symbol image extent does not match the flat image")

    bss = (sym["__bss_start__"], sym["__bss_end__"])
    code = (emitted.LOAD, emitted.LOAD + len(blob))
    stack = (emitted.STACK - 0x100000, emitted.STACK)
    if bss[0] < 0 or bss[1] <= bss[0]:
        raise AssertionError("BSS extent is empty or reversed")
    spans = (code, bss, stack)
    for index, left in enumerate(spans):
        for right in spans[index + 1:]:
            if left[0] < right[1] and right[0] < left[1]:
                raise AssertionError("admitted image, BSS and monitor stack overlap")

    callable_names = PROCEDURES + HOOK_NAMES
    for name in callable_names:
        if not 0 <= sym[name] < len(blob) or sym[name] % 4:
            raise AssertionError("invalid procedure offset: " + name)
    if len({sym[name] for name in callable_names}) != len(callable_names):
        raise AssertionError("hook/procedure symbols alias one another")
    for name in GLOBAL_NAMES:
        address = sym["global_" + name]
        if address % 8 or not bss[0] <= address <= bss[1] - 8:
            raise AssertionError("invalid global slot: " + name)
    if len({sym["global_" + name] for name in GLOBAL_NAMES}) != len(GLOBAL_NAMES):
        raise AssertionError("required global slots alias one another")
    print(f"  image SHA256 {actual}; symbols SHA256 {actual_symbols}")
    return sym, blob


def admission_checks(image: Path) -> int:
    sym = emitted.parse_symbols(image)
    must_refuse(lambda: admit(image, "0" * 64), "image digest")
    must_refuse(lambda: admit(image, symbols_hash="0" * 64), "symbol digest")
    mutations = (
        ({"__image_end__": sym["__image_end__"] - 4}, "image extent"),
        ({"__bss_end__": sym["__bss_start__"]}, "empty or reversed"),
        ({"__bss_start__": emitted.LOAD,
          "__bss_end__": emitted.LOAD + 8}, "overlap"),
        ({"eth_hwup": sym["eth_hwup"] + 1}, "invalid procedure offset"),
        ({"genetprobe": sym["genetsetmac"]}, "symbols alias"),
        ({"global_gethup": sym["__bss_end__"]}, "invalid global slot"),
        ({"global_gethup": sym["global_genet_started"]}, "global slots alias"),
    )
    from unittest.mock import patch
    for change, diagnostic in mutations:
        with patch.object(emitted, "parse_symbols", return_value={**sym, **change}):
            must_refuse(lambda: admit(image), diagnostic)
    missing = dict(sym)
    del missing["eth_hwuplocal"]
    with patch.object(emitted, "parse_symbols", return_value=missing):
        must_refuse(lambda: admit(image), "required symbols missing")
    return 10


@dataclass(frozen=True)
class Case:
    name: str
    local: bool = False
    active: int = 0
    driver: int = 0
    link: int = 0
    hardware_active: int = 0
    pre_command: bool = True
    pre_readback: bool = True
    pre_stuck: int = 0
    probe: bool = True
    hardware_mac: bool = True
    rx_region: bool = True
    start: bool = True
    start_error: int = -8
    mac_present: bool = True
    publish_mac: bool = True
    cleanup_command: bool = True
    cleanup_readback: bool = True
    cleanup_stuck: int = 0
    expected: int = 1
    expected_events: tuple[str, ...] = ()
    expected_up: int = 1
    expected_driver: int = 1
    expected_active_mask: bool = True
    reset: bool = False


def signed(value: int) -> int:
    return value - (1 << 64) if value & (1 << 63) else value


def inside(span: tuple[int, int], address: int, size: int) -> bool:
    return size > 0 and span[0] <= address and address + size <= span[1]


def check_case(a64, sym: dict[str, int], original: bytes, case: Case,
               blob: bytes | None = None, guards: bool = False) -> int:
    blob = original if blob is None else blob
    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[emitted.LOAD + offset] = byte
    code = (emitted.LOAD, emitted.LOAD + len(blob))
    bss = (sym["__bss_start__"], sym["__bss_end__"])
    stack = (emitted.STACK - 0x100000, emitted.STACK)
    mmio = {address: GENET_RETAINED[address] |
            (GENET_ENABLE[address] if case.hardware_active else 0)
            for address in GENET_WORDS}
    events: list[str] = []
    reads: list[tuple[int, int]] = []
    stop_count = 0

    def load(address: int, size: int) -> int:
        cpu.align_guard(address, size, False)
        if cpu.fetching and not inside(code, address, size):
            raise AssertionError("instruction fetch outside admitted image")
        if address in mmio:
            if size != 4:
                raise AssertionError("GENET readback was not a 32-bit access")
            reads.append((stop_count, address))
            return mmio[address]
        if not any(inside(span, address, size) for span in (code, bss, stack)):
            raise AssertionError(f"read outside admitted RAM/registers: {address:#x}+{size}")
        return sum(cpu.memory.get(address + i, 0) << (8 * i)
                   for i in range(size))

    def store(address: int, value: int, size: int) -> None:
        cpu.align_guard(address, size, True)
        if not any(inside(span, address, size) for span in (bss, stack)):
            raise AssertionError(f"write outside BSS/stack: {address:#x}+{size}")
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    if guards:
        must_refuse(lambda: store(code[0], 0, 4), "outside BSS/stack")
        must_refuse(lambda: load(0xDEAD0000, 4), "outside admitted RAM")
        must_refuse(lambda: store(GENET_WORDS[0], 0, 4), "outside BSS/stack")
        must_refuse(lambda: load(GENET_WORDS[0], 8), "32-bit access")
        cpu.fetching = True
        try:
            must_refuse(lambda: load(bss[0], 4), "fetch outside admitted image")
            must_refuse(lambda: load(stack[0], 4), "fetch outside admitted image")
        finally:
            cpu.fetching = False

    def get(name: str) -> int:
        return load(sym["global_" + name.lower()], 8)

    def put(name: str, value: int) -> None:
        store(sym["global_" + name.lower()], value & MASK, 8)

    put("gEthUp", case.active)
    put("genet_started", case.driver)
    mac_address = sym["global_gethmac"]
    hooks: dict[int, callable] = {}

    def install(name: str, callback) -> None:
        def hook(inner):
            result = callback(inner)
            for register in range(1, 19):
                inner.x[register] = 0xBAD10000 + register
            inner.x[0] = (0 if result is None else result) & MASK
        hooks[emitted.LOAD + sym[name]] = hook

    def event(name: str, result=0, arguments: tuple[int, ...] | None = None):
        def record(inner):
            if arguments is not None:
                actual = tuple(inner.x[:len(arguments)])
                if actual != arguments:
                    raise AssertionError(
                        f"{name}: wrong arguments {actual}, expected {arguments}")
            events.append(name)
            return result
        return record

    for name in ("uartwritestr", "uartwrite", "printnl", "printdec"):
        install(name, lambda _cpu: 0)
    install("uartdrain", event("uart-drain"))
    install("ethwhygenet", event("why-genet"))
    install("ethwhynet", event("why-net"))
    def driver_state(_cpu):
        events.append("driver-state")
        return get("genet_started")
    install("genetstarted", driver_state)
    install("genetphylinkup", event("link-state", case.link))

    def firmware(_cpu):
        events.append("firmware-reset")
        raise FirmwareExit()
    install("safetytofirmware", firmware)

    def stop(_cpu):
        nonlocal stop_count
        stop_count += 1
        events.append("stop")
        put("genet_started", 0)  # GenetStop publishes this before its first refusal.
        if stop_count == 1:
            command, readback, stuck = (case.pre_command, case.pre_readback,
                                         case.pre_stuck)
        elif stop_count == 2:
            command, readback, stuck = (case.cleanup_command,
                                         case.cleanup_readback,
                                         case.cleanup_stuck)
        else:
            raise AssertionError("unexpected extra GENET stop")
        if not command:
            return 0
        for index, address in enumerate(GENET_WORDS):
            is_stuck = not readback and index == stuck
            mmio[address] = GENET_RETAINED[address] | (
                GENET_ENABLE[address] if is_stuck else 0)
        return 1
    install("genetstop", stop)

    def fetch_mac(_cpu):
        events.append("mac-fetch")
        for offset, value in enumerate(MODELED_MAC):
            store(mac_address + offset, value, 1)
    install("ethmacfetch", fetch_mac)
    install("genetprobe", event("probe", int(case.probe)))

    def mac_call(name: str, result: int, arguments: tuple[int, ...]):
        record = event(name, result, arguments)
        def checked(inner):
            if bytes(load(mac_address + i, 1) for i in range(6)) != MODELED_MAC:
                raise AssertionError(name + ": modeled MAC bytes changed")
            return record(inner)
        return checked
    install("genetsetmac", mac_call("hardware-mac", int(case.hardware_mac),
                                     (mac_address,)))
    install("genetsetrxregion", event("rx-region", int(case.rx_region),
                                       (RX_BASE, RX_BYTES)))

    def start(inner):
        if inner.x[0] != LINK_MS:
            raise AssertionError("wrong bounded GENET-start timeout")
        events.append("start")
        put("genet_started", int(case.start))
        # A failed GenetStart may have reached DMA enable before link refusal.
        for address in GENET_WORDS:
            mmio[address] = GENET_RETAINED[address] | GENET_ENABLE[address]
        return int(case.start)
    install("genetstart", start)
    install("geneterror", event("start-error", case.start_error))
    install("netmacset", event("mac-present", int(case.mac_present), (1,)))
    install("netdefaults", event("net-defaults"))
    install("netarpflush", event("arp-flush", arguments=(1,)))
    install("netsetmac", mac_call("publish-mac", int(case.publish_mac),
                                   (1, mac_address)))

    cpu.pc = emitted.LOAD + sym["eth_hwuplocal" if case.local else "eth_hwup"]
    cpu.sp = emitted.STACK
    cpu.x[29] = 0x1234567887654321
    cpu.x[30] = emitted.RETURN_PC
    reset = False
    steps = 0
    try:
        steps = emitted.run_until_return(cpu, hooks, limit=2_000_000)
    except FirmwareExit:
        reset = True

    if tuple(events) != case.expected_events:
        raise AssertionError(
            f"{case.name}: actual events {events}, expected {case.expected_events}")
    if reset != case.reset:
        raise AssertionError(f"{case.name}: reset={reset}, expected {case.reset}")
    if not reset:
        if signed(cpu.x[0]) != case.expected:
            raise AssertionError(
                f"{case.name}: result {signed(cpu.x[0])}, expected {case.expected}")
        if cpu.sp != emitted.STACK or cpu.x[29] != 0x1234567887654321:
            raise AssertionError(case.name + ": emitted entry did not restore SP/x29")
    if get("gEthUp") != case.expected_up:
        raise AssertionError(case.name + ": wrong published gEthUp")
    if get("genet_started") != case.expected_driver:
        raise AssertionError(case.name + ": wrong modeled driver-started state")
    for address in GENET_WORDS:
        active = bool(mmio[address] & GENET_ENABLE[address])
        expected_active = case.expected_active_mask
        if not case.pre_readback and stop_count == 1:
            expected_active = address == GENET_WORDS[case.pre_stuck]
        if not case.cleanup_readback and stop_count == 2:
            expected_active = address == GENET_WORDS[case.cleanup_stuck]
        if active != expected_active:
            raise AssertionError(
                f"{case.name}: wrong final enable field at {address:#x}")

    expected_reads: list[tuple[int, int]] = []
    if stop_count >= 1 and case.pre_command:
        expected_reads.extend((1, address) for address in GENET_WORDS)
    if stop_count >= 2 and case.cleanup_command:
        expected_reads.extend((2, address) for address in GENET_WORDS)
    if reads != expected_reads:
        raise AssertionError(f"{case.name}: readbacks {reads}, expected {expected_reads}")
    return steps


def cases() -> list[Case]:
    rebuild = ("stop", "mac-fetch", "probe", "hardware-mac", "rx-region",
               "uart-drain", "start", "mac-present", "arp-flush",
               "publish-mac")
    cold = Case("raw cold start", expected_events=rebuild)
    local_cold = replace(cold, name="local cold start", local=True,
                         mac_present=True)
    already_events = ("driver-state", "link-state")
    already = Case("raw genuine already-up", active=1, driver=1, link=1,
                   hardware_active=1, expected=2,
                   expected_events=already_events)
    local_already = replace(already, name="local genuine already-up", local=True)
    old_loss = replace(cold, name="raw old-active PHY loss", active=1, driver=1,
                       link=0, hardware_active=1,
                       expected_events=("driver-state", "link-state") + rebuild)
    interface_only = replace(cold, name="raw interface-only stale state",
                             active=1, driver=0, hardware_active=1,
                             expected_events=("driver-state",) + rebuild)
    driver_only = replace(cold, name="raw driver-only stale state", driver=1,
                          hardware_active=1)

    pre_command = replace(
        cold, name="raw pre-stop command refusal", hardware_active=1,
        pre_command=False, expected=-1, expected_events=("stop", "why-genet"),
        expected_up=0, expected_driver=0, expected_active_mask=True)
    local_pre_command = replace(
        pre_command, name="local pre-stop command refusal", local=True,
        expected_events=("stop", "why-genet", "uart-drain", "firmware-reset"),
        reset=True)
    pre_readbacks = [replace(
        cold, name=f"raw pre-stop readback refusal {index}", hardware_active=1,
        pre_readback=False, pre_stuck=index, expected=-1,
        expected_events=("stop", "why-genet"), expected_up=0,
        expected_driver=0, expected_active_mask=False)
        for index in range(3)]
    local_pre_readback = replace(
        pre_readbacks[0], name="local pre-stop readback refusal", local=True,
        expected_events=("stop", "why-genet", "uart-drain", "firmware-reset"),
        reset=True)

    stopped = dict(expected=0, expected_up=0, expected_driver=0,
                   expected_active_mask=False)
    probe_refusal = replace(
        cold, name="raw probe refusal", probe=False,
        expected_events=("stop", "mac-fetch", "probe", "why-genet"), **stopped)
    local_probe_refusal = replace(probe_refusal, name="local probe refusal",
                                  local=True)
    mac_refusal = replace(
        cold, name="raw hardware-MAC refusal", hardware_mac=False,
        expected_events=("stop", "mac-fetch", "probe", "hardware-mac",
                         "why-genet"), **stopped)
    rx_refusal = replace(
        cold, name="raw RX-region refusal", rx_region=False,
        expected_events=("stop", "mac-fetch", "probe", "hardware-mac",
                         "rx-region", "why-genet"), **stopped)
    old_probe_refusal = replace(
        old_loss, name="raw old-active PHY-loss probe refusal", probe=False,
        expected_events=("driver-state", "link-state", "stop", "mac-fetch",
                         "probe", "why-genet"), **stopped)
    old_mac_refusal = replace(
        old_loss, name="raw old-active PHY-loss hardware-MAC refusal",
        hardware_mac=False,
        expected_events=("driver-state", "link-state", "stop", "mac-fetch",
                         "probe", "hardware-mac", "why-genet"), **stopped)
    old_rx_refusal = replace(
        old_loss, name="raw old-active PHY-loss RX-region refusal",
        rx_region=False,
        expected_events=("driver-state", "link-state", "stop", "mac-fetch",
                         "probe", "hardware-mac", "rx-region", "why-genet"),
        **stopped)

    start_failure_events = rebuild[:7] + ("start-error", "stop")
    start_down = replace(cold, name="raw start failure checked down", start=False,
                         expected_events=start_failure_events, **stopped)
    start_cleanup_command = replace(
        cold, name="raw start cleanup command refusal", start=False,
        cleanup_command=False, expected=-1, expected_up=0, expected_driver=0,
        expected_active_mask=True,
        expected_events=start_failure_events + ("why-genet",))
    start_cleanup_readback = replace(
        cold, name="raw start cleanup readback refusal", start=False,
        cleanup_readback=False, expected=-1, expected_up=0, expected_driver=0,
        expected_active_mask=False,
        expected_events=start_failure_events + ("why-genet",))
    local_start_cleanup = replace(
        start_cleanup_readback, name="local start cleanup readback refusal",
        local=True, reset=True,
        expected_events=start_failure_events +
        ("why-genet", "uart-drain", "firmware-reset"))

    publish_events = rebuild[:-1] + ("publish-mac", "stop")
    publish_down = replace(cold, name="raw MAC-publish refusal checked down",
                           publish_mac=False,
                           expected_events=publish_events + ("why-net",), **stopped)
    publish_cleanup_command = replace(
        cold, name="raw MAC-publish cleanup command refusal", publish_mac=False,
        cleanup_command=False, expected=-1, expected_up=0, expected_driver=0,
        expected_active_mask=True,
        expected_events=publish_events + ("why-genet",))
    local_publish_cleanup = replace(
        cold, name="local MAC-publish cleanup readback refusal", local=True,
        publish_mac=False, cleanup_readback=False, expected=-1, expected_up=0,
        expected_driver=0, expected_active_mask=False, reset=True,
        expected_events=publish_events +
        ("why-genet", "uart-drain", "firmware-reset"))
    defaults = replace(cold, name="raw first attachment defaults",
                       mac_present=False,
                       expected_events=rebuild[:-3] +
                       ("mac-present", "net-defaults", "arp-flush", "publish-mac"))
    return [already, local_already, cold, local_cold, old_loss, interface_only,
            driver_only, pre_command, local_pre_command, *pre_readbacks,
            local_pre_readback, probe_refusal, local_probe_refusal, mac_refusal,
            rx_refusal, old_probe_refusal, old_mac_refusal, old_rx_refusal,
            start_down, start_cleanup_command,
            start_cleanup_readback, local_start_cleanup, publish_down,
            publish_cleanup_command, local_publish_cleanup, defaults]


def reachable_calls(blob: bytes, entry: int, target: int) -> list[int]:
    pending, seen, matches = [entry], set(), []
    def sext(value: int, bits: int) -> int:
        return value - (1 << bits) if value & (1 << (bits - 1)) else value
    while pending:
        offset = pending.pop()
        if offset in seen:
            continue
        if offset < 0 or offset + 4 > len(blob) or offset % 4 or len(seen) > 10000:
            raise AssertionError("decoded control flow escaped admitted image")
        seen.add(offset)
        ins = int.from_bytes(blob[offset:offset + 4], "little")
        if ins & 0xFFFFFC1F == 0xD65F0000:
            continue
        if ins >> 26 == 0b100101:
            if offset + sext(ins & 0x03FFFFFF, 26) * 4 == target:
                matches.append(offset)
        elif ins & 0xFC000000 == 0x14000000:
            pending.append(offset + sext(ins & 0x03FFFFFF, 26) * 4)
            continue
        elif ins & 0xFF000010 == 0x54000000 or ins & 0x7E000000 == 0x34000000:
            pending.append(offset + sext((ins >> 5) & 0x7FFFF, 19) * 4)
        elif ins & 0x7E000000 == 0x36000000:
            pending.append(offset + sext((ins >> 5) & 0x3FFF, 14) * 4)
        elif ins & 0xFFFFFC1F == 0xD61F0000:
            raise AssertionError("unmodeled indirect branch in decoded procedure")
        pending.append(offset + 4)
    return sorted(matches)


def patch_nop(blob: bytes, offset: int) -> bytes:
    changed = bytearray(blob)
    changed[offset:offset + 4] = (0xD503201F).to_bytes(4, "little")
    return bytes(changed)


def mutation_checks(a64, sym: dict[str, int], blob: bytes) -> int:
    table: list[tuple[str, Case, bytes]] = []
    cold = next(case for case in cases() if case.name == "raw cold start")
    old_loss = next(case for case in cases() if case.name == "raw old-active PHY loss")
    local_cold = next(case for case in cases() if case.name == "local cold start")
    local_unsafe = next(
        case for case in cases() if case.name == "local pre-stop command refusal")

    stop_calls = reachable_calls(blob, sym["eth_hwup"], sym["ethpayloadstopchecked"])
    if len(stop_calls) != 3:
        raise AssertionError(f"expected three eth_HwUp checked-stop calls, got {stop_calls}")
    table.append(("missing common pre-rebuild stop", cold,
                  patch_nop(blob, stop_calls[0])))

    link_calls = reachable_calls(blob, sym["eth_hwup"], sym["genetphylinkup"])
    if len(link_calls) != 1:
        raise AssertionError("expected one emitted PHY-link call")
    table.append(("stale already-up shortcut", old_loss,
                  patch_nop(blob, link_calls[0])))

    start_calls = reachable_calls(blob, sym["eth_hwup"], sym["genetstart"])
    if len(start_calls) != 1:
        raise AssertionError("expected one emitted GenetStart call")
    call = start_calls[0]
    mov = None
    for offset in range(call - 4, max(sym["eth_hwup"], call - 48) - 1, -4):
        ins = int.from_bytes(blob[offset:offset + 4], "little")
        # The current compiler may materialise the argument in an allocator
        # register and marshal it through the stack before x0.  Match MOVZ's
        # value, not a particular destination register.
        if ins & 0x7F800000 == 0x52800000:
            value = ((ins >> 5) & 0xFFFF) << (((ins >> 21) & 3) * 16)
            if value == LINK_MS:
                mov = offset
                changed = bytearray(blob)
                changed[offset:offset + 4] = (
                    (ins & ~(0xFFFF << 5)) | (4999 << 5)).to_bytes(4, "little")
                table.append(("wrong bounded start constant", cold, bytes(changed)))
                break
    if mov is None:
        raise AssertionError("could not locate emitted 5000-ms GenetStart argument")

    wrapper_calls = reachable_calls(blob, sym["eth_hwuplocal"], sym["eth_hwup"])
    if len(wrapper_calls) != 1:
        raise AssertionError("expected one local-wrapper raw call")
    table.append(("local wrapper skipped raw bring-up", local_cold,
                  patch_nop(blob, wrapper_calls[0])))
    reset_calls = reachable_calls(blob, sym["eth_hwuplocal"], sym["safetytofirmware"])
    if len(reset_calls) != 1:
        raise AssertionError("expected one local-wrapper firmware-reset call")
    table.append(("local unsafe result returned to prompt", local_unsafe,
                  patch_nop(blob, reset_calls[0])))

    for label, case, mutant in table:
        try:
            check_case(a64, sym, blob, case, mutant)
        except AssertionError as error:
            allowed = ("actual events", "result", "wrong bounded", "reset=",
                       "wrong published", "wrong modeled", "wrong final")
            if not any(fragment in str(error) for fragment in allowed):
                raise AssertionError(
                    f"{label}: unexpected mutation rejection: {error}") from error
        else:
            raise AssertionError("emitted mutation survived: " + label)
    return len(table)


def check(a64, image: Path, image_hash: str | None = None,
          symbols_hash: str | None = None) -> None:
    sym, blob = admit(image, image_hash, symbols_hash)
    admission_count = admission_checks(image)
    all_cases = cases()
    steps = sum(check_case(a64, sym, blob, case, guards=index == 0)
                for index, case in enumerate(all_cases))
    mutation_count = mutation_checks(a64, sym, blob)
    print(f"eth_hwup_emitted_check: PASS {len(all_cases)} machine-code routes, "
          f"{mutation_count} killed decoded mutations, {admission_count} admission "
          f"refusals, 6 memory guards, {steps:,} returned-route instructions")
    print("  GENET/printing/reset seams modeled; no physical DMA, PHY, or reset claim.")


def main() -> int:
    if not __debug__:
        raise SystemExit("This acceptance gate must not run with Python assertion optimization.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler")
    parser.add_argument("--image", type=Path,
                        help="full Pi monitor image with its exact .sym sidecar")
    parser.add_argument("--image-sha256")
    parser.add_argument("--symbols-sha256")
    args = parser.parse_args()
    a64 = emitted.load_interpreter(emitted.INTERP)
    if args.image:
        if not args.image_sha256 or not args.symbols_sha256:
            parser.error("--image requires both --image-sha256 and --symbols-sha256")
        check(a64, args.image.resolve(), args.image_sha256, args.symbols_sha256)
    else:
        with tempfile.TemporaryDirectory(prefix="anvil-eth-hwup-") as name:
            image = emitted.build(
                emitted.anvil_build.find_compiler(args.compiler), Path(name))
            check(a64, image)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print("eth_hwup_emitted_check: FAIL " + str(error))
        raise SystemExit(1)
