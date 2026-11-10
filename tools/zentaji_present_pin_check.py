"""Public image/memory lifetime through native DMA presentation and quarantine."""
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
Global presentPhase.i
'''
BODY=r''' Protected token.q,stale.q,s.i=avkImgSlot(image),m.i=avkImgMemSlot[s],faults.i
 If ZentajiGraphicsDisplayManagedStart(arena+$3FD000)<>1 : ProcedureReturn 40 : EndIf
 token=AnvilVkZentajiPresentBegin(image)
 If token<1 Or avkImgInFlight[s]<>1 Or avkMemInFlight[m]<>1 : ProcedureReturn 41 : EndIf
 If AnvilVkZentajiPresentBegin(image)<>0 Or AnvilVkZentajiPresentCommit(token,0)<>0 : ProcedureReturn 42 : EndIf
 faults=AnvilVkFaultCount()
 vkDestroyImage(device,image,0) : vkFreeMemory(device,memory,0)
 If AnvilVkFaultCount()<>faults+2 Or avkImgSlot(image)<>s Or avkMemSlot(memory)<>m : ProcedureReturn 43 : EndIf
 If presentPhase=2
  If ZentajiGraphicsDisplayWriteBegin(token,@avkZenDma)<>1 : ProcedureReturn 44 : EndIf
  PokeQ(#ZEN_DMA_CHANNEL+$10,73)
  If AnvilVkZentajiPresentCommit(token,250000)<>0 : ProcedureReturn 45 : EndIf
  If avkZenPresentState<>2 Or avkImgInFlight[s]<>1 Or avkMemInFlight[m]<>1 Or avkBackendGpuLeaseState()<>-2 : ProcedureReturn 46 : EndIf
  If AnvilVkZentajiPresentAbort(token)<>0 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 47 : EndIf
  faults=AnvilVkFaultCount() : vkDestroyImage(device,image,0) : vkFreeMemory(device,memory,0)
  If AnvilVkFaultCount()<>faults+2 Or avkImgSlot(image)<>s Or avkMemSlot(memory)<>m : ProcedureReturn 48 : EndIf
  report[21]=avkZenPresentState : report[22]=avkImgInFlight[s] : report[23]=avkMemInFlight[m]
  report[24]=avkBackendGpuLeaseState() : report[25]=zgdLost : report[26]=zgdWriter
  ProcedureReturn 42
 EndIf
 stale=token
 If AnvilVkZentajiPresentAbort(token)<>1 Or avkImgInFlight[s]<>0 Or avkMemInFlight[m]<>0 : ProcedureReturn 49 : EndIf
 token=AnvilVkZentajiPresentBegin(image)
 If token<=stale Or AnvilVkZentajiPresentCommit(stale,250000)<>0 Or AnvilVkZentajiPresentAbort(stale)<>0 : ProcedureReturn 50 : EndIf
 If AnvilVkZentajiPresentCommit(token,250000)<>1 : ProcedureReturn 51 : EndIf
 If avkImgInFlight[s]<>0 Or avkMemInFlight[m]<>0 Or avkZenPresentState<>0 Or avkBackendGpuLeaseState()<>0 : ProcedureReturn 52 : EndIf
 If zgdSequence<>1 Or zgdShown<>0 Or ZentajiGraphicsDisplayRelease()<>1 : ProcedureReturn 53 : EndIf
 report[21]=avkImgInFlight[s] : report[22]=avkMemInFlight[m] : report[23]=zgdSequence
 report[24]=avkZenPresentState : report[25]=avkBackendGpuLeaseState()
 vkDeviceWaitIdle(device)'''
SOURCE=PREFIX+LIFECYCLE.replace('Procedure.i Main(',r'''XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_present.pbi"
Procedure.i VulkanMain(''').replace(
    'AnvilVkZentajiWindow(arena,$400000)','AnvilVkZentajiWindow(arena,$3FD000)').replace(
    r'imageInfo\usage=#VK_IMAGE_USAGE_TRANSFER_DST_BIT',
    r'imageInfo\usage=#VK_IMAGE_USAGE_TRANSFER_DST_BIT|#VK_IMAGE_USAGE_TRANSFER_SRC_BIT').replace(
    ' If vkEndCommandBuffer(cmd)',r''' barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
 barrier\srcAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_READ_BIT
 vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
 If vkEndCommandBuffer(cmd)''').replace(' vkDeviceWaitIdle(device)',BODY)+r'''
Procedure.i Main(table.i,source.i,context.i)
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 80 : EndIf
 If ZentajiMemoryGraphicsInit($400000)<>1 : ProcedureReturn 81 : EndIf
 ProcedureReturn VulkanMain(presentPhase&1,zenMemoryGraphicsBase)
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
        assert p.returncode==0,(p.returncode,p.stdout[-5000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-present-pin-') as tmp:
        td=a.keep.resolve() if a.keep else Path(tmp);td.mkdir(parents=True,exist_ok=True)
        src=td/'probe.zentaji';image=td/'probe.zex';src.write_text(SOURCE)
        run([cc,'--compile',src,'-o',image]);print('Compiled public Vulkan presentation pin composition',flush=True)
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        for phase in (0,1,2):
            machine=F.Fixture(ram_size=32<<20,cores=2,display_modes=[(33,17,60000)]);machine.load_image(wrapped)
            struct.pack_into('<q',machine.ram,ref.sym['GLOBAL_PRESENTPHASE'],phase);machine.write(td)
            output=run([zt/'zenemu.exe',td/'machine.txt','--max','30000000','--ram',td/'final.bin'])
            (td/f'native-{phase}.txt').write_text(output)
            ram=(td/'final.bin').read_bytes();report=struct.unpack_from('<32q',ram,ref.sym['GLOBAL_REPORT'])
            end=next(line for line in output.splitlines() if line.startswith('END '))
            assert ' exit=2A ' in end,(phase,end,report)
            arena=(((32<<20)-(1<<20)-meta['stack_bytes'])&-4096)-0x400000
            plane=arena+0x3fd000
            if phase==2:
                assert report[21:27]==(2,1,1,-2,1,2),report
                assert ram[plane:plane+0x3000]==bytes(0x3000)
                print('PASS ownership loss retains public image/memory pins, display writer and quarantined GPU lease',flush=True)
            else:
                assert report[21:26]==(0,0,1,0,0),report
                assert ram[plane:plane+2244]==struct.pack('<I',0x803380B2)*561
                assert ram[plane+2244:plane+0x3000]==bytes(0x3000-2244)
                frames=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','30000000'])
                crc='%08X'%zlib.crc32(struct.pack('<I',0x003380B2)*561)
                assert any(crc.lower() in line.lower() for line in frames.splitlines() if line.startswith('FRAME ')),frames[-1500:]
                print(f'PASS tiling{phase}: public destroy/free refusals, abort/stale token, native copy/latch/CRC, pins released after retirement',flush=True)


if __name__=='__main__':main()
