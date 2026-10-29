from pathlib import Path
import subprocess,sys,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build the returning attribute record packing proof')
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
s=(r/'RaspberryPi4/Tests/Vulkan/v3d_attribute_words.pi4').read_bytes();(d/'proof.pi4').write_bytes(s)
pending=[s.decode()];inputs={}
while pending:
 for n in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',pending.pop(0)):
  if n in inputs:continue
  assert len(inputs)<64
  b=(r/n).read_bytes();inputs[n]=hashlib.sha256(b).hexdigest();pending.append(b.decode('utf-8-sig'))
c=Path(resolve_compiler(a.compiler))
q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-2500:],flush=True);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
items=[(n,*(int(x,16) for x in p)) for n,p in ranges.items()]
for i,(n,a,b) in enumerate(items):
 assert a<=b
 for m,c1,c2 in items[i+1:]:assert b<c1 or c2<a,(n,m)
p=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_hashes=inputs,checked_ranges=ranges,source_sha256=hashlib.sha256(s).hexdigest()),indent=2))
