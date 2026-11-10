"""Public ordered native GPU frames, atomic admission and fault quarantine."""
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
import zentaji_neon_pipeline_check as neon
import zentaji_vulkan_sample_check as sample
from zentaji_vulkan_blend_check import blend

ROOT = Path(__file__).resolve().parents[1]
RECTS = ((0, 0, 16, 16), (3, 4, 5, 6), (0, 0, 8, 16),
         (8, 0, 8, 16), (0, 8, 16, 8), (0, 0, 16, 16))
TINTS = ((1, 2), (2, 4), (4, 2), (1, 4), (2, 2), (4, 4))


def source():
    s = neon.source()
    s = sample.replace_once(s, 'Global phase.i,samplePhase.i', '''Global phase.i,samplePhase.i,listMode.i
Global Dim listReport.q[32]
Global Dim probeRecords.AnvilVkBackendDraw[#ANVIL_VK_MAX_RECORDED_DRAWS]''')
    s = sample.replace_once(s, ' Protected chromeFsBytes.i', ''' Protected lateSampler.i,lateSet.i,recordIndex.i,firstSequence.q,sentinel.i,originalShader.q
 Protected probeHeader.AnvilVkBackendDrawList
 Protected attachment.VkClearAttachment,clearRect.VkClearRect
 Protected chromeFsBytes.i''')
    for n in (0, 1):
        s = sample.replace_once(s, 'chromePoolSizes[%d]\\descriptorCount=1' % n,
                                'chromePoolSizes[%d]\\descriptorCount=2' % n)
    s = sample.replace_once(s, 'dpci\\maxSets=1', 'dpci\\maxSets=2')
    s = sample.replace_once(s, ' If AnvilVkFaultCount()<>0 : ProcedureReturn 65 : EndIf', r'''
 If vkAllocateDescriptorSets(device,@dsai,@lateSet)<>0 : ProcedureReturn 74 : EndIf
 If listMode=1 : sci\magFilter=1-(samplePhase&1) : EndIf
 If vkCreateSampler(device,@sci,0,@lateSampler)<>0 : ProcedureReturn 75 : EndIf
 write\dstSet=lateSet
 vkUpdateDescriptorSets(device,1,@write,0,0)
 di\sampler=lateSampler
 write\dstBinding=1 : write\descriptorType=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : write\pImageInfo=@di : write\pBufferInfo=0
 vkUpdateDescriptorSets(device,1,@write,0,0)
 If AnvilVkFaultCount()<>0 : ProcedureReturn 65 : EndIf
 If listMode=1
  For n=0 To 1023 : PokeA(AnvilVkImageAddress(sampledImage)+n,$A5) : Next
 EndIf''')
    start = s.index(' vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledPipeline)')
    end = s.index(' sampleReport[3]=vkEndCommandBuffer', start)
    frame = r'''
 attachment\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : attachment\colorAttachment=0
 attachment\clearValue[2]=$3F800000 : attachment\clearValue[3]=$3F800000
 clearRect\rect\offset\x=4 : clearRect\rect\offset\y=3 : clearRect\rect\extent\width=6 : clearRect\rect\extent\height=4 : clearRect\layerCount=1
 vkCmdBindPipeline(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledPipeline)
 vkCmdBindVertexBuffers(cmd,0,1,@sampleBuffer,@offset)
 vkCmdSetViewport(cmd,0,1,@vp)
 If listMode=3
  vkCmdClearAttachments(cmd,1,@attachment,1,@clearRect)
 Else
'''
    for i, ((x, y, w, h), (red_div, alpha_div)) in enumerate(zip(RECTS, TINTS)):
        bits = {1: '$3F800000', 2: '$3F000000', 4: '$3E800000'}
        frame += r'''
 sc\offset\x=%d : sc\offset\y=%d : sc\extent\width=%d : sc\extent\height=%d
 vkCmdSetScissor(cmd,0,1,@sc)
 push[0]=%s : push[1]=$3F800000 : push[2]=$3F800000 : push[3]=%s
 vkCmdPushConstants(cmd,sampledLayout,#VK_SHADER_STAGE_FRAGMENT_BIT,0,16,@push[0])
''' % (x, y, w, h, bits[red_div], bits[alpha_div])
        frame += ' vkCmdBindDescriptorSets(cmd,#VK_PIPELINE_BIND_POINT_GRAPHICS,sampledLayout,0,1,@%s,0,0)\n' % ('lateSet' if i == 5 else 'ds')
        frame += ' vkCmdDraw(cmd,3,1,0,0)\n'
        if i == 2:
            frame += ' vkCmdClearAttachments(cmd,1,@attachment,1,@clearRect)\n'
    frame += ' EndIf\n vkCmdEndRenderPass(cmd)\n'
    s = s[:start]+frame+s[end:]
    s = sample.replace_once(s, ' sampleReport[4]=vkQueueSubmit(queue,1,@submit,fence)', r'''
 firstSequence=avkZenQueue\sequence
 sampleReport[4]=vkQueueSubmit(queue,1,@submit,fence)
 If listMode=1
  listReport[0]=sampleReport[4] : listReport[1]=avkZenQueue\sequence-firstSequence
  listReport[2]=AnvilVkSubmissionOutstanding() : listReport[3]=vkGetFenceStatus(device,fence)
  listReport[4]=Bool(avkZenLease=0 And avkZenListActive=0 And avkZenPending=0 And avkSampInFlight[avkSamplerSlot(sampler)]=0 And avkSampInFlight[avkSamplerSlot(lateSampler)]=0 And avkImgInFlight[avkImgSlot(sampledImage)]=0)
  sentinel=1 : For n=0 To 1023 : If PeekA(AnvilVkImageAddress(sampledImage)+n)<>$A5 : sentinel=0 : EndIf : Next
  listReport[5]=sentinel
  If sampleReport[4]<>#VK_ERROR_FEATURE_NOT_PRESENT : ProcedureReturn 76 : EndIf
  di\sampler=sampler
  write\dstSet=lateSet : write\dstBinding=1 : write\descriptorType=#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER : write\pImageInfo=@di : write\pBufferInfo=0
  vkUpdateDescriptorSets(device,1,@write,0,0)
  ; Same executable command buffer and unsignalled fence must be retryable.
  sampleReport[4]=vkQueueSubmit(queue,1,@submit,fence)
 EndIf''')
    s = sample.replace_once(s, ' sampleReport[5]=vkWaitForFences(device,1,@fence,1,250000000)', r'''
 If listMode=0 And samplePhase=0
  ; Whole-array limits and hostile metadata are checked without dispatch.
  For n=0 To #ANVIL_VK_MAX_RECORDED_DRAWS-1 : probeRecords[n]=avkFlightDraw[0] : Next
  probeHeader\draws=@probeRecords[0] : probeHeader\drawCount=#ANVIL_VK_MAX_RECORDED_DRAWS
  recordIndex=avkZenQueue\sequence
  listReport[8]=avkZenListPreflight(@probeHeader)
  probeHeader\drawCount=#ANVIL_VK_MAX_RECORDED_DRAWS+1 : listReport[9]=avkZenListPreflight(@probeHeader)
  probeHeader\drawCount=0 : listReport[10]=avkZenListPreflight(@probeHeader)
  probeHeader\drawCount=1 : probeHeader\draws=avkZenQueue\ram-8 : listReport[11]=avkZenListPreflight(@probeHeader)
  probeHeader\draws=avkZenQueue\list : listReport[12]=avkZenListPreflight(@probeHeader)
  probeHeader\draws=@probeRecords[0] : probeHeader\drawCount=2
  probeRecords[1]\pipeline=#ANVIL_VK_MAX_PIPELINES+1 : listReport[13]=avkZenListPreflight(@probeHeader)
  probeRecords[1]=probeRecords[0] : probeRecords[1]\width=15 : listReport[14]=avkZenListPreflight(@probeHeader)
  probeHeader\drawCount=1 : probeRecords[0]\pushBase=avkZenQueue\list+2112 : listReport[16]=avkZenListPreflight(@probeHeader)
  probeRecords[0]=avkFlightDraw[0] : probeRecords[0]\bindings=avkZenQueue\ram-8 : listReport[17]=avkZenListPreflight(@probeHeader)
  listReport[15]=Bool(avkZenQueue\sequence=recordIndex)
 EndIf
 If listMode=2
  ; Let item0 finish without retiring its transport or dispatching item1.
  For n=0 To 4095
   If (PeekQ(#ZEN_GFX_3D+8)&1)=0 : Break : EndIf
   HwPromptIdleWait()
  Next
  If (PeekQ(#ZEN_GFX_3D+8)&1)<>0 : ProcedureReturn 77 : EndIf
  ; Deliberate fault injection after complete list admission. Opcode FE is
  ; reserved; the next real shader invocation must fault before writing pixels.
  PokeQ(avkZenPipelines[avkPipeSlot(sampledPipeline)]\base+#AVK_ZEN_SHADER_CODE_BYTES,$FE)
 EndIf
 sampleReport[5]=vkWaitForFences(device,1,@fence,1,2000000000)''')
    s = sample.replace_once(s, ' If sampleReport[5]<>0 : ProcedureReturn 69 : EndIf', r'''
 listReport[6]=avkZenQueue\sequence
 listReport[7]=Bool(avkZenListActive=0 And avkZenPending=0 And avkZenListBase=0)
 If listMode=2
  listReport[18]=avkFlightQuarantined : listReport[19]=avkZenLease
  listReport[20]=Bool(avkSampInFlight[avkSamplerSlot(sampler)]>0 And avkImgInFlight[avkImgSlot(sampledImage)]>0 And avkMemInFlight[avkBufMemSlot[avkBufSlot(chromeUniform)]]>0)
  listReport[21]=avkFenceSignaled[avkFenceSlot(fence)]
  listReport[22]=AnvilVkCompleteCount() : listReport[23]=avkZenListActive
  If sampleReport[5]<>#VK_ERROR_DEVICE_LOST : ProcedureReturn 78 : EndIf
  vkDestroySampler(device,sampler,0)
  listReport[24]=AnvilVkFaultCode() : listReport[25]=Bool(avkSamplerSlot(sampler)<>0)
  vkDestroyPipeline(device,sampledPipeline,0)
  listReport[26]=AnvilVkFaultCode() : listReport[27]=Bool(avkPipeSlot(sampledPipeline)<>0)
  ; Resources intentionally remain quarantined until machine reset.
  ProcedureReturn 42
 EndIf
 If sampleReport[5]<>0 : ProcedureReturn 69 : EndIf''')
    s = sample.replace_once(s, ' vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)',
                            ' vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0) : vkDestroySampler(device,lateSampler,0)')
    return s


def expected_pixels(linear, mode):
    texels = sample.expected_pixels(linear)
    result = []
    for at, texel in enumerate(texels):
        x, y = at % 16, at // 16
        pixel = 0
        if mode == 3:
            result.append(0xFF0000FF if 4 <= x < 10 and 3 <= y < 7 else 0)
            continue
        for i, ((sx, sy, w, h), (red_div, alpha_div)) in enumerate(zip(RECTS, TINTS)):
            if mode == 2 and i == 1:
                break
            if sx <= x < sx+w and sy <= y < sy+h and x+y < 15:
                red = (((texel >> 16) & 255)+red_div//2)//red_div
                alpha = (((texel >> 24) & 255)+alpha_div//2)//alpha_div
                pixel = blend((alpha << 24) | (red << 16), pixel, True)
            if i == 2 and 4 <= x < 10 and 3 <= y < 7:
                pixel = 0xFF0000FF
        result.append(pixel)
    return result


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
        p = subprocess.run([str(x) for x in argv], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        assert p.returncode == 0, (p.returncode, p.stdout[-6000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-native-draw-list-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src, image = td/'probe.zentaji', td/'probe.zex'
        src.write_text(source(), encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        print('Compiled actual Neon ordered native frame composition', flush=True)
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        executable, _, _, _ = B.pack(image.read_bytes(), zt/'zasm.exe', source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        cases = [(phase, 0) for phase in range(4)]+[(0, 1), (1, 1), (0, 2), (0, 3)]
        for index, (phase, mode) in enumerate(cases):
            m = F.Fixture(ram_size=32 << 20, cores=2, display_modes=[(16, 16, 60000)])
            m.load_image(executable)
            for name, value in [('SAMPLEPHASE', phase), ('LISTMODE', mode)]:
                struct.pack_into('<q', m.ram, ref.sym['GLOBAL_'+name], value)
            assert not F.capture(m, str(td))
            out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '100000000', '--ram', td/'final.bin'])
            (td/('native-%d.txt' % index)).write_text(out, encoding='utf-8')
            ram = (td/'final.bin').read_bytes()
            sr = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_SAMPLEREPORT'])
            lr = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_LISTREPORT'])
            end = next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end, (phase, mode, end, sr, lr)
            assert sr[2:5] == (0, 0, 0), (phase, mode, sr, lr)
            pixels = expected_pixels(phase & 1, mode)
            actual = struct.unpack_from('<256I', ram, sr[1])
            assert actual == tuple(pixels), (phase, mode, 'ordered RGBA', [(i, hex(x), hex(y)) for i, (x, y) in enumerate(zip(actual, pixels)) if x != y][:12], sr, lr)
            if mode == 2:
                assert sr[5] == -4 and sr[6] >> 32 == 5 and sr[6] & 4, (sr, lr)
                assert lr[6] == 3 and lr[18:24] == (1, -1, 1, 0, 1, -1), (sr, lr)
                assert lr[24:28] == (-20004, 1, -20004, 1), (sr, lr)
            else:
                faults = int(mode == 1)
                assert sr[5:8] == (0, 0, faults) and sr[15] == faults, (phase, mode, sr, lr)
                assert lr[6:8] == (2 if mode == 3 else 8, 1), (phase, mode, lr)
                if mode == 1:
                    assert lr[:6] == (-8, 0, 0, 1, 1, 1), lr
                if phase == 0 and mode == 0:
                    assert lr[8:18] == (0, -20001, -20001, -20001, -20001, -20001, -20001, 1, -8, -8), lr
                frames = run([zt/'zenwin.exe', td/'machine.txt', '--headless', '--max', '100000000'])
                crc = zlib.crc32(b''.join(struct.pack('<I', p & 0xFFFFFF) for p in pixels))
                assert any(('%08X' % crc).lower() in line.lower() for line in frames.splitlines() if line.startswith('FRAME ')), (phase, mode, hex(crc), frames[-1000:])
            print('PASS native ordered frame phase=%d mode=%d: exact RGBA%s' %
                  (phase, mode, ', later GPU fault quarantines resources without signalling the fence' if mode == 2 else ', final fence and exact scanout CRC'), flush=True)


if __name__ == '__main__':
    main()
