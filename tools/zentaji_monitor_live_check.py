"""Measure the published monitor's real sleep command and replay its live run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--native-text',action='store_true');a=ap.parse_args();zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zen_sleep_check as S
    artifact=ROOT/'build/zentaji/anvil.zex';image=artifact.read_bytes();meta=json.loads(Path(str(artifact)+'.boot.json').read_text())
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']
    def run(args):
        p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    def states(out):return [s for s in out.splitlines() if s.startswith('STATE ')]
    results=[]
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-monitor-live-') as tmp:
        td=Path(tmp)
        for seconds in (0,2):
            modes=[(640,480,60000),(1280,720,60000),(1920,1080,60000)] if a.native_text else [(1,1,60000)]
            m=I.Fixture(ram_size=8<<20,cores=2,hostfiles=[['anvil.zex',bytearray(image),False]],display_modes=modes);m.power_on(0,0)
            m.serial[0].incoming=[(300000000,b) for b in ('sleep %d\r'%seconds).encode()]+[(600000000,b) for b in b'halt\r']
            assert not L.capture(m,str(td));rec=td/('recorded%d.txt'%seconds)
            live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','12000000'],timeout=30)
            out=run([L.EXE,rec,'--max','12000000','--ram',td/'final.bin']);assert ' exit=0 ' in out,out[-1600:]
            assert states(live)==states(out)
            m=runner.execute_config(rec,12000000,td);c=m.cores[0]
            assert c.state=='HALTED' and c.r[1]==0 and m.cores[1].state=='PARKED'
            if a.native_text:
                assert m.fields['text'][2]==(8<<20)-(1<<20)-65536-65536 and m.fields['textmeta'][1]==0
                assert m.fields['display'][0]>=300 and m.fields['textmeta'][0]==0 and m.fields['textmeta'][3]==0
            assert (td/'final.bin').read_bytes()==m.ram;I.assert_same_state(out,m)
            output=bytes(m.serial[0].out)
            phrase=b'Done - waited 2 seconds.' if seconds else b'Slept for zero seconds'
            assert phrase in output and b'Anvil stopped.' in output,output[-2000:]
            assert m.hostfiles[0][1]==image==(td/'hostfile0.bin').read_bytes()
            assert wall>=5.8 and cpu<1.2,(seconds,wall,cpu)
            results.append((wall,cpu));print('PASS published monitor sleep%d: wall=%.6fs CPU=%.6fs, real ROM/startup/commands/timer/WFI, exact recorded native state/RAM and unchanged boot image'%(seconds,wall,cpu),flush=True)
    extra=max(0,results[1][1]-results[0][1]);assert extra<0.4,results
    print('PASS sleep2 adds %.6f CPU seconds against the same six-second prompt/boot baseline (<0.4s ceiling); no busy polling'%extra,flush=True)


if __name__=='__main__':main()
