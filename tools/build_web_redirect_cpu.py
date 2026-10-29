"""Physical known-length and chunked upload proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile streaming HTTP upload qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_redirect.pbi']
s='\n'.join(x for n in names for x in (r/n).read_text(encoding='utf8').splitlines() if not x.startswith('XIncludeFile'))+r'''
Global base.WebUrl,dest.WebUrl
Global Dim bh.a[256]
Global Dim bt.a[3072]
Global Dim dh.a[256]
Global Dim dt.a[3072]
Global Dim scratch.a[4097]
Procedure Record(index.i,reference.i,bytes.i)
 Define rc.i,i.i,p.i
 rc=WebUrlResolve(@base,reference,bytes,@dest,@scratch[0],4097)
 p=$E1C00100+index*256
 For i=0 To 255 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,dest\secure) : PokeI(p+16,dest\port)
 If rc=0
  For i=0 To dest\hostLength-1 : PokeA(p+32+i,dh[i]) : Next
  For i=0 To dest\targetLength-1 : PokeA(p+96+i,dt[i]) : Next
 EndIf
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57524431)
 base\host=@bh[0] : base\hostCapacity=256 : base\target=@bt[0] : base\targetCapacity=3072
 dest\host=@dh[0] : dest\hostCapacity=256 : dest\target=@dt[0] : dest\targetCapacity=3072
 rc=WebUrlParse("http://a/b/c/d;p?q",18,0,@base)
'''
# RFC 3986 normal/abnormal reference examples; fragments omitted in HTTP targets.
pairs=[('g','/b/c/g'),('./g','/b/c/g'),('g/','/b/c/g/'),('/g','/g'),('//g','/'),('?y','/b/c/d;p?y'),('g?y','/b/c/g?y'),('#s','/b/c/d;p?q'),('g#s','/b/c/g'),('g?y#s','/b/c/g?y'),(';x','/b/c/;x'),('g;x','/b/c/g;x'),('g;x?y#s','/b/c/g;x?y'),('','/b/c/d;p?q'),('.','/b/c/'),('./','/b/c/'),('..','/b/'),('../','/b/'),('../g','/b/g'),('../..','/'),('../../','/'),('../../g','/g'),('../../../g','/g'),('../../../../g','/g'),('/./g','/g'),('/../g','/g'),('g.','/b/c/g.'),('.g','/b/c/.g'),('g..','/b/c/g..'),('..g','/b/c/..g'),('./../g','/b/g'),('./g/.','/b/c/g/'),('g/./h','/b/c/g/h'),('g/../h','/b/c/h'),('g;x=1/./y','/b/c/g;x=1/y'),('g;x=1/../y','/b/c/y'),('g?y/./x','/b/c/g?y/./x'),('g?y/../x','/b/c/g?y/../x'),('g#s/./x','/b/c/g'),('g#s/../x','/b/c/g'),('https://EXAMPLE.com:8443/a/../b?q','/b?q'),('/a//b/../c','/a//c'),('/%2e/%2e%2e/x','/%2e/%2e%2e/x'),('/a///../c','/a//c'),('?','/b/c/d;p?'),('/a/..','/'),('http:g',None),('javascript:alert(1)',None),('g%zz',None),('http://user@host/a',None)]
cases=[]
for reference,target in pairs:
 i=len(cases);cases.append(dict(reference=reference,target=target,host='g' if reference=='//g' else ('example.com' if reference.startswith('https:') else 'a'),secure=int(reference.startswith('https:')),port=8443 if reference.startswith('https:') else 80))
 s+=f' Record({i},"{reference}",{len(reference)})\n'
s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\n'
s=s.replace('d;p?q",18','d;p?q",'+str(len('http://a/b/c/d;p?q')))
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
