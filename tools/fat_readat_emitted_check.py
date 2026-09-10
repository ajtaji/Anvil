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
FAT = ROOT / "RaspberryPi4" / "Lib" / "fat.pi4"
HWFILE = ROOT / "RaspberryPi4" / "Board" / "hw_file.pi4"
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
        "fat_Fail", "fat_CopyBytes", "fat_ReadRaw", "fat_ReadSec",
        "fat_ReadFatSec", "fat_ClusterValid", "fat_ClusterLba",
        "fat_NextCluster", "FatRead", "FatClose", "fat_NextOrAlloc",
        "fat_ChainAt", "fat_FixCursor", "FatSeek", "FatTell",
        "FatLastError",
    )
    hw_names = (
        "hwfile_MapFat", "HwFileOpen", "HwFileReadAt", "HwFileClose",
    )
    return "\n\n".join(
        [procedure(fat, name) for name in fat_names]
        + [procedure(hw, name) for name in hw_names]
    )


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

#GATE_CLUSTER_STRIDE = 128
#GATE_FAT_LBA = 100
#GATE_DATA_LBA = 10000
#GATE_CLUSTERS = 16
#GATE_BYTES = #GATE_CLUSTERS * #FAT_SECTOR_SIZE

Global *fat_reader
Global fat_err.i
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
Global Dim fat_secBuf.a[#FAT_SECTOR_SIZE]
Global Dim fat_fatBuf.a[#FAT_SECTOR_SIZE]

Global gHwFileErr.i
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

Procedure.i GateReader(lba.i, *dst)
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

  ProcedureReturn 0
EndProcedure

DataSection
  gateName: Data.a 80,65,89,76,79,65,68,46,80,77,70,0
EndDataSection
'''


def build(pmfc: Path, work: Path, source: Path, stem: str) -> Path:
    staged = work / pmfc.name
    if not staged.exists():
        shutil.copy2(pmfc, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{stem}.img"
    command = [
        str(staged), str(source), "-t", "pi4",
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


def run_probe(a64, pmfc: Path, work: Path, bodies: str, stem: str) -> tuple[int, int]:
    source = work / f"{stem}.pi4"
    source.write_text(PRELUDE + "\n" + bodies + "\n" + MAIN,
                      encoding="utf-8", newline="\n")
    return emitted.execute(a64, build(pmfc, work, source, stem))


def audit_exclusive_cursor() -> None:
    """Fail if a new direct FAT file consumer weakens the continuation proof."""
    direct = []
    for path in (ROOT / "RaspberryPi4").rglob("*.pi4"):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in ("FatOpen(", "FatRead(", "FatSeek(", "FatClose(")):
            direct.append(path.relative_to(ROOT).as_posix())
    allowed = {
        "RaspberryPi4/Board/hw_file.pi4",
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
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP") or str(LOCAL_INTERP))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    audit_exclusive_cursor()

    hw = HWFILE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-fat-readat-emitted-") as temporary:
        work = Path(temporary)
        result, steps = run_probe(a64, pmfc, work, production_bodies(hw), "fat_readat_gate")

        mutants = (
            (
                "old-always-seek",
                "  If canContinue = 0\n    If FatSeek(off) = 0",
                "  If 1 = 1\n    If FatSeek(off) = 0",
            ),
            (
                "tell-only-after-failed-boundary",
                "  If gHwFileReadCont <> 0\n    If FatTell() = off",
                "  If 1 = 1\n    If FatTell() = off",
            ),
            (
                "failure-keeps-continuation",
                "  If got < 0\n    gHwFileErr = hwfile_MapFat()",
                "  If got < 0\n    gHwFileReadCont = 1\n    gHwFileErr = hwfile_MapFat()",
            ),
        )
        mutant_steps = 0
        for index, (label, old, new) in enumerate(mutants):
            mutant_hw = replace_once(hw, old, new, label)
            mutant_result, used = run_probe(
                a64, pmfc, work, production_bodies(mutant_hw), f"fat_readat_mutant_{index}"
            )
            mutant_steps += used
            if mutant_result == 0:
                print(f"fat_readat_emitted_check: FAIL mutant {label} escaped")
                return 1

    if result:
        print(f"fat_readat_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"fat_readat_emitted_check: PASS - 19 cases, {steps:,} emitted A64 instructions")
    print(f"  3 continuation mutants rejected in {mutant_steps:,} emitted instructions")
    print("  production FatRead/FatSeek walked a 16-cluster fragmented memory-only FAT")
    print("  exact bytes, actual FAT-sector reads, random offsets and failure repair checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
