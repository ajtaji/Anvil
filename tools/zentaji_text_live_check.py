"""Measure real native text PRESENT idle CPU; replay its recorded hardware clock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
from zentaji_text_service_check import SOURCE

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zen_sleep_check as S
    import zasm_ref as A
    import zexpack
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    needle=' WaitFrame()\n Check(TextServiceLeave(),0)'
    assert SOURCE.count(needle)==1
    source=SOURCE.replace(needle,' For n=1 To 180\n  Check(TextServiceCall(#NTX_PRESENT,handle,0,0),0)\n Next\n Check(TextServiceLeave(),0)')
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-text-live-') as tmp:
        td=Path(tmp);src=td/'text.zentaji';out=td/'text.zex';src.write_text(source,encoding='utf-8')
        run([cc,'--compile',src,'-o',out])
        ref=A.Asm();org,body=ref.assemble(Path(str(out)+'.asm').read_text(encoding='utf-8-sig'))
        assert out.read_bytes()==zexpack.header(org,org,body)+body
        image,_,_,_=B.pack(out.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(out)+'.zmap').read_text(encoding='utf-8-sig')))
        m=I.Fixture(ram_size=8<<20,cores=2,display_modes=[(320,160,60000),(640,480,60000)]);m.load_image(image)
        assert not L.capture(m,str(td));record=td/'recorded.txt'
        live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(record),'--max','4000000'],timeout=15)
        native=run([L.EXE,record,'--max','4000000','--ram',td/'final.bin'])
        states=lambda s:[row for row in s.splitlines() if row.startswith('STATE ')]
        assert states(live)==states(native) and ' exit=2A ' in native,native[-1500:]
        m=runner.execute_config(record,4000000,td)
        assert m.cores[0].state=='HALTED' and m.cores[0].exit==42 and m.cores[1].state=='PARKED'
        assert int.from_bytes(m.ram[0x600000:0x600008],'little')==0
        assert int.from_bytes(m.ram[0x600008:0x600010],'little')>=190
        assert (td/'final.bin').read_bytes()==m.ram
        I.assert_same_state(native,m)
        assert m.fields['display'][0]>=180 and m.fields['textmeta'][1]==0 and m.fields['textmeta'][2]==0x101
        assert wall>=2.9 and cpu<1.2,(wall,cpu)
        print('PASS live native text PRESENT180: wall=%.6fs CPU=%.6fs (<1.2s), actual provider/owned timer/WFI, 60Hz hardware display and exact recorded native CPU/RAM; no host callback or sleep stub'%(wall,cpu),flush=True)


if __name__=='__main__':main()
