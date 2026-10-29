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
Global base.WebUrl,dest.WebUrl,old.WebRequest,new.WebRequest,opt.WebRedirectOptions
Global Dim bh.a[256]
Global Dim bt.a[3072]
Global Dim dh.a[256]
Global Dim dt.a[3072]
Global Dim scratch.a[4097]
Global Dim oh.a[1024]
Global Dim nh.a[1024]
Procedure Record(index.i,status.i,method.i,methodLength.i,length.i,replay.i,unsafe.i,cross.i,down.i,hops.i)
 Define rc.i,i.i,p.i
 p=$E1C00100+index*1024
 For i=0 To 1023 : PokeA(p+i,0) : Next
 rc=WebUrlParse("https://a/b/c/d;p?q",19,1,@base)
 If cross=0 : rc=WebUrlResolve(@base,"#s",2,@dest,@scratch[0],4097) : EndIf
 If cross=1 : rc=WebUrlResolve(@base,"https://other:8443/next",23,@dest,@scratch[0],4097) : EndIf
 If cross=2 : rc=WebUrlResolve(@base,"http://a/next",13,@dest,@scratch[0],4097) : EndIf
 If rc=0 : rc=WebRequestInit(@old,@base,method,methodLength,length,1,@oh[0],1024) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"Authorization",13,"Bearer synthetic",16) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"Cookie",6,"synthetic=1",11) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"X-Api-Key",9,"synthetic",9) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"Accept",6,"text/plain",10) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"Content-Type",12,"text/plain",10) : EndIf
 If rc=0 : rc=WebRequestHeader(@old,"Range",5,"bytes=0-1",9) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@old) : EndIf
 opt\bodyLength=length : opt\replayable=replay : opt\allowUnsafe=unsafe : opt\hops=hops : opt\maximum=3 : opt\allowDowngrade=down : opt\keepAlive=1
 If rc=0 : rc=WebRequestRedirect(@old,@base,@dest,status,@opt,@new,@nh[0],1024) : EndIf
 PokeI(p,rc)
 If rc>0
  PokeI(p+8,new\length)
  For i=0 To new\length-1 : PokeA(p+64+i,nh[i]) : Next
 EndIf
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57524432)
 base\host=@bh[0] : base\hostCapacity=256 : base\target=@bt[0] : base\targetCapacity=3072
 dest\host=@dh[0] : dest\hostCapacity=256 : dest\target=@dt[0] : dest\targetCapacity=3072
'''
cases=[]
for status,method,length,replay,unsafe,cross,down,hops,expected in [(302,'POST',3,0,0,0,0,0,1),(303,'PUT',3,0,0,1,0,0,1),(307,'POST',3,0,1,0,0,0,-562),(307,'POST',3,1,0,0,0,0,-564),(307,'POST',3,1,1,1,0,0,2),(308,'GET',0,0,0,1,0,0,2),(302,'GET',0,0,0,2,0,0,-561),(302,'GET',0,0,0,2,1,0,2),(302,'GET',0,0,0,0,0,3,-563),(200,'GET',0,0,0,0,0,0,-560),(303,'HEAD',0,0,0,0,0,0,2),(301,'PATCH',0,0,1,0,0,0,2),(308,'PUT',-1,1,1,1,0,0,2)]:
 i=len(cases);cases.append(dict(status=status,method=method,length=length,cross=cross,expected=expected))
 s+=f' Record({i},{status},"{method}",{len(method)},{length},{replay},{unsafe},{cross},{down},{hops})\n'
s+=f' PokeI($E1C00008,{len(cases)})\n'
# Empty-reference resolution retains the base query exactly.
s+=' rc=WebUrlResolve(@base,0,0,@dest,@scratch[0],4097)\n PokeI($E1C03D00,rc)\n For i=0 To dest\\targetLength-1 : PokeA($E1C03D10+i,dt[i]) : Next\n PokeA($E1C03D10+dest\\targetLength,0)\n ProcedureReturn 0\nEndProcedure\n'
for url in ['https://a/b/c/d;p?q','https://other:8443/next','http://a/next']:
 s=re.sub(re.escape('"'+url+'",')+r'\d+', '"'+url+'",'+str(len(url)),s)
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
