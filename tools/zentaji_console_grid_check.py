"""Production Forge and native Zentaji execute the shared terminal model/output taps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Anvil/Core/console_mirror.pbi"
Procedure.i ScreenProportionalAdvance(previous.i,c.i) : ProcedureReturn 524288 : EndProcedure
XIncludeFile "Anvil/Core/console_grid.pbi"
Global order.i,paints.i,overlays.i,resets.i
Procedure Paint() : order=order*10+1 : paints=paints+1 : EndProcedure
Procedure Overlay() : order=order*10+2 : overlays=overlays+1 : EndProcedure
Procedure Reset() : resets=resets+1 : EndProcedure
Procedure.i Main()
 Protected i.i
 If *gConPaint<>0 Or *gConOverlay<>0 Or *gConOverlayReset<>0 Or *uart_mirrorDrain<>0 Or *uart_auxFlush<>0 : ProcedureReturn 101 : EndIf
 ConGridInit(6,3) : UartMirror(1)
 uart_MirrorPut(97) : uart_MirrorPut(98) : uart_MirrorPut(13) : uart_MirrorPut(10)
 uart_MirrorPut(99) : uart_MirrorPut(100)
 UartScreenStyle(#UART_SCREEN_STYLE_PROMPT) : uart_MirrorPut(112)
 UartScreenStyle(#UART_SCREEN_STYLE_NORMAL) : uart_MirrorPut(113)
 ConDrainRing()
 If ConGridCell(0,0)<>97 Or ConGridCell(0,1)<>98 Or ConGridCell(1,0)<>99 Or ConGridCell(1,1)<>100 : ProcedureReturn 102 : EndIf
 If ConGridCell(1,2)<>112 Or ConGridCellStyle(1,2)<>1 Or ConGridCell(1,3)<>113 Or ConGridCellStyle(1,3)<>0 : ProcedureReturn 103 : EndIf
 If ConGridCurC()<>4 Or ConGridCurR()<>1 Or UartMirrorCount()<>0 : ProcedureReturn 104 : EndIf
 ConSetOverlay(@Overlay,@Reset) : ConSetRenderer(@Paint)
 ScreenPump()
 If order<>12 Or paints<>1 Or overlays<>1 : ProcedureReturn 105 : EndIf
 ConNoRenderer() : ConGridMarkAll() : ScreenPump()
 If paints<>1 Or overlays<>1 : ProcedureReturn 106 : EndIf
 ConOverlayReset() : If resets<>1 : ProcedureReturn 107 : EndIf
 ConNoOverlay() : ConOverlayReset() : If resets<>1 : ProcedureReturn 108 : EndIf
 ConGridProportionalSet(80,1) : ConGridResize(10,5)
 If ConGridCell(0,0)<>97 Or ConGridCell(1,2)<>112 Or ConGridCellStyle(1,2)<>1 : ProcedureReturn 114 : EndIf
 If ConGridCurC()<>4 Or ConGridCurR()<>1 Or gConCurPen<>2097152 : ProcedureReturn 115 : EndIf
 ConGridResize(4,1)
 If ConGridCell(0,0)<>99 Or ConGridCell(0,3)<>113 Or ConGridCellStyle(0,2)<>1 : ProcedureReturn 116 : EndIf
 If ConGridCurC()<>3 Or ConGridCurR()<>0 Or gConCurPen<>1572864 : ProcedureReturn 117 : EndIf
 ConGridResize(6,3) : ConGridProportionalSet(0,0)
 If ConGridCell(0,0)<>99 Or ConGridCell(0,4)<>32 Or ConGridCell(1,0)<>32 : ProcedureReturn 118 : EndIf
 ConGridClear() : UartMirrorSetDrain(@ConMirrorDrain)
 For i=0 To 10000 : uart_MirrorPut(65) : Next
 ConDrainRing()
 If UartMirrorLost()<>0 Or UartMirrorCount()<>0 Or paints<>1 Or overlays<>1 : ProcedureReturn 109 : EndIf
 For i=0 To 5
  If ConGridCell(0,i)<>65 Or ConGridCell(1,i)<>65 : ProcedureReturn 110 : EndIf
 Next
 For i=0 To 4 : If ConGridCell(2,i)<>65 : ProcedureReturn 111 : EndIf : Next
 If ConGridCell(2,5)<>32 Or ConGridCurC()<>5 Or ConGridCurR()<>2 : ProcedureReturn 112 : EndIf
 UartMirrorSetDrain(0) : UartMirror(0) : ConGridStop()
 If *gConPaint<>0 Or *gConOverlay<>0 Or *gConOverlayReset<>0 Or *uart_mirrorDrain<>0 : ProcedureReturn 113 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--keep',type=Path)
    args=ap.parse_args();cc=resolve_compiler(args.compiler);zt=args.zen_tools.resolve()
    sys.path.insert(0,str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(v) for v in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-console-grid-') as tmp:
        td=args.keep.resolve() if args.keep else Path(tmp);td.mkdir(parents=True,exist_ok=True)
        src=td/'console.zentaji';image=td/'console.zex';src.write_text(SOURCE,encoding='utf-8')
        (td/'build.log').write_text(run([cc,'--compile',src,'-o',image]))
        mapping=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig'))
        assert mapping['image']==hashlib.sha256(image.read_bytes()).hexdigest()
        ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(origin,origin,data)+data
        m=F.Fixture(ram_size=4<<20);m.load_image(image.read_bytes());m.write(td)
        output=run([zt/'zenemu.exe',td/'machine.txt','--max','10000000','--ram',td/'final.bin'])
        (td/'native.log').write_text(output)
        end=next(line for line in output.splitlines() if line.startswith('END '))
        assert ' exit=2A ' in end,end
        ram=(td/'final.bin').read_bytes();grid=ref.sym['GLOBAL_GCONGRID'];styles=ref.sym['GLOBAL_GCONSTYLE']
        assert ram[grid:grid+18]==b'A'*17+b' '
        assert ram[styles:styles+18]==bytes(18)
        for name,want in [('ORDER',12),('PAINTS',1),('OVERLAYS',1),('RESETS',1)]:
            assert struct.unpack_from('<q',ram,ref.sym['GLOBAL_'+name])[0]==want,name
    print('PASS shared fixed-grid console/native Zentaji: production source maps and independent image bytes, exact grid/styles/cursor, ordered callbacks, zero/uninstall/reset, 10001 lossless bytes, wrap/scroll, clear and stop')
if __name__=='__main__':main()
