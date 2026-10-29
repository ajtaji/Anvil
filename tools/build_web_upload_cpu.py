"""Physical known-length and chunked upload proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile streaming HTTP upload qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi']
s='\n'.join(x for n in names for x in (r/n).read_text(encoding='utf8').splitlines() if not x.startswith('XIncludeFile'))+'''
Global u.WebUrl,req.WebRequest
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim headers.a[1024]
Global Dim output.a[512]
Procedure Record(index.i,method.i,methodLength.i,bodyLength.i,cap.i,bad.i)
 Define rc.i,i.i,offset.i,count.i,steps.i,p.i,amount.i
 u\\host=@host[0] : u\\hostCapacity=256 : u\\target=@target[0] : u\\targetCapacity=3072
 rc=WebUrlParse("https://Example.com:8443/upload?x=1#drop",39,1,@u)
 If rc=0 : rc=WebRequestInit(@req,@u,method,methodLength,bodyLength,1,@headers[0],1024) : EndIf
 If rc=0
  If bad=1
   rc=WebRequestHeader(@req,"Content-Length",14,"99",2)
  ElseIf bad=2
   rc=WebRequestHeader(@req,"X-Test",6,?inject,6)
  Else
   rc=WebRequestHeader(@req,"Content-Type",12,"text/plain",10)
  EndIf
 EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@req) : EndIf
 For i=0 To 511 : output[i]=0 : Next
 While rc>=0 And req\\state<>2
  amount=cap
  If steps=0 : amount=0 : EndIf
  rc=WebRequestOutput(@req,?body+offset,3-offset,1,@output[count],amount)
  offset=offset+req\\consumed : count=count+req\\written : steps=steps+1
  If steps>1000 : rc=-999 : Break : EndIf
 Wend
 p=$E1C00100+index*768
 For i=0 To 767 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,req\\state) : PokeI(p+16,offset) : PokeI(p+24,count)
 For i=0 To 511 : PokeA(p+64+i,output[i]) : Next
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57555031)
'''
cases=[]
for method,length,cap,bad in [('POST',3,1,0),('POST',3,512,0),('PUT',-1,1,0),('PUT',-1,7,0),('PUT',-1,512,0),('PATCH',3,7,0),('POST',2,512,0),('POST',4,512,0),('POST',3,7,1),('POST',3,7,2),('CONNECT',3,7,0)]:
 i=len(cases);cases.append(dict(method=method,length=length,cap=cap,bad=bad));s+=f' Record({i},"{method}",{len(method)},{length},{cap},{bad})\n'
s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\nDataSection\nbody:\n Data.a 0,255,97\ninject:\n Data.a 97,13,10,88,58,98\nEndDataSection\n'
# Explicit URL span, not its terminator.
s=s.replace('8443/upload?x=1#drop",39','8443/upload?x=1#drop",'+str(len('https://Example.com:8443/upload?x=1#drop')))
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
