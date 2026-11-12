"""Exercise the shared redo journal using native Zentaji persistent disk I/O."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zlib

from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
BLOCK = 4096
SECTORS = 8
MARKER_A, MARKER_B, PAYLOAD_A, PAYLOAD_B = 2, 3, 4, 5
HOME_A, HOME_B = 1, 20
CONTROL = 0x100000
TOTAL_BLOCKS = 24

SOURCE = r'''
XIncludeFile "Zentaji/Board/disk.pbi"
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Storage/journal.pbi"

Global journal.FsJournal
Global Dim source.a[4096]
Global operation.i,stopAfter.i,failAt.i

ProcedureNaked CutPower(code.i)
 ASM
  HALT r1
  JR r254
 EndASM
EndProcedure

Procedure.i ProbeWrite(lba.i,count.i,*buffer)
 operation=operation+1
 If ZentajiDiskWriteBuffered(lba,count,*buffer)=0 : ProcedureReturn 0 : EndIf
 If operation=stopAfter : CutPower($100+operation) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ProbeFlush()
 operation=operation+1
 If operation=failAt : ProcedureReturn 0 : EndIf
 If ZentajiDiskFlush()=0 : ProcedureReturn 0 : EndIf
 If operation=stopAfter : CutPower($100+operation) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i Main()
 Protected i.i,mode.i=PeekQ($100000)
 stopAfter=PeekQ($100008) : failAt=PeekQ($100010)
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3)
 PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)=0 Or ZentajiDiskOpen(0)=0 : ProcedureReturn 1 : EndIf
 If mode=4
  If FsJournalBind(@journal,0,ZentajiDiskSectors(),16,@ZentajiDiskRead,0,0)=0 : ProcedureReturn 2 : EndIf
 Else
  If FsJournalBind(@journal,0,ZentajiDiskSectors(),16,@ZentajiDiskRead,@ProbeWrite,@ProbeFlush)=0 : ProcedureReturn 2 : EndIf
 EndIf
 If FsJournalRecover(@journal)=0
  If mode=2 And journal\error=#FSJ_E_CORRUPT And operation=0 : ProcedureReturn $C0 : EndIf
  If mode=4 And journal\error=#FSJ_E_READONLY And operation=0 : ProcedureReturn $C1 : EndIf
  ProcedureReturn 3
 EndIf
 If mode=2 : ProcedureReturn 4 : EndIf
 If mode=0
  If FsJournalBegin(@journal)=0 Or FsJournalAbort(@journal)=0 Or operation<>0 : ProcedureReturn 5 : EndIf
  If FsJournalBegin(@journal)=0 : ProcedureReturn 6 : EndIf
  If FsJournalAdd(@journal,9,@source[0])<>0 Or journal\error<>#FSJ_E_RANGE : ProcedureReturn 7 : EndIf
  If FsJournalAdd(@journal,16,@source[0])<>0 Or journal\error<>#FSJ_E_RANGE : ProcedureReturn 8 : EndIf
  If FsJournalAdd(@journal,ZentajiDiskSectors(),@source[0])<>0 Or journal\error<>#FSJ_E_RANGE : ProcedureReturn 9 : EndIf
  For i=0 To 4095 : source[i]=(i*13+37)&255 : Next
  If FsJournalAdd(@journal,8,@source[0])=0 : ProcedureReturn 10 : EndIf
  If FsJournalAdd(@journal,8,@source[0])<>0 Or journal\error<>#FSJ_E_DUPLICATE : ProcedureReturn 11 : EndIf
  For i=0 To 4095 : source[i]=(i*7+193)&255 : Next
  If FsJournalAdd(@journal,160,@source[0])=0 : ProcedureReturn 12 : EndIf
  For i=0 To 4095 : source[i]=0 : Next
  If failAt<>0
   If FsJournalCommit(@journal)<>0 Or journal\error<>#FSJ_E_IO : ProcedureReturn 13 : EndIf
   If FsJournalBegin(@journal)<>0 Or FsJournalRecover(@journal)=0 : ProcedureReturn 14 : EndIf
  Else
   If FsJournalCommit(@journal)=0 Or operation<>14 : ProcedureReturn 15 : EndIf
  EndIf
 ElseIf mode=3
  If FsJournalBegin(@journal)=0 : ProcedureReturn 17 : EndIf
  For i=0 To #FSJ_MAX_BLOCKS-1
   PokeA(@source[0],i+1)
   If FsJournalAdd(@journal,160+i*8,@source[0])=0 : ProcedureReturn 18 : EndIf
  Next
  If FsJournalAdd(@journal,288,@source[0])<>0 Or journal\error<>#FSJ_E_FULL Or operation<>0 : ProcedureReturn 19 : EndIf
  If FsJournalCommit(@journal)=0 : ProcedureReturn 20 : EndIf
 ElseIf mode=4
  If FsJournalBegin(@journal)<>0 Or journal\error<>#FSJ_E_READONLY Or operation<>0 : ProcedureReturn 21 : EndIf
 ElseIf mode=5
  For i=0 To 4095 : source[i]=(i*13+37)&255 : Next
  If ZentajiDiskWrite(8,8,@source[0])=0 : ProcedureReturn 22 : EndIf
  CutPower($F0)
 EndIf
 If ZentajiDiskClose()=0 : ProcedureReturn 16 : EndIf
 ProcedureReturn $2A
EndProcedure
'''


def block_slice(index):
    return slice(index * BLOCK, (index + 1) * BLOCK)


def marker_for(blocks):
    marker = bytearray(BLOCK)
    struct.pack_into("<8sII", marker, 0, b"PMFJNL1\0", len(blocks), 0)
    for index, (home, payload) in enumerate(blocks):
        struct.pack_into("<QII", marker, 16 + index * 16, home * SECTORS, zlib.crc32(payload), 0)
    struct.pack_into("<I", marker, BLOCK - 4, zlib.crc32(marker[:-4]))
    return marker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler")
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path)
    parser.add_argument("--probe", type=Path, help="Use an already compiled guest probe")
    args = parser.parse_args()
    zen_tools = args.zen_tools.resolve()
    sys.path.insert(0, str(zen_tools))
    from zen_native_fixture import Fixture

    zenemu = zen_tools / ("zenemu.exe" if os.name == "nt" else "zenemu")
    with tempfile.TemporaryDirectory(prefix="zentaji-journal-") as temp:
        work = args.keep.resolve() if args.keep else Path(temp)
        work.mkdir(parents=True, exist_ok=True)
        if args.probe:
            image = args.probe.read_bytes()
        else:
            source = work / "journal_probe.zentaji"
            compiled = work / "journal_probe.zex"
            source.write_text(SOURCE, encoding="ascii")
            built = subprocess.run(
                [str(resolve_compiler(args.compiler)), "--compile", str(source), "-o", str(compiled)],
                cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True, timeout=120,
            )
            (work / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
            assert built.returncode == 0, built.stdout[-4000:] + built.stderr
            image = compiled.read_bytes()

        def run(label, medium, exit_code, mode=0, cut=0, fail=0, readonly=False):
            folder = work / label
            fixture = Fixture(ram_size=2 << 20, cores=2, disks={0: (medium, readonly)})
            fixture.load_image(image)
            struct.pack_into("<QQQ", fixture.ram, CONTROL, mode, cut, fail)
            config = fixture.write(folder)
            config.write_text(config.read_text().replace("disk-memory 0 ", "disk 0 "), encoding="ascii")
            native = subprocess.run(
                [str(zenemu), str(config), "--max", "20000000"],
                capture_output=True, text=True, timeout=40,
            )
            (folder / "native.log").write_text(native.stdout + native.stderr, encoding="utf-8")
            assert native.returncode == 0, (label, native.stdout[-2000:], native.stderr)
            assert re.search(rf"^END .* exit={exit_code:X} ", native.stdout, re.M), (label, native.stdout[-2000:])
            return (folder / "disk0.img").read_bytes()

        old = bytearray((i * 11 + (i // BLOCK) * 17) & 255 for i in range(TOTAL_BLOCKS * BLOCK))
        blank = bytes(BLOCK)
        old[block_slice(MARKER_A)] = blank
        old[block_slice(MARKER_B)] = blank
        new_a = bytes((i * 13 + 37) & 255 for i in range(BLOCK))
        new_b = bytes((i * 7 + 193) & 255 for i in range(BLOCK))
        marker = marker_for([(HOME_A, new_a), (HOME_B, new_b)])
        snapshots = {}
        for cut in range(1, 15):
            expected = bytearray(old)
            if cut >= 3:
                expected[block_slice(PAYLOAD_A)] = new_a
                expected[block_slice(PAYLOAD_B)] = new_b
            if 5 <= cut < 12:
                expected[block_slice(MARKER_A)] = marker
            if 7 <= cut < 14:
                expected[block_slice(MARKER_B)] = marker
            if cut >= 10:
                expected[block_slice(HOME_A)] = new_a
                expected[block_slice(HOME_B)] = new_b
            crashed = run(f"cut-{cut:02}", old, 0x100 + cut, cut=cut)
            assert crashed == expected, f"unexpected persistent disk at operation {cut}"
            snapshots[cut] = crashed
            recovered = bytearray(crashed)
            recovered[block_slice(MARKER_A)] = blank
            recovered[block_slice(MARKER_B)] = blank
            if cut >= 5:
                recovered[block_slice(HOME_A)] = new_a
                recovered[block_slice(HOME_B)] = new_b
            assert run(f"recover-{cut:02}", crashed, 0x2A, mode=1) == recovered, cut

        done = snapshots[14]
        assert run("normal", old, 0x2A) == done
        for failed_flush in (3, 5, 7, 10, 12, 14):
            wanted = snapshots[3] if failed_flush == 3 else done
            assert run(f"retry-flush-{failed_flush:02}", old, 0x2A, fail=failed_flush) == wanted

        partial_marker = marker[:123] + blank[123:]
        partial_clear = blank[:123] + marker[123:]
        partial_home = new_a[:1365] + old[block_slice(HOME_A)][1365:]
        for label, cut, block, contents, wanted in (
            ("publish-first", 3, MARKER_A, partial_marker, snapshots[3]),
            ("publish-second", 5, MARKER_B, partial_marker, done),
            ("write-home", 7, HOME_A, partial_home, done),
            ("clear-first", 10, MARKER_A, partial_clear, done),
            ("clear-second", 12, MARKER_B, partial_clear, done),
        ):
            torn = bytearray(snapshots[cut])
            torn[block_slice(block)] = contents
            assert run("torn-" + label, torn, 0x2A, mode=1) == wanted, label

        # Interrupt recovery itself after its first home write and after home flush.
        for cut in (2, 4, 6, 8):
            interrupted = run(f"replay-cut-{cut:02}", snapshots[7], 0x100 + cut, mode=1, cut=cut)
            assert run(f"replay-again-{cut:02}", interrupted, 0x2A, mode=1) == done

        damaged_payload = bytearray(new_b)
        damaged_payload[47] ^= 128
        invalid_home = marker_for([(HOME_A, new_a), (MARKER_B, new_b)])
        duplicate_home = marker_for([(HOME_A, new_a), (HOME_A, new_b)])
        for label, edits in (
            ("payload", [(PAYLOAD_B, damaged_payload)]),
            ("home-in-journal", [(MARKER_A, invalid_home), (MARKER_B, invalid_home)]),
            ("duplicate-home", [(MARKER_A, duplicate_home), (MARKER_B, duplicate_home)]),
            ("conflicting-markers", [(MARKER_B, invalid_home)]),
            ("both-markers-torn", [(MARKER_A, partial_marker), (MARKER_B, partial_clear)]),
        ):
            damaged = bytearray(snapshots[7])
            for block, contents in edits:
                damaged[block_slice(block)] = contents
            assert run("corrupt-" + label, damaged, 0xC0, mode=2) == damaged, label

        assert run("readonly-clean", old, 0x2A, mode=4, readonly=True) == old
        assert run("readonly-replay-required", snapshots[7], 0xC1, mode=4, readonly=True) == snapshots[7]

        large = old + bytearray(16 * BLOCK)
        full_blocks = [(20 + i, bytes([i + 1]) + blank[1:]) for i in range(16)]
        full_marker = marker_for(full_blocks)
        expected = bytearray(large)
        for i, (_, payload) in enumerate(full_blocks):
            expected[block_slice(PAYLOAD_A + i)] = payload
        expected[block_slice(MARKER_A)] = full_marker
        interrupted = run("full-transaction-cut", large, 0x113, mode=3, cut=19)
        assert interrupted == expected
        expected[block_slice(MARKER_A)] = blank
        for home, payload in full_blocks:
            expected[block_slice(home)] = payload
        assert run("full-transaction-replay", interrupted, 0x2A, mode=1) == expected

        fua = bytearray(old)
        fua[block_slice(HOME_A)] = new_a
        assert run("ordinary-write-fua", old, 0xF0, mode=5) == fua

        receipt = dict(probe_sha256=hashlib.sha256(image).hexdigest(), commit_cuts=14,
                       torn_blocks=5, recovery_cuts=4, corruption_refusals=5, flush_retries=6,
                       readonly_cases=2, max_transaction_blocks=16, ordinary_fua=True)
        (work / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="ascii")
        print("PASS 14 commit cuts, 5 torn blocks, 4 interrupted replays, 5 unchanged corrupt volumes, 6 live flush retries, read-only handling, full 16-block replay and ordinary FUA")


if __name__ == "__main__":
    main()
