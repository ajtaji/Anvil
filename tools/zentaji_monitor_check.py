"""Boot the published, counted Zentaji board artifact; no replacement guest code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import build_count
import zentaji_boot_image as B
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    artifact=ROOT/'build/zentaji/anvil.zex';image=artifact.read_bytes()
    meta=json.loads(Path(str(artifact)+'.boot.json').read_text());mapping=json.loads(Path(str(artifact)+'.zmap').read_text())
    digest=hashlib.sha256(image).hexdigest();assert digest==meta['image_sha256']==mapping['image']
    for row in mapping['sources']:
        path=Path(row['path']);path=path if path.is_absolute() else ROOT/path
        path=path.resolve();assert path.is_relative_to(ROOT),('source outside checkout',path)
        assert hashlib.sha256(path.read_bytes().replace(b'\r',b'')).hexdigest()==row['sha256'],('stale artifact source',path)
    compiled=Path(str(artifact)+'.compiled.zex').read_bytes();assert hashlib.sha256(compiled).hexdigest()==meta['compiled_sha256']
    ref=A.Asm();origin,data=ref.assemble(Path(str(artifact)+'.compiled.asm').read_text(encoding='utf-8-sig'))
    assert compiled==zexpack.header(origin,origin,data)+data
    wrapper=A.Asm();org,wrapped=wrapper.assemble(Path(str(artifact)+'.asm').read_text())
    assert org==meta['load'] and image[64:]==wrapped
    assert meta['context_version']==2 and meta['payload_call']==wrapper.sym['ANVIL_ZEN_PAYLOAD_CALL']
    version=build_count.current('zentaji');stage=(meta['image_end']+4095)&-4096
    expected=bytes((n*7+n//512+31)&255 for n in range(1800))
    def run(args):
        p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-production-zen-') as tmp:
        td=Path(tmp)
        for diskboot,native_text,keyboard in ((True,False,False),(False,False,False),(False,True,False),(False,True,True)):
            if diskboot:
                medium=E.build(4096);E.seed_file(medium,expected)
                boot=zexpack.disk_image(image);assert len(boot)<=4096*512
                medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
                disks={15:(bytearray(medium),False)};files=[]
                commands=['version full','map','time set 1794009600','sleep 1','load SEED.BIN','mkdir Folder','save "Folder/Long file name.bin" %X 708'%stage,'rm SEED.BIN','ls Folder','halt']
            else:
                medium=None;disks={};files=[['anvil.zex',bytearray(image),False]]
                commands=['version full','map','halt']
                if keyboard:commands=['version full','map','echo ac','sleep 2','halt']
            modes=[(320,160,60000),(640,480,60000)] if native_text else [(1,1,60000)]
            m=I.Machine(ram_size=8<<20,cores=2,disks=disks,hostfiles=files,display_modes=modes);m.power_on(int(diskboot),15 if diskboot else 0)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
            scheduled=[];starts=[];frames=[];keys=[];cancelled=False;advance=m.display.advance
            def observe(t):
                advance(t);frames.append('FRAME %d %08X'%(m.display.vsyncs,m.display.crc()))
            m.display.advance=observe
            def operator(core):
                nonlocal cancelled
                tick=max(m.time,core.cr[I.CR['CYCLE']])+100
                if keyboard and not cancelled and b'Press any key to end the wait early.' in bytes(m.serial[0].out):
                    for fields in ((27,1,0,0,120),(27,0,0,0,0)):
                        m.input_feed(tick,'key',*fields);keys.append((tick,fields))
                    cancelled=True
                if len(scheduled)>=len(commands) or bytes(m.serial[0].out).count(b'pmf> ')<=len(scheduled):return
                if native_text:
                    assert m.text.layer==1 and m.display.ctrl==1 and m.text.err==0
                    assert m.text.cells==(8<<20)-(1<<20)-65536-12288
                    cells=bytes(m.ram[m.text.cells:m.text.cells+m.text.cols*m.text.rows*4])
                    text=''.join(chr(int.from_bytes(cells[n:n+2],'little')) for n in range(0,len(cells),4))
                    assert 'pmf> ' in text,repr(text)
                starts.append(tick)
                if keyboard:
                    events=[]
                    def press(usage,char=0):events.extend(((usage,1,0,0,char),(usage,0,0,0,0)))
                    for char in commands[len(scheduled)]:
                        usage=44 if char==' ' else (30+int(char)-1 if char.isdigit() else ord(char)-93)
                        press(usage,ord(char))
                    if len(scheduled)==2:
                        press(80);press(5,98);press(77);press(42)
                    press(40)
                    for fields in events:m.input_feed(tick,'key',*fields);keys.append((tick,fields))
                    scheduled.append([])
                    return
                line=[(tick,b) for b in (commands[len(scheduled)]+'\r').encode()]
                scheduled.append(line);m.serial[0].incoming.extend(line)
            m.on_slice=operator;m.run(30000000);m.on_slice=None;c=m.cores[0]
            assert len(scheduled)==len(commands) and c.state=='HALTED' and c.r[1]==0,(diskboot,c.state,c.r[1],bytes(m.serial[0].out)[-3500:])
            with cfg.open('a',encoding='utf-8') as stream:
                for line in scheduled:
                    for tick,byte in line:stream.write('serial 0 $%X %02X\n'%(tick,byte))
                for tick,fields in keys:stream.write('key $%X %s\n'%(tick,' '.join(str(x) for x in fields)))
            out=run([L.EXE,cfg,'--max','30000000','--ram',td/'final.bin']);assert ' exit=0 ' in out,out[-1800:]
            assert (td/'final.bin').read_bytes()==m.ram
            if native_text:
                assert frames and m.text.layer==0 and m.display.ctrl==0
                shown=run([zt/'zenwin.exe',cfg,'--headless','--max','30000000'])
                assert [line for line in shown.splitlines() if line.startswith('FRAME ')]==frames
            state=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            output=bytes(m.serial[0].out)
            if keyboard:
                assert cancelled and b'\r\nab\r\n' in output and b'because a key was pressed.' in output,output[-2200:]
                assert b'? this monitor' not in output and m.input.queue==[] and not m.serial[0].incoming
            for phrase in (('build %d date '%version).encode(),b'64-bit Zentaji',b'Zentaji supervisor mode',b'No image CRC is claimed',b'THE MEMORY MAP',b'Anvil stopped.'):
                assert phrase in output,(phrase,output[-2500:])
            assert b'AArch64' not in output and b'exception level' not in output and b'Its crc32 is' not in output
            assert c.cr[I.CR['EVEC']]==meta['vectors'] and m.cores[1].state=='PARKED'
            for row in mapping['code']:
                pc=int(row['pc'],16);size=row['size'];assert m.ram[pc:pc+size]==image[64+pc-org:64+pc-org+size],'monitor instruction changed'
            if diskboot:
                assert m.ram[stage:stage+1800]==expected and b'Done - waited 1 seconds' in output
                assert (td/'disk15.img').read_bytes()==bytes(m.disks[15].image)
                lo=1794009600+max(0,(starts[6]-starts[3])//100000000)
                hi=1794009600+max(0,(starts[7]-starts[2]+99999999)//100000000)
                proof=E.check(bytes(m.disks[15].image),medium,expected,lo,hi)
                print('PASS published build%d ROM disk15: real loop/version/layout/time/sleep/load/save/list/delete/halt; full native/twin state/RAM/host image, immutable instruction bytes; '%version+proof,flush=True)
            else:
                assert b'no configured version-1 block device' in output
                assert bytes(m.hostfile.files[0][1])==image==(td/'hf0.bin').read_bytes()
                print('PASS published build%d ROM hostfile: no disk, honest storage refusal, usable loop/version/map/halt, full native/twin state/RAM and unchanged boot file'%version+('; protected native text prompt and exact headless frames' if native_text else '')+('; native keyboard-only commands, caret editing and sleep cancellation' if keyboard else ''),flush=True)


if __name__=='__main__':main()
