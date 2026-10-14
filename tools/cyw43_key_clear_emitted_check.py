#!/usr/bin/env python3
"""Emit and execute the shipped CYW43 key install / clear-on-disassociate path.

Every disassociation must remove the keys the last association installed,
the way the reference does on every disconnect (cfg80211
__cfg80211_disconnected deletes key indexes 0-5; brcmf_cfg80211_del_key
sends each configured one as a wsec_key with the index, flags
BRCMF_PRIMARY_KEY, algorithm OFF, length 0 and no address). Before this,
`wifi rejoin` re-associated with the old session's keys still in the
firmware and only a reset (a firmware reload) removed them.

The procedures are taken verbatim from Anvil/Net/cyw43.pbi; only the
firmware transport (Cyw43IoctlSet, Cyw43SetBsscfgData) is stubbed, and the
stub records every wsec_key struct the code sends.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
CYW43 = ROOT / "Anvil" / "Net" / "cyw43.pbi"


def procedure(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^Procedure(?:\.i)? {name}\(.*?^EndProcedure\s*$", source)
    if not match:
        raise SystemExit(f"cyw43 key clear gate: production procedure {name} not found")
    return match.group(0)


def constant(source: str, name: str) -> str:
    match = re.search(rf"(?m)^#{name}\s*=.*$", source)
    if not match:
        raise SystemExit(f"cyw43 key clear gate: production constant #{name} not found")
    return match.group(0)


def probe_source(source: str) -> str:
    names = (
        "CYW43_KEY_STRUCT", "CYW43_KEY_OFF_INDEX", "CYW43_KEY_OFF_LEN",
        "CYW43_KEY_OFF_DATA", "CYW43_KEY_OFF_ALGO", "CYW43_KEY_OFF_FLAGS",
        "CYW43_KEY_OFF_IVINIT", "CYW43_KEY_OFF_RXIVHI", "CYW43_KEY_OFF_RXIVLO",
        "CYW43_KEY_OFF_EA", "CYW43_KEY_DATA_MAX", "CYW43_CRYPTO_ALGO_OFF",
        "CYW43_CRYPTO_ALGO_AES_CCM", "CYW43_PRIMARY_KEY", "CYW43_WSECKEY_NAMELEN",
        "CYW43_IFACE_STA", "CYW43_C_DISASSOC", "CYW43_IO_OK", "CYW43_IO_TOOBIG",
    )
    constants = "\n".join(constant(source, name) for name in names)
    keyset = re.search(r"(?m)^Global cyw43_keySet\.i = 0.*$", source)
    keybuf = re.search(r"(?m)^Global Dim cyw43_keybuf\.l\[42\].*$", source)
    if not keyset or not keybuf:
        raise SystemExit("cyw43 key clear gate: key globals not found")
    bodies = "\n\n".join(procedure(source, name) for name in (
        "cyw43_PutLE32", "Cyw43SetWsecKey", "Cyw43ClearKeys",
        "Cyw43KeysInstalled", "Cyw43Disassoc",
    ))
    stubs = r'''
Global gate_disassocs.i = 0
Global gate_disassocRc.i = 0
Global gate_keyRc.i = 0
Global gate_sends.i = 0
Global gate_badName.i = 0
Global Dim gateIndex.i[16]
Global Dim gateLen.i[16]
Global Dim gateAlgo.i[16]
Global Dim gateFlags.i[16]
Global Dim gateEaSum.i[16]
Global Dim gateDataSum.i[16]

Procedure.i gate_Le32(p.i)
  ProcedureReturn PeekA(p) | (PeekA(p + 1) << 8) | (PeekA(p + 2) << 16) | (PeekA(p + 3) << 24)
EndProcedure

Procedure.i Cyw43IoctlSet(cmd.i, *src, len.i, timeoutMs.i)
  If cmd = #CYW43_C_DISASSOC
    gate_disassocs = gate_disassocs + 1
  EndIf
  ProcedureReturn gate_disassocRc
EndProcedure

; Records the wsec_key struct exactly as the firmware would read it.
Procedure.i Cyw43SetBsscfgData(src.i, namelen.i, idx.i, *data, datalen.i, timeoutMs.i)
  Define i.i
  Define s.i
  Define n.i
  If src <> ?cyw43_WsecKeyName Or namelen <> #CYW43_WSECKEY_NAMELEN Or datalen <> #CYW43_KEY_STRUCT
    gate_badName = gate_badName + 1
  EndIf
  n = gate_sends
  If n < 16
    gateIndex[n] = gate_Le32(*data + #CYW43_KEY_OFF_INDEX)
    gateLen[n] = gate_Le32(*data + #CYW43_KEY_OFF_LEN)
    gateAlgo[n] = gate_Le32(*data + #CYW43_KEY_OFF_ALGO)
    gateFlags[n] = gate_Le32(*data + #CYW43_KEY_OFF_FLAGS)
    s = 0
    For i = 0 To 5
      s = s + PeekA(*data + #CYW43_KEY_OFF_EA + i)
    Next
    gateEaSum[n] = s
    s = 0
    For i = 0 To #CYW43_KEY_DATA_MAX - 1
      s = s + PeekA(*data + #CYW43_KEY_OFF_DATA + i)
    Next
    gateDataSum[n] = s
  EndIf
  gate_sends = gate_sends + 1
  ProcedureReturn gate_keyRc
EndProcedure

DataSection
  cyw43_WsecKeyName:
    Data.b 98, 115, 115, 99, 102, 103, 58, 119, 115, 101, 99, 95, 107, 101, 121
  gateKey:
    Data.b 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
  gateMac:
    Data.b $AA, $BB, $CC, $DD, $EE, $FF
  gateRsc:
    Data.b 1, 0, 0, 0, 0, 0, 0, 0
EndDataSection

; A cleared slot as brcmf_cfg80211_del_key sends it.
Procedure.i gate_IsClear(n.i, index.i)
  If gateIndex[n] <> index
    ProcedureReturn 0
  EndIf
  If gateLen[n] <> 0 Or gateAlgo[n] <> #CYW43_CRYPTO_ALGO_OFF Or gateFlags[n] <> #CYW43_PRIMARY_KEY
    ProcedureReturn 0
  EndIf
  If gateEaSum[n] <> 0 Or gateDataSum[n] <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i GateMain()
  ; 1. A first disassociation, nothing installed: the ioctl, and no key sends.
  If Cyw43Disassoc(2000) <> 0
    ProcedureReturn 10
  EndIf
  If gate_disassocs <> 1 Or gate_sends <> 0
    ProcedureReturn 11
  EndIf

  ; 2. A session's keys: pairwise at index 0 for the AP, group at index 2.
  If Cyw43SetWsecKey(0, ?gateKey, 16, #CYW43_CRYPTO_ALGO_AES_CCM, ?gateMac, 0, 2000) <> 0
    ProcedureReturn 20
  EndIf
  If Cyw43SetWsecKey(2, ?gateKey, 16, #CYW43_CRYPTO_ALGO_AES_CCM, 0, ?gateRsc, 2000) <> 0
    ProcedureReturn 21
  EndIf
  If Cyw43KeysInstalled() <> 5 Or gate_sends <> 2
    ProcedureReturn 22
  EndIf

  ; 3. The kick / rejoin: disassociate. Both slots must be cleared, in
  ;    index order, each exactly as the reference clears it.
  gate_sends = 0
  If Cyw43Disassoc(2000) <> 0
    ProcedureReturn 30
  EndIf
  If gate_disassocs <> 2
    ProcedureReturn 31
  EndIf
  If gate_sends <> 2
    ProcedureReturn 32
  EndIf
  If gate_IsClear(0, 0) = 0
    ProcedureReturn 33
  EndIf
  If gate_IsClear(1, 2) = 0
    ProcedureReturn 34
  EndIf
  If Cyw43KeysInstalled() <> 0
    ProcedureReturn 35
  EndIf

  ; 4. Nothing left: the next disassociation sends no key.
  gate_sends = 0
  Cyw43Disassoc(2000)
  If gate_sends <> 0
    ProcedureReturn 40
  EndIf

  ; 5. A clear the firmware refuses stays owed and is retried next time;
  ;    the disassociation's own rc is what Cyw43Disassoc returns.
  Cyw43SetWsecKey(1, ?gateKey, 16, #CYW43_CRYPTO_ALGO_AES_CCM, 0, ?gateRsc, 2000)
  gate_keyRc = -5
  gate_sends = 0
  gate_disassocRc = 7
  If Cyw43Disassoc(2000) <> 7
    ProcedureReturn 50
  EndIf
  If gate_sends <> 1 Or Cyw43KeysInstalled() <> 2
    ProcedureReturn 51
  EndIf
  If Cyw43ClearKeys(2000) <> -5
    ProcedureReturn 52
  EndIf
  gate_keyRc = 0
  gate_disassocRc = 0
  gate_sends = 0
  Cyw43Disassoc(2000)
  If gate_sends <> 1 Or gate_IsClear(0, 1) = 0 Or Cyw43KeysInstalled() <> 0
    ProcedureReturn 53
  EndIf

  ; 6. An install the firmware refused is not recorded as installed.
  gate_keyRc = -3
  Cyw43SetWsecKey(3, ?gateKey, 16, #CYW43_CRYPTO_ALGO_AES_CCM, 0, ?gateRsc, 2000)
  gate_keyRc = 0
  If Cyw43KeysInstalled() <> 0
    ProcedureReturn 60
  EndIf

  If gate_badName <> 0
    ProcedureReturn 70
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i main()
  ProcedureReturn GateMain()
EndProcedure
'''
    return ("EnableExplicit\n\n" + constants + "\n" + keyset.group(0) + "\n"
            + keybuf.group(0) + "\n" + stubs + "\n" + bodies + "\n")


def build(compiler: Path, work: Path, probe: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / "cyw43_key_clear_gate.img"
    command = [str(staged), "--compile", str(probe), "-t", "pi4",
               "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("cyw43 key clear gate: compile failed\n" + run.stdout)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    source = CYW43.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-cyw43-key-clear-") as temporary:
        work = Path(temporary)
        probe = work / "cyw43_key_clear_gate.pi4"
        exact = probe_source(source)
        probe.write_text(exact, encoding="utf-8", newline="\n")
        result, steps = emitted.execute(a64, build(compiler, work, probe))
        if result != 0:
            raise SystemExit(f"cyw43 key clear gate: FAIL - case code {result}")

        # The defect itself: a disassociation that leaves the keys behind.
        disassoc = procedure(source, "Cyw43Disassoc")
        mutant = disassoc.replace("  Cyw43ClearKeys(timeoutMs)\n", "", 1)
        if mutant == disassoc:
            raise SystemExit("cyw43 key clear gate: no-clear mutation site not found")
        probe.write_text(probe_source(source.replace(disassoc, mutant, 1)), encoding="utf-8", newline="\n")
        mutant_result, _ = emitted.execute(a64, build(compiler, work, probe))
        if mutant_result != 32:
            raise SystemExit(f"cyw43 key clear gate: the keep-old-keys mutant returned {mutant_result}, expected 32")

        # Clearing with the slot's address still on it is not the reference clear.
        clear = procedure(source, "Cyw43ClearKeys")
        mutant = clear.replace("#CYW43_CRYPTO_ALGO_OFF)", "#CYW43_CRYPTO_ALGO_AES_CCM)", 1)
        if mutant == clear:
            raise SystemExit("cyw43 key clear gate: algorithm mutation site not found")
        probe.write_text(probe_source(source.replace(clear, mutant, 1)), encoding="utf-8", newline="\n")
        mutant_result, _ = emitted.execute(a64, build(compiler, work, probe))
        if mutant_result != 33:
            raise SystemExit(f"cyw43 key clear gate: the wrong-algorithm mutant returned {mutant_result}, expected 33")

        # A refused clear that is forgotten instead of retried.
        mutant = clear.replace("      If r = 0\n        cyw43_keySet", "      If 1\n        cyw43_keySet", 1)
        if mutant == clear:
            raise SystemExit("cyw43 key clear gate: forget-on-refusal mutation site not found")
        probe.write_text(probe_source(source.replace(clear, mutant, 1)), encoding="utf-8", newline="\n")
        mutant_result, _ = emitted.execute(a64, build(compiler, work, probe))
        if mutant_result != 51:
            raise SystemExit(f"cyw43 key clear gate: the forget-on-refusal mutant returned {mutant_result}, expected 51")

    print(f"cyw43_key_clear_emitted_check: PASS - 6 cases, {steps:,} A64 instructions; "
          "keep-old-keys, wrong-algorithm and forget-on-refusal mutants rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
