"""Exact public Vulkan RGBA blending on native GPU and software executors."""
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
from fractions import Fraction

from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
from zentaji_vulkan_draw_check import SOURCE as DRAW_SOURCE
from zentaji_vulkan_sample_check import replace_once

ROOT = Path(__file__).resolve().parents[1]


def source(software):
    s = replace_once(DRAW_SOURCE, 'Global phase.i',
                     'Global phase.i,blendAlpha.i,legacyAlpha.i\nGlobal Dim blendReport.q[8]')
    s = replace_once(s, ' Protected ici.VkInstanceCreateInfo',
                     ' Protected blendProperties.VkFormatProperties,closedMode.i\n Protected ici.VkInstanceCreateInfo')
    s = replace_once(s, ' cba\\colorWriteMask=15', r'''
 cba\colorWriteMask=15 : cba\blendEnable=#VK_TRUE
 cba\srcColorBlendFactor=#VK_BLEND_FACTOR_SRC_ALPHA : cba\dstColorBlendFactor=#VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
 cba\srcAlphaBlendFactor=#VK_BLEND_FACTOR_ONE : cba\dstAlphaBlendFactor=#VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
 If legacyAlpha<>0 : cba\srcAlphaBlendFactor=#VK_BLEND_FACTOR_SRC_ALPHA : EndIf
 clear[2]=$3F800000 : clear[3]=$3F000000''')
    s = replace_once(s, ' push[0]=$3F800000 : push[3]=$3F800000',
                     ' push[0]=$3F800000 : push[3]=blendAlpha')
    s = replace_once(s, ' vkDeviceWaitIdle(device) : vkDestroyFence(device,fence,0)', r'''
 blendReport[0]=avkPipeBlendMode[avkPipeSlot(pipeline)]
 blendReport[1]=AnvilVkBackendCanBlendSourceOver()
 vkGetPhysicalDeviceFormatProperties(physical,#VK_FORMAT_B8G8R8A8_UNORM,@blendProperties)
 blendReport[2]=blendProperties\linearTilingFeatures
 ; Asking for a different factor must never silently select the native mode.
 cba\srcAlphaBlendFactor=#VK_BLEND_FACTOR_SRC_ALPHA
 blendReport[3]=avkPipeCheckColorBlend(@cb,@closedMode)
 blendReport[4]=closedMode
 cba\srcAlphaBlendFactor=#VK_BLEND_FACTOR_ZERO
 blendReport[5]=avkPipeCheckColorBlend(@cb,@closedMode)
 blendReport[6]=closedMode
 vkDeviceWaitIdle(device) : vkDestroyFence(device,fence,0)''')
    if software:
        s = replace_once(s, 'XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_backend.pbi"',
                         'XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_software.pbi"')
        s = replace_once(s, '#ANVIL_VULKAN_BACKEND=3', '#ANVIL_VULKAN_BACKEND=2')
        s = replace_once(s, ' If ZentajiMemoryBind(context)<>1 Or ZentajiMemoryGraphicsInit($400000)<>1 : ProcedureReturn 1 : EndIf\n', '')
        s = replace_once(s, ' If AnvilVkZentajiWindow(zenMemoryGraphicsBase,zenMemoryGraphicsBytes)<>0 : ProcedureReturn 2 : EndIf\n', '')
        start = s.index(' If phase=0\n  ; Mutate only a closed probe record.')
        end = s.index(' If phase=1 Or phase=6', start)
        s = s[:start]+s[end:]
        start = s.index(' If ZentajiGraphicsDisplayStart(')
        end = s.index(' blendReport[0]', start)
        s = s[:start]+s[end:]
    return s


def blend(src, dst, alpha_one, source_alpha=None):
    a = source_alpha if source_alpha is not None else Fraction((src >> 24) & 255, 255)
    values = []
    for shift in (0, 8, 16, 24):
        sk = (src >> shift) & 255
        dk = (dst >> shift) & 255
        if shift == 24:
            value = 255*a if alpha_one else 255*a*a
            value += dk*(1-a)
        else:
            value = sk*a+dk*(1-a)
        values.append((value.numerator*2+value.denominator)//(value.denominator*2))
    return sum(v << (8*i) for i, v in enumerate(values))


def expected_pixels(alpha, second_pass, alpha_one, source_alpha=None):
    result = []
    for y in range(16):
        for x in range(16):
            pixel = 0x800000FF
            if x+y < 15:
                pixel = blend((alpha << 24) | 0xFF0000, pixel, alpha_one, source_alpha)
                if second_pass and 3 <= x < 8 and 4 <= y < 10:
                    pixel = blend((alpha << 24) | 0x00FF00, pixel, alpha_one, source_alpha)
            result.append(pixel)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zen-tools', type=Path, required=True)
    ap.add_argument('--backend', choices=('native', 'software'), required=True)
    ap.add_argument('--keep', type=Path)
    a = ap.parse_args()
    cc = resolve_compiler(a.compiler)
    zt = a.zen_tools.resolve()
    sys.path.insert(0, str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    software = a.backend == 'software'

    def run(argv):
        p = subprocess.run([str(x) for x in argv], cwd=ROOT,
                           env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=180)
        assert p.returncode == 0, (p.returncode, p.stdout[-6000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-vulkan-blend-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src = td/'probe.zentaji'
        image = td/'probe.zex'
        src.write_text(source(software), encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        print('Compiled public Vulkan %s blend composition' % a.backend, flush=True)
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        executable = image.read_bytes()
        if not software:
            executable, _, _, _ = B.pack(executable, zt/'zasm.exe', source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        print('Verified independent assembly%s' % ('' if software else ' and owned ROM startup'), flush=True)
        alphas = [(0, 0), (0x3E800000, 64), (0x3F000000, 128), (0x3F800000, 255)]
        cases = [(bits, byte, 0, 0) for bits, byte in alphas]
        cases.append((0x3F000000, 128, 6, 0))
        if software:
            cases += [(bits, byte, 0, 1) for bits, byte in alphas]
            cases.append((0x3F000000, 128, 6, 1))
        for index, (bits, byte, phase, legacy) in enumerate(cases):
            m = F.Fixture(ram_size=(128 if software else 32) << 20, cores=2, display_modes=[(16, 16, 60000)])
            m.load_image(executable)
            if software:
                m.cores[0].r[255] = (128 << 20)-65536
            for name, value in [('PHASE', phase), ('BLENDALPHA', bits), ('LEGACYALPHA', legacy)]:
                struct.pack_into('<q', m.ram, ref.sym['GLOBAL_'+name], value)
            assert not F.capture(m, str(td))
            out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '100000000', '--ram', td/'final.bin'])
            (td/('native-%d.txt' % index)).write_text(out, encoding='utf-8')
            final = (td/'final.bin').read_bytes()
            report = struct.unpack_from('<16q', final, ref.sym['GLOBAL_REPORT'])
            br = struct.unpack_from('<8q', final, ref.sym['GLOBAL_BLENDREPORT'])
            end = next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end, (a.backend, index, end, report, br)
            assert report[1:7] == (0,)*6, (a.backend, index, report)
            assert br[:3] == (1 if legacy else 2, 1, 0x181), (a.backend, index, br)
            assert br[3:7] == ((0, 1, -20005, 0) if software else (-8, 0, -20005, 0)), (a.backend, index, br)
            assert report[8] == (1 if software else 2), (a.backend, index, 'expected diagnostic count', report)
            pixels = expected_pixels(byte, phase == 6, not legacy,
                                     {0: Fraction(0), 0x3E800000: Fraction(1, 4), 0x3F000000: Fraction(1, 2), 0x3F800000: Fraction(1)}[bits] if software else None)
            actual = struct.unpack_from('<256I', final, report[0])
            assert actual == tuple(pixels), (a.backend, index, 'RGBA equation', [(i, hex(x), hex(y)) for i, (x, y) in enumerate(zip(actual, pixels)) if x != y][:12])
            if not software:
                headless = run([zt/'zenwin.exe', td/'machine.txt', '--headless', '--max', '100000000'])
                crc = zlib.crc32(b''.join(struct.pack('<I', p & 0xFFFFFF) for p in pixels))
                frames = [line for line in headless.splitlines() if line.startswith('FRAME ')]
                assert any(('%08X' % crc).lower() in line.lower() for line in frames), (index, frames, hex(crc))
            print('PASS %s blend alpha=%d/%s%s: exact RGBA, public pipeline/queue/fence, precise factor admission%s' %
                  (a.backend, byte, 'SRC_ALPHA' if legacy else 'ONE', ', scissored LOAD' if phase else '', ', exact native scanout CRC' if not software else ''), flush=True)


if __name__ == '__main__':
    main()
