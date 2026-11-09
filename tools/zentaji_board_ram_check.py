"""Exercise the published board at its exact RAM floor and one alignment below."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',type=Path,required=True);a=ap.parse_args();sys.path.insert(0,str(a.zen_tools.resolve()))
    import zentaji_native as I
    import zen_native_fixture as L
    image=(ROOT/'build/zentaji/anvil.zex').read_bytes();meta=json.loads((ROOT/'build/zentaji/anvil.zex.boot.json').read_text())
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']
    floor=meta['minimum_ram_bytes'];assert floor>meta['startup_minimum_ram_bytes'] and floor%16==0
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-board-ram-') as tmp:
        td=Path(tmp)
        for ram,expected in ((floor,0),(floor-16,0x5B04)):
            m=I.Fixture(ram_size=ram,cores=2,hostfiles=[['anvil.zex',bytearray(image),True]],display_modes=[(1,1,60000)]);m.power_on(0,0)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';schedule=[];commands=['map','halt']
            def operator(observed):
                core=observed.cores[0]
                if len(schedule)>=len(commands) or bytes(observed.serial[0].out).count(b'pmf> ')<=len(schedule):return
                tick=max(observed.time,core.cr[I.CR['CYCLE']])+100;line=[(tick,b) for b in (commands[len(schedule)]+'\r').encode()];schedule.append(line);m.serial[0].incoming.extend(line)
            m=runner.operate(m,operator,3000000,td);c=m.cores[0];output=bytes(m.serial[0].out)
            assert c.state=='HALTED' and c.exit==expected,(ram,c.state,c.exit,output[-1800:])
            if expected==0:
                bottom=struct.unpack_from('<Q',m.ram,meta['context']+56)[0]
                assert bottom-((meta['image_end']+4095)&-4096)==4096
                assert len(schedule)==2 and b'THE MEMORY MAP' in output and b'Anvil stopped.' in output
            else:assert not schedule and b'Startup memory layout failed (0x5B04)' in output and b'pmf> ' not in output
            p=subprocess.run([str(L.EXE),str(cfg),'--max','3000000','--ram',str(td/'final.bin')],capture_output=True,text=True,timeout=120)
            assert p.returncode==0,(p.returncode,p.stdout[-1500:],p.stderr)
            assert (td/'final.bin').read_bytes()==m.ram
            I.assert_same_state(p.stdout,m)
            assert m.cores[1].state=='PARKED' and m.hostfiles[0][1]==image==(td/'hostfile0.bin').read_bytes()
            print('PASS published board RAM=%d exit=%X: exact floor admits one4KB payload window; below-floor fail-stop, full native state/RAM and unchanged ROM host file'%(ram,expected),flush=True)


if __name__=='__main__':main()
