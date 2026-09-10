#!/usr/bin/env python3
"""Check the returning-payload Ethernet lifecycle in source and emitted A64.

The state model proves ownership and expiry decisions without hardware. The
emitted gate compiles the real Pi 4 monitor with -S and checks the actual call
order and the absence of logical-network resets from the controller restart.
It does not claim that GENET stopped or restarted on silicon.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import build as anvil_build


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "RaspberryPi4" / "Board" / "cache.pi4"
ETH = ROOT / "RaspberryPi4" / "Board" / "eth.pi4"


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$",
        source,
    )
    if not match:
        raise AssertionError(f"production procedure is missing: {name}")
    return match.group(0)


def in_order(checks: Checks, text: str, needles: list[str], context: str) -> None:
    cursor = -1
    for needle in needles:
        found = text.find(needle, cursor + 1)
        checks.yes(found >= 0, f"{context}: missing {needle}")
        checks.yes(found > cursor, f"{context}: {needle} is out of order")
        cursor = found


@dataclass(eq=True)
class Identity:
    mac: str = ""
    ip: str = ""
    mask: str = ""
    gateway: str = ""
    source: str = "none"
    alias: str = ""
    listener_5555: bool = False
    listener_67: bool = False
    dhcp_server: bool = False
    served_leases: tuple[tuple[str, int], ...] = ()
    lease_left: int = 0


@dataclass
class Machine:
    eth_flag: bool
    genet_started: bool
    wired: Identity = field(default_factory=Identity)
    wifi: Identity = field(default_factory=Identity)
    wifi_associated: bool = False
    go_rc: int = 0
    stop_ok: bool = True
    return_stop_ok: bool = True
    restart_ok: bool = True
    stop_calls: int = 0
    restart_calls: int = 0

    def quiesce(self) -> int:
        was = int(self.eth_flag or self.genet_started)
        self.stop_calls += 1
        self.eth_flag = False
        self.genet_started = False
        return was if self.stop_ok else -1

    def resume(self, was: int) -> bool:
        # RunAt reclaims the untrusted peripheral immediately after return,
        # before cache/display/network recovery. Resume only restores an owed
        # physical controller.
        if was == 0:
            return True
        self.restart_calls += 1
        if not self.restart_ok:
            self.eth_flag = False
            self.genet_started = False
            return False
        self.eth_flag = True
        self.genet_started = True
        return True

    def reclaim(self) -> bool:
        self.stop_calls += 1
        self.eth_flag = False
        self.genet_started = False
        return self.return_stop_ok

    def tick_elapsed(self, seconds: int) -> None:
        # Only a DHCP-client lease expires here. Static/link-local identity and
        # the direct-cable server's independently timed slots are not a client
        # lease and are untouched by this transition.
        if self.wired.source != "lease":
            return
        self.wired.lease_left = max(0, self.wired.lease_left - seconds)
        if self.wired.lease_left == 0:
            self.wired.ip = ""
            self.wired.mask = ""
            self.wired.gateway = ""
            self.wired.source = "none"
            self.wired.alias = ""
            self.wired.listener_5555 = False


def model_checks(checks: Checks) -> None:
    down = Machine(False, False)
    checks.yes(down.quiesce() == 0, "inactive controller must owe no restart")
    checks.yes(down.stop_calls == 1, "inactive flags must still issue an entry hardware stop")
    down.genet_started = True             # payload tried to leave DMA active
    checks.yes(down.reclaim(), "return must reclaim payload-started GENET")
    checks.yes(down.resume(0), "inactive controller resume must succeed as a no-op")
    checks.yes(not down.genet_started and down.stop_calls == 2, "return must reclaim payload-started GENET")
    checks.yes(down.restart_calls == 0, "inactive controller must not be started")

    half = Machine(False, True)
    checks.yes(half.quiesce() == 1, "driver-active/flag-clear mismatch must be restored")
    checks.yes(half.reclaim(), "active controller must be reclaimed before recovery")
    checks.yes(half.resume(1), "mismatched active controller must restart")
    checks.yes(half.eth_flag and half.genet_started, "successful restart must publish active")

    refused = Machine(True, True, stop_ok=False)
    checks.yes(refused.quiesce() == -1, "failed DMA stop must refuse the payload")
    checks.yes(not refused.eth_flag and not refused.genet_started, "failed stop must not claim active")

    return_refused = Machine(False, False, return_stop_ok=False)
    owed = return_refused.quiesce()
    return_refused.genet_started = True
    checks.yes(not return_refused.reclaim(), "failed return reclaim must be reported")
    checks.yes(not return_refused.eth_flag and not return_refused.genet_started, "failed return reclaim must not claim active")

    wired = Identity(
        mac="b8:27:eb:00:00:01",
        ip="169.254.170.250",
        mask="255.255.0.0",
        source="link-local",
        alias="192.168.137.1",
        listener_5555=True,
        listener_67=True,
        dhcp_server=True,
        served_leases=(("192.168.137.2", 120),),
    )
    wifi = Identity(
        mac="b8:27:eb:00:00:02",
        ip="192.168.1.16",
        mask="255.255.255.0",
        gateway="192.168.1.1",
        source="lease",
        listener_5555=True,
        lease_left=1800,
    )
    active = Machine(True, True, wired=Identity(**vars(wired)), wifi=Identity(**vars(wifi)), wifi_associated=True, go_rc=0xFEDCBA9876543210)
    before_wired = Identity(**vars(active.wired))
    before_wifi = Identity(**vars(active.wifi))
    result = active.quiesce()
    checks.yes(result == 1, "active controller must record a restart obligation")
    checks.yes(active.reclaim(), "active controller must be reclaimed before recovery")
    checks.yes(active.resume(result), "active controller must restart")
    active.tick_elapsed(20)
    checks.yes(active.wired == before_wired, "static/link-local/alias/server state must survive")
    checks.yes(active.wifi == before_wifi, "Ethernet restart must not rewrite Wi-Fi identity")
    checks.yes(active.wifi_associated, "Ethernet restart must not detach associated Wi-Fi")
    checks.yes(active.go_rc == 0xFEDCBA9876543210, "lifecycle must preserve payload x0 result")

    detached = Machine(True, True, wired=Identity(**vars(wired)), wifi=Identity(**vars(wifi)), wifi_associated=False)
    detached_before = Identity(**vars(detached.wifi))
    detached_was = detached.quiesce()
    checks.yes(detached.reclaim(), "detached-Wi-Fi case must reclaim GENET")
    checks.yes(detached.resume(detached_was), "wired restart must not depend on Wi-Fi association")
    checks.yes(detached.wifi == detached_before and not detached.wifi_associated, "detached Wi-Fi is left to its bounded health/rejoin path")

    leased = Machine(True, True, wired=Identity(mac=wired.mac, ip="10.0.0.9", mask="255.255.255.0", gateway="10.0.0.1", source="lease", listener_5555=True, lease_left=30), wifi=Identity(**vars(wifi)))
    leased.tick_elapsed(29)
    checks.yes(leased.wired.ip == "10.0.0.9" and leased.wired.lease_left == 1, "unexpired lease must survive elapsed time")
    wifi_before_expiry = Identity(**vars(leased.wifi))
    leased.tick_elapsed(1)
    checks.yes(leased.wired.ip == "" and leased.wired.source == "none", "expired lease must not carry return output")
    checks.yes(leased.wifi == wifi_before_expiry, "wired lease expiry must not erase Wi-Fi row")

    failed = Machine(True, True, wired=Identity(**vars(wired)), wifi=Identity(**vars(wifi)), restart_ok=False, go_rc=0x123456789ABCDEF0)
    failed_before = Identity(**vars(failed.wired))
    failed_was = failed.quiesce()
    checks.yes(failed.reclaim(), "init-failure case must first reclaim GENET")
    checks.yes(not failed.resume(failed_was), "bounded controller init failure must be reported")
    checks.yes(not failed.eth_flag and not failed.genet_started, "failed init must leave link inactive")
    checks.yes(failed.wired == failed_before, "failed hardware init must retain logical identity")
    checks.yes(failed.go_rc == 0x123456789ABCDEF0, "failed init must not overwrite return x0")


def source_checks(checks: Checks) -> None:
    cache = CACHE.read_text(encoding="utf-8")
    eth = ETH.read_text(encoding="utf-8")
    run = procedure(cache, "RunAt")
    checked_stop = procedure(eth, "EthPayloadStopChecked")
    quiesce = procedure(eth, "EthPayloadQuiesce")
    reclaim = procedure(eth, "EthPayloadReclaim")
    resume = procedure(eth, "EthPayloadResume")
    hwup = procedure(eth, "eth_HwUp")

    in_order(
        checks,
        run,
        [
            'Print("Starting the payload at ")',
            "NetConsoleFlush()",
            "EthPayloadQuiesce()",
            "SafetyWatchdogStart(gDead)",
            "CallAddr()",
            "EthPayloadReclaim()",
            "EthPayloadResume(wasEth)",
            "NetDhcpTick()",
            "NetConsoleRearm()",
            "SafetyWatchdogStop()",
            "PutHex16(gGoRc)",
            "NetConsoleFlush()",
        ],
        "RunAt source",
    )
    checks.yes("If wasEth < 0" in run and "ProcedureReturn 0" in run, "DMA-stop failure must refuse before jump")
    checks.yes("gGoX0 = 0" in run, "failed or completed handover must clear service x0")
    checks.yes("GenetStarted()" in quiesce and "EthPayloadStopChecked()" in quiesce, "quiesce must reconcile both state layers")
    checks.yes("ProcedureReturn -1" in quiesce, "quiesce must expose a fail-closed result")
    checks.yes("GenetStop()" in checked_stop and checked_stop.count("a64_barrier()") == 2, "checked stop must order writes and readback")
    for register in ("#GENET_UMAC_CMD", "#GENET_TDMA_CTRL", "#GENET_RDMA_CTRL"):
        checks.yes(register in checked_stop, f"checked stop must read back {register}")
    checks.yes("EthPayloadStopChecked()" in reclaim, "return reclaim must use checked stop")
    checks.yes("SafetyToFirmware()" in run, "failed return reclaim must take the reset path")
    checks.yes(run.find("EthPayloadReclaim()") < run.find("CacheEnable()"), "return reclaim must precede cache recovery")
    checks.yes(run.find("EthPayloadReclaim()") < run.find("DmaChannelReset()"), "return reclaim must precede display DMA recovery")
    checks.yes("If was = 0" in resume and "eth_HwUp()" in resume, "resume must restart only a prior active controller")
    for forbidden in ("NetClearIPv4", "NetIfClear", "NetReset", "NetInit", "DhcpdStop", "NetUdpListen"):
        checks.yes(forbidden not in hwup, f"hardware restart must not call {forbidden}")
    checks.yes("NetMacSet(#HW_LINK_WIRED)" in hwup, "first attachment must initialise defaults")
    checks.yes("NetArpFlush(#HW_LINK_WIRED)" in hwup, "restart must invalidate wired neighbours")
    checks.yes("NetSetMac(#HW_LINK_WIRED" in hwup, "restart must revalidate wired MAC identity")
    checks.yes("#HW_LINK_WIFI" not in hwup + checked_stop + quiesce + reclaim + resume, "wired lifecycle must not mutate Wi-Fi")


def asm_procedure(assembly: str, start: str, end: str) -> str:
    begin = assembly.find(f"\n{start}:\n")
    finish = assembly.find(f"\n{end}:\n", begin + 1)
    if begin < 0 or finish < 0:
        raise AssertionError(f"emitted procedure boundary missing: {start}..{end}")
    return assembly[begin + 1 : finish]


def emitted_checks(checks: Checks, assembly: str) -> None:
    run = asm_procedure(assembly, "RunAt", "CmdBlock")
    checked_stop = asm_procedure(assembly, "EthPayloadStopChecked", "EthPayloadQuiesce")
    quiesce = asm_procedure(assembly, "EthPayloadQuiesce", "EthPayloadReclaim")
    reclaim = asm_procedure(assembly, "EthPayloadReclaim", "EthPayloadResume")
    resume = asm_procedure(assembly, "EthPayloadResume", "HwLinkClose")
    hwup = asm_procedure(assembly, "eth_HwUp", "EthCableIn")

    in_order(
        checks,
        run,
        [
            "bl netconsoleflush",
            "bl ethpayloadquiesce",
            "bl safetywatchdogstart",
            "bl calladdr",
            "bl ethpayloadreclaim",
            "bl ethpayloadresume",
            "bl netdhcptick",
            "bl netconsolerearm",
            "bl safetywatchdogstop",
            "global_ggorc",
            "bl puthex16",
            "bl netconsoleflush",
        ],
        "RunAt emitted A64",
    )
    q_stop = quiesce.find("bl ethpayloadstopchecked")
    q_fail = quiesce.find("movk x11, #65535, lsl #48", q_stop)
    checks.yes("bl genetstarted" in quiesce, "emitted quiesce must inspect driver state")
    checks.yes(q_stop >= 0 and q_fail > q_stop, "emitted quiesce must return -1 after failed stop")
    checks.yes(
        "bl genetstop" in checked_stop
        and checked_stop.count("dsb sy") == 2
        and checked_stop.count("isb") == 2,
        "emitted checked stop must barrier around readback",
    )
    checks.yes("bl ethpayloadstopchecked" in reclaim, "emitted return reclaim must use checked stop")
    checks.yes(run.find("bl ethpayloadreclaim") < run.find("bl cacheenable"), "emitted reclaim must precede cache recovery")
    checks.yes(run.find("bl ethpayloadreclaim") < run.find("bl dmachannelreset"), "emitted reclaim must precede display DMA recovery")
    checks.yes("bl safetytofirmware" in run, "emitted failed reclaim must reset rather than continue")
    checks.yes("bl eth_hwup" in resume, "emitted resume must call the full hardware start")
    for forbidden in ("netclearipv4", "netifclear", "netreset", "netinit", "dhcpdstop", "netudplisten"):
        checks.yes(f"bl {forbidden}" not in hwup, f"emitted hardware restart calls {forbidden}")
    in_order(checks, hwup, ["bl netmacset", "bl netdefaults", "bl netarpflush", "bl netsetmac"], "eth_HwUp emitted A64")


def compile_assembly(pmfc: str, temporary: Path) -> str:
    compiler_dir = temporary / "compiler"
    compiler_dir.mkdir(parents=True, exist_ok=True)
    compiler = anvil_build.staged_compiler(pmfc, compiler_dir)
    output = temporary / "anvil.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [compiler, "RaspberryPi4/Board/board.pi4", "-t", "pi4", "-S", "-o", str(output)]
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise AssertionError(f"Pi 4 emitted build failed ({completed.returncode}):\n{completed.stdout}")
    asm = Path(str(output) + ".asm")
    if not asm.is_file():
        raise AssertionError("compiler succeeded but did not write the requested assembly")
    return asm.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"), help="PureMetal compiler path or command")
    parser.add_argument("--assembly", help="check an existing full-monitor .asm instead of compiling")
    args = parser.parse_args()
    checks = Checks()
    try:
        model_checks(checks)
        source_checks(checks)
        if args.assembly:
            assembly = Path(args.assembly).read_text(encoding="utf-8")
        else:
            compiler = anvil_build.find_compiler(args.pmfc)
            with tempfile.TemporaryDirectory(prefix="anvil-payload-lifecycle-") as name:
                assembly = compile_assembly(compiler, Path(name))
        emitted_checks(checks, assembly)
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        print(f"payload_lifecycle_check: FAIL after {checks.count} checks: {error}")
        return 1
    print(f"payload_lifecycle_check: PASS - {checks.count} source/model/emitted-A64 checks")
    print("No hardware was contacted; GENET stop/restart and network response remain silicon checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
