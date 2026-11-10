"""Execute Neon's production textured pipeline and fragment shader on Zentaji."""
# SPDX-License-Identifier: MIT
import re
from pathlib import Path
import zentaji_vulkan_sample_check as sample
from zentaji_vulkan_blend_check import blend

ROOT = Path(__file__).resolve().parents[1]
original_source = sample.source
original_pixels = sample.expected_pixels


def procedure(text, name):
    match = re.search(r'^Procedure(?:\.\w+)?\s+'+re.escape(name)+r'\(', text, re.M)
    assert match, name
    end = text.index('\nEndProcedure', match.start())+len('\nEndProcedure')
    return text[match.start():end]+'\n'


def source():
    chrome = (ROOT/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi').read_text(encoding='utf-8')
    assert re.search(r'^#NEON_VK_CHROME_VERTEX_BYTES\s*=\s*24\s*$', chrome, re.M)
    for name in ('neon_vk_chrome.pbi', 'neon_vk_line_stream.pbi', 'neon_vk_outline.pbi'):
        text = (ROOT/'Anvil/Graphics/Vulkan'/name).read_text(encoding='utf-8')
        assert text.count('cba\\srcAlphaBlendFactor = #VK_BLEND_FACTOR_ONE') == 1, name
    s = original_source()
    helper = '''XIncludeFile "Anvil/Graphics/float_bits.pbi"
#NEON_VK_CHROME_VERTEX_BYTES=24
#NEON_VK_CHROME_F_ONE=$3F800000
Global nvcDevice.i,nvcWidth.i,nvcHeight.i,nvcPipelineLayout.i,nvcRenderPass.i
Global Dim nvcFs.l[1024]
'''
    helper += procedure(chrome, 'nvcBuildFragmentShader')
    helper += procedure(chrome, 'nvcCreateDrawPipelineBlend')
    s = sample.replace_once(s, 'Procedure.i Main(', helper+'Procedure.i Main(')
    s = sample.replace_once(s, ' Protected sampledImage.i', ''' Protected chromeFsBytes.i,chromeUniform.i,chromeUniformMem.i,chromeUniformAddress.i
 Protected Dim chromeBindings.VkDescriptorSetLayoutBinding[2]
 Protected Dim chromePoolSizes.VkDescriptorPoolSize[2]
 Protected chromeUniformInfo.VkDescriptorBufferInfo
 Protected sampledImage.i''')
    s = sample.replace_once(s, '\n bci\\size=48\n', '\n bci\\size=72\n')
    start = s.index(' PokeL(sampleAddress,$BF800000)')
    end = s.index(' dsb\\binding=0', start)
    s = s[:start]+r'''
 PokeL(sampleAddress,$BF800000) : PokeL(sampleAddress+4,$BF800000)
 PokeL(sampleAddress+24,$3F800000) : PokeL(sampleAddress+28,$BF800000)
 PokeL(sampleAddress+48,$BF800000) : PokeL(sampleAddress+52,$3F800000)
 PokeL(sampleAddress+8,0) : PokeL(sampleAddress+12,0)
 PokeL(sampleAddress+32,$40000000) : PokeL(sampleAddress+36,0)
 PokeL(sampleAddress+56,0) : PokeL(sampleAddress+60,$40000000)
 bci\size=16 : bci\usage=#VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT
 If vkCreateBuffer(device,@bci,0,@chromeUniform)<>0 : ProcedureReturn 72 : EndIf
 vkGetBufferMemoryRequirements(device,chromeUniform,@req) : alloc\allocationSize=req\size
 If vkAllocateMemory(device,@alloc,0,@chromeUniformMem)<>0 Or vkBindBufferMemory(device,chromeUniform,chromeUniformMem,0)<>0 : ProcedureReturn 73 : EndIf
 chromeUniformAddress=AnvilVkBufferAddress(chromeUniform)
 For n=0 To 3 : PokeL(chromeUniformAddress+n*4,0) : Next
 chromeFsBytes=nvcBuildFragmentShader()
'''+s[end:]
    start = s.index(' dsb\\binding=0')
    end = s.index(' plci\\pushConstantRangeCount=0', start)
    s = s[:start]+r'''
 chromeBindings[0]\binding=0 : chromeBindings[0]\descriptorType=#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER
 chromeBindings[0]\descriptorCount=1 : chromeBindings[0]\stageFlags=#VK_SHADER_STAGE_FRAGMENT_BIT
 chromeBindings[1]=chromeBindings[0] : chromeBindings[1]\binding=1 : chromeBindings[1]\descriptorType=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
 dlci\sType=#VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO : dlci\bindingCount=2 : dlci\pBindings=@chromeBindings[0]
 If vkCreateDescriptorSetLayout(device,@dlci,0,@dsl)<>0 : ProcedureReturn 59 : EndIf
'''+s[end:]
    s = sample.replace_once(s, 'plci\\pushConstantRangeCount=0 : plci\\pPushConstantRanges=0',
                            'plci\\pushConstantRangeCount=1 : plci\\pPushConstantRanges=@pcr')
    start = s.index(' binding\\stride=16 : sampleAttributes[0]')
    end = s.index(' sci\\sType=', start)
    s = s[:start]+r'''
 nvcDevice=device : nvcWidth=16 : nvcHeight=16 : nvcPipelineLayout=sampledLayout : nvcRenderPass=sampledPass
 sampleReport[2]=nvcCreateDrawPipelineBlend(chromeFsBytes,#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,@sampledPipeline,#VK_TRUE)
 If sampleReport[2]<>0 : ProcedureReturn 61 : EndIf
'''+s[end:]
    start = s.index(' dps\\type=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER')
    end = s.index(' dsai\\sType=', start)
    s = s[:start]+r'''
 chromePoolSizes[0]\type=#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : chromePoolSizes[0]\descriptorCount=1
 chromePoolSizes[1]\type=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : chromePoolSizes[1]\descriptorCount=1
 dpci\sType=#VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO : dpci\maxSets=1 : dpci\poolSizeCount=2 : dpci\pPoolSizes=@chromePoolSizes[0]
 If vkCreateDescriptorPool(device,@dpci,0,@dp)<>0 : ProcedureReturn 63 : EndIf
'''+s[end:]
    s = sample.replace_once(s, 'write\\dstSet=ds : write\\descriptorCount=1',
                            'write\\dstSet=ds : write\\dstBinding=1 : write\\descriptorCount=1')
    s = sample.replace_once(s, ' vkUpdateDescriptorSets(device,1,@write,0,0)', r'''
 vkUpdateDescriptorSets(device,1,@write,0,0)
 chromeUniformInfo\buffer=chromeUniform : chromeUniformInfo\range=16
 write\dstBinding=0 : write\descriptorType=#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER : write\pImageInfo=0 : write\pBufferInfo=@chromeUniformInfo
 vkUpdateDescriptorSets(device,1,@write,0,0)''')
    s = sample.replace_once(s, ' vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledPipeline)', r'''
 vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledPipeline)
 vkCmdSetViewport(cmd,0,1,@vp) : vkCmdSetScissor(cmd,0,1,@sc)
 For n=0 To 3 : push[n]=$3F800000 : Next
 push[0]=$3F000000 : push[3]=$3F000000
 vkCmdPushConstants(cmd,sampledLayout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@push[0])''')
    s = sample.replace_once(s, 'AnvilVkDescriptorSetSampledImage(ds,0,@avkSampleStage)',
                            'AnvilVkDescriptorSetSampledImage(ds,1,@avkSampleStage)')
    s = sample.replace_once(s, 'sampleSnapshot\\pushBase=0 : sampleSnapshot\\pushBytes=0',
                            'sampleSnapshot\\pushBase=@push[0] : sampleSnapshot\\pushBytes=16\n sampleSnapshot\\uniformBase=chromeUniformAddress : sampleSnapshot\\uniformBytes=16 : sampleSnapshot\\blendMode=#ANVIL_VK_BLEND_ALPHA_ONE')
    s = sample.replace_once(s, 'witnessBinding\\stride=16', 'witnessBinding\\stride=24')
    s = sample.replace_once(s, ' vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)', r'''
 vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)
 vkDestroyBuffer(device,chromeUniform,0) : vkFreeMemory(device,chromeUniformMem,0)''')
    return s


def pixels(linear):
    # The actual shader multiplies sampled red and alpha by one half before
    # the native GPU's UNORM8 conversion and blend. Round those two channels
    # independently, then apply the documented hardware blend equation.
    result = []
    for pixel in original_pixels(linear):
        red = (((pixel >> 16) & 255)+1)//2
        alpha = (((pixel >> 24) & 255)+1)//2
        result.append(blend((alpha << 24) | (red << 16), 0, True))
    return result


if __name__ == '__main__':
    sample.source = source
    sample.expected_pixels = pixels
    sample.main()
    print('PASS production Neon textured pipeline builder and atlas fragment shader: native GPU sampling, tint/zero UBO, ALPHA_ONE and dynamic state; full resident lifecycle not claimed')
