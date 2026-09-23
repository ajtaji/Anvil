#!/usr/bin/env python3
"""Execute Anvil's real boot/network progress boundaries in the A64 model.

The probe extracts the shipped procedure bodies. Hardware, storage and packet
I/O are deterministic stubs; this proves service ordering, cadence, recursion
refusal and wrap arithmetic without modelling a display or touching a board.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "Anvil" / "Core" / "auto.pbi"
BOOTFILE = ROOT / "Anvil" / "Core" / "bootfile_cmd.pbi"
PMFBOOT = ROOT / "Anvil" / "Core" / "pmfboot.pbi"
NETCON = ROOT / "Anvil" / "Core" / "netconsole.pbi"
GENET = ROOT / "RaspberryPi4" / "Lib" / "genet.pi4"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"boot progress gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"boot progress gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def production_bodies() -> str:
    auto = AUTO.read_text(encoding="utf-8")
    bootfile = BOOTFILE.read_text(encoding="utf-8")
    pmfboot = PMFBOOT.read_text(encoding="utf-8")
    netcon = NETCON.read_text(encoding="utf-8")
    genet = GENET.read_text(encoding="utf-8")
    selected = (
        (auto, "BootWait"),
        (bootfile, "PmfDelay"),
        (bootfile, "PmfMaxFails"),
        (bootfile, "PmfFails"),
        (bootfile, "PmfSetFails"),
        (bootfile, "BootFileWait"),
        (pmfboot, "PmfVerifyPlaced"),
        (pmfboot, "PmfEnter"),
        (pmfboot, "PmfBootFile"),
        (netcon, "NetWaitSetProgressHook"),
        (netcon, "netwait_Progress"),
        (netcon, "NetDhcpAcquire"),
        (genet, "GenetTimeoutTicks"),
        (genet, "GenetSetProgressHook"),
        (genet, "genet_Progress"),
        (genet, "GenetPhyWaitLink"),
    )
    return "\n\n".join(procedure(source, name) for source, name in selected)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    """Make one deliberate source mutation, and refuse an ambiguous match."""
    if source.count(old) != 1:
        raise SystemExit(
            f"boot progress gate: mutant {label} expected one source match, "
            f"found {source.count(old)}"
        )
    return source.replace(old, new, 1)


PRELUDE = r'''
EnableExplicit

#CAP_STORAGE = 1
#BOOT_DOT = 250
#BOOT_MS = 2000
#PMF_DELAY_DEFAULT = 2
#PMF_DELAY_MAX = 30
#PMF_MAXFAILS_DEFAULT = 3
#PMF_HDR_LEN_V1 = 96
#PMF_HDR_LEN_V2 = 128
#PMF_VERSION_V2 = 2
#PMF_OFF_VERSION = 8
#PMF_OFF_HDRLEN = 12
#PMF_HDR_LEN = 96
#PMF_DIGEST = 32
#PMF_PROGRESS_CHUNK = 65536
#PMF_FLAG_RETURNS = 1
#PMF_FLAG_WANTS_DTB = 2
#PMF_FLAG_WANTS_SERVICES = 4
#SVC_ABI_MAJOR = 1
#SVC_ABI_MINOR = 0
#SVC_SLOT_COUNT = 184
#SET_ERR_NO_FILE = 2
#NETWAIT_PROGRESS_MS = 50
#DHCPC_BOUND = 4
#NET_ADDR_LEASE = 3
#GENET_PROGRESS_MS = 50
#GENET_HZ_MAX = 1000000000
#GENET_HZ_FALLBACK = 54000000
#GENET_ERR_NONE = 0
#GENET_ERR_ARG = -1
#GENET_ERR_PHY_NONE = -5
#GENET_ERR_ANEG = -8
#GENET_ERR_NO_LINK = -7
#GENET_MII_BMSR = 1
#GENET_BMSR_ANEGCAPABLE = $0008
#GENET_BMSR_LSTATUS = $0004
#GENET_BMSR_ANEGCOMPLETE = $0020

Global Dim gNumBuf.a[32]
Global Dim gPmfName.a[31]
Global gMonHitLo.i
Global gMonHitHi.i

Global gate_ticks.i
Global gate_tickStep.i
Global gate_input.i
Global gate_autoEntry.i
Global gate_runAt.i
Global gate_bootFile.i
Global gate_handoffOrdered.i
Global gate_preBootFileOrdered.i
Global gate_services.i
Global gate_paints.i
Global gate_screen.i
Global gate_output.i
Global gate_servicedOutput.i
Global gate_events.i
Global gate_lastServiceEvent.i
Global gate_dots.i
Global gate_settingsLoaded.i
Global gate_delay.i
Global gate_fails.i
Global gate_maxFails.i
Global gate_saveOk.i
Global gate_setFails.i
Global gate_fileCalls.i
Global gate_fileImageCalls.i
Global gate_fileMode.i
Global gate_fileImageResultCalls.i
Global gate_fileNeedsService.i
Global gate_fileServiced.i
Global Dim gate_fileOff.i[8]
Global Dim gate_fileLen.i[8]
Global gate_hashChunks.i
Global gate_hashNeedsService.i
Global gate_hashServiced.i

Global Dim gPmfHdr.a[#PMF_HDR_LEN_V2]
Global Dim gPmfGot.a[#PMF_DIGEST]
Global Dim gPmfWant.a[#PMF_DIGEST]
Global gPmfLoad.i
Global gPmfImgLen.i
Global gPmfEntry.i
Global gPmfFlags.i
Global gPmfHdrLen.i
Global gEntry.i
Global gHaveEntry.i
Global gSvcMayReturn.i
Global gGoX0.i

Global *gNetWaitProgressHook = 0
Global gNetWaitProgressBusy.i
Global gNetWaitProgressAt.i
Global gate_ms.i
Global gate_netProgress.i
Global gate_netBusySeen.i
Global gate_netPumps.i
Global gate_netTicks.i
Global gate_netCancels.i
Global gate_netBindAfter.i

Global *genet_progressHook = 0
Global genet_progressBusy.i
Global genet_progressAt.i
Global genet_progressStep.i
Global genet_err.i
Global genet_phyAddr.i
Global gate_genetTicks.i
Global gate_mdioStep.i
Global gate_mdioReads.i
Global gate_mdioLinkAt.i
Global gate_genetProgress.i
Global gate_genetBusySeen.i
Global gate_genetBusyRefused.i

Procedure GateBump() : gate_output = gate_output + 1 : EndProcedure
Procedure str_print_at(v.i) : GateBump() : EndProcedure
Procedure PrintNl() : GateBump() : EndProcedure
Procedure PrintDec(v.i) : GateBump() : EndProcedure
Procedure PutAddr(v.i) : GateBump() : EndProcedure
Procedure UartWriteStr(v.i) : GateBump() : EndProcedure
Procedure UartWrite(v.i) : GateBump() : If v = 46 : gate_dots = gate_dots + 1 : EndIf : EndProcedure
Procedure.i UartReadReady() : ProcedureReturn gate_input : EndProcedure
Procedure.i UartRead() : gate_input = 0 : ProcedureReturn 65 : EndProcedure
Procedure.i TickHz() : ProcedureReturn 1000 : EndProcedure
Procedure.i Ticks() : gate_ticks = gate_ticks + gate_tickStep : ProcedureReturn gate_ticks : EndProcedure
Procedure.i AutoEntry() : ProcedureReturn gate_autoEntry : EndProcedure
Procedure.i HitsMonitor(a.i, b.i) : ProcedureReturn 0 : EndProcedure
Procedure AutoSet(a.i) : gate_autoEntry = a : EndProcedure
Procedure ScreenServiceTick()
  gate_services = gate_services + 1
  gate_events = gate_events + 1
  gate_lastServiceEvent = gate_events
  gate_servicedOutput = gate_output
  If gate_fileNeedsService <> 0
    gate_fileServiced = gate_fileServiced + 1
    gate_fileNeedsService = 0
  EndIf
  If gate_hashNeedsService <> 0
    gate_hashServiced = gate_hashServiced + 1
    gate_hashNeedsService = 0
  EndIf
  If gate_screen <> 0 : gate_paints = gate_paints + 1 : EndIf
EndProcedure
Procedure RunAt(a.i)
  gate_events = gate_events + 1
  gate_runAt = a
  If gate_lastServiceEvent = (gate_events - 1) : gate_handoffOrdered = gate_handoffOrdered + 1 : EndIf
EndProcedure

Procedure.i PmfKeyFile() : ProcedureReturn ?keyFile : EndProcedure
Procedure.i PmfKeyDelay() : ProcedureReturn ?keyDelay : EndProcedure
Procedure.i PmfKeyFails() : ProcedureReturn ?keyFails : EndProcedure
Procedure.i PmfKeyMaxFails() : ProcedureReturn ?keyMax : EndProcedure
Procedure.i PmfDecOf(p.i, fallback.i)
  If p = ?delayValue : ProcedureReturn gate_delay : EndIf
  If p = ?failsValue : ProcedureReturn gate_fails : EndIf
  If p = ?maxValue : ProcedureReturn gate_maxFails : EndIf
  ProcedureReturn fallback
EndProcedure
Procedure PmfPutDec(v.i, p.i) : PokeA(p, 48 + (v % 10)) : PokeA(p + 1, 0) : EndProcedure
Procedure.i SettingsGet(k.i)
  If k = ?keyFile : ProcedureReturn ?fileValue : EndIf
  If k = ?keyDelay : ProcedureReturn ?delayValue : EndIf
  If k = ?keyFails : ProcedureReturn ?failsValue : EndIf
  If k = ?keyMax : ProcedureReturn ?maxValue : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i SettingsSet(k.i, v.i) : gate_setFails = gate_setFails + 1 : ProcedureReturn gate_saveOk : EndProcedure
Procedure.i SettingsSave() : ProcedureReturn gate_saveOk : EndProcedure
Procedure.i SettingsLoadState() : ProcedureReturn gate_settingsLoaded : EndProcedure
Procedure.i SettingsLoad() : gate_settingsLoaded = 1 : ProcedureReturn 1 : EndProcedure
Procedure.i SettingsLastError() : ProcedureReturn 0 : EndProcedure
Procedure SettingsSayWhyNot() : GateBump() : EndProcedure
Procedure.i HwStorageUp()
  gate_events = gate_events + 1
  If gate_lastServiceEvent = (gate_events - 1) And gate_servicedOutput = gate_output
    gate_preBootFileOrdered = gate_preBootFileOrdered + 1
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i HwFileOpen(p.i) : gate_bootFile = p : ProcedureReturn 1 : EndProcedure
Procedure.i HwFileSize() : ProcedureReturn #PMF_HDR_LEN + gPmfImgLen : EndProcedure
Procedure.i HwFileReadAt(off.i, dst.i, n.i)
  Define answer.i
  gate_fileOff[gate_fileCalls] = off
  gate_fileLen[gate_fileCalls] = n
  gate_fileCalls = gate_fileCalls + 1
  answer = n
  If off >= #PMF_HDR_LEN
    gate_fileImageCalls = gate_fileImageCalls + 1
    gate_fileImageResultCalls = gate_fileImageResultCalls + 1
    If gate_fileMode = 1 And gate_fileImageResultCalls = 1
      answer = 0
    EndIf
    If gate_fileMode = 2 And gate_fileImageResultCalls = 1
      answer = n - 1
    EndIf
    If gate_fileMode = 3 And gate_fileImageResultCalls = 1
      answer = -1
    EndIf
    If gate_fileMode = 4 And gate_fileImageResultCalls = 2
      answer = -1
    EndIf
    If answer > 0
      gate_fileNeedsService = 1
    EndIf
  EndIf
  ProcedureReturn answer
EndProcedure
Procedure HwFileClose() : EndProcedure
Procedure.i HwFileErrorText() : ProcedureReturn ?fileError : EndProcedure
Procedure.i PmfMagicOk(p.i) : ProcedureReturn 1 : EndProcedure
Procedure.i PmfRd32(p.i) : ProcedureReturn 0 : EndProcedure
Procedure PmfParseAt(p.i) : gPmfHdrLen = #PMF_HDR_LEN_V1 : EndProcedure
Procedure.i PmfCheckHeader(n.i) : ProcedureReturn 1 : EndProcedure
Procedure.i PmfCheckPlacement() : ProcedureReturn 1 : EndProcedure
Procedure UartDrain() : EndProcedure
Procedure.i OutBreak() : ProcedureReturn 0 : EndProcedure
Procedure Sha256Begin() : gate_hashChunks = 0 : EndProcedure
Procedure Sha256Update(p.i, n.i) : gate_hashChunks = gate_hashChunks + 1 : gate_hashNeedsService = 1 : EndProcedure
Procedure Sha256End(p.i)
  Define i.i
  For i = 0 To #PMF_DIGEST - 1 : PokeA(p + i, 0) : Next
EndProcedure
Procedure PmfPutDigest(p.i) : EndProcedure
Procedure PmfZeroBss() : EndProcedure
Procedure BuildServiceTable() : EndProcedure
Procedure.i SvcTableAddr() : ProcedureReturn $44550000 : EndProcedure

Procedure.i millis() : ProcedureReturn gate_ms & $FFFFFFFF : EndProcedure
Procedure.i NetDhcpStart(kind.i, keep.i) : ProcedureReturn 1 : EndProcedure
Procedure netcon_PumpOne(kind.i) : gate_netPumps = gate_netPumps + 1 : EndProcedure
Procedure NetDhcpTick() : gate_netTicks = gate_netTicks + 1 : gate_ms = (gate_ms + 10) & $FFFFFFFF : EndProcedure
Procedure.i DhcpClientState(kind.i)
  If gate_netBindAfter > 0 And gate_netTicks >= gate_netBindAfter : ProcedureReturn #DHCPC_BOUND : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NetIfSrc(kind.i)
  If DhcpClientState(kind) = #DHCPC_BOUND : ProcedureReturn #NET_ADDR_LEASE : EndIf
  ProcedureReturn 0
EndProcedure
Procedure NetDhcpCancel(kind.i) : gate_netCancels = gate_netCancels + 1 : EndProcedure
Global Dim netdhcp_auto.i[6]
; No call back into netwait_Progress() from the hook: the compiler
; refuses that loop (see ProbeGenetProgress below). The hook records that
; the busy guard is armed while it runs; the main body arms the guard by
; hand and shows a call under it reaches no hook.
Procedure ProbeNetProgress()
  gate_netProgress = gate_netProgress + 1
  If gNetWaitProgressBusy <> 0 : gate_netBusySeen = gate_netBusySeen + 1 : EndIf
EndProcedure

Procedure.i genet_Ticks() : ProcedureReturn gate_genetTicks : EndProcedure
Procedure.i genet_TickHz() : ProcedureReturn 1000 : EndProcedure
Procedure.i GenetMdioRead(a.i, r.i)
  gate_mdioReads = gate_mdioReads + 1
  gate_genetTicks = gate_genetTicks + gate_mdioStep
  If gate_mdioLinkAt > 0 And gate_mdioReads >= gate_mdioLinkAt
    ProcedureReturn #GENET_BMSR_ANEGCAPABLE | #GENET_BMSR_LSTATUS | #GENET_BMSR_ANEGCOMPLETE
  EndIf
  ProcedureReturn #GENET_BMSR_ANEGCAPABLE
EndProcedure
; The hook does not call genet_Progress() back. It used to, to show a
; second entry was refused at depth one, and the compiler now refuses
; that loop itself - a call through the hook variable is a call to every
; procedure assigned to it, and this one led straight back. The guard
; is proven the other way round: the hook records that the busy flag is
; armed while it runs, and the main body arms the flag by hand and shows
; a call under it reaches no hook at all.
Procedure ProbeGenetProgress()
  gate_genetProgress = gate_genetProgress + 1
  If genet_progressBusy <> 0 : gate_genetBusySeen = gate_genetBusySeen + 1 : EndIf
EndProcedure
'''


MAIN = r'''
Procedure GateBootReset()
  gate_ticks = 0 : gate_tickStep = 25 : gate_input = 0
  gate_runAt = 0 : gate_bootFile = 0 : gate_handoffOrdered = 0
  gate_preBootFileOrdered = 0
  gate_services = 0 : gate_paints = 0 : gate_screen = 1
  gate_output = 0 : gate_servicedOutput = 0 : gate_events = 0
  gate_lastServiceEvent = 0 : gate_dots = 0
  gate_settingsLoaded = 1 : gate_delay = 1 : gate_fails = 0
  gate_maxFails = 3 : gate_saveOk = 1 : gate_setFails = 0
  gate_fileCalls = 0 : gate_fileImageCalls = 0
  gate_fileMode = 0 : gate_fileImageResultCalls = 0
  gate_fileNeedsService = 0 : gate_fileServiced = 0
  gate_hashChunks = 0 : gate_hashNeedsService = 0 : gate_hashServiced = 0
  gPmfLoad = $02000000 : gPmfImgLen = 131073 : gPmfEntry = $02000100
  gPmfFlags = #PMF_FLAG_RETURNS
  gate_bootFile = 0
EndProcedure

Procedure GateNetReset()
  NetWaitSetProgressHook(0)
  gate_ms = 1000 : gate_netProgress = 0 : gate_netBusySeen = 0
  gate_netPumps = 0 : gate_netTicks = 0
  gate_netCancels = 0 : gate_netBindAfter = 0
EndProcedure

Procedure GateGenetReset()
  GenetSetProgressHook(0)
  gate_genetTicks = 0 : gate_mdioStep = 10 : gate_mdioReads = 0
  gate_mdioLinkAt = 9 : gate_genetProgress = 0 : gate_genetBusySeen = 0
  gate_genetBusyRefused = 0 : genet_phyAddr = 1 : genet_err = 0
EndProcedure

Procedure.i Main()
  Define offPumps.i
  Define offTicks.i
  Define offCancels.i
  Define offReads.i
  Define rc.i

  ; Real BootWait: announcement/dots/final newline are serviced and the final
  ; service is immediately before the potentially non-returning RunAt.
  GateBootReset()
  gate_autoEntry = $12345000
  BootWait()
  If gate_runAt <> gate_autoEntry Or gate_handoffOrdered <> 1 : ProcedureReturn 1 : EndIf
  If gate_dots < 1 Or gate_services < (gate_dots + 2) : ProcedureReturn 2 : EndIf

  ; The key-stop prose is serviced; no handoff occurs.
  GateBootReset()
  gate_autoEntry = $12345000 : gate_input = 1
  BootWait()
  If gate_runAt <> 0 Or gate_servicedOutput <> gate_output : ProcedureReturn 3 : EndIf

  ; Real BootFileWait, with no screen backend: service remains safe/inert and
  ; the pre-handoff order is still mandatory on both shared-core consumers.
  GateBootReset()
  gate_screen = 0
  BootFileWait()
  If gate_bootFile = 0 Or gate_preBootFileOrdered <> 1 Or gate_handoffOrdered <> 1 Or gate_paints <> 0 : ProcedureReturn 4 : EndIf
  If gate_setFails <> 1 Or gate_dots < 1 Or gate_services < (gate_dots + 2) : ProcedureReturn 5 : EndIf
  If gate_fileCalls <> 4 Or gate_fileImageCalls <> 3 Or gate_hashChunks <> 3 : ProcedureReturn 17 : EndIf
  If gate_fileServiced <> 3 Or gate_fileNeedsService <> 0 : ProcedureReturn 21 : EndIf
  If gate_hashServiced <> 3 Or gate_hashNeedsService <> 0 : ProcedureReturn 22 : EndIf
  If gate_fileOff[1] <> #PMF_HDR_LEN Or gate_fileLen[1] <> #PMF_PROGRESS_CHUNK : ProcedureReturn 18 : EndIf
  If gate_fileOff[2] <> (#PMF_HDR_LEN + #PMF_PROGRESS_CHUNK) Or gate_fileLen[2] <> #PMF_PROGRESS_CHUNK : ProcedureReturn 19 : EndIf
  If gate_fileOff[3] <> (#PMF_HDR_LEN + #PMF_PROGRESS_CHUNK * 2) Or gate_fileLen[3] <> 1 : ProcedureReturn 20 : EndIf

  ; Zero, short and negative storage results all refuse before hashing or
  ; handoff. Only completed positive chunks receive a post-read service.
  GateBootReset()
  gate_fileMode = 1
  rc = PmfBootFile(?fileValue)
  If rc <> 0 Or gate_runAt <> 0 Or gate_hashChunks <> 0 : ProcedureReturn 23 : EndIf
  If gate_fileImageCalls <> 1 Or gate_fileServiced <> 0 : ProcedureReturn 24 : EndIf

  GateBootReset()
  gate_fileMode = 2
  rc = PmfBootFile(?fileValue)
  If rc <> 0 Or gate_runAt <> 0 Or gate_hashChunks <> 0 : ProcedureReturn 25 : EndIf
  If gate_fileImageCalls <> 1 Or gate_fileServiced <> 1 : ProcedureReturn 26 : EndIf

  GateBootReset()
  gate_fileMode = 3
  rc = PmfBootFile(?fileValue)
  If rc <> 0 Or gate_runAt <> 0 Or gate_hashChunks <> 0 : ProcedureReturn 27 : EndIf
  If gate_fileImageCalls <> 1 Or gate_fileServiced <> 0 : ProcedureReturn 28 : EndIf

  GateBootReset()
  gate_fileMode = 4
  rc = PmfBootFile(?fileValue)
  If rc <> 0 Or gate_runAt <> 0 Or gate_hashChunks <> 0 : ProcedureReturn 29 : EndIf
  If gate_fileImageCalls <> 2 Or gate_fileServiced <> 1 : ProcedureReturn 30 : EndIf

  ; Persisted-boot key-stop: text is serviced and the attempt counter/file
  ; entry are untouched.
  GateBootReset()
  gate_input = 1
  BootFileWait()
  If gate_bootFile <> 0 Or gate_setFails <> 0 : ProcedureReturn 6 : EndIf
  If gate_servicedOutput <> gate_output : ProcedureReturn 7 : EndIf

  ; Callback-off changes no DHCP protocol scheduling/outcome.
  GateNetReset()
  rc = NetDhcpAcquire(1, 200, 0)
  offPumps = gate_netPumps : offTicks = gate_netTicks : offCancels = gate_netCancels
  If rc <> 0 Or gate_netProgress <> 0 : ProcedureReturn 8 : EndIf
  GateNetReset()
  NetWaitSetProgressHook(@ProbeNetProgress)
  rc = NetDhcpAcquire(1, 200, 0)
  If rc <> 0 Or gate_netPumps <> offPumps Or gate_netTicks <> offTicks Or gate_netCancels <> offCancels : ProcedureReturn 9 : EndIf
  If gate_netProgress < 2 Or gate_netBusySeen <> gate_netProgress : ProcedureReturn 10 : EndIf

  ; 32-bit millis wrap: immediate first service, not at +49 ms, then at +50.
  GateNetReset()
  gate_ms = $FFFFFFF0
  NetWaitSetProgressHook(@ProbeNetProgress)
  netwait_Progress()
  If gate_netProgress <> 1 : ProcedureReturn 11 : EndIf
  gate_ms = $21
  netwait_Progress()
  If gate_netProgress <> 1 : ProcedureReturn 12 : EndIf
  gate_ms = $22
  netwait_Progress()
  If gate_netProgress <> 2 Or gate_netBusySeen <> 2 : ProcedureReturn 13 : EndIf
  ; A call under an armed guard reaches no hook; the next call without it does.
  gate_ms = $60
  gNetWaitProgressBusy = 1
  netwait_Progress()
  gNetWaitProgressBusy = 0
  If gate_netProgress <> 2 : ProcedureReturn 19 : EndIf
  netwait_Progress()
  If gate_netProgress <> 3 : ProcedureReturn 20 : EndIf

  ; GENET callback-off preserves the exact completed MDIO-read sequence and
  ; link result. The busy guard is armed for the whole of every hook call,
  ; and a call made while it is armed reaches no hook.
  GateGenetReset()
  rc = GenetPhyWaitLink(500)
  offReads = gate_mdioReads
  If rc <> 1 Or gate_genetProgress <> 0 : ProcedureReturn 14 : EndIf
  GateGenetReset()
  GenetSetProgressHook(@ProbeGenetProgress)
  rc = GenetPhyWaitLink(500)
  If rc <> 1 Or gate_mdioReads <> offReads : ProcedureReturn 15 : EndIf
  If gate_genetProgress < 1 Or gate_genetBusySeen <> gate_genetProgress : ProcedureReturn 16 : EndIf
  gate_genetBusyRefused = gate_genetProgress
  genet_progressBusy = 1
  genet_progressAt = genet_Ticks() - genet_progressStep
  genet_Progress()
  genet_progressBusy = 0
  If gate_genetProgress <> gate_genetBusyRefused : ProcedureReturn 17 : EndIf
  genet_Progress()
  If gate_genetProgress <> gate_genetBusyRefused + 1 : ProcedureReturn 18 : EndIf

  ProcedureReturn 0
EndProcedure

DataSection
  keyFile: Data.a 102,0
  keyDelay: Data.a 100,0
  keyFails: Data.a 97,0
  keyMax: Data.a 109,0
  fileValue: Data.a 65,80,80,46,80,77,70,0
  delayValue: Data.a 49,0
  failsValue: Data.a 48,0
  maxValue: Data.a 51,0
  fileError: Data.a 101,114,114,111,114,0
EndDataSection
'''


def build(compiler: Path, work: Path, source: Path, stem: str) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile", str(source), "-t", "pi4",
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
        raise SystemExit("boot progress gate: compile failed\n" + run.stdout)
    return image


def run_probe(a64, compiler: Path, work: Path, bodies: str, stem: str) -> tuple[int, int]:
    source = work / f"{stem}.pi4"
    source.write_text(PRELUDE + "\n" + bodies + "\n" + MAIN,
                      encoding="utf-8", newline="\n")
    image = build(compiler, work, source, stem)
    return emitted.execute(a64, image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument(
        "--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP)
    )
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-boot-progress-emitted-") as temporary:
        work = Path(temporary)
        bodies = production_bodies()
        result, steps = run_probe(a64, compiler, work, bodies, "boot_progress_gate")
        mutants = (
            (
                "autoboot-pre-handoff",
                "  ScreenServiceTick()\n  RunAt(e)",
                "  RunAt(e)",
            ),
            (
                "bootfile-pre-call",
                "  ScreenServiceTick()\n  PmfBootFile(@gPmfName[0])",
                "  PmfBootFile(@gPmfName[0])",
            ),
            (
                "image-chunk",
                "    ScreenServiceTick()\n    If part <> chunk",
                "    If part <> chunk",
            ),
            (
                "hash-chunk",
                "    ScreenServiceTick()\n  Wend\n  Sha256End",
                "  Wend\n  Sha256End",
            ),
            (
                "dhcp-complete-iteration",
                "    netwait_Progress()\n    If DhcpClientState",
                "    If DhcpClientState",
            ),
            (
                "phy-complete-read-pair",
                "    genet_Progress()\n\n    If (bmsr & #GENET_BMSR_LSTATUS)",
                "\n    If (bmsr & #GENET_BMSR_LSTATUS)",
            ),
        )
        mutant_steps = 0
        for index, (label, old, new) in enumerate(mutants):
            mutant = replace_once(bodies, old, new, label)
            mutant_result, used = run_probe(
                a64, compiler, work, mutant, f"boot_progress_mutant_{index}"
            )
            mutant_steps += used
            if mutant_result == 0:
                print(f"boot_progress_emitted_check: FAIL mutant {label} escaped")
                return 1
    if result:
        print(f"boot_progress_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"boot_progress_emitted_check: PASS - 30 cases, {steps:,} emitted A64 instructions")
    print(f"  6 required-boundary mutants rejected in {mutant_steps:,} emitted instructions")
    print("  real countdown, chunk/refusal/hash, PmfEnter handoff, DHCP and GENET procedures ran")
    print("  storage, packets, MDIO and display were deterministic memory-only seams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
