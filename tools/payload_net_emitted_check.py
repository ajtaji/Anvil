#!/usr/bin/env python3
"""Desk gate for the payload ABI's net group (service table base 72, ABI 1.5).

    PMF_COMPILER=<PureMetalForge.exe> py -3 tools/payload_net_emitted_check.py
    (--interp defaults to tools/a64/a64_interp.py)

No board is contacted and no host network is used.

WHAT IT PROVES
==============
A. STATIC - the sources agree with each other:
     * the slot installer puts exactly fifteen procedures in the net block -
       72..79, 85 and 86 (1.5), TLS at 80..83 and 87 (1.6) - and leaves 84
       (HTTP) and 88..95 at SvcUnimplemented; each slot calls the engine
       procedure of its own name; the minor is 6 and #SVC_EAGAIN is -110;
     * the engine's service pass (PayNetService in Anvil/Core/payload_net.pbi)
       calls exactly the network services the prompt's scheduler runs
       (AnvilPromptServiceOne slots 2 and 4 in Anvil/Core/parse.pbi), in the
       same order - so the two lists cannot drift apart;
     * the dispatcher (NetServiceInput) offers UDP to the registered hook
       after the NTP service and before the console, and RunAt calls
       PayNetPayloadReturned inside its message bracket, after the lease
       worker and before the console re-derivation;
     * every number the fixture RESTATES equals the published one.

B. DYNAMIC - RaspberryPi4/Tests/payload_net_emitted_gate.pi4 compiles the
   REAL engine against counting stubs and runs it on the A64 interpreter:
   a Wi-Fi-only board; DNS pending then answered from a stubbed reply, the
   callback doing no I/O, the cache, retries and the timeout said once, an
   NXDOMAIN, an ARP wait; four TCP handles and a refusal past them; a bad
   handle refused by name in both of its forms; bytes moved both ways
   through a stubbed TCP with a short send; reset, reuse and timeout
   latched with their reasons; ARP-pending opens rate-limited and timed
   out; the service slot bounded by its slice, by its cap and by its pass
   count, and run inside the message bracket; and the payload-return
   cleanup.

C. MUTATIONS - four defects are put into a COPY of the engine (the tree is
   never written) and each must be caught at the assertion named:
     no-slice-bound      the drain ignores sliceMs             -> 124
     resend-every-call   a pending query is re-sent each poll  -> 24
     no-generation       a reset connection is not noticed      -> 92
     outside-bracket     the services run with no bracket open  -> 3
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "payload_net_emitted_gate.pi4"
ENGINE = ROOT / "Anvil" / "Core" / "payload_net.pbi"
ABI = ROOT / "Anvil" / "Hal" / "abi.pbi"
ABI_VERSION = ROOT / "Anvil" / "Hal" / "abi_version.pbi"
PARSE = ROOT / "Anvil" / "Core" / "parse.pbi"
NETCONSOLE = ROOT / "Anvil" / "Core" / "netconsole.pbi"
CACHE = ROOT / "RaspberryPi4" / "Board" / "cache.pi4"
TCP = ROOT / "Anvil" / "Network" / "tcp.pbi"
NET = ROOT / "Anvil" / "Network" / "net.pbi"
DNS = ROOT / "Anvil" / "Network" / "dns_codec.pbi"
NETIF = ROOT / "Anvil" / "Core" / "netif.pbi"
DEFAULT_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"

LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 40_000_000

# The net block as this gate states it, by hand, from the brief's table and
# abi.pbi's GROUP 6 comment - not parsed from the installer it checks.
NET_SLOTS = {
    0: ("SvcNetUp", "PayNetUp"),
    1: ("SvcNetLink", "PayNetLink"),
    2: ("SvcNetAddr", "PayNetAddr"),
    3: ("SvcDnsResolve", "PayNetDnsResolve"),
    4: ("SvcTcpOpen", "PayNetTcpOpen"),
    5: ("SvcTcpSend", "PayNetTcpSend"),
    6: ("SvcTcpRecv", "PayNetTcpRecv"),
    7: ("SvcTcpClose", "PayNetTcpClose"),
    13: ("SvcNetService", "PayNetService"),
    14: ("SvcTcpState", "PayNetTcpState"),
    # 1.6: TLS over the same engine (Anvil/Core/tls_client.pbi)
    8: ("SvcTlsOpen", "TlsClientOpen"),
    9: ("SvcTlsSend", "TlsClientSend"),
    10: ("SvcTlsRecv", "TlsClientRecv"),
    11: ("SvcTlsClose", "TlsClientClose"),
    15: ("SvcTlsState", "TlsClientState"),
}

MUTATIONS = {
    "no-slice-bound": (
        "While sliceMs > 0 And (millis() - t0) < sliceMs And passes < #PAYNET_DRAIN_PASSES",
        "While sliceMs > 0 And passes < #PAYNET_DRAIN_PASSES",
        124,
    ),
    "resend-every-call": (
        "    If (now - paynet_dnsDeadline) >= 0\n",
        "    If (now - paynet_dnsDeadline) >= -100000\n",
        24,
    ),
    "no-generation": (
        "  If g <> paynet_tcpGen[i]\n",
        "  If g = -12345\n",
        92,
    ),
    "outside-bracket": (
        "  UartMessageBegin()\n  ; ---- THE PROMPT'S NETWORK SERVICES.",
        "  ; ---- THE PROMPT'S NETWORK SERVICES.",
        3,
    ),
}

CONST_RE = re.compile(r'^\s*(#[A-Za-z_]\w*)\s*=\s*(-?\$?[0-9A-Fa-f]+)\s*(?:;.*)?$')


class GateFailure(Exception):
    pass


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def consts(body: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in body.splitlines():
        m = CONST_RE.match(line)
        if not m:
            continue
        raw = m.group(2)
        neg = raw.startswith("-")
        raw = raw[1:] if neg else raw
        try:
            v = int(raw[1:], 16) if raw.startswith("$") else int(raw, 10)
        except ValueError:
            continue
        out.setdefault(m.group(1), -v if neg else v)
    return out


def body_of(source: str, header: str) -> str:
    start = source.find(header)
    if start < 0:
        raise GateFailure(f"cannot find `{header}`")
    end = source.find("EndProcedure", start)
    return source[start:end]


def code_lines(body: str) -> list[str]:
    out = []
    for line in body.splitlines():
        line = re.sub(r'"[^"]*"', '""', line).split(";", 1)[0].strip()
        if line:
            out.append(line)
    return out


def calls(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        if line.startswith(("CompilerIf", "CompilerElse", "CompilerEndIf", "Case", "Select",
                            "EndSelect")):
            continue
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", line):
            if m.group(1) not in {"If", "ElseIf", "While", "Until", "Bool"}:
                names.append(m.group(1))
    return names


def static_checks() -> int:
    n = 0
    abi = text(ABI)
    version = consts(text(ABI_VERSION))
    published = consts(abi)
    if (version.get("#SVC_ABI_MINOR") or 0) < 6:
        raise GateFailure(f"#SVC_ABI_MINOR is {version.get('#SVC_ABI_MINOR')}, expected 6 or later "
                          "- the net group at 1.5 and its TLS slots at 1.6 are minor bumps")
    if version.get("#SVC_SLOT_COUNT") != 200:
        raise GateFailure("#SVC_SLOT_COUNT moved; filling reserved slots must not move it")
    if published.get("#SVC_EAGAIN") != -110:
        raise GateFailure("#SVC_EAGAIN is not -110")
    if '"the operation has been started and has not finished yet, at code -110 (SVC_EAGAIN)' not in abi:
        raise GateFailure("SvcErrText has no sentence for #SVC_EAGAIN that keeps its number")
    n += 4

    # The installer's net block, exactly.
    installer = body_of(abi, "Procedure BuildServiceTable()")
    wired = {int(i): name for i, name in re.findall(
        r"#SVC_BASE_NET\s*\+\s*(\d+)\]\s*=\s*@(\w+)", installer)}
    want = {i: svc for i, (svc, _) in NET_SLOTS.items()}
    if wired != want:
        raise GateFailure(f"the net block installs {wired}, expected {want}")
    if "CompilerIf #ANVIL_PAYLOAD_NET = 1" not in installer:
        raise GateFailure("the net block is installed whether or not the composition built the engine")
    n += 2
    for svc, engine in NET_SLOTS.values():
        body = body_of(abi, f"Procedure.i {svc}(")
        if f"{engine}(" not in body:
            raise GateFailure(f"{svc} does not call {engine}")
        if "SvcRequireCap(#CAP_NET" not in body:
            raise GateFailure(f"{svc} does not ask the net capability question first")
        n += 2

    # The service pass is the prompt's network list, in order.
    parse = text(PARSE)
    one = body_of(parse, "Procedure AnvilPromptServiceOne()")
    if "EndSelect" not in one:
        raise GateFailure("AnvilPromptServiceOne has no Select over its slots any more")
    one = one[:one.index("EndSelect")]
    cases = re.split(r"\n\s*Case\s+", one)
    slot = {}
    for chunk in cases[1:]:
        number = int(re.match(r"(\d+)", chunk).group(1))
        slot[number] = calls(code_lines(chunk.split("\n", 1)[1] if "\n" in chunk else ""))
    prompt_net = [c for c in slot.get(2, []) + slot.get(4, [])]
    engine = text(ENGINE)
    service = body_of(engine, "Procedure.i PayNetService(")
    begin = service.find("UartMessageBegin()")
    mine_end = service.find("paynet_DnsStep(")
    mine = calls(code_lines(service[begin:mine_end]))
    mine = [c for c in mine if c not in ("UartMessageBegin",)]
    if mine != prompt_net:
        raise GateFailure(f"PayNetService runs {mine} but the prompt's network slots run "
                          f"{prompt_net}; the two lists must be the same calls in the same order")
    for owned in ("MouseTick", "TouchTick", "ScreenServiceTick", "FanTick", "TouchKeyboardServiceTick"):
        if f"{owned}(" in service:
            raise GateFailure(f"PayNetService calls {owned} - that belongs to the payload or to "
                              "no one, not to the network")
    n += 2

    # The dispatcher and the return path.
    disp = body_of(text(NETCONSOLE), "Procedure.i NetServiceInput(")
    a, b, c = (disp.find("NtpServiceInput(kind)"), disp.find("gNetUdpSvcHook(kind)"),
               disp.find("NetConsoleOfferUdp("))
    if not (0 <= a < b < c):
        raise GateFailure("NetServiceInput does not offer UDP to the hook between the NTP "
                          "service and the console")
    run = body_of(text(CACHE), "Procedure RunAt(")
    d, p, r = (run.rfind("NetDhcpTick()"), run.find("PayNetPayloadReturned()"),
               run.rfind("NetConsoleRearm()"))
    if not (0 <= d < p < r):
        raise GateFailure("RunAt does not call PayNetPayloadReturned after the lease worker "
                          "and before the console re-derivation")
    if run.rfind("UartMessageBegin()", 0, p) < run.rfind("UartMessageEnd()", 0, p):
        raise GateFailure("RunAt calls PayNetPayloadReturned outside its message bracket")
    n += 3

    # Every number the fixture restates is the published one.
    fixture = consts(text(FIXTURE))
    sources = {}
    for path in (ABI, TCP, NET, DNS, NETIF, ENGINE):
        for k, v in consts(text(path)).items():
            sources.setdefault(k, v)
    hal = text(ROOT / "Anvil" / "Hal" / "hal.pbi")
    sources.update({k: v for k, v in consts(hal).items() if k.startswith("#HW_LINK_")})
    for name, value in fixture.items():
        if name.startswith("#GATE_") or name in ("#CAP_NET", "#NETIF_KINDS"):
            continue
        if name not in sources:
            raise GateFailure(f"the fixture restates {name}, which no source publishes")
        if sources[name] != value:
            raise GateFailure(f"the fixture restates {name} = {value}; the source says {sources[name]}")
        n += 1
    return n


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_payload_net_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"payload net gate: cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards")
    probe = FIXTURE
    if mutation:
        fixed, broken, _ = MUTATIONS[mutation]
        engine = text(ENGINE)
        if engine.count(fixed) != 1:
            raise SystemExit(f"payload net gate: the {mutation} mutation site drifted")
        mutated = work / "payload_net_mutant.pbi"
        mutated.write_text(engine.replace(fixed, broken, 1), encoding="utf-8")
        source = text(FIXTURE)
        include = 'XIncludeFile "Anvil/Core/payload_net.pbi"'
        if source.count(include) != 1:
            raise SystemExit("payload net gate: the fixture's engine include drifted")
        probe = work / "payload_net_mutant_gate.pi4"
        probe.write_text(source.replace(include, f'XIncludeFile "{mutated.as_posix()}"'),
                         encoding="utf-8")
    image = work / "payload_net_gate.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        [str(staged), "--compile", str(probe), "-t", "pi4", "--load-addr", hex(LOAD),
         "--stack-addr", hex(STACK), "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("payload net gate: compile failed\n" + run.stdout)
    return image


def bss_bounds(image: Path) -> tuple[int, int]:
    values = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, raw = line.split("=", 1)
            if name in ("__bss_start__", "__bss_end__"):
                values[name] = int(raw, 0)
    return values["__bss_start__"], values["__bss_end__"]


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    lo, hi = bss_bounds(image)
    readable = ((LOAD, LOAD + len(blob)), (lo, hi), (STACK - STACK_BYTES, STACK + 16))
    writable = readable[1:]

    def inside(ranges, addr, size):
        return any(a <= addr and addr + size <= b for a, b in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not inside(readable, addr, size):
            raise SystemExit(f"payload net gate: read outside image/BSS/stack at ${addr:08X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not inside(writable, addr, size):
            raise SystemExit(f"payload net gate: write outside BSS/stack at ${addr:08X}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"payload net gate: no return in {STEP_LIMIT:,} instructions")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(DEFAULT_INTERP))
    ap.add_argument("--no-mutate", action="store_true", help="skip part C")
    args = ap.parse_args()

    try:
        n_static = static_checks()
    except GateFailure as error:
        print(f"payload_net_emitted_check: FAIL (static) {error}")
        return 1
    print(f"  A: static - {n_static} source agreements")

    compiler = Path(resolve_compiler(args.compiler))
    a64 = load_interpreter(Path(args.interp))
    with tempfile.TemporaryDirectory(prefix="anvil-payload-net-") as temporary:
        result, steps = execute(a64, build(compiler, Path(temporary)))
    if result:
        print(f"payload_net_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"  B: dynamic - every assertion held, {steps:,} A64 instructions")

    killed = 0
    if not args.no_mutate:
        for name, (_, _, expected) in MUTATIONS.items():
            with tempfile.TemporaryDirectory(prefix=f"anvil-payload-net-{name}-") as temporary:
                got, _ = execute(a64, build(compiler, Path(temporary), name))
            if got != expected:
                print(f"payload_net_emitted_check: FAIL mutation {name} returned {got}; "
                      f"expected assertion {expected}")
                return 1
            killed += 1
            print(f"  C: mutation {name} caught at assertion {got}")
    print(f"payload_net_emitted_check: PASS - {n_static} static agreements, the engine's "
          f"scenarios on the A64 interpreter, {killed} mutations killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
