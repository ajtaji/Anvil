"""Real public Vulkan pipeline/draw lifecycle on the native Zentaji GPU."""
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

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''EnableFloatingPoint
XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Zentaji/Board/graphics_display.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_backend.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi"
#ANVIL_VULKAN_BACKEND=3
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"
Global phase.i
Global mask.l
Global Dim firstPixels.l[256]
Global Dim report.q[16]
Global Dim entry.a[5]
Global Dim stages.VkPipelineShaderStageCreateInfo[2]
Global Dim push.l[4]
Global Dim clear.l[4]
Procedure.i Main(table.i,source.i,context.i)
 Protected ici.VkInstanceCreateInfo,qci.VkDeviceQueueCreateInfo,dci.VkDeviceCreateInfo
 Protected pci.VkCommandPoolCreateInfo,cbai.VkCommandBufferAllocateInfo,bi.VkCommandBufferBeginInfo
 Protected ii.VkImageCreateInfo,req.VkMemoryRequirements,alloc.VkMemoryAllocateInfo,iv.VkImageViewCreateInfo
 Protected att.VkAttachmentDescription,aref.VkAttachmentReference,sub.VkSubpassDescription,rpci.VkRenderPassCreateInfo,fbci.VkFramebufferCreateInfo
 Protected bci.VkBufferCreateInfo,smci.VkShaderModuleCreateInfo,plci.VkPipelineLayoutCreateInfo,pcr.VkPushConstantRange
 Protected binding.VkVertexInputBindingDescription,attribute.VkVertexInputAttributeDescription,vi.VkPipelineVertexInputStateCreateInfo
 Protected ia.VkPipelineInputAssemblyStateCreateInfo,vp.VkViewport,sc.VkRect2D,vps.VkPipelineViewportStateCreateInfo
 Protected rs.VkPipelineRasterizationStateCreateInfo,ms.VkPipelineMultisampleStateCreateInfo,cba.VkPipelineColorBlendAttachmentState,cb.VkPipelineColorBlendStateCreateInfo,gp.VkGraphicsPipelineCreateInfo
 Protected rpbi.VkRenderPassBeginInfo,fci.VkFenceCreateInfo,submit.VkSubmitInfo
 Protected barrier.VkImageMemoryBarrier,range.VkImageSubresourceRange
 Protected snapshot.AnvilVkBackendDraw,witnessBinding.AnvilVkBackendBinding
 Protected instance.i,physical.i,device.i,queue.i,pool.i,cmd.i,image.i,mem.i,view.i,rp.i,fb.i
 Protected buffer.i,bmem.i,address.i,vs.i,fs.i,layout.i,pipeline.i,fence.i,count.l=1,priority.l=0,offset.q=0,n.i
 Protected ibuffer.i,imem.i,iaddress.i,ibytes.i,indexType.i,rp2.i,fb2.i,pipeline2.i,sequence.q
 If ZentajiMemoryBind(context)<>1 Or ZentajiMemoryGraphicsInit($400000)<>1 : ProcedureReturn 1 : EndIf
 If AnvilVkZentajiWindow(zenMemoryGraphicsBase,zenMemoryGraphicsBytes)<>0 : ProcedureReturn 2 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 : ProcedureReturn 3 : EndIf
 ici\sType=#VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
 If vkCreateInstance(@ici,0,@instance)<>0 : ProcedureReturn 4 : EndIf
 If vkEnumeratePhysicalDevices(instance,@count,@physical)<>0 Or count<>1 : ProcedureReturn 5 : EndIf
 qci\sType=#VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO : qci\queueCount=1 : qci\pQueuePriorities=@priority
 dci\sType=#VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO : dci\queueCreateInfoCount=1 : dci\pQueueCreateInfos=@qci
 If vkCreateDevice(physical,@dci,0,@device)<>0 : ProcedureReturn 6 : EndIf
 vkGetDeviceQueue(device,0,0,@queue)
 pci\sType=#VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO : pci\flags=#VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT
 If vkCreateCommandPool(device,@pci,0,@pool)<>0 : ProcedureReturn 7 : EndIf
 cbai\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO : cbai\commandPool=pool : cbai\level=#VK_COMMAND_BUFFER_LEVEL_PRIMARY : cbai\commandBufferCount=1
 If vkAllocateCommandBuffers(device,@cbai,@cmd)<>0 : ProcedureReturn 8 : EndIf
 ii\sType=#VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO : ii\imageType=#VK_IMAGE_TYPE_2D : ii\format=#VK_FORMAT_B8G8R8A8_UNORM
 ii\extent\width=16 : ii\extent\height=16 : ii\extent\depth=1 : ii\mipLevels=1 : ii\arrayLayers=1 : ii\samples=#VK_SAMPLE_COUNT_1_BIT
 ii\tiling=#VK_IMAGE_TILING_LINEAR : ii\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_TRANSFER_DST_BIT
 ii\sharingMode=#VK_SHARING_MODE_EXCLUSIVE : ii\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED
 If vkCreateImage(device,@ii,0,@image)<>0 : ProcedureReturn 9 : EndIf
 vkGetImageMemoryRequirements(device,image,@req)
 alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO : alloc\allocationSize=((req\size+4095)&-4096)*3
 If vkAllocateMemory(device,@alloc,0,@mem)<>0 Or vkBindImageMemory(device,image,mem,0)<>0 : ProcedureReturn 10 : EndIf
 report[0]=AnvilVkImageAddress(image)
 iv\sType=#VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO : iv\image=image : iv\viewType=#VK_IMAGE_VIEW_TYPE_2D : iv\format=#VK_FORMAT_B8G8R8A8_UNORM
 iv\subresourceRange\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : iv\subresourceRange\levelCount=1 : iv\subresourceRange\layerCount=1
 If vkCreateImageView(device,@iv,0,@view)<>0 : ProcedureReturn 11 : EndIf
 att\format=#VK_FORMAT_B8G8R8A8_UNORM : att\samples=#VK_SAMPLE_COUNT_1_BIT
 att\loadOp=#VK_ATTACHMENT_LOAD_OP_CLEAR : att\storeOp=#VK_ATTACHMENT_STORE_OP_STORE
 att\stencilLoadOp=#VK_ATTACHMENT_LOAD_OP_DONT_CARE : att\stencilStoreOp=#VK_ATTACHMENT_STORE_OP_DONT_CARE
 att\initialLayout=#VK_IMAGE_LAYOUT_UNDEFINED : att\finalLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
 aref\attachment=0 : aref\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
 sub\pipelineBindPoint=#VK_PIPELINE_BIND_POINT_GRAPHICS : sub\colorAttachmentCount=1 : sub\pColorAttachments=@aref
 rpci\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO : rpci\attachmentCount=1 : rpci\pAttachments=@att : rpci\subpassCount=1 : rpci\pSubpasses=@sub
 If vkCreateRenderPass(device,@rpci,0,@rp)<>0 : ProcedureReturn 12 : EndIf
 fbci\sType=#VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO : fbci\renderPass=rp : fbci\attachmentCount=1 : fbci\pAttachments=@view : fbci\width=16 : fbci\height=16 : fbci\layers=1
 If vkCreateFramebuffer(device,@fbci,0,@fb)<>0 : ProcedureReturn 13 : EndIf
 bci\sType=#VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO : bci\size=24
 If phase=2 Or phase=3 : bci\size=48 : EndIf
 bci\sType=#VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO : bci\usage=#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT : bci\sharingMode=#VK_SHARING_MODE_EXCLUSIVE
 If vkCreateBuffer(device,@bci,0,@buffer)<>0 : ProcedureReturn 14 : EndIf
 vkGetBufferMemoryRequirements(device,buffer,@req) : alloc\allocationSize=req\size
 If vkAllocateMemory(device,@alloc,0,@bmem)<>0 Or vkBindBufferMemory(device,buffer,bmem,0)<>0 : ProcedureReturn 15 : EndIf
 address=AnvilVkBufferAddress(buffer)
 PokeL(address,$BF800000) : PokeL(address+4,$BF800000)
 PokeL(address+8,$3F800000) : PokeL(address+12,$BF800000)
 PokeL(address+16,$BF800000) : PokeL(address+20,$3F800000)
 If phase=2 Or phase=3
  For n=0 To 23 Step 4 : PokeL(address+24+n,PeekL(address+n)) : PokeL(address+n,0) : Next
  ibytes=6 : indexType=#VK_INDEX_TYPE_UINT16
  If phase=3 : ibytes=12 : indexType=#VK_INDEX_TYPE_UINT32 : EndIf
  bci\size=ibytes : bci\usage=#VK_BUFFER_USAGE_INDEX_BUFFER_BIT
  If vkCreateBuffer(device,@bci,0,@ibuffer)<>0 : ProcedureReturn 29 : EndIf
  vkGetBufferMemoryRequirements(device,ibuffer,@req) : alloc\allocationSize=req\size
  If vkAllocateMemory(device,@alloc,0,@imem)<>0 Or vkBindBufferMemory(device,ibuffer,imem,0)<>0 : ProcedureReturn 30 : EndIf
  iaddress=AnvilVkBufferAddress(ibuffer)
  For n=0 To 2
   If phase=2 : PokeW(iaddress+n*2,n+3) : Else : PokeL(iaddress+n*4,n+3) : EndIf
  Next
 EndIf
 smci\sType=#VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO : smci\codeSize=vtpBuildVsA() : smci\pCode=@vtpVsA[0]
 If vkCreateShaderModule(device,@smci,0,@vs)<>0 : ProcedureReturn 16 : EndIf
 smci\codeSize=vtpBuildFsA() : smci\pCode=@vtpFsA[0]
 If vkCreateShaderModule(device,@smci,0,@fs)<>0 : ProcedureReturn 17 : EndIf
 pcr\stageFlags=#VK_SHADER_STAGE_FRAGMENT_BIT : pcr\size=16
 plci\sType=#VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO : plci\pushConstantRangeCount=1 : plci\pPushConstantRanges=@pcr
 If vkCreatePipelineLayout(device,@plci,0,@layout)<>0 : ProcedureReturn 18 : EndIf
 binding\binding=0 : binding\stride=8 : binding\inputRate=#VK_VERTEX_INPUT_RATE_VERTEX
 attribute\location=0 : attribute\binding=0 : attribute\format=#VK_FORMAT_R32G32_SFLOAT
 vi\sType=#VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO : vi\vertexBindingDescriptionCount=1 : vi\pVertexBindingDescriptions=@binding
 vi\vertexAttributeDescriptionCount=1 : vi\pVertexAttributeDescriptions=@attribute
 ia\sType=#VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO : ia\topology=#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
 PokeL(@vp\width,$41800000) : PokeL(@vp\height,$41800000) : PokeL(@vp\maxDepth,$3F800000)
 sc\extent\width=16 : sc\extent\height=16
 If phase=1 : sc\offset\x=3 : sc\offset\y=4 : sc\extent\width=5 : sc\extent\height=6 : EndIf
 vps\sType=#VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO : vps\viewportCount=1 : vps\pViewports=@vp : vps\scissorCount=1 : vps\pScissors=@sc
 rs\sType=#VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO : rs\polygonMode=#VK_POLYGON_MODE_FILL : rs\cullMode=#VK_CULL_MODE_NONE : rs\frontFace=#VK_FRONT_FACE_COUNTER_CLOCKWISE
 PokeL(@rs\lineWidth,$3F800000)
 ms\sType=#VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO : ms\rasterizationSamples=#VK_SAMPLE_COUNT_1_BIT
 If phase=4 : mask=0 : ms\pSampleMask=@mask : EndIf
 cba\colorWriteMask=15
 cb\sType=#VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO : cb\attachmentCount=1 : cb\pAttachments=@cba
 PokeL(@entry[0],$6E69616D)
 stages[0]\sType=#VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO : stages[0]\stage=#VK_SHADER_STAGE_VERTEX_BIT : stages[0]\module=vs : stages[0]\pName=@entry[0]
 stages[1]\sType=#VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO : stages[1]\stage=#VK_SHADER_STAGE_FRAGMENT_BIT : stages[1]\module=fs : stages[1]\pName=@entry[0]
 gp\sType=#VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO : gp\stageCount=2 : gp\pStages=@stages[0]
 gp\pVertexInputState=@vi : gp\pInputAssemblyState=@ia : gp\pViewportState=@vps : gp\pRasterizationState=@rs : gp\pMultisampleState=@ms : gp\pColorBlendState=@cb
 gp\layout=layout : gp\renderPass=rp : gp\basePipelineIndex=-1
 report[1]=vkCreateGraphicsPipelines(device,0,1,@gp,0,@pipeline)
 If report[1]<>0 : ProcedureReturn 19 : EndIf
 If phase=6
  att\loadOp=#VK_ATTACHMENT_LOAD_OP_LOAD : att\initialLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  If vkCreateRenderPass(device,@rpci,0,@rp2)<>0 : ProcedureReturn 31 : EndIf
  fbci\renderPass=rp2
  If vkCreateFramebuffer(device,@fbci,0,@fb2)<>0 : ProcedureReturn 32 : EndIf
  sc\offset\x=3 : sc\offset\y=4 : sc\extent\width=5 : sc\extent\height=6
  gp\renderPass=rp2
  If vkCreateGraphicsPipelines(device,0,1,@gp,0,@pipeline2)<>0 : ProcedureReturn 33 : EndIf
 EndIf
 ; Source modules are no longer a runtime dependency of generated native code.
 vkDestroyShaderModule(device,vs,0) : vkDestroyShaderModule(device,fs,0)
 push[0]=$3F800000 : push[3]=$3F800000
 rpbi\sType=#VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO : rpbi\renderPass=rp : rpbi\framebuffer=fb
 rpbi\renderArea\extent\width=16 : rpbi\renderArea\extent\height=16 : rpbi\clearValueCount=1 : rpbi\pClearValues=@clear[0]
 bi\sType=#VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
 If vkBeginCommandBuffer(cmd,@bi)<>0 : ProcedureReturn 20 : EndIf
 vkCmdBeginRenderPass(cmd,@rpbi,#VK_SUBPASS_CONTENTS_INLINE)
 vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,pipeline)
 vkCmdBindVertexBuffers(cmd,0,1,@buffer,@offset)
 vkCmdPushConstants(cmd,layout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@push[0])
 If phase=2 Or phase=3
  vkCmdBindIndexBuffer(cmd,ibuffer,0,indexType) : vkCmdDrawIndexed(cmd,3,1,0,0,0)
 ElseIf phase=5
  vkCmdDraw(cmd,3,2,0,0)
 Else
  vkCmdDraw(cmd,3,1,0,0)
 EndIf
 vkCmdEndRenderPass(cmd)
 report[2]=vkEndCommandBuffer(cmd)
 If report[2]<>0 : ProcedureReturn 21 : EndIf
 fci\sType=#VK_STRUCTURE_TYPE_FENCE_CREATE_INFO
 If vkCreateFence(device,@fci,0,@fence)<>0 : ProcedureReturn 22 : EndIf
 submit\sType=#VK_STRUCTURE_TYPE_SUBMIT_INFO : submit\commandBufferCount=1 : submit\pCommandBuffers=@cmd
 report[3]=vkQueueSubmit(queue,1,@submit,fence)
 If report[3]<>0 : ProcedureReturn 23 : EndIf
 report[4]=vkWaitForFences(device,1,@fence,1,250000000)
 report[5]=avkBackendLastNativeError() : report[6]=AnvilVkFaultCount()
 If report[4]<>0 : ProcedureReturn 24 : EndIf
 report[10]=PeekQ(#ZEN_GFX_3D+$70)
 For n=0 To 255 : firstPixels[n]=PeekL(AnvilVkImageAddress(image)+n*4) : Next
 If phase=0
  ; Mutate only a closed probe record. Every refusal must precede launch.
  witnessBinding\base=AnvilVkBufferAddress(buffer) : witnessBinding\stride=8
  snapshot\kind=#ANVIL_VK_RENDER_OP_DRAW : snapshot\pipeline=avkPipeSlot(pipeline)
  snapshot\targetBase=AnvilVkImageAddress(image) : snapshot\targetBytes=1024 : snapshot\width=16 : snapshot\height=16 : snapshot\pitch=64
  snapshot\bindingCount=1 : snapshot\bindings=@witnessBinding
  snapshot\vertexCount=3 : snapshot\instanceCount=1 : snapshot\sampleMask=1
  snapshot\viewportW=16 : snapshot\viewportH=16 : snapshot\scissorW=16 : snapshot\scissorH=16
  snapshot\pushBase=@push[0] : snapshot\pushBytes=16
  report[11]=avkZenDrawPreflight(@snapshot)
  sequence=avkZenQueue\sequence
  snapshot\pushBytes=15 : report[12]=avkZenDrawPreflight(@snapshot)
  snapshot\pushBytes=16 : snapshot\viewportX=17 : report[13]=avkZenDrawPreflight(@snapshot)
  report[14]=Bool(avkZenQueue\sequence=sequence And avkZenPending=0)
  If report[11]<>0 Or report[12]<>#VK_ERROR_FEATURE_NOT_PRESENT Or report[13]<>#VK_ERROR_FEATURE_NOT_PRESENT Or report[14]<>1 : ProcedureReturn 34 : EndIf
 EndIf
 If phase=1 Or phase=6
  If vkResetCommandBuffer(cmd,0)<>0 Or vkResetFences(device,1,@fence)<>0 Or vkBeginCommandBuffer(cmd,@bi)<>0 : ProcedureReturn 35 : EndIf
  If phase=1
   range\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : range\levelCount=1 : range\layerCount=1
   barrier\sType=#VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER : barrier\oldLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
   barrier\srcQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED : barrier\dstQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED
   barrier\image=image : barrier\subresourceRange=range : barrier\srcAccessMask=#VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT
   vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
   clear[2]=$3F800000 : clear[3]=$3F800000
   vkCmdClearColorImage(cmd,image,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,@clear[0],1,@range)
  Else
   rpbi\renderPass=rp2 : rpbi\framebuffer=fb2
   vkCmdBeginRenderPass(cmd,@rpbi,#VK_SUBPASS_CONTENTS_INLINE)
   vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,pipeline2)
   vkCmdBindVertexBuffers(cmd,0,1,@buffer,@offset)
   push[0]=0 : push[1]=$3F800000
   vkCmdPushConstants(cmd,layout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@push[0])
   vkCmdDraw(cmd,3,1,0,0) : vkCmdEndRenderPass(cmd)
  EndIf
  If vkEndCommandBuffer(cmd)<>0 Or vkQueueSubmit(queue,1,@submit,fence)<>0 Or vkWaitForFences(device,1,@fence,1,250000000)<>0 : ProcedureReturn 36 : EndIf
 EndIf
 If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(image))<>1 : ProcedureReturn 25 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,0)<>1 Or ZentajiGraphicsDisplayWait(250000)<>1 : ProcedureReturn 26 : EndIf
 report[7]=zgdSequence
 If ZentajiGraphicsDisplayRelease()<>1 : ProcedureReturn 27 : EndIf
 vkDeviceWaitIdle(device) : vkDestroyFence(device,fence,0)
 vkFreeCommandBuffers(device,pool,1,@cmd) : vkDestroyCommandPool(device,pool,0)
 If pipeline2<>0 : vkDestroyPipeline(device,pipeline2,0) : EndIf
 If ibuffer<>0 : vkDestroyBuffer(device,ibuffer,0) : vkFreeMemory(device,imem,0) : EndIf
 If fb2<>0 : vkDestroyFramebuffer(device,fb2,0) : vkDestroyRenderPass(device,rp2,0) : EndIf
 vkDestroyPipeline(device,pipeline,0) : vkDestroyPipelineLayout(device,layout,0)
 vkDestroyBuffer(device,buffer,0) : vkFreeMemory(device,bmem,0)
 vkDestroyFramebuffer(device,fb,0) : vkDestroyRenderPass(device,rp,0) : vkDestroyImageView(device,view,0)
 vkDestroyImage(device,image,0) : vkFreeMemory(device,mem,0)
 vkDestroyDevice(device,0) : vkDestroyInstance(instance,0)
 report[8]=AnvilVkFaultCount()
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 28 : EndIf
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
    with tempfile.TemporaryDirectory(prefix='anvil-vulkan-draw-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',image]);print('Compiled public Vulkan native-draw composition',flush=True)
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        print('Verified independent assembly and owned startup wrapper',flush=True)
        for phase in range(7):
            m=F.Fixture(ram_size=32<<20,cores=2,display_modes=[(16,16,60000)]);m.load_image(wrapped)
            struct.pack_into('<q',m.ram,ref.sym['GLOBAL_PHASE'],phase)
            assert not F.capture(m,str(td))
            out=run([zt/'zenemu.exe',td/'machine.txt','--max','100000000','--ram',td/'final.bin'])
            final=(td/'final.bin').read_bytes();report=struct.unpack_from('<16q',final,ref.sym['GLOBAL_REPORT'])
            end=next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end,(phase,end,report)
            assert report[1:9]==(0,0,0,0,0,0,1,0),(phase,report)
            first=[];expected=[]
            for y in range(16):
                for x in range(16):
                    covered=x+y<15 and phase!=4
                    scissor=3<=x<8 and 4<=y<10
                    first_pixel=0xFFFF0000 if covered and (phase!=1 or scissor) else 0
                    pixel=first_pixel
                    if phase==1:pixel=0xFF0000FF
                    if phase==6 and covered and scissor:pixel=0xFF00FF00
                    first.append(first_pixel);expected.append(pixel)
            assert struct.unpack_from('<256I',final,ref.sym['GLOBAL_FIRSTPIXELS'])==tuple(first),(phase,'first-frame coverage/scissor oracle',report)
            pixels=b''.join(struct.pack('<I',pixel) for pixel in expected)
            assert final[report[0]:report[0]+len(pixels)]==pixels,(phase,'independent Vulkan triangle/load/clear oracle',report)
            if phase==5:assert report[10]==2,(phase,'native instanced triangle count',report)
            if phase==0:assert report[11:15]==(0,-8,-8,1),(phase,'pre-launch refusal',report)
            if phase in (0,1,6):
                headless=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','100000000'])
                frames=[line for line in headless.splitlines() if line.startswith('FRAME ')]
                rgb=b''.join(struct.pack('<I',pixel&0xffffff) for pixel in expected)
                crc=zlib.crc32(rgb)
                assert any(('%08X'%crc).lower() in line.lower() for line in frames),(phase,frames,hex(crc))
            print('PASS public Vulkan draw phase %d: real pipeline/queue/fence, generated GPU pixels, source lifetime, load/scissor/index/instance/mask contract%s'%(phase,', exact native scanout CRC' if phase in (0,1,6) else ''),flush=True)



if __name__=='__main__':main()
