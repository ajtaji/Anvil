"""Native owned DMA: exact bytes/guards, chaining, fills, refusal and quarantine."""
# SPDX-License-Identifier: MIT
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Zentaji/Board/dma_transfer.pbi"
Global dma.ZentajiDmaTransfer,other.ZentajiDmaTransfer
Global Dim report.q[32]
Procedure.i Main(phase.i)
 Protected n.i,src.i=$200000,dst.i=$400000,scratch.i=$120000,old.i,rc.i
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 : ProcedureReturn 1 : EndIf
 If phase=5 : PokeQ(#ZEN_DMA_CHANNEL+$10,73) : EndIf
 report[0]=ZentajiDmaBind(@dma,scratch,4096)
 If phase=5
  report[1]=dma\error : report[2]=PeekQ(#ZEN_DMA_CHANNEL+$10)
  ProcedureReturn 42
 EndIf
 If report[0]<>1 : ProcedureReturn 2 : EndIf
 report[1]=ZentajiDmaBind(@other,scratch,4096)
 report[2]=ZentajiDmaRowsValid(@dma,src,29,dst,31,17,100,0)
 report[3]=ZentajiDmaRowsValid(@dma,src,29,src+1,31,17,100,0)
 report[4]=ZentajiDmaRowsValid(@dma,src,29,scratch,31,17,100,0)
 report[5]=ZentajiDmaRowsValid(@dma,src,29,dma\ram-8,31,17,100,0)
 report[6]=ZentajiDmaRowsValid(@dma,src,29,dst,31,17,$7FFFFFFFFFFFFFFF,0)
 report[7]=ZentajiDmaRowsValid(@dma,src,29,@dma,31,17,1,0)
 report[22]=ZentajiDmaRowsValid(@dma,src,0,dst,31,17,100,0)
 report[23]=ZentajiDmaRowsValid(@dma,src,29,dst,0,17,100,0)
 report[24]=ZentajiDmaRowsValid(@dma,src,29,dst,31,0,100,0)
 report[25]=ZentajiDmaRowsValid(@dma,src,29,dst,31,17,0,0)
 report[26]=ZentajiDmaRowsValid(@dma,src,29,dst,31,17,-1,0)
 report[27]=ZentajiDmaRowsValid(@dma,src,29,dst,31,dma\ram+1,1,0)
 If phase=0
  report[8]=ZentajiDmaRows(@dma,src,29,dst,31,17,100,0,250000)
 ElseIf phase=1
  report[8]=ZentajiDmaRows(@dma,$A1B2C3D4,0,dst,36,28,100,1,250000)
 ElseIf phase=2
  report[8]=ZentajiDmaStartRows(@dma,src,$100000,dst,$100000,$100000,1,0)
  report[9]=ZentajiDmaWait(@dma,HwMicros())
  For n=0 To 9 : HwPromptIdleWait() : Next
  report[10]=PeekQ(#ZEN_DMA_CHANNEL+$30)
  report[11]=ZentajiDmaPoll(@dma)
 ElseIf phase=3
  report[8]=ZentajiDmaStartRows(@dma,src,$100000,dst,$100000,$100000,2,0)
  ; Fault injection AFTER validated publication; corrupt only item1's destination.
  PokeQ(scratch+48+8,dma\ram)
  report[9]=ZentajiDmaWait(@dma,HwMicros()+250000)
 ElseIf phase=4
  PokeQ(#ZEN_DMA_CHANNEL+$10,73)
  report[8]=ZentajiDmaOwned(@dma) : report[9]=PeekQ(#ZEN_DMA_CHANNEL+$10)
 ElseIf phase=6
  old=ZenCpuSwapStatus(1)
  report[8]=ZentajiDmaStartRows(@dma,src,29,dst,31,17,2,0)
  ZenCpuSwapStatus(old)
  report[9]=PeekQ(#ZEN_DMA_CHANNEL+$10)
 ElseIf phase=7
  report[8]=ZentajiDmaRows(@dma,src,29,dst,31,17,100,0,250000)
  report[9]=ZentajiDmaRows(@dma,$A1B2C3D4,0,dst+4096,36,28,100,1,250000)
 ElseIf phase=8
  report[8]=ZentajiDmaRows(@dma,src,36,src+17,36,17,100,0,250000)
 EndIf
 report[12]=dma\state : report[13]=dma\lost : report[14]=dma\error
 report[15]=dma\launches : report[16]=dma\sleeps : report[17]=dma\status
 report[18]=ZentajiDmaOwned(@dma)
 report[19]=PeekQ(#ZEN_DMA_CHANNEL+$30)
 report[20]=PeekQ(#ZEN_DMA_BASE+$10) : report[21]=PeekQ(#ZEN_DMA_BASE+$18)
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zen-tools', type=Path, required=True)
    ap.add_argument('--keep', type=Path)
    a = ap.parse_args()
    cc = resolve_compiler(a.compiler)
    zt = a.zen_tools.resolve()
    sys.path.insert(0, str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack

    def run(argv):
        p = subprocess.run([str(x) for x in argv], cwd=ROOT,
                           env=dict(os.environ, PMF_ROOT=str(ROOT)),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        assert p.returncode == 0, (p.returncode, p.stdout[-5000:], p.stderr)
        return p.stdout

    names = ['pitched-100-rows', 'fill-100-rows', 'timeout-late-completion',
             'later-descriptor-device-fault', 'foreign-idle-registers',
             'foreign-initial-registers', 'wrong-context', 'copy-then-fill-reuse',
             'disjoint-rows-shared-allocation']
    with tempfile.TemporaryDirectory(prefix='zentaji-dma-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src, image = td/'probe.zentaji', td/'probe.zex'
        src.write_text(SOURCE, encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        ref = A.Asm()
        org, body = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, body)+body
        receipts = []
        source = bytes((i*37+11) & 255 for i in range(2 << 20))
        for phase, name in enumerate(names):
            m = F.Fixture(ram_size=8 << 20, cores=2)
            m.load_image(image.read_bytes())
            c = m.cores[0]
            c.r[1], c.r[255] = phase, 0x7f0000
            for r in range(128, 253):
                c.r[r] = 0x123400000000+r*17
            kept = list(c.r[128:253])
            m.ram[0x200000:0x400000] = source
            m.ram[0x3ffff0:0x600010] = b'\xa5'*0x200020
            # Keep source's final16 bytes independent of destination guard setup.
            source_now = bytes(m.ram[0x200000:0x400000])
            m.ram[0x11fff0:0x121010] = b'\xa6'*0x1020
            assert not F.capture(m, str(td))
            out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '2000000', '--ram', td/'final.bin', '--dump'])
            ram = (td/'final.bin').read_bytes()
            result = F.parse_result(out, ram)
            report = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_REPORT'])
            assert result.states == [3, 0] and result.exit_code == 42, (name, report, out[-1500:])
            assert result.registers[0][128:253] == kept and result.registers[0][255] == 0x7f0000, name
            expected = bytearray(b'\xa5'*(2 << 20))
            if phase != 5:
                assert report[:8] == (1, 0, 1, 0, 0, 0, 0, 0), (name, report)
                assert report[20:22] == (0, 0), (name, report)
                assert report[22:28] == (0,)*6, (name, 'zero/negative/oversized shape refusal', report)
            if phase in (0, 7):
                for row in range(100):
                    expected[row*31:row*31+17] = source_now[row*29:row*29+17]
            if phase in (1, 7):
                offset = 4096 if phase == 7 else 0
                for row in range(100):
                    expected[offset+row*36:offset+row*36+28] = struct.pack('<I', 0xa1b2c3d4)*7
            if phase in (2, 3):
                expected[:1 << 20] = source_now[:1 << 20]
                assert report[8] == 1 and report[9] == -1, (name, report)
                assert report[12:15] == (3, 1, 7 if phase == 2 else 5), (name, report)
                assert report[18] == 0, (name, report)
                if phase == 2:
                    assert report[10:12] == (2, -1), report
                else:
                    assert report[17] == 0x204, report
            elif phase in (0, 1, 7, 8):
                assert report[8] == 1 and report[12:15] == (1, 0, 0), (name, report)
                assert report[15] == (4 if phase == 7 else 2) and report[16] >= int(phase != 8) and report[18:20] == (1, 0), report
                if phase == 7:
                    assert report[9] == 1, report
            elif phase == 4:
                assert report[8:10] == (0, 73) and report[12:15] == (1, 1, 4), report
            elif phase == 5:
                assert report[:3] == (0, 4, 73), report
            elif phase == 6:
                assert report[8:10] == (0, 0) and report[12:15] == (1, 0, 3), report
            assert ram[0x400000:0x600000] == expected, (name, 'destination bytes')
            expected_source = bytearray(source_now)
            if phase == 8:
                for row in range(100):
                    expected_source[row*36+17:row*36+34] = source_now[row*36:row*36+17]
            assert ram[0x200000:0x400000] == expected_source, (name, 'source/read-only bytes and aliased padding')
            assert ram[0x11fff0:0x120000] == b'\xa6'*16 and ram[0x121000:0x121010] == b'\xa6'*16, (name, 'scratch guards')
            assert ram[0x600000:0x600010] == b'\xa5'*16, (name, 'destination guard')
            (td/('native-%d.txt' % phase)).write_text(out, encoding='utf-8')
            receipts.append(dict(case=name, report=report))
            (td/'results.json').write_text(json.dumps(receipts, indent=2)+'\n', encoding='utf-8')
            print('PASS native DMA '+name+': exact bytes, guards, ownership and retirement', flush=True)


if __name__ == '__main__':
    main()
