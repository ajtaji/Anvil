"""Persist a real boot target, power-cycle, exercise countdown/guard/cancellation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]


def settings(medium):
    part=struct.unpack_from('<I',medium,454)[0];heap=(part+26)*512
    root=medium[heap+1024:heap+1536];index=64
    while index<len(root) and root[index]:
        assert root[index]==0x85
        n=root[index+1];entry=root[index:index+32*(n+1)]
        assert E.checksum(entry,16,(2,3))==struct.unpack_from('<H',entry,2)[0]
        ext=entry[32:64];name=b''.join(entry[k+2:k+32] for k in range(64,len(entry),32))[:ext[3]*2].decode('utf-16le')
        if name=='SETTINGS.TXT':
            cl=struct.unpack_from('<I',ext,20)[0];length=struct.unpack_from('<Q',ext,24)[0];content=bytearray();seen=set()
            while len(content)<length:
                assert 2<=cl<130 and cl not in seen;seen.add(cl)
                content+=medium[heap+(cl-2)*512:heap+(cl-1)*512]
                if ext[1]&2:cl+=1
                else:cl=struct.unpack_from('<I',medium,(part+24)*512+cl*4)[0]
            pairs={}
            for line in bytes(content[:length]).decode('utf-8').splitlines():
                if line and not line.startswith(('#',';')):
                    key,value=line.split('=',1);pairs[key.strip()]=value.strip()
            return pairs
        index+=len(entry)
    raise AssertionError('real SETTINGS.TXT was not found')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keyboard-cancel',action='store_true');a=ap.parse_args();cc=resolve_compiler(a.compiler);sys.path.insert(0,str(a.zen_tools.resolve()))
    import zentaji_native as I
    import zen_native_fixture as L
    import zexpack
    image=(ROOT/'build/zentaji/anvil.zex').read_bytes();meta=json.loads((ROOT/'build/zentaji/anvil.zex.boot.json').read_text())
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-auto-boot-') as tmp:
        td=Path(tmp);src=td/'app.zentaji';app=td/'app.zex'
        src.write_text('Procedure.q Main()\nPokeQ($600000,PeekQ($600000)+1)\nProcedureReturn 42\nEndProcedure\n')
        run([cc,'--compile',src,'--load-addr','0x280008','--stack-addr','0x2F0000','--entry-returns','-o',app])
        pmf=Path(str(app)+'.pmf').read_bytes();assert pmf[128:]==app.read_bytes()[64:] and pmf[64:96]==hashlib.sha256(pmf[128:]).digest()
        medium=E.build(4096);E.seed_file(medium,pmf,'APP.PMF');boot=zexpack.disk_image(image);assert len(boot)<=4096*512
        medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
        phases=[('provision',['time set 1794009600','setenv boot.file APP.PMF','setenv boot.delay 1','setenv boot.maxfails 1','saveenv','halt'],0,False),('automatic-return',['boot status','halt'],1,False),('guard-and-acknowledge',['boot status','boot ok','halt'],0,False),('cancel-countdown',['boot status','halt'],0,True)]
        for name,commands,expected,cancel in phases:
            m=I.Fixture(ram_size=8<<20,cores=2,disks={15:(bytearray(medium),False)},display_modes=[(1,1,60000)]);m.power_on(1,15)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '))
            schedule=[];key_schedule=[];sent=0;cancelled=False
            def operator(observed):
                core=observed.cores[0]
                nonlocal sent,cancelled
                output=bytes(observed.serial[0].out)
                announcing=b'Press any key now to stop it' in output and b'pmf> ' not in output
                tick=max(observed.time,core.cr[I.CR['CYCLE']])+100
                if cancel and announcing and not cancelled:
                    if a.keyboard_cancel:
                        for fields in ((27,1,0,0,120),(27,0,0,0,0)):
                            m.input_feed(tick,'key',*fields);key_schedule.append((tick,fields))
                    else:
                        line=[(tick,120)];schedule.extend(line);m.serial[0].incoming.extend(line)
                    cancelled=True
                if sent<len(commands) and output.count(b'pmf> ')>sent:
                    line=[(tick,b) for b in (commands[sent]+'\r').encode()];schedule.extend(line);m.serial[0].incoming.extend(line);sent+=1
            m=runner.operate(m,operator,30000000,td);c=m.cores[0]
            cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8');output=bytes(m.serial[0].out)
            assert c.state=='HALTED' and c.exit==0 and sent==len(commands),(name,c.state,c.exit,output[-3500:])
            assert struct.unpack_from('<Q',m.ram,0x600000)[0]==expected,name
            if name=='automatic-return':assert c.perf['wait_cycles']>=90000000 and b'attempt 1 of 1 recorded on the medium' in output and b'The payload returned, r1 = $000000000000002A' in output,(c.perf['wait_cycles'],output[-3500:])
            if name=='guard-and-acknowledge':assert b'reboot-loop' in output and b'boot.fails is now 0' in output
            if cancel:assert cancelled and b'Stopped by a keypress.' in output and b'counter was NOT touched' in output
            out=run([L.EXE,cfg,'--max','30000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram
            I.assert_same_state(out,m)
            assert m.cores[1].state=='PARKED' and (td/'disk15.img').read_bytes()==bytes(m.disks[15].image)
            medium=bytearray(m.disks[15].image);pairs=settings(medium)
            assert pairs['boot.file']=='APP.PMF' and pairs['boot.delay']=='1' and pairs['boot.maxfails']=='1'
            assert pairs.get('boot.fails','0')==('1' if name=='automatic-return' else '0'),(name,pairs)
            print('PASS %s: real persisted settings/power-on ROM/boot policy, app calls=%d, actual WFI wait ticks=%d; independent on-disk counter and exact native state/RAM/host medium'%(name,expected,c.perf['wait_cycles'])+('; native keyboard cancellation' if cancel and a.keyboard_cancel else ''),flush=True)


if __name__=='__main__':main()
