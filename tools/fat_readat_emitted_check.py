#!/usr/bin/env python3
"""Execute the Pi HwFileReadAt continuation against real FAT read code.

The emitted probe uses the production FatRead/FatSeek/chain procedures and
the production HwFile seam over a sparse, fragmented, memory-only FAT32
fixture.  It checks exact bytes, chain-sector reads, random/repeated offsets,
failure invalidation and open/close lifecycle without touching a block device.
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
FAT = ROOT / "Anvil" / "Storage" / "fat32.pbi"
HWFILE = ROOT / "Anvil" / "Storage" / "hwfile.pbi"
LOCAL_INTERP = ROOT / "tools" / "a64" / "a64_interp.py"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"fat read-at gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"fat read-at gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def production_bodies(hw_source: str | None = None) -> str:
    fat = FAT.read_text(encoding="utf-8")
    hw = HWFILE.read_text(encoding="utf-8") if hw_source is None else hw_source
    fat_names = (
        "fat_Fail", "fat_CopyBytes", "fat_ReadRaw", "fat_ReadRun", "fat_ReadSec",
        "fat_ReadFatSec", "fat_ClusterValid", "fat_ClusterLba",
        "fat_NextCluster", "fat_ReadAdvance", "fat_RunSectors", "FatRead", "FatClose", "fat_NextOrAlloc",
        "fat_ChainAt", "fat_FixCursor", "FatSeek", "FatTell",
        "FatLastError",
    )
    hw_names = (
        "hwfile_MapFat", "HwFileOpen", "HwFileReadAt", "HwFileClose",
        # The failure-REPORTING half of the seam. It is here because the
        # reason a change failed and the code for it do not survive equally
        # long: hwfile_FinishChange settles the volume with a flush, and a
        # flush resets the filesystem's error, so words fetched afterwards
        # are about the flush. See hwfile_MapFat's header.
        "hwfile_SettleAfterFailure", "hwfile_FinishChange", "HwFileErrorText",
    )
    return "\n\n".join(
        [procedure(fat, name) for name in fat_names]
        + [FACADE]
        + [procedure(hw, name) for name in hw_names]
    )


# Since 2026-09-16 the seam reaches FAT through the filesystem facade
# (Anvil/Storage/filesystem.pbi). This proof is about the FAT cursor under the
# seam, so the facade is reduced to the FAT branch of each call it uses - the
# same one-line forwarding the real facade does when a FAT volume is mounted.
# Until 2026-09-17 the gate did not build at all for want of these names.
FACADE = r'''
Procedure.i FsOpen(*path)
  ProcedureReturn FatOpen(*path)
EndProcedure

Procedure.i FsRead(*dst, count.i)
  ProcedureReturn FatRead(*dst, count)
EndProcedure

Procedure.i FsSeek(position.i)
  ProcedureReturn FatSeek(position)
EndProcedure

Procedure.i FsTell()
  ProcedureReturn FatTell()
EndProcedure

Procedure FsClose()
  FatClose()
EndProcedure

Procedure.i FsSize()
  ProcedureReturn fat_fileSize
EndProcedure

Procedure.i FsLastError()
  ProcedureReturn FatLastError()
EndProcedure

Procedure.i FsErrorIsNotFound()
  ProcedureReturn Bool(FatLastError() = #FAT_ERR_NOTFOUND)
EndProcedure

Procedure.i FsErrorIsNoWriter()
  ProcedureReturn Bool(FatLastError() = #FAT_ERR_NO_WRITER)
EndProcedure

; THE SENTENCE, and the flush that destroys it. Two distinguishable first
; bytes are all the probe needs: 90 (Z) while the filesystem has an error to
; report, 110 (n) once it has none - which is the shape of the real facade,
; whose no-error sentence is "nothing went wrong".
Procedure.i FsErrorText()
  If FatLastError() = 0
    ProcedureReturn "nothing went wrong"
  EndIf
  ProcedureReturn "Z: the filesystem's own reason for this failure"
EndProcedure

; FsFlush as the real one behaves on this path: it clears the error first
; and, when it succeeds, leaves the layer reporting OK. That is exactly what
; wipes the reason out from under a later reader.
Procedure.i FsFlush()
  fat_err = #FAT_ERR_NONE
  gateFlushes = gateFlushes + 1
  ProcedureReturn 1
EndProcedure

Procedure FsSetRangeWriter(address.i)
  gateWriterArmed = address
EndProcedure
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(
            f"fat read-at gate: mutant {label} expected one source match, "
            f"found {source.count(old)}"
        )
    return source.replace(old, new, 1)


PRELUDE = r'''
EnableExplicit

#FAT_SECTOR_SIZE = 512
#FAT_ENTRY_MASK = $0FFFFFFF
#FAT_CLUS_BAD = $0FFFFFF7
#FAT_CLUS_EOC = $0FFFFFF8
#FAT_ERR_NONE = 0
#FAT_ERR_NO_READER = 1
#FAT_ERR_READ_FAIL = 2
#FAT_ERR_NOT_MOUNTED = 26
#FAT_ERR_NOTFOUND = 28
#FAT_ERR_BADCLUS = 31
#FAT_ERR_BADCLUS_MARK = 32
#FAT_ERR_CHAINLOOP = 33
#FAT_ERR_SHORT_CHAIN = 34
#FAT_ERR_FILE_CLUSTER = 35
#FAT_ERR_NO_FILE = 36
#FAT_ERR_NULL_DST = 37
#FAT_ERR_BAD_MAX = 38
#FAT_ERR_NO_WRITER = 40
#FAT_ERR_BAD_LEN = 48

#HW_FILE_OK = 0
#HW_FILE_NOMEDIUM = 1
#HW_FILE_NOTFOUND = 2
#HW_FILE_NOTOPEN = 3
#HW_FILE_BADNAME = 4
#HW_FILE_READONLY = 5
#HW_FILE_TOOBIG = 6
#HW_FILE_IO = 7
#HW_FILE_UNNAMED = 9

#GATE_CLUSTER_STRIDE = 128
#GATE_FAT_LBA = 100
#GATE_DATA_LBA = 10000
#GATE_CLUSTERS = 16
#GATE_BYTES = #GATE_CLUSTERS * #FAT_SECTOR_SIZE

Global *fat_reader
Global fat_err.i
Global gateFlushes.i
Global gateWriterArmed.i
Global fat_lastLba.i
Global fat_mounted.i
Global fat_open.i
Global fat_fileSize.i
Global fat_firstClus.i
Global fat_curClus.i
Global fat_pos.i
Global fat_fileSteps.i
Global fat_entLba.i
Global fat_entOff.i
Global fat_attr.i
Global fat_clusterCount.i
Global fat_secPerClus.i
Global fat_clusterBytes.i
Global fat_fatLba.i
Global fat_dataLba.i
Global fat_secLba.i
Global fat_fatBufLba.i
Global fat_changeBegun.i
Global fat_ioFailed.i
Global Dim fat_secBuf.a[#FAT_SECTOR_SIZE]
Global Dim fat_fatBuf.a[#FAT_SECTOR_SIZE]

Global gHwFileErr.i
Global gHwFileFsText.i
Global gHwFileOpen.i
Global gHwFileReadCont.i
Global gHwFileMounted.i = 1

Global gateFatReads.i
Global gateDataReads.i
Global gateFailFatIndex.i
Global gateFailFatArmed.i
Global gateFailDataIndex.i
Global gateFailDataArmed.i
Global Dim gateBuf.a[4095]

Procedure fat_PutU32(*p, off.i, v.i)
  PokeA(*p + off, v & $FF)
  PokeA(*p + off + 1, (v >> 8) & $FF)
  PokeA(*p + off + 2, (v >> 16) & $FF)
  PokeA(*p + off + 3, (v >> 24) & $FF)
EndProcedure

Procedure.i fat_U32(*p, off.i)
  ProcedureReturn PeekA(*p + off) | (PeekA(*p + off + 1) << 8) | (PeekA(*p + off + 2) << 16) | (PeekA(*p + off + 3) << 24)
EndProcedure

Procedure.i fat_AllocCluster(prev.i)
  fat_err = #FAT_ERR_BADCLUS
  ProcedureReturn 0
EndProcedure

Procedure.i GateCluster(index.i)
  ProcedureReturn 2 + index * #GATE_CLUSTER_STRIDE
EndProcedure

; Nothing in a read changes the FAT, so there is never a sector to write back.
Procedure.i fat_FlushFat()
  ProcedureReturn 1
EndProcedure

Procedure.i GateBlock(lba.i, *dst)
  Define i.i
  Define sec.i
  Define cl.i
  Define index.i
  i = 0
  While i < #FAT_SECTOR_SIZE
    PokeA(*dst + i, 0)
    i = i + 1
  Wend

  If lba >= #GATE_FAT_LBA And lba < (#GATE_FAT_LBA + #GATE_CLUSTERS)
    sec = lba - #GATE_FAT_LBA
    gateFatReads = gateFatReads + 1
    If gateFailFatArmed <> 0 And sec = gateFailFatIndex
      gateFailFatArmed = 0
      ProcedureReturn 0
    EndIf
    If sec < (#GATE_CLUSTERS - 1)
      fat_PutU32(*dst, 8, GateCluster(sec + 1))
    Else
      fat_PutU32(*dst, 8, $0FFFFFFF)
    EndIf
    ProcedureReturn 1
  EndIf

  If lba >= #GATE_DATA_LBA
    cl = (lba - #GATE_DATA_LBA) + 2
    If cl >= 2 And ((cl - 2) % #GATE_CLUSTER_STRIDE) = 0
      index = (cl - 2) / #GATE_CLUSTER_STRIDE
      If index >= 0 And index < #GATE_CLUSTERS
        gateDataReads = gateDataReads + 1
        If gateFailDataArmed <> 0 And index = gateFailDataIndex
          gateFailDataArmed = 0
          ProcedureReturn 0
        EndIf
        i = 0
        While i < #FAT_SECTOR_SIZE
          PokeA(*dst + i, (index + i) & $FF)
          i = i + 1
        Wend
        ProcedureReturn 1
      EndIf
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

; The block-range seam: every block of the run is served, and counted, as
; the one-block reader always counted it.
Procedure.i GateReader(lba.i, count.i, *dst)
  Define k.i
  k = 0
  While k < count
    If GateBlock(lba + k, *dst + k * #FAT_SECTOR_SIZE) = 0
      ProcedureReturn 0
    EndIf
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure GateReset()
  *fat_reader = @GateReader
  fat_err = #FAT_ERR_NONE : fat_lastLba = -1
  fat_mounted = 1 : fat_open = 1
  fat_fileSize = #GATE_BYTES : fat_firstClus = GateCluster(0)
  fat_curClus = fat_firstClus : fat_pos = 0 : fat_fileSteps = 0
  fat_clusterCount = 10000 : fat_secPerClus = 1
  fat_clusterBytes = #FAT_SECTOR_SIZE
  fat_fatLba = #GATE_FAT_LBA : fat_dataLba = #GATE_DATA_LBA
  fat_secLba = -1 : fat_fatBufLba = -1
  gHwFileErr = #HW_FILE_OK : gHwFileOpen = 1 : gHwFileReadCont = 1
  gateFatReads = 0 : gateDataReads = 0
  gateFailFatIndex = -1 : gateFailFatArmed = 0
  gateFailDataIndex = -1 : gateFailDataArmed = 0
EndProcedure

; HwFileOpen's production seam is tested with a deterministic open of the
; same fabricated file. FatRead/FatSeek themselves remain the real bodies.
Procedure.i FatOpen(name.i)
  fat_open = 1 : fat_err = #FAT_ERR_NONE
  fat_firstClus = GateCluster(0) : fat_curClus = fat_firstClus
  fat_pos = 0 : fat_fileSteps = 0
  ProcedureReturn 1
EndProcedure

Procedure.i GateBytes(off.i, n.i)
  Define i.i
  Define index.i
  Define inSec.i
  i = 0
  While i < n
    index = (off + i) / #FAT_SECTOR_SIZE
    inSec = (off + i) % #FAT_SECTOR_SIZE
    If PeekA(@gateBuf[0] + i) <> ((index + inSec) & $FF)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure
'''


MAIN = r'''
Procedure.i Main()
  Define off.i
  Define got.i
  Define before.i

  ; Sequential chunks traverse each chain edge once. The fragmented fixture
  ; puts every next-cluster entry in a different FAT sector, so this count is
  ; the actual number of block-reader FAT accesses, not a helper counter.
  GateReset()
  off = 0
  While off < #GATE_BYTES
    got = HwFileReadAt(off, @gateBuf[0], 2048)
    If got <> 2048 Or GateBytes(off, got) = 0 : ProcedureReturn 1 : EndIf
    off = off + got
  Wend
  If gateFatReads <> (#GATE_CLUSTERS - 1) : ProcedureReturn 2 : EndIf
  If gateDataReads <> #GATE_CLUSTERS : ProcedureReturn 3 : EndIf

  ; A repeated non-current offset is an offset transaction and must rebuild
  ; from the first cluster both times.
  GateReset()
  got = HwFileReadAt(4096, @gateBuf[0], 512)
  If got <> 512 Or GateBytes(4096, got) = 0 : ProcedureReturn 4 : EndIf
  before = gateFatReads
  got = HwFileReadAt(4096, @gateBuf[0], 512)
  If got <> 512 Or GateBytes(4096, got) = 0 : ProcedureReturn 5 : EndIf
  If gateFatReads <= before : ProcedureReturn 6 : EndIf

  ; Forward and backward random offsets preserve exact byte identity.
  got = HwFileReadAt(6144, @gateBuf[0], 733)
  If got <> 733 Or GateBytes(6144, got) = 0 : ProcedureReturn 7 : EndIf
  got = HwFileReadAt(1537, @gateBuf[0], 991)
  If got <> 991 Or GateBytes(1537, got) = 0 : ProcedureReturn 8 : EndIf

  ; A data-sector failure invalidates continuation even though the FAT cursor
  ; still names that cluster. Retry at FatTell must take a repair seek.
  GateReset()
  gateFailDataIndex = 3 : gateFailDataArmed = 1
  got = HwFileReadAt(0, @gateBuf[0], 2048)
  If got <> -1 Or gHwFileReadCont <> 0 Or FatTell() <> 1536 : ProcedureReturn 9 : EndIf
  before = gateFatReads
  got = HwFileReadAt(1536, @gateBuf[0], 512)
  If got <> 512 Or GateBytes(1536, got) = 0 : ProcedureReturn 10 : EndIf
  If gateFatReads <= before : ProcedureReturn 11 : EndIf

  ; More dangerous: the read reaches a boundary, advances fat_pos, then the
  ; next-cluster FAT access fails. FatTell equals the retry offset but
  ; fat_curClus is still the previous cluster. A tell-only optimization reads
  ; the wrong sector; the continuation token forces a repairing seek.
  GateReset()
  gateFailFatIndex = 1 : gateFailFatArmed = 1
  got = HwFileReadAt(0, @gateBuf[0], 1024)
  If got <> -1 Or gHwFileReadCont <> 0 Or FatTell() <> 1024 : ProcedureReturn 12 : EndIf
  got = HwFileReadAt(1024, @gateBuf[0], 512)
  If got <> 512 Or GateBytes(1024, got) = 0 : ProcedureReturn 13 : EndIf

  ; Close destroys eligibility. A successful new open re-establishes only
  ; the new file's zero cursor; the old offset can never be continued.
  GateReset()
  got = HwFileReadAt(2048, @gateBuf[0], 512)
  If got <> 512 : ProcedureReturn 14 : EndIf
  HwFileClose()
  If gHwFileReadCont <> 0 Or gHwFileOpen <> 0 Or fat_open <> 0 : ProcedureReturn 15 : EndIf
  If HwFileOpen(?gateName) = 0 Or gHwFileReadCont = 0 Or FatTell() <> 0 : ProcedureReturn 16 : EndIf
  got = HwFileReadAt(2048, @gateBuf[0], 512)
  If got <> 512 Or GateBytes(2048, got) = 0 : ProcedureReturn 17 : EndIf

  ; Zero-length calls do not disturb a valid cursor and do not touch media.
  before = gateDataReads
  If HwFileReadAt(FatTell(), @gateBuf[0], 0) <> 0 : ProcedureReturn 18 : EndIf
  If gHwFileReadCont = 0 Or gateDataReads <> before : ProcedureReturn 19 : EndIf

  ; A FAILED CHANGE STILL HAS TO SAY WHY, AFTER THE SETTLING FLUSH.
  ; hwfile_FinishChange maps the filesystem's code, then settles the volume
  ; with a flush - and that flush resets the filesystem's error. Anything
  ; that fetches the words afterwards is asking about the flush, which
  ; succeeded, so the console printed "nothing went wrong" under a refusal
  ; that had a reason. Build 174, 2026-09-17, on a real board.
  fat_err = #FAT_ERR_READ_FAIL
  gateFlushes = 0
  If hwfile_FinishChange(0) <> 0 : ProcedureReturn 20 : EndIf
  If gHwFileErr <> #HW_FILE_IO : ProcedureReturn 21 : EndIf
  ; the settle really did run, and really did wipe the layer's error
  If gateFlushes <> 1 Or FatLastError() <> 0 : ProcedureReturn 22 : EndIf
  ; and the sentence is still the filesystem's own, not the flush's
  If PeekA(HwFileErrorText()) <> 90 : ProcedureReturn 23 : EndIf
  ; the writer is disarmed on the failure path, as it always was
  If gateWriterArmed <> 0 : ProcedureReturn 24 : EndIf

  ; AND A LAYER THAT REFUSES WITHOUT NAMING ANYTHING IS NOT A SUCCESS.
  ; "no error" is not an answer hwfile_MapFat can pass on: it is only ever
  ; called on a failure, so it gets its own code and its own sentence rather
  ; than being printed as "nothing went wrong".
  fat_err = #FAT_ERR_NONE
  If hwfile_FinishChange(0) <> 0 : ProcedureReturn 25 : EndIf
  If gHwFileErr <> #HW_FILE_UNNAMED : ProcedureReturn 26 : EndIf
  If PeekA(HwFileErrorText()) = 110 : ProcedureReturn 27 : EndIf

  ProcedureReturn 0
EndProcedure

DataSection
  gateName: Data.a 80,65,89,76,79,65,68,46,80,77,70,0
EndDataSection
'''


def build(compiler: Path, work: Path, source: Path, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
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
        raise SystemExit("fat read-at gate: compile failed\n" + run.stdout)
    return image


def run_probe(a64, compiler: Path, work: Path, bodies: str, stem: str) -> tuple[int, int]:
    source = work / f"{stem}.pi4"
    source.write_text(PRELUDE + "\n" + bodies + "\n" + MAIN,
                      encoding="utf-8", newline="\n")
    return emitted.execute(a64, build(compiler, work, source, stem))


def audit_exclusive_cursor() -> None:
    """Fail if a new direct FAT file consumer weakens the continuation proof."""
    import re
    direct = []
    # A whole word only: ExFatOpen( is not FatOpen(. Standalone diagnostics
    # and test programs are their own Main and never share the monitor's
    # seam cursor, so they are not consumers this proof has to cover; until
    # 2026-09-17 the substring match and the missing exemption left this
    # audit red on three of them.
    word = re.compile(r"(?<![A-Za-z0-9_])(FatOpen|FatRead|FatSeek|FatClose)\(")
    for path in (ROOT / "RaspberryPi4").rglob("*.pi4"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("RaspberryPi4/Examples/Diagnostics/", "RaspberryPi4/Tests/")):
            continue
        text = path.read_text(encoding="utf-8")
        if word.search(text):
            direct.append(rel)
    allowed = {
        "Anvil/Storage/hwfile.pbi",
        "RaspberryPi4/Lib/fat.pi4",
        "RaspberryPi4/Lib/wifi.pi4",
    }
    unexpected = sorted(set(direct) - allowed)
    if unexpected:
        raise SystemExit("fat read-at gate: unexpected direct FAT consumer(s): " + ", ".join(unexpected))

    service = (ROOT / "RaspberryPi4" / "Board" / "banner_clock.pi4").read_text(encoding="utf-8")
    service_body = procedure(service, "ScreenServiceTick")
    forbidden = ("Fat", "HwFile", "Wifi", "Net", "Storage", "Pmf")
    if any(word in service_body for word in forbidden):
        raise SystemExit("fat read-at gate: ScreenServiceTick can mutate the live FAT file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    audit_exclusive_cursor()

    hw = HWFILE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-fat-readat-emitted-") as temporary:
        work = Path(temporary)
        result, steps = run_probe(a64, compiler, work, production_bodies(hw), "fat_readat_gate")

        mutants = (
            (
                "old-always-seek",
                "  If canContinue = 0\n    If FsSeek(off) = 0",
                "  If 1 = 1\n    If FsSeek(off) = 0",
            ),
            (
                "tell-only-after-failed-boundary",
                "  If gHwFileReadCont <> 0\n    If FsTell() = off",
                "  If 1 = 1\n    If FsTell() = off",
            ),
            (
                "failure-keeps-continuation",
                "  If got < 0\n    gHwFileErr = hwfile_MapFat()",
                "  If got < 0\n    gHwFileReadCont = 1\n    gHwFileErr = hwfile_MapFat()",
            ),
            # The reason fetched after the settling flush instead of captured
            # at the failure: the shape that printed "nothing went wrong".
            (
                "reason-fetched-after-the-settle",
                "  If gHwFileFsText <> 0\n    ProcedureReturn gHwFileFsText\n  EndIf\n",
                "",
            ),
            # A refusal that names nothing, reported as success.
            (
                "unnamed-refusal-reported-as-ok",
                "    gHwFileFsText = 0\n    ProcedureReturn #HW_FILE_UNNAMED",
                "    gHwFileFsText = 0\n    ProcedureReturn #HW_FILE_OK",
            ),
            # The capture taken too late - after the flush has reset the layer.
            (
                "capture-taken-after-the-flush",
                "  gHwFileFsText = FsErrorText()\n  If FsLastError() = 0",
                "  If FsLastError() = 0",
            ),
        )
        mutant_steps = 0
        for index, (label, old, new) in enumerate(mutants):
            mutant_hw = replace_once(hw, old, new, label)
            mutant_result, used = run_probe(
                a64, compiler, work, production_bodies(mutant_hw), f"fat_readat_mutant_{index}"
            )
            mutant_steps += used
            if mutant_result == 0:
                print(f"fat_readat_emitted_check: FAIL mutant {label} escaped")
                return 1

    if result:
        print(f"fat_readat_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"fat_readat_emitted_check: PASS - 27 cases, {steps:,} emitted A64 instructions")
    print(f"  6 continuation and failure-reporting mutants rejected in {mutant_steps:,} emitted instructions")
    print("  production FatRead/FatSeek walked a 16-cluster fragmented memory-only FAT")
    print("  exact bytes, actual FAT-sector reads, random offsets and failure repair checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
