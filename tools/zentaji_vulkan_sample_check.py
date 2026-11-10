"""GPU render-to-texture through public Vulkan, checked against exact RGBA."""
# SPDX-License-Identifier: MIT
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
from zentaji_vulkan_draw_check import SOURCE as DRAW_SOURCE

ROOT = Path(__file__).resolve().parents[1]


def replace_once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def source():
    # Reuse the public device/queue/render-pass setup and its original opaque
    # triangle. phase stays zero; samplePhase independently selects the sampler.
    s = replace_once(DRAW_SOURCE, 'Global phase.i', 'Global phase.i,samplePhase.i\nGlobal Dim sampleReport.q[32]')
    s = replace_once(s, ' Protected ici.VkInstanceCreateInfo', r'''
 Protected sampledImage.i,sampledMem.i,sampledView.i,sampledPass.i,sampledFb.i,sampledPipeline.i,sampledLayout.i
 Protected sampleBuffer.i,sampleBufferMem.i,sampleAddress.i,sampleVs.i,sampleFs.i,sampler.i,dsl.i,dp.i,ds.i
 Protected sci.VkSamplerCreateInfo,dsb.VkDescriptorSetLayoutBinding,dlci.VkDescriptorSetLayoutCreateInfo
 Protected dpci.VkDescriptorPoolCreateInfo,dps.VkDescriptorPoolSize,dsai.VkDescriptorSetAllocateInfo
 Protected di.VkDescriptorImageInfo,write.VkWriteDescriptorSet,properties.VkFormatProperties,imageProperties.VkImageFormatProperties
 Protected Dim sampleAttributes.VkVertexInputAttributeDescription[2]
 Protected sampleSnapshot.AnvilVkBackendDraw,sampleWitness.AnvilVkBackendSampledImage,sampleSequence.q
 Protected ici.VkInstanceCreateInfo''')
    s = replace_once(s, 'ii\\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_TRANSFER_DST_BIT',
                     'ii\\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_SAMPLED_BIT\n If samplePhase>=2 : ii\\tiling=#VK_IMAGE_TILING_OPTIMAL : EndIf')
    s = replace_once(s, ' vkCmdEndRenderPass(cmd)\n report[2]', r'''
 vkCmdEndRenderPass(cmd)
 range\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : range\levelCount=1 : range\layerCount=1
 barrier\sType=#VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER
 barrier\oldLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
 barrier\srcQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED : barrier\dstQueueFamilyIndex=#VK_QUEUE_FAMILY_IGNORED
 barrier\image=image : barrier\subresourceRange=range
 barrier\srcAccessMask=#VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_SHADER_READ_BIT
 vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,#VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,0,0,0,0,0,1,@barrier)
 report[2]''')
    s = replace_once(s, ' If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(image))<>1 : ProcedureReturn 25 : EndIf', r'''
 ; The first public draw is the texture producer. No CPU writes its pixels.
 sampleReport[0]=AnvilVkImageAddress(image)
 vkGetPhysicalDeviceFormatProperties(physical,#VK_FORMAT_B8G8R8A8_UNORM,@properties)
 sampleReport[16]=properties\optimalTilingFeatures
 sampleReport[17]=vkGetPhysicalDeviceImageFormatProperties(physical,#VK_FORMAT_B8G8R8A8_UNORM,#VK_IMAGE_TYPE_2D,ii\tiling,ii\usage,0,@imageProperties)
 sampleReport[18]=imageProperties\maxExtent\width
 ii\tiling=#VK_IMAGE_TILING_LINEAR : ii\usage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
 If vkCreateImage(device,@ii,0,@sampledImage)<>0 : ProcedureReturn 50 : EndIf
 vkGetImageMemoryRequirements(device,sampledImage,@req) : alloc\allocationSize=((req\size+4095)&-4096)*3
 If vkAllocateMemory(device,@alloc,0,@sampledMem)<>0 Or vkBindImageMemory(device,sampledImage,sampledMem,0)<>0 : ProcedureReturn 51 : EndIf
 sampleReport[1]=AnvilVkImageAddress(sampledImage)
 iv\image=sampledImage
 If vkCreateImageView(device,@iv,0,@sampledView)<>0 : ProcedureReturn 52 : EndIf
 att\finalLayout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
 If vkCreateRenderPass(device,@rpci,0,@sampledPass)<>0 : ProcedureReturn 53 : EndIf
 fbci\renderPass=sampledPass : fbci\pAttachments=@sampledView
 If vkCreateFramebuffer(device,@fbci,0,@sampledFb)<>0 : ProcedureReturn 54 : EndIf
 bci\size=48
 If vkCreateBuffer(device,@bci,0,@sampleBuffer)<>0 : ProcedureReturn 55 : EndIf
 vkGetBufferMemoryRequirements(device,sampleBuffer,@req) : alloc\allocationSize=req\size
 If vkAllocateMemory(device,@alloc,0,@sampleBufferMem)<>0 Or vkBindBufferMemory(device,sampleBuffer,sampleBufferMem,0)<>0 : ProcedureReturn 56 : EndIf
 sampleAddress=AnvilVkBufferAddress(sampleBuffer)
 PokeL(sampleAddress,$BF800000) : PokeL(sampleAddress+4,$BF800000)
 PokeL(sampleAddress+16,$3F800000) : PokeL(sampleAddress+20,$BF800000)
 PokeL(sampleAddress+32,$BF800000) : PokeL(sampleAddress+36,$3F800000)
 PokeL(sampleAddress+8,0) : PokeL(sampleAddress+12,0)
 PokeL(sampleAddress+24,$40000000) : PokeL(sampleAddress+28,0)
 PokeL(sampleAddress+40,0) : PokeL(sampleAddress+44,$40000000)
 smci\codeSize=vtpBuildVsD() : smci\pCode=@vtpVsD[0]
 If vkCreateShaderModule(device,@smci,0,@sampleVs)<>0 : ProcedureReturn 57 : EndIf
 smci\codeSize=vtpBuildFsD() : smci\pCode=@vtpFsD[0]
 If vkCreateShaderModule(device,@smci,0,@sampleFs)<>0 : ProcedureReturn 58 : EndIf
 dsb\binding=0 : dsb\descriptorType=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : dsb\descriptorCount=1 : dsb\stageFlags=#VK_SHADER_STAGE_FRAGMENT_BIT
 dlci\sType=#VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO : dlci\bindingCount=1 : dlci\pBindings=@dsb
 If vkCreateDescriptorSetLayout(device,@dlci,0,@dsl)<>0 : ProcedureReturn 59 : EndIf
 plci\pushConstantRangeCount=0 : plci\pPushConstantRanges=0 : plci\setLayoutCount=1 : plci\pSetLayouts=@dsl
 If vkCreatePipelineLayout(device,@plci,0,@sampledLayout)<>0 : ProcedureReturn 60 : EndIf
 binding\stride=16 : sampleAttributes[0]=attribute : sampleAttributes[1]=attribute
 sampleAttributes[1]\location=1 : sampleAttributes[1]\offset=8
 vi\vertexAttributeDescriptionCount=2 : vi\pVertexAttributeDescriptions=@sampleAttributes[0]
 stages[0]\module=sampleVs : stages[1]\module=sampleFs
 gp\layout=sampledLayout : gp\renderPass=sampledPass
 sampleReport[2]=vkCreateGraphicsPipelines(device,0,1,@gp,0,@sampledPipeline)
 If sampleReport[2]<>0 : ProcedureReturn 61 : EndIf
 vkDestroyShaderModule(device,sampleVs,0) : vkDestroyShaderModule(device,sampleFs,0)
 sci\sType=#VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO
 sci\minFilter=samplePhase&1 : sci\magFilter=samplePhase&1
 sci\addressModeU=#VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE : sci\addressModeV=#VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE : sci\addressModeW=#VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE
 If vkCreateSampler(device,@sci,0,@sampler)<>0 : ProcedureReturn 62 : EndIf
 dps\type=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : dps\descriptorCount=1
 dpci\sType=#VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO : dpci\maxSets=1 : dpci\poolSizeCount=1 : dpci\pPoolSizes=@dps
 If vkCreateDescriptorPool(device,@dpci,0,@dp)<>0 : ProcedureReturn 63 : EndIf
 dsai\sType=#VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO : dsai\descriptorPool=dp : dsai\descriptorSetCount=1 : dsai\pSetLayouts=@dsl
 If vkAllocateDescriptorSets(device,@dsai,@ds)<>0 : ProcedureReturn 64 : EndIf
 di\sampler=sampler : di\imageView=view : di\imageLayout=#VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
 write\sType=#VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET : write\dstSet=ds : write\descriptorCount=1 : write\descriptorType=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : write\pImageInfo=@di
 vkUpdateDescriptorSets(device,1,@write,0,0)
 If AnvilVkFaultCount()<>0 : ProcedureReturn 65 : EndIf
 If vkResetCommandBuffer(cmd,0)<>0 Or vkResetFences(device,1,@fence)<>0 Or vkBeginCommandBuffer(cmd,@bi)<>0 : ProcedureReturn 66 : EndIf
 rpbi\renderPass=sampledPass : rpbi\framebuffer=sampledFb
 vkCmdBeginRenderPass(cmd,@rpbi,#VK_SUBPASS_CONTENTS_INLINE)
 vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledPipeline)
 vkCmdBindVertexBuffers(cmd,0,1,@sampleBuffer,@offset)
 vkCmdBindDescriptorSets(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledLayout,0,1,@ds,0,0)
 vkCmdDraw(cmd,3,1,0,0) : vkCmdEndRenderPass(cmd)
 sampleReport[3]=vkEndCommandBuffer(cmd)
 If sampleReport[3]<>0 : ProcedureReturn 67 : EndIf
 sampleReport[4]=vkQueueSubmit(queue,1,@submit,fence)
 If sampleReport[4]<>0 : ProcedureReturn 68 : EndIf
 ; The shared flight ledger must retain the exact generations, even if the
 ; hardware has already finished but its completion has not been retired.
 sampleReport[19]=Bool(avkSampInFlight[avkSamplerSlot(sampler)]>0 And avkIvInFlight[avkIvSlot(view)]>0 And avkImgInFlight[avkImgSlot(image)]>0)
 sampleReport[5]=vkWaitForFences(device,1,@fence,1,250000000)
 sampleReport[6]=avkBackendLastNativeError() : sampleReport[7]=AnvilVkFaultCount()
 If sampleReport[5]<>0 : ProcedureReturn 69 : EndIf
 ; Closed-record invalid-input probes must refuse without changing the queue.
 If AnvilVkDescriptorSetSampledImage(ds,0,@avkSampleStage)<>1 : ProcedureReturn 71 : EndIf
 sampleSnapshot=snapshot : sampleWitness=avkSampleStage
 sampleSnapshot\pipeline=avkPipeSlot(sampledPipeline) : sampleSnapshot\viewportX=0
 sampleSnapshot\targetBase=AnvilVkImageAddress(sampledImage) : sampleSnapshot\pushBase=0 : sampleSnapshot\pushBytes=0
 witnessBinding\base=sampleAddress : witnessBinding\stride=16
 sampleSnapshot\sampledImage=@sampleWitness : sampleSequence=avkZenQueue\sequence
 sampleReport[8]=avkZenDrawPreflight(@sampleSnapshot)
 sampleWitness\width=0 : sampleReport[9]=avkZenDrawPreflight(@sampleSnapshot)
 sampleWitness=avkSampleStage : sampleWitness\bytes=1 : sampleReport[10]=avkZenDrawPreflight(@sampleSnapshot)
 sampleWitness=avkSampleStage : sampleWitness\magFilter=1-(samplePhase&1) : sampleReport[11]=avkZenDrawPreflight(@sampleSnapshot)
 sampleSnapshot\sampledImage=0 : sampleReport[12]=avkZenDrawPreflight(@sampleSnapshot)
 sampleSnapshot\sampledImage=@sampleWitness : sampleWitness=avkSampleStage : sampleWitness\base=sampleSnapshot\targetBase
 sampleReport[13]=avkZenDrawPreflight(@sampleSnapshot)
 sampleWitness=avkSampleStage : sampleWitness\layout=#VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
 sampleReport[20]=avkZenDrawPreflight(@sampleSnapshot)
 sampleWitness=avkSampleStage : sampleWitness\pitch=1
 sampleReport[21]=avkZenDrawPreflight(@sampleSnapshot)
 sampleSnapshot\sampledImage=avkZenQueue\ram-8
 sampleReport[22]=avkZenDrawPreflight(@sampleSnapshot)
 sampleReport[14]=Bool(avkZenQueue\sequence=sampleSequence And avkZenPending=0)
 If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(sampledImage))<>1 : ProcedureReturn 70 : EndIf''')
    s = replace_once(s, ' vkDeviceWaitIdle(device) : vkDestroyFence(device,fence,0)', r'''
 vkDeviceWaitIdle(device)
 vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)
 vkDestroyPipeline(device,sampledPipeline,0) : vkDestroyPipelineLayout(device,sampledLayout,0) : vkDestroyDescriptorSetLayout(device,dsl,0)
 vkDestroyBuffer(device,sampleBuffer,0) : vkFreeMemory(device,sampleBufferMem,0)
 vkDestroyFramebuffer(device,sampledFb,0) : vkDestroyRenderPass(device,sampledPass,0) : vkDestroyImageView(device,sampledView,0)
 vkDestroyImage(device,sampledImage,0) : vkFreeMemory(device,sampledMem,0)
 sampleReport[15]=AnvilVkFaultCount()
 vkDestroyFence(device,fence,0)''')
    return s


def expected_pixels(linear):
    def source_pixel(x, y):
        return 255 if min(15, max(0, x)) + min(15, max(0, y)) < 15 else 0
    result = []
    for y in range(16):
        for x in range(16):
            value = 0
            if x + y < 15:
                if linear:
                    # UV=2*pixel-center/16. ROM texel-center coordinates are
                    # (2*x+.5,2*y+.5): four equally weighted, clamped texels.
                    value = (sum(source_pixel(2*x+dx, 2*y+dy)
                                 for dy in (0, 1) for dx in (0, 1)) + 2)//4
                else:
                    value = source_pixel(2*x+1, 2*y+1)
            result.append((value << 24) | (value << 16))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zen-tools', type=Path, required=True)
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
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=120)
        assert p.returncode == 0, (p.returncode, p.stdout[-5000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-vulkan-sample-') as tmp:
        td = Path(tmp)
        src = td/'probe.zentaji'
        image = td/'probe.zex'
        src.write_text(source(), encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        print('Compiled public Vulkan render-to-texture composition', flush=True)
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        wrapped, _, _, _ = B.pack(image.read_bytes(), zt/'zasm.exe',
                                  source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        for phase in range(4):
            m = F.Fixture(ram_size=32 << 20, cores=2, display_modes=[(16, 16, 60000)])
            m.load_image(wrapped)
            struct.pack_into('<q', m.ram, ref.sym['GLOBAL_SAMPLEPHASE'], phase)
            assert not F.capture(m, str(td))
            out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '100000000', '--ram', td/'final.bin'])
            final = (td/'final.bin').read_bytes()
            report = struct.unpack_from('<32q', final, ref.sym['GLOBAL_SAMPLEREPORT'])
            end = next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end, (phase, end, report)
            assert report[2:8] == (0,)*6 and report[15] == 0, (phase, report)
            assert report[8:15] == (0, -8, -8, -8, -8, -8, 1), (phase, 'pre-launch refusals', report)
            assert report[16:23] == (0x81, 0, 16384, 1, -8, -8, -8), (phase, 'format queries, flight retention and descriptor bounds', report)
            producer = b''.join(struct.pack('<I', 0xFFFF0000 if x+y < 15 else 0)
                                for y in range(16) for x in range(16))
            assert final[report[0]:report[0]+1024] == producer, (phase, 'producer/source immutability')
            pixels = expected_pixels(phase & 1)
            expected = b''.join(struct.pack('<I', p) for p in pixels)
            actual = final[report[1]:report[1]+1024]
            assert actual == expected, (phase, 'RGBA sampler oracle',
                                       [(i, hex(a), hex(b)) for i, (a, b) in enumerate(zip(struct.unpack('<256I', actual), pixels)) if a != b][:12])
            headless = run([zt/'zenwin.exe', td/'machine.txt', '--headless', '--max', '100000000'])
            crc = zlib.crc32(b''.join(struct.pack('<I', p & 0xFFFFFF) for p in pixels))
            frames = [line for line in headless.splitlines() if line.startswith('FRAME ')]
            assert any(('%08X' % crc).lower() in line.lower() for line in frames), (phase, frames, hex(crc))
            print('PASS public Vulkan sampling %s/%s: GPU producer, retained descriptor, ROM filtering, exact RGBA and scanout, bounded preflight' %
                  ('optimal' if phase >= 2 else 'linear', 'bilinear' if phase & 1 else 'nearest'), flush=True)


if __name__ == '__main__':
    main()
