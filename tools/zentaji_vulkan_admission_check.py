"""Zentaji execution of the real shared Vulkan layouts/API; no GPU claim."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]
API=r'''EnableFloatingPoint
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_none.pbi"
Global instance.i
Procedure.q Main()
 Protected info.VkInstanceCreateInfo
 info\sType=#VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
 If vkCreateInstance(@info,0,@instance)<>#VK_ERROR_INCOMPATIBLE_DRIVER : ProcedureReturn 1 : EndIf
 If instance<>0 Or avkBackendCaps()<>0 : ProcedureReturn 2 : EndIf
 ProcedureReturn 0
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case',choices=('layout','api'));a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-6000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-vulkan-admission-') as tmp:
        td=Path(tmp)
        for name,source in [('layout',(ROOT/'Anvil/Graphics/Vulkan/Tests/vulkan_alignc_abi.pbi').read_text(encoding='utf-8')),('api',API)]:
            if a.case and a.case!=name:continue
            src=td/'probe.zentaji';out=td/'probe.zex';src.write_bytes(source.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
            run([cc,'--compile',src,'--stack-addr','0x1F00000','-o',out])
            assert out.is_file(),name
            ref=A.Asm();origin,data=ref.assemble(Path(str(out)+'.asm').read_text(encoding='utf-8-sig'))
            assert out.read_bytes()==zexpack.header(origin,origin,data,stack=0x1F00000)+data
            m=I.Machine(ram_size=32<<20,cores=2);m.load_image(out.read_bytes())
            assert not L.capture(m,str(td));m.run(2000000);c=m.cores[0]
            assert c.state=='HALTED' and c.exit==0,(name,c.state,c.exit)
            native=run([L.EXE,td/'machine.txt','--max','2000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram,name
            # Each final state record contains every core, plus device/RAM digests.
            states=[line[6:] for line in native.splitlines() if line.startswith('STATE ')]
            assert len(states)==1,name
            assert states[0].split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],name
            assert m.cores[1].state=='PARKED'
            print('PASS shared Vulkan '+name+' on Zentaji: actual compiled source, independent assembly, full native/twin CPU/RAM; '+('12 layout constants' if name=='layout' else 'no backend honestly refuses instance creation; no graphics output claimed'),flush=True)


if __name__=='__main__':main()
