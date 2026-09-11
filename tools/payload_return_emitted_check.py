#!/usr/bin/env python3
"""Execute real RunAt/Ethernet recovery branches with modeled hardware seams.

No board is contacted. This checks decoded machine-code control flow, not
physical DMA quiescence or real DHCP expiry. Those remain separate proofs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch

import dsi_diag_read_safety_check as emitted


MASK = (1 << 64) - 1
PAYLOAD_RC = 0xFEDCBA9876543210
PAYLOAD_ENTRY = 0x00500000
SERVICE_ARGUMENT = 0x1234567887654320
GENET_WORDS = (0xFD580808, 0xFD585044, 0xFD583044)
GENET_ENABLE = dict(zip(GENET_WORDS, (3, 1, 1)))
# Non-owned speed/pause/ring fields need not be zero after a valid stop.
GENET_RETAINED = dict(zip(GENET_WORDS, (0x10000, 0x20000, 0x40000)))
HOOK_NAMES = (
    "uartwritestr", "uartwrite", "printnl", "putaddr", "printdec",
    "ethwhygenet", "ethwhynet", "hitsmonitor", "genetstarted",
    "genetphylinkup", "geneterror", "genetstop", "cachedisable",
    "cacheenable", "safetytofirmware", "safetywatchdogstart",
    "safetywatchdogstop", "uartdrain", "netconsoleflush", "dmachannelreset",
    "displayusedma", "ethmacfetch", "genetprobe", "genetsetmac",
    "genetsetrxregion", "genetstart", "netmacset", "netarpflush",
    "netsetmac", "netdhcptick", "netconsolerearm", "puthex16",
)
FORBIDDEN_HOOKS = (
    "netdefaults", "netclearipv4", "netifclear", "netreset", "netinit",
    "dhcpdstop", "netudplisten",
)
GLOBAL_NAMES = ("gethup", "gcacheon", "gdma", "gdead", "ggox0", "ggoaddr", "ggorc", "gsp",
                "gethmac", "genet_started")
MODELED_MAC = bytes.fromhex("02 17 28 39 4a 5b")


def admit(image: Path, image_hash: str | None = None, symbols_hash: str | None = None):
    blob = image.read_bytes()
    sidecar = Path(str(image) + ".sym")
    if not sidecar.is_file():
        raise AssertionError("required symbol sidecar is missing")
    actual = hashlib.sha256(blob).hexdigest()
    actual_symbols = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    if image_hash is not None and actual != image_hash.lower():
        raise AssertionError("image digest does not match the admitted artifact")
    if symbols_hash is not None and actual_symbols != symbols_hash.lower():
        raise AssertionError("symbol digest does not match the admitted sidecar")
    sym = emitted.parse_symbols(image)
    required = ("__image_start__", "__image_end__", "__bss_start__", "__bss_end__",
                "runat", "calladdr", "ethpayloadquiesce", "ethpayloadreclaim",
                "ethpayloadresume", "eth_hwup") + HOOK_NAMES + tuple("global_" + name for name in GLOBAL_NAMES)
    missing = [name for name in required if name not in sym]
    if missing:
        raise AssertionError("required symbols missing: " + ", ".join(missing))
    if sym.get("__image_start__") != 0 or sym.get("__image_end__") != len(blob):
        raise AssertionError("symbol image extent does not match the flat image")
    lo, hi = sym["__bss_start__"], sym["__bss_end__"]
    regions = [(emitted.LOAD, emitted.LOAD + len(blob)), (lo, hi),
               (emitted.STACK - 0x100000, emitted.STACK)]
    if lo < 0 or hi <= lo:
        raise AssertionError("BSS extent is empty or reversed")
    for index, left in enumerate(regions):
        for right in regions[index + 1:]:
            if left[0] < right[1] and right[0] < left[1]:
                raise AssertionError("admitted image, BSS and monitor stack overlap")
    if any(left <= PAYLOAD_ENTRY < right for left, right in regions):
        raise AssertionError("modeled payload entry overlaps admitted monitor memory")
    procedures = ("runat", "calladdr", "ethpayloadquiesce", "ethpayloadreclaim",
                  "ethpayloadresume", "eth_hwup")
    names = procedures + HOOK_NAMES + tuple(name for name in FORBIDDEN_HOOKS if name in sym)
    for name in names:
        if not 0 <= sym[name] < len(blob) or sym[name] % 4:
            raise AssertionError("invalid procedure offset: " + name)
    if len({sym[name] for name in names}) != len(names):
        raise AssertionError("hook/procedure symbols alias one another")
    for name in GLOBAL_NAMES:
        address = sym["global_" + name]
        if address % 8 or not lo <= address <= hi - 8:
            raise AssertionError("invalid global slot: " + name)
    if len({sym["global_" + name] for name in GLOBAL_NAMES}) != len(GLOBAL_NAMES):
        raise AssertionError("required global slots alias one another")
    print(f"  image SHA256 {actual}; symbols SHA256 {actual_symbols}")
    return sym, blob


def must_refuse(action, diagnostic):
    try:
        action()
    except AssertionError as error:
        if diagnostic not in str(error):
            raise AssertionError(f"unexpected refusal: {error}; wanted {diagnostic}") from error
    else:
        raise AssertionError("negative acceptance control survived: " + diagnostic)


def admission_checks(image: Path):
    """Negative controls keep admission requirements executable, not prose."""
    sym = emitted.parse_symbols(image)
    must_refuse(lambda: admit(image, "0" * 64), "image digest")
    must_refuse(lambda: admit(image, symbols_hash="0" * 64), "symbol digest")
    mutations = (
        ({"__image_end__": sym["__image_end__"] - 4}, "image extent"),
        ({"__bss_end__": sym["__bss_start__"]}, "empty or reversed"),
        ({"__bss_start__": emitted.LOAD, "__bss_end__": emitted.LOAD + 8}, "overlap"),
        ({"__bss_start__": PAYLOAD_ENTRY, "__bss_end__": PAYLOAD_ENTRY + 8}, "payload entry overlaps"),
        ({"runat": sym["runat"] + 1}, "invalid procedure offset"),
        ({"netdhcptick": sym["netconsolerearm"]}, "symbols alias"),
        ({"global_ggorc": sym["__bss_end__"]}, "invalid global slot"),
        ({"global_ggorc": sym["global_ggox0"]}, "global slots alias"),
    )
    for change, diagnostic in mutations:
        with patch.object(emitted, "parse_symbols", return_value={**sym, **change}):
            must_refuse(lambda: admit(image), diagnostic)
    missing = dict(sym)
    del missing["netdhcptick"]
    with patch.object(emitted, "parse_symbols", return_value=missing):
        must_refuse(lambda: admit(image), "required symbols missing")
    return 11


def reachable_calls(blob: bytes, entry: int, target: int) -> list[int]:
    """Find BL sites in one decoded CFG; do not infer its end from a neighbour."""
    pending, seen, matches = [entry], set(), []
    def signed(value, bits):
        return value - (1 << bits) if value & (1 << (bits - 1)) else value
    while pending:
        offset = pending.pop()
        if offset in seen:
            continue
        if offset < 0 or offset + 4 > len(blob) or offset % 4 or len(seen) > 10000:
            raise AssertionError("RunAt control flow escaped its admitted image")
        seen.add(offset)
        ins = int.from_bytes(blob[offset:offset + 4], "little")
        if ins & 0xFFFFFC1F == 0xD65F0000:  # RET
            continue
        if ins >> 26 == 0b100101:  # BL, but do not traverse the callee
            if offset + signed(ins & 0x03FFFFFF, 26) * 4 == target:
                matches.append(offset)
        elif ins & 0xFC000000 == 0x14000000:  # B
            pending.append(offset + signed(ins & 0x03FFFFFF, 26) * 4)
            continue
        elif ins & 0xFF000010 == 0x54000000 or ins & 0x7E000000 == 0x34000000:
            pending.append(offset + signed((ins >> 5) & 0x7FFFF, 19) * 4)
        elif ins & 0x7E000000 == 0x36000000:  # TBZ/TBNZ
            pending.append(offset + signed((ins >> 5) & 0x3FFF, 14) * 4)
        elif ins & 0xFFFFFC1F == 0xD61F0000:
            raise AssertionError("unmodeled indirect branch in RunAt")
        pending.append(offset + 4)
    return matches


@dataclass(frozen=True)
class Case:
    name: str
    active: int = 1
    driver_active: int | None = None
    cached: int = 1
    dma: int = 1
    entry_stop: bool = True
    return_stop: bool = True
    entry_stop_command: bool = True
    return_stop_command: bool = True
    rebuild_stop: bool = True
    rebuild_stop_command: bool = True
    cleanup_stop: bool = True
    cleanup_stop_command: bool = True
    stuck_register: int | None = None
    restart: bool = True
    mac_set: bool = True
    dma_reset: bool = True


class FirmwareExit(Exception):
    """The modeled nonreturning firmware reset boundary was reached."""


def check_case(a64, image: Path, case: Case, mutant: str = "", guards=False) -> int:
    sym = emitted.parse_symbols(image)
    blob = image.read_bytes()
    cpu = emitted.fresh_cpu(a64, image)
    bss = (sym["__bss_start__"], sym["__bss_end__"])
    stack = (emitted.STACK - 0x100000, emitted.STACK)
    code = (emitted.LOAD, emitted.LOAD + len(blob))
    events: list[str] = []
    stop_count = 0
    driver_started = case.active if case.driver_active is None else case.driver_active
    owed_restart = bool(case.active or driver_started)
    reclaimed = False
    mmio = {address: retained | (GENET_ENABLE[address] if owed_restart else 0)
            for address, retained in GENET_RETAINED.items()}
    register_reads: list[tuple[int, int]] = []
    printed_rc: list[int] = []

    def inside(span, address, size):
        return size > 0 and span[0] <= address and address + size <= span[1]

    def load(address, size):
        nonlocal reclaimed
        cpu.align_guard(address, size, False)
        if cpu.fetching and not inside(code, address, size):
            raise AssertionError("instruction fetch outside admitted image")
        if address in mmio:
            if size != 4:
                raise AssertionError("GENET readback was not a 32-bit access")
            register_reads.append((stop_count, address))
            if stop_count == 2 and address == GENET_WORDS[-1] and not any(
                    mmio[key] & GENET_ENABLE[key] for key in GENET_WORDS):
                reclaimed = True
            return mmio[address]
        if not any(inside(span, address, size) for span in (code, bss, stack)):
            raise AssertionError(f"read outside admitted RAM/registers: {address:#x}+{size}")
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address, value, size):
        cpu.align_guard(address, size, True)
        if not any(inside(span, address, size) for span in (bss, stack)):
            raise AssertionError(f"write outside BSS/stack: {address:#x}+{size}")
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 255

    cpu.load, cpu.store = load, store
    if guards:
        must_refuse(lambda: store(code[0], 0, 4), "outside BSS/stack")
        must_refuse(lambda: load(0xDEAD0000, 4), "outside admitted RAM")
        must_refuse(lambda: store(GENET_WORDS[0], 0, 4), "outside BSS/stack")
        must_refuse(lambda: load(GENET_WORDS[0], 8), "32-bit access")
        cpu.fetching = True
        try:
            for address in (bss[0], stack[0], PAYLOAD_ENTRY):
                must_refuse(lambda address=address: load(address, 4), "fetch outside admitted image")
        finally:
            cpu.fetching = False

    def get(name):
        return load(sym["global_" + name.lower()], 8)

    def put(name, value):
        store(sym["global_" + name.lower()], value & MASK, 8)

    put("gEthUp", case.active)
    put("genet_started", driver_started)
    put("gCacheOn", case.cached)
    put("gDma", case.dma)
    put("gDead", 15)
    put("gGoX0", SERVICE_ARGUMENT)
    hooks = {}

    def install(name, callback):
        def hook(inner):
            result = callback(inner)
            # Deliberately model AAPCS caller clobbers, preserving SP/x29/x30.
            for register in range(1, 19):
                inner.x[register] = 0xBAD00000 + register
            inner.x[0] = (0 if result is None else result) & MASK
        hooks[name if isinstance(name, int) else emitted.LOAD + sym[name]] = hook

    def event(name, result=0, argument=None):
        def record(inner):
            if argument is not None:
                expected = argument if isinstance(argument, tuple) else (argument,)
                actual = tuple(inner.x[:len(expected)])
                if actual != expected:
                    raise AssertionError(f"{name}: wrong arguments {actual}, expected {expected}")
            events.append(name)
            return result
        return record

    for name in ("uartwritestr", "uartwrite", "printnl", "putaddr", "printdec",
                 "ethwhygenet", "ethwhynet"):
        install(name, lambda _cpu: 0)
    install("hitsmonitor", lambda _cpu: 0)
    install("genetstarted", lambda _cpu: get("genet_started"))
    install("genetphylinkup", lambda _cpu: 1)
    install("geneterror", lambda _cpu: 0)

    def stop(_cpu):
        nonlocal stop_count
        stop_count += 1
        put("genet_started", 0)
        events.append("stop")
        commands = (case.entry_stop_command, case.return_stop_command,
                    case.rebuild_stop_command, case.cleanup_stop_command)
        readbacks = (case.entry_stop, case.return_stop, case.rebuild_stop, case.cleanup_stop)
        if not 1 <= stop_count <= 4:
            raise AssertionError("unexpected extra GENET stop")
        if not commands[stop_count - 1]:
            return 0
        successful = readbacks[stop_count - 1]
        for index, address in enumerate(GENET_WORDS):
            stuck = not successful and (case.stuck_register is None or case.stuck_register == index)
            mmio[address] = GENET_RETAINED[address] | (GENET_ENABLE[address] if stuck else 0)
        return 1  # Stop issued; the real production readback decides success.
    install("genetstop", stop)

    def payload(inner):
        if get("gGoAddr") != PAYLOAD_ENTRY or inner.x[0] != SERVICE_ARGUMENT:
            raise AssertionError("payload entry/service argument changed")
        if any(inner.x[index] != 0 for index in range(1, 8)):
            raise AssertionError("payload x1..x7 were not cleared by real CallAddr")
        events.append("payload")
        put("genet_started", 1)  # Returning code left the controller active.
        for address in GENET_WORDS:
            mmio[address] = GENET_RETAINED[address] | GENET_ENABLE[address]
        # A returning payload may leave its own stack active. Real CallAddr
        # must restore monitor SP before its generated epilogue reads a frame.
        inner.sp = 0x007FFF00
        return PAYLOAD_RC
    install(PAYLOAD_ENTRY, payload)

    def cache_off(_cpu):
        events.append("cache-off")
        put("gCacheOn", 0)
    def cache_on(_cpu):
        if not reclaimed:
            raise AssertionError("payload DMA enable bits survived reclaim before cache recovery")
        events.append("cache-on")
        put("gCacheOn", 1)
        return 1
    install("cachedisable", cache_off)
    install("cacheenable", cache_on)

    def firmware(_cpu):
        events.append("firmware-reset")
        raise FirmwareExit()
    install("safetytofirmware", firmware)
    install("safetywatchdogstart", event("watchdog-start", 15, 15))
    install("safetywatchdogstop", event("watchdog-stop"))
    install("uartdrain", event("uart-drain"))
    install("netconsoleflush", event("flush"))
    install("dmachannelreset", event("dma-reset", int(case.dma_reset)))
    install("displayusedma", event("dma-fallback", argument=0))
    mac_address = sym["global_gethmac"]
    def fetch_mac(_cpu):
        events.append("mac-fetch")
        for offset, value in enumerate(MODELED_MAC):
            store(mac_address + offset, value, 1)
    def set_mac(name, result, arguments):
        record = event(name, result, arguments)
        def checked(inner):
            if bytes(load(mac_address + offset, 1) for offset in range(6)) != MODELED_MAC:
                raise AssertionError(name + ": fetched MAC bytes changed")
            return record(inner)
        return checked
    install("ethmacfetch", fetch_mac)
    install("genetprobe", event("probe", 1))
    install("genetsetmac", set_mac("hardware-mac", 1, (mac_address,)))
    install("genetsetrxregion", event("rx-region", 1, (0x08100000, 524288)))
    def hardware_start(inner):
        if not reclaimed:
            raise AssertionError("payload DMA enable bits survived reclaim before hardware restart")
        if inner.x[0] != 5000:
            raise AssertionError("wrong bounded GENET-start timeout")
        events.append("hardware-start")
        put("genet_started", int(case.restart))
        # A failed start can also have enabled DMA before its link wait failed.
        for address in GENET_WORDS:
            mmio[address] = GENET_RETAINED[address] | GENET_ENABLE[address]
        return int(case.restart)
    install("genetstart", hardware_start)
    install("netmacset", event("mac-present", 1, 1))
    install("netarpflush", event("wired-arp-flush", argument=1))
    install("netsetmac", set_mac("software-mac", int(case.mac_set), (1, mac_address)))
    install("netdhcptick", event("dhcp-tick"))
    install("netconsolerearm", event("console-rearm"))
    # These are forbidden logical resets, not callbacks silently modeled away.
    for name in FORBIDDEN_HOOKS:
        if name in sym:
            def forbidden(_cpu, called=name):
                raise AssertionError("returning controller restart called " + called)
            install(name, forbidden)

    def print_rc(inner):
        events.append("rc-output")
        printed_rc.append(inner.x[0])
    install("puthex16", print_rc)

    if mutant:
        # Patch only the one BL in RunAt, never the source or on-disk image.
        matches = reachable_calls(blob, sym["runat"], sym[mutant])
        if len(matches) != 1:
            raise AssertionError(f"expected one mutation site for {mutant}, got {matches}")
        instruction = (0xD2800020 if mutant == "ethpayloadreclaim" else 0xD503201F)
        for i, byte in enumerate(instruction.to_bytes(4, "little")):
            cpu.memory[emitted.LOAD + matches[0] + i] = byte

    cpu.pc = emitted.LOAD + sym["runat"]
    cpu.sp = emitted.STACK
    cpu.x[0] = PAYLOAD_ENTRY
    cpu.x[29] = 0x12345678
    cpu.x[30] = emitted.RETURN_PC
    reset = False
    try:
        steps = emitted.run_until_return(cpu, hooks, limit=100_000)
    except FirmwareExit:
        reset, steps = True, 0

    expected = ["flush", "stop"]
    entered = case.entry_stop and case.entry_stop_command
    reclaimed_ok = case.return_stop and case.return_stop_command
    rebuild_safe = case.rebuild_stop and case.rebuild_stop_command
    restarted = owed_restart and rebuild_safe and case.restart and case.mac_set
    cleanup_needed = owed_restart and rebuild_safe and not (case.restart and case.mac_set)
    cleanup_safe = case.cleanup_stop and case.cleanup_stop_command
    must_reset = entered and (not reclaimed_ok or (owed_restart and not rebuild_safe)
                              or (cleanup_needed and not cleanup_safe))
    expected_reads = []
    if case.entry_stop_command:
        expected_reads += [(1, address) for address in GENET_WORDS]
    if not entered:
        expected += ["flush"]
        assert get("gGoX0") == 0 and get("gEthUp") == 0
        assert get("gCacheOn") == case.cached and get("gDma") == case.dma
        assert get("gGoRc") == 0 and printed_rc == []
    else:
        expected += ["watchdog-start", "uart-drain"]
        if case.cached:
            expected += ["cache-off"]
        expected += ["payload", "stop"]
        if case.return_stop_command:
            expected_reads += [(2, address) for address in GENET_WORDS]
        if not reclaimed_ok:
            expected += ["rc-output", "uart-drain", "firmware-reset"]
        else:
            if case.cached:
                expected += ["cache-on"]
            if case.dma:
                expected += ["dma-reset"]
                if not case.dma_reset:
                    expected += ["dma-fallback"]
            if owed_restart:
                expected += ["stop"]
                if case.rebuild_stop_command:
                    expected_reads += [(3, address) for address in GENET_WORDS]
                if rebuild_safe:
                    expected += ["mac-fetch", "probe", "hardware-mac", "rx-region", "uart-drain", "hardware-start"]
                    if case.restart:
                        expected += ["mac-present", "wired-arp-flush", "software-mac"]
                    if cleanup_needed:
                        expected += ["stop"]
                        if case.cleanup_stop_command:
                            expected_reads += [(4, address) for address in GENET_WORDS]
            if must_reset:
                expected += ["rc-output", "uart-drain", "firmware-reset"]
            else:
                expected += ["dhcp-tick", "console-rearm", "watchdog-stop", "rc-output", "flush"]
            assert get("gGoX0") == 0
            assert get("gEthUp") == int(restarted)
            assert get("genet_started") == int(restarted)
            assert get("gCacheOn") == case.cached
            assert get("gDma") == int(bool(case.dma and case.dma_reset))
            if not reclaimed:
                raise AssertionError("payload DMA enable bits survived reclaim")
            expected_mmio = {address: GENET_RETAINED[address] | (GENET_ENABLE[address] if restarted else 0)
                             for address in GENET_WORDS}
            if not must_reset and mmio != expected_mmio:
                raise AssertionError("final modeled GENET state does not match restart success/refusal")
        assert get("gGoRc") == PAYLOAD_RC and printed_rc == [PAYLOAD_RC]
    if events != expected:
        raise AssertionError(f"{case.name}: actual events {events}, expected {expected}")
    assert reset == must_reset
    assert register_reads == expected_reads, (case.name, register_reads, expected_reads)
    if not reset:
        assert cpu.sp == emitted.STACK and cpu.x[29] == 0x12345678
        assert cpu.x[0] == int(entered)
    return steps


def check(a64, image: Path, image_hash=None, symbols_hash=None):
    admit(image, image_hash, symbols_hash)
    admission_count = admission_checks(image)
    base = Case("active cached return")
    cases = [base, replace(base, name="inactive uncached return", active=0, cached=0, dma=0),
             replace(base, name="interface-only active flag", driver_active=0),
             replace(base, name="driver-only active flag", active=0, driver_active=1),
             replace(base, name="entry-stop refusal", entry_stop=False),
             replace(base, name="entry-stop command refusal", entry_stop_command=False),
             replace(base, name="return-stop refusal", return_stop=False),
             replace(base, name="return-stop command refusal", return_stop_command=False),
             replace(base, name="rebuild stop command refusal", rebuild_stop_command=False),
             replace(base, name="rebuild stop readback refusal", rebuild_stop=False),
             replace(base, name="restart failure", restart=False),
             replace(base, name="restart cleanup command refusal", restart=False, cleanup_stop_command=False),
             replace(base, name="restart cleanup readback refusal", restart=False, cleanup_stop=False),
             replace(base, name="MAC refusal cleanup", mac_set=False),
             replace(base, name="MAC cleanup command refusal", mac_set=False, cleanup_stop_command=False),
             replace(base, name="MAC cleanup readback refusal", mac_set=False, cleanup_stop=False),
             replace(base, name="display DMA fallback", dma_reset=False)]
    for index, field in enumerate(("UMAC TX/RX", "TDMA enable", "RDMA enable")):
        cases += [
            replace(base, name="entry single-field refusal: " + field, entry_stop=False, stuck_register=index),
            replace(base, name="return single-field refusal: " + field, return_stop=False, stuck_register=index),
            replace(base, name="rebuild single-field refusal: " + field, rebuild_stop=False, stuck_register=index),
            replace(base, name="cleanup single-field refusal: " + field, restart=False, cleanup_stop=False, stuck_register=index),
        ]
    steps = sum(check_case(a64, image, case, guards=(index == 0)) for index, case in enumerate(cases))
    for mutant in ("ethpayloadreclaim", "netdhcptick", "netconsolerearm", "safetywatchdogstop"):
        try:
            check_case(a64, image, base, mutant)
        except AssertionError as error:
            if "actual events" not in str(error) and "DMA enable bits survived" not in str(error):
                raise AssertionError(f"{mutant}: not an expected ordering rejection: {error}") from error
        else:
            raise AssertionError("missing recovery operation survived: " + mutant)
    print(f"payload_return_emitted_check: PASS {len(cases)} machine-code routes, 4 killed mutations, {admission_count} admission refusals, 7 memory guards, {steps:,} returned-route instructions")
    print("  Hardware/printing/network-service seams modeled; no physical DMA, DHCP-expiry or board claim.")


def main():
    if not __debug__:
        raise SystemExit("This acceptance gate must not run with Python assertion optimization.")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler")
    ap.add_argument("--image", type=Path, help="full Pi monitor image with its exact symbol sidecar")
    ap.add_argument("--image-sha256", help="required pinned digest when using an existing image")
    ap.add_argument("--symbols-sha256", help="required pinned digest for that image's exact symbol sidecar")
    args = ap.parse_args()
    a64 = emitted.load_interpreter(emitted.INTERP)
    if args.image:
        if not args.image_sha256 or not args.symbols_sha256:
            ap.error("--image requires both --image-sha256 and --symbols-sha256")
        check(a64, args.image.resolve(), args.image_sha256, args.symbols_sha256)
    else:
        with tempfile.TemporaryDirectory(prefix="anvil-payload-control-") as name:
            check(a64, emitted.build(emitted.anvil_build.find_compiler(args.compiler), Path(name)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print("payload_return_emitted_check: FAIL " + str(error))
        raise SystemExit(1)
