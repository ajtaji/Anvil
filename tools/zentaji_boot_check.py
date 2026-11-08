"""Boot actual compiler PMFs through the published Anvil command/file loader."""
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


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--case');ap.add_argument('--only',choices=['valid','all'],default='all')
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    artifact=ROOT/'build/zentaji/anvil.zex';image=artifact.read_bytes();meta=json.loads(Path(str(artifact)+'.boot.json').read_text());mapping=json.loads(Path(str(artifact)+'.zmap').read_text())
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']==mapping['image']
    for row in mapping['sources']:
        p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
        assert p.resolve().is_relative_to(ROOT) and hashlib.sha256(p.read_bytes().replace(b'\r',b'')).hexdigest()==row['sha256'],('stale source',p)
    stage=(meta['image_end']+4095)&-4096;load=0x280008;marker=0x600000
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-pmf-boot-') as tmp:
        td=Path(tmp);src=td/'app.zentaji';app=td/'app.zex'
        def compile(damage=''):
            src.write_text('Procedure.q Main(argument.q)\nIf argument<>0 : ProcedureReturn $BAD : EndIf\nPokeQ($600000,PeekQ($600000)+1)\n'+damage+'\nProcedureReturn $1122334455667788\nEndProcedure\n')
            run([cc,'--compile',src,'--load-addr',hex(load),'--stack-addr','0x2F0000','--entry-returns','-o',app])
            raw=app.read_bytes();ref=A.Asm();org,body=ref.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'))
            assert raw==zexpack.header(org,org,body,stack=0x2F0000)+body and org==load
            pmf=Path(str(app)+'.pmf').read_bytes();assert pmf[128:]==body and pmf[64:96]==hashlib.sha256(body).digest()
            assert struct.unpack_from('<IIQ',pmf,96)==(2,1,0x2F0000)
            return pmf
        valid=compile();timer_bad=compile('PokeQ($FFFF00000005F000,1)');disk_bad=compile('PokeQ($FFFF0000002F0010,3)')
        def altered(offset,value,fmt='<I'):
            pmf=bytearray(valid);struct.pack_into(fmt,pmf,offset,value);return bytes(pmf)
        cases=[('file-repeat',valid,['boot APP.PMF','boot APP.PMF','ls','halt'],2,0,None),('memory',valid,['load APP.PMF','boot mem %X'%stage,'halt'],1,0,None)]
        if a.only=='all':
            cases += [('conflicting-arguments',altered(56,6),['boot APP.PMF','halt'],0,0,b'Only one is possible'),('services',altered(56,5),['boot APP.PMF','halt'],0,0,b'no payload service-table provider'),('foreign-isa',altered(96,1),['boot APP.PMF','halt'],0,0,b'architecture ID'),('foreign-target',altered(100,99),['boot APP.PMF','halt'],0,0,b'target ID'),('stack-outside',altered(104,0x900000,'<Q'),['boot APP.PMF','halt'],0,0,b'not in a payload stack window'),('entry-alignment',altered(24,load+1,'<Q'),['boot APP.PMF','halt'],0,0,b'not aligned for this CPU'),('monitor-overlap',altered(16,0x1000,'<Q'),['boot APP.PMF','halt'],0,0,b'monitor'),('truncated',valid[:-1],['boot APP.PMF','halt'],0,0,b'file on the'),('digest-mismatch',valid[:-1]+bytes([valid[-1]^1]),['boot APP.PMF','halt'],0,0,b'SHA-256'),('timer-return',timer_bad,['boot APP.PMF'],1,0x5B02,None),('foreign-disk-return',disk_bad,['boot APP.PMF'],1,0x5B03,None)]
            v1=bytearray(valid[:96]);struct.pack_into('<II',v1,8,1,96)
            cases.append(('legacy-v1',bytes(v1)+valid[128:],['boot APP.PMF','halt'],0,0,b'version-1 payloads'))
            tiny=bytearray(valid[:128]);struct.pack_into('<Q',tiny,32,1);tiny[64:96]=hashlib.sha256(valid[128:129]).digest()
            cases.append(('partial-instruction',bytes(tiny)+valid[128:129],['boot APP.PMF','halt'],0,0,b'complete instruction'))
            cases += [('memory-short-header',valid,['boot mem 7FFFA0','halt'],0,0,b'beyond the RAM fitted'),('memory-short-body',valid,['boot mem 7FFF00','halt'],0,0,b'beyond the RAM fitted')]
        for name,pmf,commands,want_calls,exit_code,phrase in cases:
            if a.case and a.case not in name:continue
            medium=E.build(4096);E.seed_file(medium,pmf,'APP.PMF');boot=zexpack.disk_image(image);assert len(boot)<=4096*512
            medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
            m=I.Machine(ram_size=8<<20,cores=2,disks={15:(bytearray(medium),False)},display_modes=[(1,1,60000)]);m.power_on(1,15)
            m.ram[load:load+len(valid)-128]=b'\xA5'*(len(valid)-128)
            if name=='memory-short-header':m.ram[(8<<20)-96:]=valid[:96]
            if name=='memory-short-body':m.ram[(8<<20)-256:(8<<20)-128]=valid[:128]
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '))
            scheduled=[]
            def operator(core):
                if len(scheduled)>=len(commands) or bytes(m.serial[0].out).count(b'pmf> ')<=len(scheduled):return
                tick=max(m.time,core.cr[I.CR['CYCLE']])+100
                line=[(tick,b) for b in (commands[len(scheduled)]+'\r').encode()];scheduled.append(line);m.serial[0].incoming.extend(line)
            m.on_slice=operator;m.run(30000000);m.on_slice=None;c=m.cores[0]
            assert c.state=='HALTED' and c.exit==exit_code,(name,c.state,c.exit,bytes(m.serial[0].out)[-3000:])
            assert struct.unpack_from('<Q',m.ram,marker)[0]==want_calls,name
            output=bytes(m.serial[0].out)
            assert b' x0' not in output and b'AArch64' not in output, name
            if exit_code==0:assert len(scheduled)==len(commands) and b'Anvil stopped.' in output,(name,output[-2000:])
            else:
                assert output.count(b'pmf> ')==1 and b'The payload returned' not in output,name
                assert ('Payload return failed (0x%X)'%exit_code).encode() in output,(name,output[-1600:])
            if phrase is not None:assert phrase in output,(name,phrase,output[-2000:])
            if want_calls and not exit_code:assert output.count(b'The payload returned, r1 = $1122334455667788')==want_calls,(name,output[-2000:])
            if name not in ('digest-mismatch','memory') and not want_calls:
                assert m.ram[load:load+len(valid)-128]==b'\xA5'*(len(valid)-128),('refusal wrote payload RAM',name)
            with cfg.open('a') as stream:
                for line in scheduled:
                    for tick,byte in line:stream.write('serial 0 $%X %02X\n'%(tick,byte))
            out=run([L.EXE,cfg,'--max','30000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram,name
            state=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],name
            assert m.cores[1].state=='PARKED' and (td/'disk15.img').read_bytes()==bytes(m.disks[15].image),name
            assert bytes(m.disks[15].image)==bytes(medium),('read-only boot changed medium bytes',name)
            for row in mapping['code']:
                pc=int(row['pc'],16);n=row['size'];assert m.ram[pc:pc+n]==image[64+pc-meta['load']:64+pc-meta['load']+n],('monitor instruction changed',name,pc)
            print('PASS published Anvil PMF %s: real ROM disk15/command/file/hash/CPU path; calls=%d exit=%X, exact native/twin state/RAM/persisted medium and immutable monitor instructions'%(name,want_calls,exit_code),flush=True)


if __name__=='__main__':main()
