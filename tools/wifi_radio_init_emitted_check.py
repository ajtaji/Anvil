#!/usr/bin/env python3
"""Compile and execute the production coarse Wi-Fi radio initializer.

The fixture supplies deterministic hardware seams. Constants, globals and
procedure bodies are extracted from RaspberryPi4/Lib/wifi.pi4, so ordering and
cancellation assertions execute the emitted product code rather than a model
copy. Requires PMF_COMPILER and PMF_A64_INTERP (or --compiler/--interp).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "RaspberryPi4" / "Lib" / "wifi.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "wifi_radio_init_emitted_gate.pi4"
WIFI_CMD = ROOT / "Anvil" / "Core" / "wifi_cmd.pbi"
COMMAND_FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "wifi_cmd_ownership_emitted_gate.pi4"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"wifi radio init gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"wifi radio init gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def source_range(source: str, first_text: str, last_text: str) -> str:
    lines = source.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(first_text))
    last = next(i for i in range(first, len(lines)) if lines[i].startswith(last_text))
    return "\n".join(lines[first : last + 1])


def constant(source: str, name: str) -> str:
    line = next(
        (
            item
            for item in source.splitlines()
            if item.startswith(name + " ") or item.startswith(name + "=")
        ),
        None,
    )
    if line is None:
        raise SystemExit(f"wifi radio init gate: production constant {name} not found")
    return line


def probe_source(source: str | None = None) -> str:
    source = WIFI.read_text(encoding="utf-8") if source is None else source
    constants = [
        constant(source, name)
        for name in (
            "#WIFI_FW_ADDR", "#WIFI_FW_LEN", "#WIFI_NV_ADDR", "#WIFI_NV_LEN",
            "#WIFI_CLM_ADDR", "#WIFI_CLM_LEN", "#WIFI_NV_WORK",
            "#WIFI_NV_WORK_MAX", "#WIFI_SCRATCH", "#WIFI_SCRATCH_LEN",
            "#WIFI_CLOCK_ID_EMMC", "#WIFI_CLOCK_TRIES", "#WIFI_CLOCK_GAP_MS",
            "#WIFI_HEAL_MS", "#WIFI_REC_IDLE", "#WIFI_REC_LEAVE", "#WIFI_REC_EAPOL_BEGIN",
            "#WIFI_REC_GTK_INSTALL",
        )
    ]
    constants.append(source_range(source, "#WIFI_RINIT_IDLE", "#WIFI_RINIT_READY"))
    constants.append(source_range(source, "#WIFI_EAPOL_FAIL_NONE", "Global gWifiEapolRecoverRc"))
    globals_ = source_range(source, "Global gWifiRecPhase", "Global Dim wifi_recPmk")
    globals_ += "\n" + source_range(source, "Global gWifiRinitPhase", "Global gWifiRinitFwCalls")
    globals_ += "\n" + "\n".join(line for line in source.splitlines() if line.startswith("Global gWifiRxReady"))
    names = (
        "wifi_RadioGenerationPreflight", "WifiRadioUp",
        "WifiRadioInitCancel", "WifiRecoveryCancel", "wifi_RecordLinkDown",
        "WifiRadioInitActive", "WifiRadioInitPhase",
        "WifiRadioInitAttempts", "WifiRadioInitFirmwareCalls",
        "WifiRadioInitLastFailPhase", "WifiRadioInitLastFailRc",
        "WifiRadioInitArm", "wifi_RadioInitStillOwned", "wifi_RadioInitFail",
        "WifiRadioInitTick", "WifiRecoveryInitialJoinFailed",
        "WifiRecoveryStart", "WifiRecoveryReconcile", "WifiConfigChanged",
        "WifiHealSet", "WifiLinkSet",
        "WifiRxReadyArm", "WifiRxReadyDisable", "WifiRxReadyActive",
        "WifiRxReadyGeneration", "WifiRxReadyGenerationValid",
        "WifiRxReadyElapsed", "WifiRxReadyRawDelta", "WifiRxReadyFrameDelta",
        "WifiRxReadyEmptyDelta", "WifiRxReadyFirstDelta", "WifiRxReadyCmd53Delta",
    )
    bodies = "\n\n".join(procedure(source, name) for name in names)
    template = FIXTURE.read_text(encoding="utf-8")
    for marker, text in (
        ("; @@PRODUCTION_CONSTANTS@@", "\n".join(constants)),
        ("; @@PRODUCTION_GLOBALS@@", globals_),
        ("; @@PRODUCTION_PROCEDURES@@", bodies),
    ):
        if template.count(marker) != 1:
            raise SystemExit(f"wifi radio init gate: fixture marker {marker!r} is not unique")
        template = template.replace(marker, text)
    return template


def command_probe(source: str) -> str:
    template = COMMAND_FIXTURE.read_text(encoding="utf-8")
    marker = "; @@PRODUCTION_CMD_WIFI@@"
    if template.count(marker) != 1:
        raise SystemExit("wifi radio init gate: command fixture marker is not unique")
    body = procedure(source, "CmdWifi")
    # Console output is irrelevant to ownership and Print is a compiler form
    # that requires the complete string-output library. Keep the extracted
    # command control flow and calls exact while routing only its narration to
    # inert fixture leaves.
    body = body.replace("PrintN(", "GatePrintN(").replace("Print(", "GatePrint(")
    command_ids = {
        "scan": 1, "join": 2, "connect": 2, "heal": 3,
        "ssid": 4, "phrase": 5, "network": 6,
        "password": 7, "passphrase": 7, "forget": 8,
        "rxready": 9, "capture": 9, "status": 9, "arm": 10,
        "disable": 11, "off": 11,
    }
    body = re.sub(
        r'WordIs\("([^"]+)"\)',
        lambda match: ("Bool(gate_cmd >= 9 And gate_cmd <= 11)" if match.group(1) == "rxready" else f"Bool(gate_cmd = {command_ids.get(match.group(1), 0)})"),
        body,
    )
    return template.replace(marker, body)


def build(compiler: Path, work: Path, probe: Path, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile", str(probe), "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"wifi radio init gate: {stem} compile failed\n{run.stdout}")
    return image


def run_source(a64, compiler: Path, work: Path, source: str, stem: str) -> tuple[int, int]:
    probe = work / f"{stem}.pi4"
    probe.write_text(source, encoding="utf-8", newline="\n")
    return emitted.execute(a64, build(compiler, work, probe, stem))


def mutate_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(
            f"wifi radio init gate: {label} mutation site count is {source.count(old)}, expected 1"
        )
    return source.replace(old, new, 1)


def command_seam_error(source: str) -> str | None:
    """Check that actual CmdWifi success/foreground branches reach their owner seam."""
    body = procedure(source, "CmdWifi")
    regions = (
        ("slot SSID", "If SettingsSetWifiSlotSsid(s, v) = 0", 'Print("Wi-Fi slot ")', "WifiConfigChanged()"),
        ("slot phrase", "If SettingsSetWifiSlotPassword(s, v) = 0", 'Print("The passphrase for Wi-Fi slot ")', "WifiConfigChanged()"),
        ("legacy SSID", "If SettingsSetWifiNetwork(v) = 0", 'Print("The Wi-Fi network name is now ")', "WifiConfigChanged()"),
        ("legacy phrase", "If SettingsSetWifiPassword(v) = 0", 'Print("The Wi-Fi passphrase is set. It is ")', "WifiConfigChanged()"),
        ("slot forget", "If SettingsRemoveWifiSlot(s) = 0", 'PrintN("The older single pair has been forgotten', "WifiConfigChanged()"),
        ("legacy forget", "If hadNet <> 0", 'PrintN("  A copy is still in SETTINGS.TXT', "WifiConfigChanged()"),
    )
    for label, start_token, end_token, hook in regions:
        start = body.find(start_token)
        end = body.find(end_token, start + len(start_token))
        if start < 0 or end < 0 or hook not in body[start:end]:
            return f"{label} success path lacks {hook}"
        if "WifiRecoveryCancel()" in body[start:end]:
            return f"{label} can cancel before its mutation succeeds"
    scan = body.find("n = WifiScanMatch()")
    scan_end = body.find("ProcedureReturn", scan)
    if scan < 0 or scan_end < 0 or "WifiRecoveryReconcile(1)" not in body[scan:scan_end]:
        return "scan completion lacks recovery reconcile"
    join = re.search(
        r"If WifiJoinKnown\(\) <> 0.*?Else\s+WifiRecoveryInitialJoinFailed\(\)",
        body,
        re.DOTALL,
    )
    if join is None:
        return "manual join failure lacks initial-failure handoff"
    if "WifiHealSet(1)" not in body or "WifiHealSet(0)" not in body:
        return "heal policy branches bypass their ownership seam"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    wifi_source = WIFI.read_text(encoding="utf-8")
    for owner in ("WifiScanMatch", "WifiJoinKnown"):
        body = procedure(wifi_source, owner)
        if "WifiRadioInitCancel()" not in body:
            raise SystemExit(f"wifi radio init gate: foreground owner {owner} lacks cancellation")
    radio_up = procedure(wifi_source, "WifiRadioUp")
    if radio_up.find("wifi_RadioGenerationPreflight()") > radio_up.find("WifiLoadBlobs()"):
        raise SystemExit("wifi radio init gate: synchronous preflight is not before blob/bus setup")
    cancel_body = procedure(wifi_source, "WifiRecoveryCancel")
    if "WifiRadioInitCancel()" not in cancel_body:
        raise SystemExit("wifi radio init gate: shared cancellation seam does not call its radio owner")
    command_source = WIFI_CMD.read_text(encoding="utf-8")
    command_error = command_seam_error(command_source)
    if command_error is not None:
        raise SystemExit(f"wifi radio init gate: {command_error}")
    command_mutations = (
        ("scan reconcile", "    WifiRecoveryReconcile(1)", "    ; scan reconcile removed"),
        ("join failure", "      WifiRecoveryInitialJoinFailed()", "      ; join failure handoff removed"),
        ("heal on", "        WifiHealSet(1)", "        ; heal-on seam removed"),
        ("heal off", "        WifiHealSet(0)", "        ; heal-off seam removed"),
    )
    for label, old, new in command_mutations:
        mutant = mutate_once(command_source, old, new, f"command {label}")
        if command_seam_error(mutant) is None:
            raise SystemExit(f"wifi radio init gate: command {label} mutant survived")
    config_starts = (
        "If SettingsSetWifiSlotSsid(s, v) = 0",
        "If SettingsSetWifiSlotPassword(s, v) = 0",
        "If SettingsSetWifiNetwork(v) = 0",
        "If SettingsSetWifiPassword(v) = 0",
        "If SettingsRemoveWifiSlot(s) = 0",
        "If hadNet <> 0",
    )
    for label in config_starts:
        start = command_source.find(label)
        hook = command_source.find("WifiConfigChanged()", start)
        if start < 0 or hook < 0:
            raise SystemExit(f"wifi radio init gate: command mutation setup lacks {label}")
        mutant = command_source[:hook] + "; config-success seam removed" + command_source[hook + len("WifiConfigChanged()") :]
        if command_seam_error(mutant) is None:
            raise SystemExit(f"wifi radio init gate: command {label} mutant survived")

    exact = probe_source(wifi_source)
    command_exact = command_probe(command_source)
    reconcile_body = procedure(wifi_source, "WifiRecoveryReconcile")
    reconcile_mutant = mutate_once(
        reconcile_body,
        "    WifiRecoveryStart(announce)",
        "    WifiRadioInitArm(announce)",
        "ready association reconcile body",
    )
    mutations = (
        (
            "rxready callback registration",
            "  If Cyw43SetRxIrqIo(@SdioRxIrqOp) = 0",
            "  If 1 = 0",
        ),
        (
            "rxready failed-restore retention",
            "    If Cyw43RxIrqRestorePending() = 0\n      Cyw43SetRxIrqIo(0)",
            "    If 1 = 1\n      Cyw43SetRxIrqIo(0)",
        ),
        (
            "rxready generation binding",
            "  ProcedureReturn Bool(gWifiRxReadyArmed = 1 And gWifiRxReadyGeneration = gWifiRinitGeneration)",
            "  ProcedureReturn Bool(gWifiRxReadyArmed = 1)",
        ),
        (
            "coarse clock retry",
            "      r = MailboxClockRate(#WIFI_CLOCK_ID_EMMC)",
            "      r = WifiClockHz()",
        ),
        (
            "clock wait deadline",
            "      If ((millis() - gWifiRinitClockAt) & $FFFFFFFF) < #WIFI_CLOCK_GAP_MS",
            "      If ((millis() - gWifiRinitClockAt) & $FFFFFFFF) < 0",
        ),
        (
            "clock retry accumulation",
            "    Case #WIFI_RINIT_CLOCK_TRY\n      ; One complete mailbox transaction remains atomic.",
            "    Case #WIFI_RINIT_CLOCK_TRY\n      gWifiRinitClockTry = 0\n      ; One complete mailbox transaction remains atomic.",
        ),
        (
            "clock zero refusal",
            "      If r <= 0\n        gWifiRinitClockTry = gWifiRinitClockTry + 1",
            "      If r < 0\n        gWifiRinitClockTry = gWifiRinitClockTry + 1",
        ),
        (
            "clock stale generation",
            "      r = MailboxClockRate(#WIFI_CLOCK_ID_EMMC)\n      If wifi_RadioInitStillOwned(generation) = 0\n        ProcedureReturn\n      EndIf",
            "      r = MailboxClockRate(#WIFI_CLOCK_ID_EMMC)",
        ),
        (
            "clock new-generation reset",
            "    Case #WIFI_RINIT_CLOCK_BEGIN\n      gWifiRinitClockTry = 0",
            "    Case #WIFI_RINIT_CLOCK_BEGIN\n      ; old retry count retained",
        ),
        (
            "stale generation",
            "      If wifi_RadioInitStillOwned(generation) = 0\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      If r <> 1\n"
            "        wifi_RadioInitFail(phase, r)\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      gWifiRinitPhase = #WIFI_RINIT_MBX_INIT",
            "      If r <> 1\n"
            "        wifi_RadioInitFail(phase, r)\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      gWifiRinitPhase = #WIFI_RINIT_MBX_INIT",
        ),
        (
            "wrap-safe deadline",
            "If ((now - gWifiRinitAt) & $FFFFFFFF) < #WIFI_HEAL_MS",
            "If (now - gWifiRinitAt) < #WIFI_HEAL_MS",
        ),
        (
            "restore refusal",
            "      r = wifi_RadioGenerationPreflight()\n"
            "      If wifi_RadioInitStillOwned(generation) = 0\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      If r <> 1\n"
            "        wifi_RadioInitFail(phase, r)",
            "      r = wifi_RadioGenerationPreflight()\n"
            "      If wifi_RadioInitStillOwned(generation) = 0\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      If r = 999\n"
            "        wifi_RadioInitFail(phase, r)",
        ),
        (
            "early readiness publication",
            "      gWifiRinitPowerRc = r\n      gWifiRinitPhase = #WIFI_RINIT_READY",
            "      gWifiRinitPowerRc = r\n      gWifiUp = 1\n      gWifiRinitPhase = #WIFI_RINIT_READY",
        ),
        (
            "firmware phase advance",
            "      gWifiRinitPhase = #WIFI_RINIT_NVRAM",
            "      gWifiRinitPhase = #WIFI_RINIT_FW",
        ),
        (
            "byte-mode fallback",
            "      gWifiRinitBlockMode = r\n      gWifiRinitPhase = #WIFI_RINIT_PREPARE",
            "      gWifiRinitBlockMode = r\n"
            "      If r = 0\n"
            "        wifi_RadioInitFail(phase, r)\n"
            "        ProcedureReturn\n"
            "      EndIf\n"
            "      gWifiRinitPhase = #WIFI_RINIT_PREPARE",
        ),
        (
            "radio cancellation ownership",
            "  WifiRadioInitCancel()\n  gWifiRecGeneration = (gWifiRecGeneration + 1) & $FFFFFFFF",
            "  gWifiRecGeneration = (gWifiRecGeneration + 1) & $FFFFFFFF",
        ),
        (
            "common lease invalidation",
            "  NetDhcpLinkDown(#HW_LINK_WIFI)",
            "  ; common lease invalidation removed",
        ),
        (
            "saved configuration ownership",
            "  gWifiRinitBlockMode = 0\nEndProcedure",
            "  gWifiRinitBlockMode = 0\n  SettingsRemove(1)\nEndProcedure",
        ),
        (
            "synchronous readiness preflight",
            "  r = wifi_RadioGenerationPreflight()\n  If r <> 1",
            "  r = 1\n  If r <> 1",
        ),
        (
            "ready association reconcile",
            reconcile_body,
            reconcile_mutant,
        ),
        (
            "keyed address-owner reconcile",
            "    If gWifiHaveIp = 0\n      NetDhcpStart(#HW_LINK_WIFI, 1)\n    EndIf",
            "    If gWifiHaveIp = 0\n      ; DHCP ownership handoff removed\n    EndIf",
        ),
        (
            "configuration reconcile",
            "Procedure WifiConfigChanged()\n  gWifiSettingsRevisionSeen = SettingsWifiRevision()\n  WifiRecoveryCancel()\n  WifiRecoveryReconcile(0)",
            "Procedure WifiConfigChanged()\n  gWifiSettingsRevisionSeen = SettingsWifiRevision()\n  WifiRecoveryCancel()",
        ),
        (
            "heal re-enable",
            "    gWifiHealOn = 1\n    WifiRecoveryReconcile(1)",
            "    gWifiHealOn = 1",
        ),
        (
            "link re-enable",
            "    ; auto-arm on every prompt turn; a radio-off policy must remain meaningful.\n"
            "    WifiRecoveryReconcile(1)\n"
            "  Else\n"
            "    gWifiLinkOn = 0",
            "    ; auto-arm on every prompt turn; a radio-off policy must remain meaningful.\n"
            "  Else\n"
            "    gWifiLinkOn = 0",
        ),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-wifi-radio-init-emitted-") as temporary:
        work = Path(temporary)
        command_result, command_steps = run_source(
            a64, compiler, work, command_exact, "wifi_cmd_ownership_gate"
        )
        if command_result:
            print(
                f"wifi_radio_init_emitted_check: FAIL command assertion {command_result} "
                f"after {command_steps:,} A64 instructions"
            )
            return 1

        command_body = procedure(command_source, "CmdWifi")
        early_hook_body = mutate_once(
            command_body,
            "    If SettingsSetWifiSlotSsid(s, v) = 0\n",
            "    WifiConfigChanged()\n    If SettingsSetWifiSlotSsid(s, v) = 0\n",
            "command hook before setter result",
        )
        early_hook_body = mutate_once(
            early_hook_body,
            "    WifiConfigChanged()\n    Print(\"Wi-Fi slot \")",
            "    Print(\"Wi-Fi slot \")",
            "command original success hook",
        )
        early_source = command_source.replace(command_body, early_hook_body, 1)
        early_result, early_steps = run_source(
            a64, compiler, work, command_probe(early_source), "wifi_cmd_early_hook_mutant"
        )
        if early_result == 0:
            print("wifi_radio_init_emitted_check: FAIL command early-hook mutant survived")
            return 1

        result, steps = run_source(a64, compiler, work, exact, "wifi_radio_init_gate")
        if result:
            print(
                f"wifi_radio_init_emitted_check: FAIL assertion {result} "
                f"after {steps:,} A64 instructions"
            )
            return 1

        mutant_steps = 0
        for index, (label, old, new) in enumerate(mutations, 1):
            mutant = mutate_once(exact, old, new, label)
            mutant_result, used = run_source(
                a64, compiler, work, mutant, f"wifi_radio_init_mutant_{index}"
            )
            mutant_steps += used
            if mutant_result == 0:
                print(f"wifi_radio_init_emitted_check: FAIL {label} mutant survived")
                return 1

    print(
        "wifi_radio_init_emitted_check: PASS - 53 scenario assertions, "
        "17 mandatory phase-failure rows, 23 cancellation boundaries, "
        f"{steps:,} emitted A64 instructions; {len(mutations)} emitted mutants and "
        f"10 structural command mutants and 1 executed early-hook mutant rejected; "
        f"19 executed command assertions / {command_steps:,} command A64 instructions; "
        f"({mutant_steps:,} mutant instructions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
