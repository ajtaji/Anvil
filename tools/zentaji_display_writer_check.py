"""Real GPU -> owned DMA -> private display planes, token/latch and loss outcomes."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
from zentaji_vulkan_backend_check import SOURCE as LIFECYCLE

ROOT=Path(__file__).resolve().parents[1]
PREFIX=r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Zentaji/Board/graphics_display.pbi"
Global writerPhase.i
'''
BODY=r''' Protected token.q,oldToken.q,aborted.q,p0.i,p1.i
 If ZentajiGraphicsDisplayManagedStart(arena+$3FD000)<>1 : ProcedureReturn 40 : EndIf
 If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 41 : EndIf
 token=ZentajiGraphicsDisplayAcquireWrite() : oldToken=token
 If token<1 Or ZentajiGraphicsDisplayAcquireWrite()<>0 : ProcedureReturn 42 : EndIf
 p0=ZentajiGraphicsDisplayWriteAddress(token)
 If p0<>arena+$3FD000 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 43 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,0)<>0 Or ZentajiGraphicsDisplayWriteRetire(token,@avkZenQueue)<>0 : ProcedureReturn 44 : EndIf
 If ZentajiGraphicsDisplayCopyWrite(token,@avkZenDma,AnvilVkImageAddress(image),AnvilVkImageRowPitch(image),@avkZenQueue,250000)<>1 : ProcedureReturn 45 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,1)<>0 : ProcedureReturn 46 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,0)<>1 : ProcedureReturn 47 : EndIf
 If ZentajiGraphicsDisplayAcquireWrite()<>0 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 48 : EndIf
 If ZentajiGraphicsDisplayWait(250000)<>1 : ProcedureReturn 49 : EndIf
 If zgdShown<>0 Or zgdSequence<>1 Or ZentajiGraphicsDisplayWriteAddress(oldToken)<>0 : ProcedureReturn 50 : EndIf
 If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 51 : EndIf
 aborted=ZentajiGraphicsDisplayAcquireWrite() : p1=ZentajiGraphicsDisplayWriteAddress(aborted)
 If aborted<=oldToken Or p1<>p0+zgdSpan : ProcedureReturn 52 : EndIf
 If ZentajiGraphicsDisplayWriteAbort(aborted)<>1 : ProcedureReturn 53 : EndIf
 token=ZentajiGraphicsDisplayAcquireWrite()
 If token<=aborted Or ZentajiGraphicsDisplayWriteAddress(aborted)<>0 : ProcedureReturn 54 : EndIf
 If ZentajiGraphicsDisplayWriteBegin(oldToken,@avkZenDma)<>0 : ProcedureReturn 55 : EndIf
 If writerPhase=1
  If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 72 : EndIf
  If ZentajiGraphicsDisplayWriteBegin(token,@avkZenDma)<>1 : ProcedureReturn 56 : EndIf
  PokeQ(#ZEN_DMA_CHANNEL+$10,73)
  If ZentajiDmaOwned(@avkZenDma)<>0 Or avkZenDma\lost<>1 : ProcedureReturn 57 : EndIf
  If ZentajiGraphicsDisplayWriteRetire(token,@avkZenQueue)<>0 : ProcedureReturn 58 : EndIf
  If ZentajiGraphicsDisplayWriteQuarantine(token)<>1 : ProcedureReturn 59 : EndIf
  If avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 73 : EndIf
  If ZentajiGraphicsDisplayAcquireWrite()<>0 Or ZentajiGraphicsDisplayWriteAbort(token)<>0 : ProcedureReturn 60 : EndIf
  If ZentajiGraphicsDisplayPresent(@avkZenQueue,1)<>0 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 61 : EndIf
  report[21]=p0 : report[22]=p1 : report[23]=zgdWriter : report[24]=zgdLost
  report[25]=avkZenDma\launches : report[26]=avkZenDma\lost
  report[27]=zgdSequence : report[28]=avkBackendGpuLeaseState()
  ProcedureReturn 42
 EndIf
 If vkResetCommandBuffer(cmd,0)<>#VK_SUCCESS Or vkResetFences(device,1,@fence)<>#VK_SUCCESS : ProcedureReturn 62 : EndIf
 If vkBeginCommandBuffer(cmd,@bi)<>#VK_SUCCESS : ProcedureReturn 63 : EndIf
 color[0]=$3E800000 : color[1]=$3F000000 : color[2]=$3F400000 : color[3]=$3F800000
 vkCmdClearColorImage(cmd,image,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,@color[0],1,@range)
 If vkEndCommandBuffer(cmd)<>#VK_SUCCESS Or vkQueueSubmit(queue,1,@submit,fence)<>#VK_SUCCESS : ProcedureReturn 64 : EndIf
 If vkWaitForFences(device,1,@fence,1,100000000)<>#VK_SUCCESS : ProcedureReturn 65 : EndIf
 If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 66 : EndIf
 If ZentajiGraphicsDisplayCopyWrite(token,@avkZenDma,AnvilVkImageAddress(image),AnvilVkImageRowPitch(image),@avkZenQueue,250000)<>1 : ProcedureReturn 67 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,1)<>1 Or ZentajiGraphicsDisplayWait(250000)<>1 : ProcedureReturn 68 : EndIf
 If zgdShown<>1 Or zgdSequence<>2 Or ZentajiGraphicsDisplayWriteAddress(token)<>0 : ProcedureReturn 69 : EndIf
 If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)<>1 : ProcedureReturn 70 : EndIf
 report[21]=p0 : report[22]=p1 : report[23]=zgdWriter : report[24]=zgdLost
 report[25]=avkZenDma\launches : report[26]=avkZenDma\sleeps
 report[27]=zgdSequence : report[28]=avkBackendGpuLeaseState()
 report[29]=ZentajiGraphicsDisplayRelease()
 If report[29]<>1 : ProcedureReturn 71 : EndIf
 If ZentajiGraphicsDisplayManagedStart(arena+$3FD000)<>1 : ProcedureReturn 74 : EndIf
 aborted=ZentajiGraphicsDisplayAcquireWrite()
 If aborted<=token Or ZentajiGraphicsDisplayWriteAddress(oldToken)<>0 : ProcedureReturn 75 : EndIf
 If ZentajiGraphicsDisplayWriteAbort(aborted)<>1 Or ZentajiGraphicsDisplayRelease()<>1 : ProcedureReturn 76 : EndIf
 vkDeviceWaitIdle(device)'''
SOURCE=PREFIX+LIFECYCLE.replace('Procedure.i Main(','Procedure.i VulkanMain(').replace(
    'AnvilVkZentajiWindow(arena,$400000)','AnvilVkZentajiWindow(arena,$3FD000)').replace(
    ' vkDeviceWaitIdle(device)',BODY)+r'''
Procedure.i Main(table.i,source.i,context.i)
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 80 : EndIf
 If ZentajiMemoryGraphicsInit($400000)<>1 : ProcedureReturn 81 : EndIf
 ProcedureReturn VulkanMain(1,zenMemoryGraphicsBase)
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--keep',type=Path)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-display-writer-') as tmp:
        td=a.keep.resolve() if a.keep else Path(tmp);td.mkdir(parents=True,exist_ok=True)
        src=td/'probe.zentaji';image=td/'probe.zex';src.write_text(SOURCE)
        run([cc,'--compile',src,'-o',image]);print('Compiled private display writer composition',flush=True)
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        for phase in (0,1):
            m=F.Fixture(ram_size=32<<20,cores=2,display_modes=[(33,17,60000)]);m.load_image(wrapped)
            struct.pack_into('<q',m.ram,ref.sym['GLOBAL_WRITERPHASE'],phase);m.write(td)
            output=run([zt/'zenemu.exe',td/'machine.txt','--max','30000000','--ram',td/'final.bin'])
            (td/f'native-{phase}.txt').write_text(output)
            ram=(td/'final.bin').read_bytes();report=struct.unpack_from('<32q',ram,ref.sym['GLOBAL_REPORT'])
            end=next(line for line in output.splitlines() if line.startswith('END '))
            assert ' exit=2A ' in end,(phase,end,report)
            arena=(((32<<20)-(1<<20)-meta['stack_bytes'])&-4096)-0x400000
            p0,p1=report[21:23];assert (p0,p1)==(arena+0x3fd000,arena+0x3fe000),report
            assert report[4]==0x3fc000 and report[8]==arena+4096,report
            assert ram[p0:p0+2244]==struct.pack('<I',0x803380B2)*561
            assert ram[p0+2244:p0+4096]==bytes(4096-2244)
            if phase:
                assert report[23:29]==(2,1,1,1,1,-2),report
                assert ram[p1:p1+4096]==bytes(4096)
                print('PASS real DMA ownership loss: writer retained, stale/abort/present/release refused, shown plane unchanged',flush=True)
            else:
                assert report[23:25]==(0,0) and report[25]==2 and report[26]>0 and report[27:30]==(2,0,1),report
                assert ram[p1:p1+2244]==struct.pack('<I',0xFF4080BF)*561
                assert ram[p1+2244:p1+8192]==bytes(8192-2244)
                frames=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','30000000'])
                for color in (0x003380B2,0x004080BF):
                    crc='%08X'%zlib.crc32(struct.pack('<I',color)*561)
                    assert any(crc.lower() in line.lower() for line in frames.splitlines() if line.startswith('FRAME ')),(color,frames[-1500:])
                print('PASS private planes: two GPU colours, native DMA, distinct real latches/CRCs, immutable shown plane, token and release guards',flush=True)


if __name__=='__main__':main()
