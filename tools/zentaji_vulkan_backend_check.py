"""Public Vulkan image/command/fence lifecycle on the native Zentaji backend."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''EnableFloatingPoint
XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_backend.pbi"
#ANVIL_VULKAN_BACKEND=3
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"
Global Dim report.q[32]
Global Dim color.l[4]
Procedure.i Main(tiling.i,arena.i)
 Protected width.i=33,height.i=17,imageTiling.i=tiling
 If tiling=2 : width=512 : height=2000 : imageTiling=#VK_IMAGE_TILING_LINEAR : EndIf
 Protected ici.VkInstanceCreateInfo,qci.VkDeviceQueueCreateInfo,dci.VkDeviceCreateInfo
 Protected pci.VkCommandPoolCreateInfo,cbai.VkCommandBufferAllocateInfo,bi.VkCommandBufferBeginInfo
 Protected imageInfo.VkImageCreateInfo,requirements.VkMemoryRequirements,allocation.VkMemoryAllocateInfo
 Protected barrier.VkImageMemoryBarrier,range.VkImageSubresourceRange,fci.VkFenceCreateInfo,submit.VkSubmitInfo
 Protected instance.i,physical.i,device.i,queue.i,pool.i,cmd.i,image.i,memory.i,fence.i,count.l=1,priority.l=0,rc.i
 report[0]=avkBackendCaps()
 report[1]=AnvilVkZentajiWindow(arena+1,$400000)
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 : ProcedureReturn 1 : EndIf
 If AnvilVkZentajiWindow(arena,$400000)<>#VK_SUCCESS : ProcedureReturn 2 : EndIf
 report[2]=avkBackendCaps() : report[3]=avkBackendHeapBase() : report[4]=avkBackendHeapBytes()
 report[5]=avkBackendClearSupported(arena,4096,16,16,64)
 report[6]=avkBackendSubmitClear(arena+4096,4096,16,16,64,$803380B2,0)
 report[7]=PeekQ(#ZEN_GFX_3D+8)&7
 ici\sType=#VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
 If vkCreateInstance(@ici,0,@instance)<>#VK_SUCCESS : ProcedureReturn 3 : EndIf
 If vkEnumeratePhysicalDevices(instance,@count,@physical)<>#VK_SUCCESS Or count<>1 : ProcedureReturn 4 : EndIf
 qci\sType=#VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO : qci\queueCount=1 : qci\pQueuePriorities=@priority
 dci\sType=#VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO : dci\queueCreateInfoCount=1 : dci\pQueueCreateInfos=@qci
 If vkCreateDevice(physical,@dci,0,@device)<>#VK_SUCCESS : ProcedureReturn 5 : EndIf
 vkGetDeviceQueue(device,0,0,@queue)
 pci\sType=#VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO : pci\flags=#VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT
 If vkCreateCommandPool(device,@pci,0,@pool)<>#VK_SUCCESS : ProcedureReturn 6 : EndIf
 cbai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : cbai\commandPool=pool
 cbai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : cbai\commandBufferCount=1
 If vkAllocateCommandBuffers(device,@cbai,@cmd)<>#VK_SUCCESS : ProcedureReturn 7 : EndIf
 imageInfo\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO : imageInfo\imageType=#VK_IMAGE_TYPE_2D
 imageInfo\format=#VK_FORMAT_B8G8R8A8_UNORM : imageInfo\extent\width=width : imageInfo\extent\height=height : imageInfo\extent\depth=1
 imageInfo\mipLevels=1 : imageInfo\arrayLayers=1 : imageInfo\samples=#VK_SAMPLE_COUNT_1_BIT
 imageInfo\tiling=imageTiling : imageInfo\usage=#VK_IMAGE_USAGE_TRANSFER_DST_BIT
 imageInfo\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : imageInfo\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
 If vkCreateImage(device,@imageInfo,0,@image)<>#VK_SUCCESS : ProcedureReturn 8 : EndIf
 vkGetImageMemoryRequirements(device,image,@requirements)
 allocation\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO : allocation\allocationSize=requirements\size
 If vkAllocateMemory(device,@allocation,0,@memory)<>#VK_SUCCESS : ProcedureReturn 9 : EndIf
 If vkBindImageMemory(device,image,memory,0)<>#VK_SUCCESS : ProcedureReturn 10 : EndIf
 report[8]=AnvilVkImageAddress(image) : report[9]=requirements\size : report[10]=requirements\alignment
 report[11]=AnvilVkImageRowPitch(image)
 bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
 If vkBeginCommandBuffer(cmd,@bi)<>#VK_SUCCESS : ProcedureReturn 11 : EndIf
 range\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : range\levelCount=1 : range\layerCount=1
 barrier\sType=#VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
 barrier\srcQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED : barrier\dstQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED
 barrier\image=image : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT : barrier\subresourceRange=range
 vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
 color[0]=$3E4CCCCD : color[1]=$3F000000 : color[2]=$3F333333 : color[3]=$3F000000
 vkCmdClearColorImage(cmd,image,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,@color[0],1,@range)
 If vkEndCommandBuffer(cmd)<>#VK_SUCCESS : ProcedureReturn 12 : EndIf
 fci\sType=#VK_STRUCTURE_TYPE_FENCE_CREATE_INFO
 If vkCreateFence(device,@fci,0,@fence)<>#VK_SUCCESS : ProcedureReturn 13 : EndIf
 report[12]=vkGetFenceStatus(device,fence)
 submit\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : submit\commandBufferCount=1 : submit\pCommandBuffers=@cmd
 report[13]=vkQueueSubmit(queue,1,@submit,fence)
 If report[13]<>#VK_SUCCESS : ProcedureReturn 14 : EndIf
 report[14]=vkWaitForFences(device,1,@fence,1,100000000)
 report[15]=vkGetFenceStatus(device,fence) : report[16]=avkBackendGpuLeaseState()
 report[17]=avkBackendLastNativeError() : report[18]=AnvilVkFaultCount()
 If report[14]<>#VK_SUCCESS Or report[15]<>#VK_SUCCESS : ProcedureReturn 15 : EndIf
 vkDeviceWaitIdle(device) : vkDestroyFence(device,fence,0)
 vkFreeCommandBuffers(device,pool,1,@cmd) : vkDestroyCommandPool(device,pool,0)
 vkDestroyImage(device,image,0) : vkFreeMemory(device,memory,0)
 vkDestroyDevice(device,0) : vkDestroyInstance(instance,0)
 report[19]=AnvilVkFaultCount()
 report[20]=PeekQ($FFFF000000070158)
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 16 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case',type=int,choices=(0,1,2))
    ap.add_argument('--keep',type=Path)
    args=ap.parse_args()
    cc=resolve_compiler(args.compiler);sys.path.insert(0,str(args.zen_tools.resolve()))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-6000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-vulkan-backend-') as tmp:
        td=args.keep.resolve() if args.keep else Path(tmp)
        td.mkdir(parents=True,exist_ok=True)
        src=td/'probe.zentaji';image=td/'probe.zex'
        src.write_bytes(SOURCE.replace('\n','\r\n').encode('utf-8'))
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        for tiling in (0,1,2):
            if args.case is not None and args.case!=tiling:continue
            m=F.Fixture(ram_size=32<<20,cores=2);m.load_image(image.read_bytes());c=m.cores[0]
            arena=(org+len(data)+8191)&-4096
            assert arena+0x400000<0x1EF0000,('fixture RAM too small',hex(arena))
            c.r[1]=tiling;c.r[2]=arena;c.r[255]=0x1F00000
            for r in range(128,253):c.r[r]=0x10000+r*13
            kept=list(c.r[128:253])
            m.ram[arena-16:arena+0x400010]=b'\xA5'*0x400020
            assert not F.capture(m,str(td))
            native=run([F.EXE,td/'machine.txt','--max','20000000','--ram',td/'final.bin','--dump'])
            (td/f'native-{tiling}.txt').write_text(native,encoding='utf-8')
            native_end=next(line for line in native.splitlines() if line.startswith('END '))
            native_report=struct.unpack_from('<32q',(td/'final.bin').read_bytes(),ref.sym['GLOBAL_REPORT'])
            assert ' exit=2A ' in native_end,(tiling,native_end,native_report)
            result=F.parse_result(native,(td/'final.bin').read_bytes())
            ram=result.ram;registers=result.registers[0]
            report=native_report
            assert result.states==[3,0] and result.exit_code==42,(tiling,result.states,result.exit_code,report)
            assert registers[128:253]==kept and registers[255]==0x1F00000,tiling
            assert report[:8]==(0,-20001,0xC0000F,arena+4096,0x3FF000,-8,-2,0),report
            width,height=(512,2000) if tiling==2 else (33,17)
            size=width*height*4
            assert report[8:12]==(arena+4096,size,4096,width*4 if tiling!=0 else 0),report
            assert report[12:20]==(1,0,0,0,0,0,0,0),report
            pixel=struct.pack('<I',0x803380B2)
            assert ram[arena+4096:arena+4096+size]==pixel*(width*height),tiling
            assert ram[arena+4096+size:arena+0x400000]==b'\xA5'*(0x400000-4096-size),tiling
            commands=bytearray(320)
            commands[0]=1
            struct.pack_into('<QIHHB',commands,8,arena+4096,width*4,width,height,2)
            commands[64]=4
            struct.pack_into('<ii',commands,80,width,height)
            struct.pack_into('<H',commands,128,0x105)
            struct.pack_into('<I',commands,136,0x803380B2)
            commands[192]=10
            struct.pack_into('<QQ',commands,200,arena+2048,1)
            assert ram[arena:arena+320]==commands,tiling
            assert ram[arena+320:arena+2048]==b'\xA5'*(2048-320),tiling
            assert struct.unpack_from('<Q',ram,arena+2048)[0]==1,tiling
            if tiling==2:assert report[20]>0,(tiling,'GPU completion did not use hardware sleep')
            assert ram[arena+2112:arena+4096]==b'\xA5'*(4096-2112),tiling
            assert ram[arena-16:arena]==b'\xA5'*16 and ram[arena+0x400000:arena+0x400010]==b'\xA5'*16,tiling
            print(f'PASS native Vulkan tiling {tiling}: real public image/memory/command/barrier/clear/fence lifecycle; exact BGRA/alpha, private-command guards, native register and exact memory expectations',flush=True)


if __name__=='__main__':main()
