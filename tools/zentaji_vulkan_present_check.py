"""Owned startup -> protected Vulkan image -> native GPU -> real display latch."""
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
SOURCE=(r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Zentaji/Board/graphics_display.pbi"
''' + LIFECYCLE.replace('Procedure.i Main(', 'Procedure.i VulkanMain(')
 .replace('allocation\\allocationSize=requirements\\size', 'allocation\\allocationSize=((requirements\\size+4095)&-4096)*3')
 .replace(' vkDeviceWaitIdle(device)', r''' If InPayload(arena,arena+$400000-1)<>0 : ProcedureReturn 17 : EndIf
 If ZentajiGraphicsDisplayStart(AnvilVkImageAddress(image))<>1 : ProcedureReturn 18 : EndIf
 If ZentajiGraphicsDisplayPresent(@avkZenQueue,0)<>1 : ProcedureReturn 19 : EndIf
 If ZentajiGraphicsDisplayWait(250000)<>1 : ProcedureReturn 20 : EndIf
 report[21]=zgdSequence : report[22]=ZentajiGraphicsDisplayOwned()
 report[23]=ZentajiGraphicsDisplayRelease()
 If report[21]<>1 Or report[22]<>1 Or report[23]<>1 : ProcedureReturn 21 : EndIf
 vkDeviceWaitIdle(device)''') + r'''
Procedure.i Main(table.i,source.i,context.i)
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 30 : EndIf
 If ZentajiMemoryGraphicsInit($400000)<>1 : ProcedureReturn 31 : EndIf
 ProcedureReturn VulkanMain(1,zenMemoryGraphicsBase)
EndProcedure
''')

assert SOURCE.count("allocationSize=((requirements") == 1
assert SOURCE.count("ZentajiGraphicsDisplayStart(AnvilVkImageAddress(image))") == 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    def run(argv):
        p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-vulkan-present-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',image])
        print('Compiled protected Vulkan presentation composition',flush=True)
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        print('Verified independent assembly and image bytes',flush=True)
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        m=F.Fixture(ram_size=32<<20,cores=2,display_modes=[(33,17,60000)]);m.load_image(wrapped)
        assert not F.capture(m,str(td))
        out=run([zt/'zenemu.exe',td/'machine.txt','--max','20000000','--ram',td/'final.bin'])
        end=next(x for x in out.splitlines() if x.startswith('END '))
        final=(td/'final.bin').read_bytes();report=struct.unpack_from('<32q',final,ref.sym['GLOBAL_REPORT'])
        assert ' exit=2A ' in end,(end,report)
        arena=(((32<<20)-(1<<20)-meta['stack_bytes'])&-4096)-0x400000
        assert report[:5]==(0,-20001,0x1C001EF,arena+4096,0x3ff000),report
        assert report[8:12]==(arena+4096,33*17*4,4096,33*4),report
        assert report[12:20]==(1,0,0,0,0,0,0,0) and report[21:24]==(1,1,1),report
        assert final[arena+4096:arena+4096+33*17*4]==struct.pack('<I',0x803380B2)*(33*17)
        headless=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','20000000'])
        frames=[line for line in headless.splitlines() if line.startswith('FRAME ')]
        crc=zlib.crc32(struct.pack('<I',0x003380B2)*(33*17))
        assert any(('%08X'%crc).lower() in line.lower() for line in frames),(frames,hex(crc))
        print('PASS protected public Vulkan presentation: owned startup, immutable payload exclusion, real image/allocation/clear/fence, native scanout latch and independently expected headless frame CRC')


if __name__=='__main__':main()
