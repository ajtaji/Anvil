#!/usr/bin/env python3
"""Build the portable sfnt checksum correctness proof; never run or emulate it."""
from pathlib import Path
import sys,struct,re,json,hashlib,subprocess,os,random,argparse
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();r=Path(__file__).resolve().parents[1]
target=a.target;layout=state_proof_layout(target);d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
source=(r/'RaspberryPi4/Monitor/anvil_boot_ttf.pi4').read_text(encoding='utf-8-sig')
font=bytearray()
for row in re.findall(r'(?mi)^\s*Data\.[ab]\s+(.+)$',source):
 for n in row.split(','):
  n=n.strip();font.append(int(n[1:],16) if n.startswith('$') else int(n))
assert len(font)==705684
assert hashlib.sha256(font).hexdigest()=='e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724'
def checksum(data,head):
 data=bytearray(data)
 if head:data[8:min(12,len(data))]=bytes(max(0,min(12,len(data))-8))
 data+=bytes((-len(data))%4)
 return sum(struct.unpack('>'+str(len(data)//4)+'I',data))&0xffffffff
randomizer=random.Random(20261027);payload=bytes(randomizer.randrange(256) for _ in range(72))
cases=[]
for offset in range(4):
 for length in range(65):
  for head in (0,1):cases.append((offset,length,head,checksum(payload[offset:offset+length],head)))
real=[]
for i in range(struct.unpack_from('>H',font,4)[0]):
 tag,expected,offset,length=struct.unpack_from('>4sIII',font,12+i*16)
 assert checksum(font[offset:offset+length],tag==b'head')==expected
 real.append((offset,length,int(tag==b'head'),expected))
s='XIncludeFile "Anvil/Graphics/truetype.pbi"\n'
# The input is font data only. Embed the hash-verified bytes directly rather
# than including a Pi4-owned monitor file into another target's composition.
s+=source+'\n'
s+='Global checksumChecks.i,checksumFailure.i\nProcedure Ck(offset.i,length.i,head.i,expected.i)\n checksumChecks=checksumChecks+1\n If anvil_tt_TableChecksum(offset,length,head)<>expected And checksumFailure=0 : checksumFailure=checksumChecks : EndIf\nEndProcedure\n'
s+='Procedure.i Main(services.i)\n *anvil_tt_data=?testBytes\n'
for case in cases:s+=' Ck('+','.join(str(v) for v in case)+')\n'
s+=' *anvil_tt_data=?anvilBootTtf\n'
for case in real:s+=' Ck('+','.join(str(v) for v in case)+')\n'
s+=f' PokeI(${layout["report"]:X},$43484B53) : PokeI(${layout["report"]+8:X},checksumChecks) : PokeI(${layout["report"]+16:X},checksumFailure)\n ProcedureReturn checksumFailure\nEndProcedure\nDataSection\ntestBytes:\n'
s+=' Data.a '+','.join('$%02X'%v for v in payload)+'\nEndDataSection\n'
(d/'proof.pbi').write_text(s,encoding='utf8')
env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],capture_output=True,text=True,encoding='utf8',env=env,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1300:]);assert q.returncode==0
p=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(target=target,checks=len(cases)+len(real),synthetic_cases=len(cases),real_tables=len(real),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=check_linked_layout(layout,q.stdout+q.stderr),source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in ['Anvil/Graphics/truetype.pbi','RaspberryPi4/Monitor/anvil_boot_ttf.pi4']},executed=False),indent=2),encoding='utf8')
