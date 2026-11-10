"""SPIR-V -> typed IR -> generated native shaders -> GPU pixels; no execution twin."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_ir_adapter.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_none.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_shader.pbi"
Global phase.i
Global irV.AvkSpirvIrStorage,irF.AvkSpirvIrStorage
Global target.AvkZenShaderTarget,vs.AvkZenShaderResult,fs.AvkZenShaderResult
Global Dim attributes.AvkZenShaderAttribute[2]
Global Dim command.q[8]
Global Dim report.q[12]
Global queue.ZentajiGraphicsQueue
Procedure Blank()
 Protected n.i
 For n=0 To 7 : command[n]=0 : Next
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected base.i,n.i,k.i,bytes.i,vsBase.i,fsBase.i,meta.i,vertices.i,image.i,uniform.i
 Protected *node.AvkIrNode,*from.AvkIrNode,*to.AvkIrNode
 If ZentajiMemoryBind(context)<>1 Or ZentajiMemoryGraphicsInit($200000)<>1 : ProcedureReturn 1 : EndIf
 base=zenMemoryGraphicsBase : vsBase=base+8192 : fsBase=vsBase+65536+4096
 meta=base+180224 : vertices=base+184320 : uniform=base+188416 : image=base+196608
 If phase>=6
  bytes=vtpBuildVsD()
  If AnvilVkSpirvWalkIr(@vtpVsD[0],bytes)<>0 : ProcedureReturn 27 : EndIf
 ElseIf phase=1
  bytes=vtpBuildVsB()
  If AnvilVkSpirvWalkIr(@vtpVsB[0],bytes)<>0 : ProcedureReturn 2 : EndIf
 Else
  bytes=vtpBuildVsA()
  If AnvilVkSpirvWalkIr(@vtpVsA[0],bytes)<>0 : ProcedureReturn 3 : EndIf
 EndIf
 If AnvilVkSpirvIrAdapt(@irV)<>0 : ProcedureReturn 4 : EndIf
 If phase=3
  ; Add real typed arithmetic between extraction and position construction.
  ; (x+1)-1 then *1 is exact on this fixture's {-1,+1}; no encoded shader bytes
  ; or result-id pattern is supplied to the lowerer.
  For n=irV\module\nodeCount-1 To 3 Step -1
   *from=@irV\nodes[n] : *to=@irV\nodes[n+3]
   For k=0 To SizeOf(AvkIrNode)-1 : PokeA(*to+k,PeekA(*from+k)) : Next
  Next
  For n=0 To 2
   *node=@irV\nodes[3+n]
   For k=0 To SizeOf(AvkIrNode)-1 : PokeA(*node+k,0) : Next
   *node\sourceId=23+n : *node\resultType=3 : *node\blockId=irV\module\entryBlockId
   *node\kind=#ANVIL_IR_OP_FADD
   If n=1 : *node\kind=#ANVIL_IR_OP_FSUB : EndIf
   If n=2 : *node\kind=#ANVIL_IR_OP_FMUL : EndIf
   *node\sourceOpcode=avkIrExpectedNodeOpcode(*node\kind)
   *node\operandCount=2 : *node\operand0=22+n : *node\operand1=15
   If n=0 : *node\operand0=19 : EndIf
  Next
  irV\nodes[6]\operand0=25
  irV\module\nodeCount=irV\module\nodeCount+3
  irV\blocks[0]\nodeCount=irV\module\nodeCount : irV\module\idBound=26
 EndIf
 If phase>=6
  bytes=vtpBuildFsD()
  If AnvilVkSpirvWalkIr(@vtpFsD[0],bytes)<>0 : ProcedureReturn 28 : EndIf
 ElseIf phase=1
  bytes=vtpBuildFsB()
  If AnvilVkSpirvWalkIr(@vtpFsB[0],bytes)<>0 : ProcedureReturn 5 : EndIf
 ElseIf phase=2
  bytes=vtpBuildFsC()
  If AnvilVkSpirvWalkIr(@vtpFsC[0],bytes)<>0 : ProcedureReturn 6 : EndIf
 Else
  bytes=vtpBuildFsA()
  If AnvilVkSpirvWalkIr(@vtpFsA[0],bytes)<>0 : ProcedureReturn 7 : EndIf
 EndIf
 If AnvilVkSpirvIrAdapt(@irF)<>0 : ProcedureReturn 8 : EndIf
 If phase=5
  ; A typed vector addition doubles a quarter-red push colour to half red.
  ; The expected UNORM byte is 128, independently derived on the host.
  For n=irF\module\nodeCount-1 To 2 Step -1
   *from=@irF\nodes[n] : *to=@irF\nodes[n+1]
   For k=0 To SizeOf(AvkIrNode)-1 : PokeA(*to+k,PeekA(*from+k)) : Next
  Next
  *node=@irF\nodes[2]
  For k=0 To SizeOf(AvkIrNode)-1 : PokeA(*node+k,0) : Next
  *node\sourceId=17 : *node\resultType=4 : *node\blockId=irF\module\entryBlockId
  *node\kind=#ANVIL_IR_OP_FADD : *node\sourceOpcode=avkIrExpectedNodeOpcode(*node\kind)
  *node\operandCount=2 : *node\operand0=16 : *node\operand1=16
  irF\nodes[3]\operand1=17 : irF\module\nodeCount=irF\module\nodeCount+1
  irF\blocks[0]\nodeCount=irF\module\nodeCount : irF\module\idBound=18
 EndIf
 attributes[0]\location=0 : attributes[0]\binding=0 : attributes[0]\stride=24 : attributes[0]\components=2
 attributes[1]\location=1 : attributes[1]\binding=0 : attributes[1]\stride=24 : attributes[1]\components=4 : attributes[1]\offset=8
 If phase>=6 : attributes[0]\stride=16 : attributes[1]\stride=16 : attributes[1]\components=2 : EndIf
 target\invertY=Bool(phase=4)
 target\code=vsBase : target\capacity=8 : target\attributes=@attributes[0] : target\attributeCount=1+Bool(phase=1 Or phase>=6)
 For n=0 To 63 : PokeA(vsBase+n,$A5) : Next
 report[0]=AnvilVkZentajiShaderCompile(@irV,@target,@vs)
 If report[0]<>#AVK_ZEN_SHADER_ERR_SPACE : ProcedureReturn 9 : EndIf
 For n=0 To 63 : If PeekA(vsBase+n)<>$A5 : ProcedureReturn 10 : EndIf : Next
 target\capacity=65536 : attributes[0]\stride=1
 report[1]=AnvilVkZentajiShaderCompile(@irV,@target,@vs)
 If report[1]<>#AVK_ZEN_SHADER_ERR_LAYOUT : ProcedureReturn 11 : EndIf
 For n=0 To 63 : If PeekA(vsBase+n)<>$A5 : ProcedureReturn 12 : EndIf : Next
 attributes[0]\stride=24 : If phase>=6 : attributes[0]\stride=16 : EndIf
 report[2]=AnvilVkZentajiShaderCompile(@irV,@target,@vs)
 If report[2]<>0 : ProcedureReturn 13 : EndIf
 target\code=fsBase
 report[3]=AnvilVkZentajiShaderCompile(@irF,@target,@fs)
 If report[3]<>0 : ProcedureReturn 14 : EndIf
 If phase>=6
  If fs\pushBytes<>0 Or fs\uniformBytes<>0 Or fs\sampledBinding<>0 : ProcedureReturn 29 : EndIf
 ElseIf phase=1
  If fs\pushBytes<>0 Or fs\uniformBytes<>0 : ProcedureReturn 24 : EndIf
 ElseIf phase=2
  If fs\pushBytes<>0 Or fs\uniformBytes<>16 Or fs\uniformBinding<>0 : ProcedureReturn 25 : EndIf
 Else
  If fs\pushBytes<>16 Or fs\uniformBytes<>0 : ProcedureReturn 26 : EndIf
 EndIf
 report[4]=vs\codeBytes : report[5]=fs\codeBytes : report[6]=vs\varyingCount
 PokeQ(meta,uniform) : PokeQ(meta+8,uniform) : PokeQ(meta+32,vertices)
 PokeL(uniform,$3F800000) : PokeL(uniform+4,0) : PokeL(uniform+8,0) : PokeL(uniform+12,$3F800000)
 If phase=5 : PokeL(uniform,$3E800000) : EndIf
 If ZentajiGraphicsBind(@queue,15,base,4096,base,2048,base+2048)<>1 Or ZentajiGraphicsBegin(@queue)<>1 : ProcedureReturn 15 : EndIf
 Blank() : command[0]=1 : command[1]=image
 PokeL(@command[0]+16,80) : PokeW(@command[0]+20,16) : PokeW(@command[0]+22,16)
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 16 : EndIf
 Blank() : command[0]=$105
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 17 : EndIf
 Blank() : command[0]=6 : command[1]=vsBase : command[2]=fsBase
 PokeW(@command[0]+24,24) : PokeA(@command[0]+26,vs\varyingCount)
 command[5]=base+176128 : command[6]=256
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 18 : EndIf
 Blank() : command[0]=7 : command[1]=meta
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 19 : EndIf
 If phase>=6
  Blank() : command[0]=8 : command[1]=base+172032
  If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 30 : EndIf
 EndIf
 Blank() : command[0]=9 : command[1]=vertices
 PokeL(@command[0]+20,3) : PokeL(@command[0]+24,1)
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 Or ZentajiGraphicsSubmit(@queue)<>1 : ProcedureReturn 20 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 : ProcedureReturn 21 : EndIf
 report[7]=ZentajiGraphicsWait(@queue,250000) : report[8]=queue\error
 report[9]=queue\deviceStatus : report[10]=queue\faultPc : report[11]=queue\faultInfo
 If report[7]<>1 : ProcedureReturn 22 : EndIf
 If ZentajiGraphicsRelease(@queue)<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 23 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-5000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-shader-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        ram=8<<20;arena=(((ram-(1<<20)-meta['stack_bytes'])&-4096)-(2<<20))
        for phase in range(8):
            m=F.Fixture(ram_size=ram,cores=2);m.load_image(wrapped)
            struct.pack_into('<q',m.ram,ref.sym['GLOBAL_PHASE'],phase)
            positions=[(-1,-1),(1,-1),(-1,1)]
            colors=[(1,0,0,1),(0,1,0,1),(0,0,1,1)]
            for i,(position,color) in enumerate(zip(positions,colors)):
                if phase>=6:
                    uv=[(0,0),(1,0),(0,1)][i]
                    struct.pack_into('<4f',m.ram,arena+184320+i*16,*position,*uv)
                else:struct.pack_into('<6f',m.ram,arena+184320+i*24,*position,*color)
            if phase>=6:
                texture=[0xffff0000,0xff00ff00,0xff0000ff,0xffffffff]
                struct.pack_into('<4I',m.ram,arena+167936,*texture)
                struct.pack_into('<QHHIBBB5xQ',m.ram,arena+172032,arena+167936,2,2,8,2,1,int(phase==7),0)
            begin=arena+196608;pitch=80
            m.ram[begin-16:begin+pitch*16+16]=b'\xA5'*(pitch*16+32)
            assert not F.capture(m,str(td))
            out=run([zt/'zenemu.exe',td/'machine.txt','--max','30000000','--dump','--ram',td/'final.bin'])
            final=(td/'final.bin').read_bytes()
            report=struct.unpack_from('<12q',final,ref.sym['GLOBAL_REPORT'])
            end=next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end,(phase,end,report,out[-2000:])
            assert report[:4]==(-23704,-23705,0,0) and report[7:9]==(1,0),(phase,report)
            expected=bytearray(b'\xA5'*(pitch*16))
            for y in range(16):
                for x in range(16):
                    pixel=0
                    covered=(x+y<15) if phase==4 else (y>x)
                    if covered:
                        if phase>=6:
                            if phase==6:
                                pixel=texture[((31-2*y)//16)*2+(2*x+1)//16]&0xffffff
                            else:
                                ix,fx=divmod(32*x-112,256);iy,fy=divmod(368-32*y,256)
                                weights=[(256-fx)*(256-fy),fx*(256-fy),(256-fx)*fy,fx*fy]
                                taps=[texture[min(1,max(0,ty))*2+min(1,max(0,tx))] for tx,ty in ((ix,iy),(ix+1,iy),(ix,iy+1),(ix+1,iy+1))]
                                pixel=0
                                for shift in (0,8,16):
                                    value=(sum(((tap>>shift)&255)*weight for tap,weight in zip(taps,weights))+32768)//65536
                                    pixel|=value<<shift
                        elif phase==1:
                            r=round((y-x)*255/16);g=round((2*x+1)*255/32);b=round((31-2*y)*255/32)
                            pixel=(r<<16)|(g<<8)|b
                        else:pixel=0x800000 if phase==5 else 0xFF0000
                    struct.pack_into('<I',expected,y*pitch+x*4,pixel)
            assert final[begin:begin+pitch*16]==expected,(phase,'independent triangle/interpolated-colour/padding oracle',report)
            assert final[begin-16:begin]==b'\xA5'*16 and final[begin+pitch*16:begin+pitch*16+16]==b'\xA5'*16
            if phase==0:
                assembly='LD64 r8,[r3+32]\nLIQ r9,24\nMUL r9,r1,r9\nADD r8,r8,r9\nLD32U r61,[r8]\nLD32U r62,[r8+4]\nLIQ r63,0\nLIQ r64,$3F800000\n'
                for lane,reg in enumerate((61,62,63,64)):assembly+=f'VINS v0,r{reg},r0,v{lane},0,10\n'
                assembly+='JR r254\n'
                _,code=A.Asm().assemble(assembly)
                assert final[arena+8192:arena+8192+report[4]]==code,'independent instruction encoder mismatch'
            print('PASS native shader phase %d: real SPIR-V/typed IR, atomic refusal, generated GPU shader execution, exact triangle/colour/padding/guards'%phase,flush=True)


if __name__=='__main__':main()
