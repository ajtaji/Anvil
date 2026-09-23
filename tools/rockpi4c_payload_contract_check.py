#!/usr/bin/env python3
"""Offline contract gate for the Rock Pi 4C returning-payload path."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "RockPi4C/Lib/recovery.pbi"
UPDATE = ROOT / "tools/rockpi4c_update.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    found = re.search(
        rf"(?ms)^Procedure(?:Naked)?(?:\.i)?\s+{re.escape(name)}\([^\n]*\).*?^EndProcedure\s*$",
        source,
    )
    require(found is not None, f"missing procedure {name}")
    return found.group(0).lower()


def python_method(source: str, name: str) -> str:
    found = re.search(
        rf"(?ms)^    def {re.escape(name)}\([^\n]*\).*?(?=^    def |^def |\Z)",
        source,
    )
    require(found is not None, f"missing Python method {name}")
    return found.group(0).lower()


def ordered(body: str, tokens: list[str], message: str) -> None:
    cursor = 0
    for token in tokens:
        at = body.find(token, cursor)
        require(at >= 0, f"{message}: {token}")
        cursor = at + len(token)


def source_contract() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    predicate = procedure(source, "RockRecoveryLineIsPayload")
    require("rock_recovery_length<7" in predicate and
            "rock_recovery_length=7" in predicate and
            all(f"<>{byte}" in predicate for byte in (112, 97, 121, 108, 111, 97, 100)),
            "payload keyword is not exact lowercase with a token boundary")

    cache = procedure(source, "RockRecoveryPayloadCache")
    ordered(cache, ["rockrecoverypayloaddataline()", "dsb sy",
                    "rockrecoverypayloadinstructionline()", "dsb sy", "isb"],
            "A64 code cache-maintenance order drifted")
    require("length<=0 or length>#rock_storage_stage_bytes" in cache,
            "cache walk is not bounded by the existing 4 MiB stage")
    require("dc civac, x9" in procedure(source, "RockRecoveryPayloadDataLine"),
            "uploaded code is not clean+invalidated from D-cache")
    require("ic ivau, x9" in procedure(source, "RockRecoveryPayloadInstructionLine"),
            "uploaded code is not invalidated from I-cache")

    call = procedure(source, "RockRecoveryPayloadCall")
    ordered(call, ["mov x11, sp", "str x11, [x10]", "ldr x9, [x9]",
                   "movz x0, #0", "movz x1, #0", "movz x2, #0",
                   "movz x3, #0", "movz x4, #0", "movz x5, #0",
                   "movz x6, #0", "movz x7, #0", "blr x9",
                   "str x0, [x10]", "ldr x11, [x10]", "mov sp, x11",
                   "bl rockexceptioninstallraw"],
            "payload entry/return assembly drifted")

    run = procedure(source, "RockRecoveryPayload")
    ordered(run, ["rock_storage_parsehextoken", "rock_storage_parsehextoken",
                  "rockstorageReceive(length,checksum)".lower(),
                  "rockrecoverypayloadcache(length)", "rockwatchdogarm()",
                  "rock_watchdog_armed=0 or rock_watchdog_active=0",
                  "rockwatchdogpet()", 'rockuarttext("payload stage ")',
                  'rockuartline("payload enter; deadman armed")',
                  "rockuartdrain()", "rockrecoverypayloadcall()",
                  "rockrecoverypayloadvbar()<>rock_exception_vbar",
                  "rockwatchdogpet()", 'rockuarttext("payload return x0=")'],
            "payload receive/deadman/return order drifted")
    require("@rock_storage_stage[0]" in run and
            "#rock_storage_stage_bytes" in run,
            "payload does not use the existing bounded stage")
    require("length<4" in run and "(length & 3)<>0" in run and
            "((@rock_storage_stage[0]) & 3)<>0" in run,
            "payload does not require a complete aligned A64 instruction extent")

    finish = procedure(source, "RockRecoveryFinishLine")
    require("rockrecoverylineispayload()<>0" in finish and
            "err payload disabled in fatal recovery" in finish and
            finish.index("if rock_recovery_fatal_mode<>0") < finish.index("rockrecoverypayload()"),
            "fatal recovery can enter an uploaded payload")


def host_contract() -> None:
    serial_stub = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"serial": serial_stub}):
        spec = importlib.util.spec_from_file_location("rockpi4c_update_payload_gate", UPDATE)
        require(spec is not None and spec.loader is not None, "cannot load host updater")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    calls: list[tuple[str, bytes | int]] = []

    class FakeRecovery:
        def __init__(self, port: str, baud: int):
            calls.append(("open", f"{port}:{baud}".encode()))

        def payload(self, data: bytes) -> bool:
            calls.append(("payload", data))
            return True

        def close(self) -> None:
            calls.append(("close", 1))

    with tempfile.TemporaryDirectory(prefix="rockpi4c-payload-") as name:
        image = Path(name) / "returning.bin"
        image.write_bytes(b"\xC0\x03\x5F\xD6")  # ret
        with mock.patch.object(module, "Recovery", FakeRecovery):
            rc = module.main(["--port", "COM9", "payload", str(image)])
    require(rc == 0 and ("payload", b"\xC0\x03\x5F\xD6") in calls and
            calls[-1] == ("close", 1),
            "host payload operation did not pass exact bytes and close transport")

    updater = UPDATE.read_text(encoding="utf-8").lower()
    stage_map = python_method(UPDATE.read_text(encoding="utf-8"), "stage_map")
    payload = python_method(UPDATE.read_text(encoding="utf-8"), "payload")
    ordered(payload, ["self.stage_map()", 'self.send_command(f"payload ',
                      "self.transfer_in(", 'b"payload return x0="'],
            "host does not map, upload and await a bounded return line")
    require('self.send_command("map")' in stage_map and
            'item.startswith(b"stage ")' in stage_map and
            "capacity != stage_limit" in stage_map and
            "sub.add_parser(\"payload\")" in updater,
            "host payload stage discovery/CLI wiring drifted")
    require("len(data) < 4" in payload and "len(data) & 3" in payload,
            "host accepts a partial A64 instruction extent")


def main() -> int:
    source_contract()
    host_contract()
    print("ROCK Pi 4C returning payload contract: PASS (offline; silicon not run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
