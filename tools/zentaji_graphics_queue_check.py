"""Real Zentaji 3D/blitter queue, immutable lists, retirement and quarantine."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
Global queue.ZentajiGraphicsQueue,other.ZentajiGraphicsQueue
Global Dim command.q[8]
Global Dim report.q[32]
Procedure Blank()
 Protected n.i
 For n=0 To 7 : command[n]=0 : Next
EndProcedure
Procedure.i Append()
 ProcedureReturn ZentajiGraphicsAppend(@queue,@command[0])
EndProcedure
Procedure DrainTime()
 Protected n.i
 For n=1 To 3 : HwPromptIdleWait() : Next
EndProcedure
Procedure.i Main(phase.i)
 Protected kind.i=15,base.i=#ZEN_GFX_3D,w.i=16,h.i=16,pitch.i=80,n.i,old.i,result.i
 If phase=1 : kind=14 : base=#ZEN_GFX_BLIT : EndIf
 If phase=3 Or phase=4 Or phase=5 : w=512 : h=2048 : pitch=2048 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 : ProcedureReturn 1 : EndIf
 report[0]=ZentajiGraphicsBind(@queue,kind,$120000,$1000,$120000,512,$120008)
 report[1]=ZentajiGraphicsBind(@queue,kind,$120000,$1000,$120001,512,$120400)
 report[2]=ZentajiGraphicsBind(@queue,kind,$7FFFF8,$1000,$7FFFF8,512,$120400)
 If report[0]<>0 Or report[1]<>0 Or report[2]<>0 Or PeekQ(base+$40)<>0 : ProcedureReturn 2 : EndIf
 If ZentajiGraphicsBind(@queue,kind,$120000,$1000,$120000,512,$120400)<>1 : ProcedureReturn 3 : EndIf
 report[3]=ZentajiGraphicsBind(@other,kind,$121000,$1000,$121000,512,$121400)
 If report[3]<>0 : ProcedureReturn 4 : EndIf
 If phase=10
  old=ZenCpuSwapStatus(1) : report[20]=ZentajiGraphicsBegin(@queue) : report[21]=queue\error
  ZenCpuSwapStatus(old)
 EndIf
 If ZentajiGraphicsBegin(@queue)<>1 : ProcedureReturn 5 : EndIf
 Blank() : report[4]=Append()
 command[0]=9+Bool(kind=15) : report[5]=Append()
 report[6]=ZentajiGraphicsAppend(@queue,$120000)
 report[7]=ZentajiGraphicsAppend(@queue,$7FFFF0)
 If report[4]<>0 Or report[5]<>0 Or report[6]<>0 Or report[7]<>0 Or queue\count<>0 : ProcedureReturn 6 : EndIf
 Blank() : command[0]=1 : command[1]=$200000
 If phase=8 : command[1]=$7FFFF0 : EndIf
 PokeL(@command[0]+16,pitch) : PokeW(@command[0]+20,w) : PokeW(@command[0]+22,h)
 If Append()<>1 : ProcedureReturn 7 : EndIf
 If phase=7
  For n=1 To 5 : If Append()<>1 : ProcedureReturn 8 : EndIf : Next
  report[22]=Append() : report[23]=queue\count
 Else
  Blank()
  If kind=14
   command[0]=4 : PokeL(@command[0]+8,1) : PokeL(@command[0]+12,2)
   PokeL(@command[0]+16,7) : PokeL(@command[0]+20,5) : PokeL(@command[0]+24,$FF123456)
  Else
   command[0]=$105 : PokeL(@command[0]+8,$FF123456)
   If phase=2 Or phase=6 : PokeL(@command[0]+8,0) : EndIf
  EndIf
  If Append()<>1 : ProcedureReturn 9 : EndIf
 EndIf
 If phase=2 Or phase=6
  Blank() : command[0]=6 : command[1]=$100000 : command[2]=$100400
  If phase=6 : command[2]=$100800 : EndIf
  PokeW(@command[0]+24,16) : command[5]=$110000 : command[6]=256
  If Append()<>1 : ProcedureReturn 10 : EndIf
  Blank() : command[0]=9 : command[1]=$101000
  PokeL(@command[0]+20,3) : PokeL(@command[0]+24,1)
  If Append()<>1 : ProcedureReturn 11 : EndIf
 EndIf
 If ZentajiGraphicsSubmit(@queue)<>1 : ProcedureReturn 12 : EndIf
 ; The driver already copied every staging record; destroy the caller's copy.
 For n=0 To 7 : command[n]=$DEADBEEF : Next
 If phase=3
  report[8]=ZentajiGraphicsWait(@queue,1) : report[9]=queue\error : report[10]=queue\state
  report[11]=ZentajiGraphicsBegin(@queue) : report[12]=ZentajiGraphicsRelease(@queue)
 EndIf
 If phase=4
  report[13]=ZentajiGraphicsAbort(@queue)
 ElseIf phase=5
  report[20]=PeekQ(base+8)&1
  PokeQ(base+$20,1)
  report[13]=ZentajiGraphicsPoll(@queue)
  report[11]=ZentajiGraphicsAbort(@queue) : report[12]=ZentajiGraphicsRelease(@queue)
  DrainTime()
 ElseIf phase=9
  DrainTime() : PokeQ(queue\fence,0)
  report[13]=ZentajiGraphicsPoll(@queue)
 Else
  report[13]=ZentajiGraphicsWait(@queue,250000)
 EndIf
 report[14]=queue\error : report[15]=queue\state : report[16]=queue\lost
 report[17]=queue\deviceStatus : report[18]=queue\faultPc
 If phase=6 : report[20]=queue\faultInfo : EndIf
 report[19]=ZentajiGraphicsRelease(@queue)
 report[24]=PeekQ(base+$40) : report[25]=PeekQ(base+$48)
 report[26]=PeekQ(base+$18) : report[27]=PeekQ(base+8)&7 : report[28]=PeekQ(base+$20)
 If kind=15 : report[29]=PeekQ(base+$70) : report[30]=PeekQ(base+$78) : EndIf
 report[31]=PeekQ($FFFF000000070158)
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 13 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def shaders(A):
    vertex='.org $100000\n'
    for lane in range(4):
        vertex+=f'LD32U r11,[r2+{lane*4}]\nVINS v0,r11,r0,v{lane},0,10\n'
    vertex+='JR r254\n'
    fragment='.org $100400\nLIQ r10,$3F800000\nVINS v0,r10,r0,v0,0,10\nVINS v0,r0,r0,v1,0,10\nVINS v0,r0,r0,v2,0,10\nVINS v0,r10,r0,v3,0,10\nJR r254\n'
    fault='.org $100800\nHALT\n'
    return [A.Asm().assemble(s) for s in (vertex,fragment,fault)]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case',type=int,choices=range(11))
    args=ap.parse_args();cc=resolve_compiler(args.compiler)
    sys.path.insert(0,str(args.zen_tools.resolve()))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(a) for a in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-6000:],p.stderr)
        return p.stdout
    names=['3d-clear','blitter-fill','3d-shader-draw','late-retirement','confirmed-abort','foreign-configuration','shader-fault','bounded-capacity','device-range-error','missing-fence','wrong-context']
    with tempfile.TemporaryDirectory(prefix='zentaji-graphics-queue-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex'
        src.write_bytes(SOURCE.replace('\n','\r\n').encode('utf-8'))
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,body=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,body)+body
        for phase,name in enumerate(names):
            if args.case is not None and args.case!=phase:continue
            m=F.Fixture(ram_size=8<<20,cores=2);m.load_image(image.read_bytes());c=m.cores[0]
            c.r[1]=phase;c.r[255]=0x7F0000
            for r in range(128,253):c.r[r]=0x10000+r*13
            kept=list(c.r[128:253])
            for address,data in shaders(A):m.ram[address:address+len(data)]=data
            vertices=struct.pack('<12f',-1,-1,.5,1,1,-1,.5,1,-1,1,.5,1)
            m.ram[0x101000:0x101000+len(vertices)]=vertices
            width,height,pitch=(512,2048,2048) if phase in (3,4,5) else (16,16,80)
            begin=0x200000;end=begin+pitch*height
            m.ram[begin-16:end+16]=b'\xA5'*(pitch*height+32)
            m.ram[0x11FFF0:0x121010]=b'\xA6'*0x1020
            assert not F.capture(m,str(td))
            native=run([F.EXE,td/'machine.txt','--max','2000000','--ram',td/'final.bin','--dump'])
            result=F.parse_result(native,(td/'final.bin').read_bytes())
            ram=result.ram;registers=result.registers[0]
            report=struct.unpack_from('<32q',ram,ref.sym['GLOBAL_REPORT'])
            assert result.states==[3,0] and result.exit_code==42,(name,result.states,result.exit_code,report)
            assert registers[128:253]==kept and registers[255]==0x7F0000,name
            assert report[:8]==(0,)*8,(name,report)
            if phase in (5,9):
                assert report[13]==-1 and report[15:17]==(3,1) and report[19]==0,(name,report)
                assert report[14]==(4 if phase==5 else 6),(name,report)
            elif phase in (4,6,8):
                assert report[13]==int(phase==4) and report[15:17]==(1,0) and report[19]==1,(name,report)
                assert report[17]&4 and (report[17]>>8)&255=={4:4,6:6,8:2}[phase],(name,report)
                if phase==6:assert report[18]==0x100800 and report[20]==(3<<32)|2,(name,report)
            else:
                assert report[13:17]==(1,0,1,0) and report[19]==1,(name,report)
            if phase in (5,9):
                assert report[24:28]==(0x120000,256,5,2),(name,report)
                if phase==5:assert report[20]==1 and report[28]==1,(name,'active foreign IRQ ownership must be preserved')
            else:assert report[24:28]==(0,0,0,0),(name,report)
            if phase==3:assert report[8:13]==(0,7,3,0,0),(name,report)
            if phase==7:assert report[22:24]==(0,6),(name,report)
            if phase==10:assert report[20:22]==(0,3),(name,report)
            expected=bytearray(b'\xA5'*(pitch*height))
            if phase not in (4,7,8):
                for y in range(height):
                    for x in range(width):
                        pixel=0x123456
                        if phase==1:
                            if not (1<=x<8 and 2<=y<7):continue
                        elif phase in (2,6):pixel=0xFF0000 if phase==2 and y>x else 0
                        struct.pack_into('<I',expected,y*pitch+x*4,pixel)
            if ram[begin:end]!=expected:
                differences=[]
                for i in range(0,len(expected),4):
                    actual=ram[begin+i:begin+i+4]
                    if actual!=expected[i:i+4]:
                        differences.append((i//pitch,(i%pitch)//4,actual.hex(),expected[i:i+4].hex()))
                        if len(differences)==8:break
                raise AssertionError((name,'independent pixel/padding oracle',differences))
            assert ram[begin-16:begin]==b'\xA5'*16 and ram[end:end+16]==b'\xA5'*16,name
            assert ram[0x11FFF0:0x120000]==b'\xA6'*16 and ram[0x121000:0x121010]==b'\xA6'*16,name
            if phase==2:assert report[29:31]==(1,120),(name,report)
            if phase in (3,5,9):assert report[31]>0,(name,'hardware WFI was not used')
            print('PASS graphics queue '+name+': real hardware commands, independent pixels/guards, native register, pixel, packet and memory expectations',flush=True)


if __name__=='__main__':main()
