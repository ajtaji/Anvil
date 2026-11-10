"""Public DMA staging/copy/fill/update/upload followed by production Neon sampling."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib
import zentaji_boot_image as B
import zentaji_neon_pipeline_check as N
import zentaji_vulkan_sample_check as S
from zentaji_vulkan_blend_check import blend
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]


def source():
    s = N.source()
    s = S.replace_once(s, 'Global phase.i,samplePhase.i',
                      'Global phase.i,samplePhase.i,uploadMode.i\nGlobal Dim uploadReport.q[32]')
    s = S.replace_once(s, ' Protected chromeFsBytes.i', r'''
 Protected staging.i,stagingMem.i,upload.i,uploadMem.i,uploadAddress.i,x.i,y.i,clone.i,cloneMem.i,readback.i,readbackMem.i
 Protected bufferCopy.VkBufferCopy,imageCopy.VkBufferImageCopy
 Protected wholeCopy.VkImageCopy
 Protected Dim uploadHeader.l[4]
 Protected chromeFsBytes.i''')
    s = S.replace_once(s, '#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_SAMPLED_BIT',
                      '#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|#VK_IMAGE_USAGE_SAMPLED_BIT|#VK_IMAGE_USAGE_TRANSFER_DST_BIT|#VK_IMAGE_USAGE_TRANSFER_SRC_BIT')
    s = S.replace_once(s, ' ; The first public draw is the texture producer. No CPU writes its pixels.', r'''
 ; Replace the first GPU-produced triangle with a distinct staged texture.
 ; CPU writes mapped staging memory, never the image or copy destination.
 bci\size=1344 : bci\usage=#VK_BUFFER_USAGE_TRANSFER_SRC_BIT|#VK_BUFFER_USAGE_TRANSFER_DST_BIT
 If vkCreateBuffer(device,@bci,0,@staging)<>0 Or vkCreateBuffer(device,@bci,0,@upload)<>0 : ProcedureReturn 81 : EndIf
 vkGetBufferMemoryRequirements(device,staging,@req) : alloc\allocationSize=req\size
 If vkAllocateMemory(device,@alloc,0,@stagingMem)<>0 Or vkBindBufferMemory(device,staging,stagingMem,0)<>0 : ProcedureReturn 82 : EndIf
 If vkAllocateMemory(device,@alloc,0,@uploadMem)<>0 Or vkBindBufferMemory(device,upload,uploadMem,0)<>0 : ProcedureReturn 83 : EndIf
 If vkMapMemory(device,stagingMem,0,1344,0,@uploadAddress)<>0 : ProcedureReturn 84 : EndIf
 For n=0 To 335 : PokeL(uploadAddress+n*4,$A5A5A5A5) : Next
 For y=0 To 15
  For x=0 To 15
   PokeL(uploadAddress+16+y*80+x*4,((64+x*8)<<24)|((y*13)<<16)|((x*11)<<8)|(x+y))
  Next
 Next
 vkUnmapMemory(device,stagingMem)
 If samplePhase>=2
  If vkCreateImage(device,@ii,0,@clone)<>0 : ProcedureReturn 87 : EndIf
  vkGetImageMemoryRequirements(device,clone,@req) : alloc\allocationSize=req\size
  If vkAllocateMemory(device,@alloc,0,@cloneMem)<>0 Or vkBindImageMemory(device,clone,cloneMem,0)<>0 : ProcedureReturn 88 : EndIf
 Else
  If vkCreateBuffer(device,@bci,0,@readback)<>0 : ProcedureReturn 89 : EndIf
  If vkAllocateMemory(device,@alloc,0,@readbackMem)<>0 Or vkBindBufferMemory(device,readback,readbackMem,0)<>0 : ProcedureReturn 90 : EndIf
 EndIf
 uploadHeader[0]=$12345678 : uploadHeader[1]=$AABBCCDD : uploadHeader[2]=$76543210 : uploadHeader[3]=$FEDCBA98
 If vkResetCommandBuffer(cmd,0)<>0 Or vkResetFences(device,1,@fence)<>0 Or vkBeginCommandBuffer(cmd,@bi)<>0 : ProcedureReturn 85 : EndIf
 vkCmdFillBuffer(cmd,upload,0,1344,$A5A5A5A5)
 bufferCopy\srcOffset=16 : bufferCopy\dstOffset=32 : bufferCopy\size=1264
 vkCmdCopyBuffer(cmd,staging,upload,1,@bufferCopy)
 vkCmdUpdateBuffer(cmd,upload,0,16,@uploadHeader[0])
 barrier\oldLayout=#VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
 barrier\srcAccessMask=#VK_ACCESS_SHADER_READ_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT
 vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
 imageCopy\bufferOffset=32 : imageCopy\bufferRowLength=20 : imageCopy\bufferImageHeight=16
 imageCopy\imageSubresource\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : imageCopy\imageSubresource\layerCount=1
 imageCopy\imageExtent\width=16 : imageCopy\imageExtent\height=16 : imageCopy\imageExtent\depth=1
 vkCmdCopyBufferToImage(cmd,upload,image,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,@imageCopy)
 If samplePhase>=2
  ; Exercise both directions through a second optimal allocation, using the
  ; public image-copy path. The observer checks both allocations independently.
  wholeCopy\srcSubresource=imageCopy\imageSubresource : wholeCopy\dstSubresource=imageCopy\imageSubresource
  wholeCopy\extent=imageCopy\imageExtent
  barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  barrier\srcAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_READ_BIT
  vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
  barrier\image=clone : barrier\oldLayout=#VK_IMAGE_LAYOUT_UNDEFINED : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
  barrier\srcAccessMask=0 : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT
  vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
  vkCmdCopyImage(cmd,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,clone,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,@wholeCopy)
  barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  barrier\srcAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_READ_BIT
  vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
  barrier\image=image : barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL
  barrier\srcAccessMask=#VK_ACCESS_TRANSFER_READ_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT
  vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
  vkCmdCopyImage(cmd,clone,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,image,#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,@wholeCopy)
 Else
  vkCmdFillBuffer(cmd,readback,0,1344,$A5A5A5A5)
  barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  barrier\srcAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT : barrier\dstAccessMask=#VK_ACCESS_TRANSFER_READ_BIT
  vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,0,0,0,1,@barrier)
  vkCmdCopyImageToBuffer(cmd,image,#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,readback,1,@imageCopy)
 EndIf
 barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL : barrier\newLayout=#VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
 If samplePhase<2 : barrier\oldLayout=#VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : EndIf
 barrier\srcAccessMask=#VK_ACCESS_TRANSFER_WRITE_BIT|#VK_ACCESS_TRANSFER_READ_BIT : barrier\dstAccessMask=#VK_ACCESS_SHADER_READ_BIT
 vkCmdPipelineBarrier(cmd,#VK_PIPELINE_STAGE_TRANSFER_BIT,#VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,0,0,0,0,0,1,@barrier)
 If vkEndCommandBuffer(cmd)<>0 : ProcedureReturn 86 : EndIf
 If uploadMode<>0 : PokeQ(#ZEN_DMA_CHANNEL+$10,73) : EndIf
 uploadReport[0]=vkQueueSubmit(queue,1,@submit,fence)
 If uploadMode<>0
  uploadReport[1]=vkWaitForFences(device,1,@fence,1,250000000)
  uploadReport[2]=vkGetFenceStatus(device,fence)
  uploadReport[3]=avkFlightQuarantined : uploadReport[4]=avkZenLease
  uploadReport[5]=Bool(avkBufInFlight[avkBufSlot(upload)]>0 And avkBufInFlight[avkBufSlot(staging)]>0)
  uploadReport[6]=Bool(avkMemInFlight[avkMemSlot(uploadMem)]>0 And avkMemInFlight[avkMemSlot(stagingMem)]>0)
  uploadReport[7]=Bool(avkImgInFlight[avkImgSlot(image)]>0)
  uploadReport[8]=avkZenDma\launches : uploadReport[9]=avkZenDma\lost : uploadReport[10]=avkZenDma\error
  uploadReport[11]=avkBackendLastNativeError()
  vkDestroyBuffer(device,upload,0)
  uploadReport[12]=AnvilVkFaultCode() : uploadReport[13]=Bool(avkBufSlot(upload)<>0)
  vkFreeMemory(device,uploadMem,0)
  uploadReport[14]=AnvilVkFaultCode() : uploadReport[15]=Bool(avkMemSlot(uploadMem)<>0)
  uploadReport[16]=avkFlightPoll() : uploadReport[17]=avkFenceSignaled[avkFenceSlot(fence)]
  uploadReport[18]=avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_QUEUE)
  uploadReport[19]=PeekQ(#ZEN_DMA_CHANNEL+$10)
  uploadReport[20]=AnvilVkImageAddress(image)
  ProcedureReturn 42
 EndIf
 If uploadReport[0]<>0 Or vkWaitForFences(device,1,@fence,1,250000000)<>0 : ProcedureReturn 86 : EndIf
 sampleReport[24]=AnvilVkBufferAddress(upload) : sampleReport[25]=AnvilVkBufferAddress(staging)
 sampleReport[26]=avkZenDma\launches : sampleReport[27]=avkZenDma\sleeps
 sampleReport[28]=avkBackendCaps() : sampleReport[29]=avkZenDma\lost
 If clone<>0 : sampleReport[30]=AnvilVkImageAddress(clone) : EndIf
 If readback<>0 : sampleReport[31]=AnvilVkBufferAddress(readback) : EndIf
 bci\usage=#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT
''')
    s = S.replace_once(s, ' vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)', r'''
 vkDestroyBuffer(device,staging,0) : vkFreeMemory(device,stagingMem,0)
 vkDestroyBuffer(device,upload,0) : vkFreeMemory(device,uploadMem,0)
 If clone<>0 : vkDestroyImage(device,clone,0) : vkFreeMemory(device,cloneMem,0) : EndIf
 If readback<>0 : vkDestroyBuffer(device,readback,0) : vkFreeMemory(device,readbackMem,0) : EndIf
 vkDestroyDescriptorPool(device,dp,0) : vkDestroySampler(device,sampler,0)''')
    s = S.replace_once(s, ' If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(sampledImage))<>1 : ProcedureReturn 70 : EndIf', r'''
 ; Cross three descriptor batches without overwriting the retired GPU fence.
 uploadReport[3]=avkZenQueue\sequence : uploadReport[4]=avkZenDma\launches
 If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_QUEUE)<>1 : ProcedureReturn 91 : EndIf
 uploadReport[1]=avkBackendSubmitBufferCopyRows(AnvilVkBufferAddress(staging),12,AnvilVkBufferAddress(upload),12,4,100)
 uploadReport[2]=Bool(PeekQ(avkZenQueue\fence)=uploadReport[3])
 uploadReport[4]=avkZenDma\launches-uploadReport[4]
 uploadReport[5]=avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_QUEUE)
 If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(sampledImage))<>1 : ProcedureReturn 70 : EndIf''')
    return s


def texel(x, y):
    x, y = min(15, max(0, x)), min(15, max(0, y))
    return (64+x*8, y*13, x*11, x+y)


def pixels(linear):
    result = []
    for y in range(16):
        for x in range(16):
            if x+y >= 15:
                result.append(0)
                continue
            channels = texel(2*x+1, 2*y+1)
            if linear:
                taps = [texel(2*x+dx, 2*y+dy) for dy in (0, 1) for dx in (0, 1)]
                channels = tuple((sum(t[i] for t in taps)+2)//4 for i in range(4))
            alpha, red, green, blue = channels
            value = (((alpha+1)//2) << 24) | (((red+1)//2) << 16) | (green << 8) | blue
            result.append(blend(value, 0, True))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zen-tools', type=Path, required=True)
    ap.add_argument('--keep', type=Path)
    ap.add_argument('--reuse', action='store_true', help='reuse a kept image only when every compiler source and the guest text still match')
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
        assert p.returncode == 0, (p.returncode, p.stdout[-5000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-native-upload-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src, image = td/'probe.zentaji', td/'probe.zex'
        if a.reuse:
            assert a.keep and src.read_text(encoding='utf-8') == source(), 'reuse needs an identical kept guest source'
            mapping = json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig'))
            assert hashlib.sha256(image.read_bytes()).hexdigest() == mapping['image'], 'reused image identity'
            for row in mapping['sources']:
                assert hashlib.sha256(Path(row['path']).read_bytes().replace(b'\r', b'')).hexdigest() == row['sha256'], ('reused source identity', row['path'])
            print('Verified kept image and all%d compiler source identities' % len(mapping['sources']), flush=True)
        else:
            src.write_text(source(), encoding='utf-8')
            run([cc, '--compile', src, '-o', image])
        print('Prepared public native upload and production Neon composition', flush=True)
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        executable, _, _, _ = B.pack(image.read_bytes(), zt/'zasm.exe', source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        receipts = []
        for phase, mode in [(p, 0) for p in range(4)]+[(0, 1), (2, 1)]:
            m = F.Fixture(ram_size=32 << 20, cores=2, display_modes=[(16, 16, 60000)])
            m.load_image(executable)
            struct.pack_into('<q', m.ram, ref.sym['GLOBAL_SAMPLEPHASE'], phase)
            struct.pack_into('<q', m.ram, ref.sym['GLOBAL_UPLOADMODE'], mode)
            assert not F.capture(m, str(td))
            out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '100000000', '--ram', td/'final.bin'])
            (td/('native-%d-%d.txt' % (phase, mode))).write_text(out, encoding='utf-8')
            ram = (td/'final.bin').read_bytes()
            report = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_SAMPLEREPORT'])
            end = next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end, (phase, end, report)
            if mode:
                fault = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_UPLOADREPORT'])
                assert fault[:11] == (-4, -4, -4, 1, -1, 1, 1, 1, 0, 1, 4), fault
                assert fault[11] == 4 << 32 and fault[12:20] == (-20004, 1, -20004, 1, -1, 0, 0, 73), fault
                original = b''.join(struct.pack('<I', 0xffff0000 if x+y < 15 else 0) for y in range(16) for x in range(16))
                assert ram[fault[20]:fault[20]+1024] == original, (phase, 'no image transfer after owner loss')
                receipts.append(dict(phase=phase, mode=mode, report=fault))
                (td/'results.json').write_text(json.dumps(receipts, indent=2)+'\n', encoding='utf-8')
                print('PASS native public upload owner loss phase=%d: retained resources, refused destruction, unsignalled fence and repeated device loss' % phase, flush=True)
                continue
            assert report[2:8] == (0,)*6 and report[15] == 0, (phase, report)
            upload_report = struct.unpack_from('<32q', ram, ref.sym['GLOBAL_UPLOADREPORT'])
            assert upload_report[:6] == (0, 0, 1, 2, 3, 1), ('retired GPU fence across DMA batches', upload_report)
            assert report[26] == 6 and report[27] >= 0 and report[28:30] == (0x1C001EF, 0), report
            staging = bytearray(b'\xa5'*1344)
            texture = bytearray()
            for y in range(16):
                for x in range(16):
                    alpha, red, green, blue = texel(x, y)
                    word = struct.pack('<I', (alpha << 24) | (red << 16) | (green << 8) | blue)
                    staging[16+y*80+x*4:20+y*80+x*4] = word
                    texture.extend(word)
            uploaded = bytearray(b'\xa5'*1344)
            uploaded[32:1296] = staging[16:1280]
            uploaded[:16] = struct.pack('<4I', 0x12345678, 0xaabbccdd, 0x76543210, 0xfedcba98)
            for row in range(100):
                uploaded[row*12:row*12+4] = staging[row*12:row*12+4]
            assert ram[report[25]:report[25]+1344] == staging, (phase, 'staging immutability')
            assert ram[report[24]:report[24]+1344] == uploaded, (phase, 'copy/fill/update guards')
            assert ram[report[0]:report[0]+1024] == texture, (phase, 'pitched upload pixels')
            if phase >= 2:
                assert report[30] != report[0], (phase, 'distinct optimal allocations')
                assert ram[report[30]:report[30]+1024] == texture, (phase, 'optimal image copy pixels')
            else:
                readback = bytearray(b'\xa5'*1344)
                for row in range(16):
                    readback[32+row*80:96+row*80] = texture[row*64:(row+1)*64]
                assert ram[report[31]:report[31]+1344] == readback, (phase, 'pitched image readback and guards')
            expected = pixels(phase & 1)
            assert struct.unpack_from('<256I', ram, report[1]) == tuple(expected), (phase, 'Neon RGBA', report)
            frames = run([zt/'zenwin.exe', td/'machine.txt', '--headless', '--max', '100000000'])
            crc = zlib.crc32(b''.join(struct.pack('<I', p & 0xffffff) for p in expected))
            assert any(('%08X' % crc).lower() in line.lower() for line in frames.splitlines() if line.startswith('FRAME ')), (phase, frames[-1000:])
            receipts.append(dict(phase=phase, report=report, crc='%08X' % crc))
            (td/'results.json').write_text(json.dumps(receipts, indent=2)+'\n', encoding='utf-8')
            print('PASS native public staging/copy/fill/update/upload phase=%d: exact bytes, RGBA and frame CRC' % phase, flush=True)


if __name__ == '__main__':
    main()
