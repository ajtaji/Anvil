"""Compile credential and streamed form fixtures for physical execution."""
from pathlib import Path
import argparse,base64,hashlib,json,os,re,subprocess,urllib.parse
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/web_credentials.pbi','Anvil/Network/web_form.pbi'];cases=[]
 def add(kind,a,b=b'',rc=None,cap=512,separator=0):
  if rc is None:
   if kind==0:expected=b'Basic '+base64.b64encode(a+b':'+b)
   elif kind==1:expected=b'Bearer '+a
   else:expected=(b'&' if separator else b'')+urllib.parse.quote_plus(a,safe='*-._').replace('~','%7E').encode()+b'='+urllib.parse.quote_plus(b,safe='*-._').replace('~','%7E').encode()
   rc=len(expected)
  else:expected=b''
  cases.append(dict(kind=kind,a=a.hex(),b=b.hex(),rc=rc,expected=expected.hex(),cap=cap,separator=separator))
 for a,b in [(b'Aladdin',b'open sesame'),(b'',b''),(b'a',b'b'),(b'ab',b'cd'),(b'user',b'p:a:ss'),('usér'.encode(),'päss'.encode())]:add(0,a,b)
 for a,b in [(b'a:b',b'c'),(b'a\r',b'b'),(b'a',b'\x7f'),(b'a',b'\0')]:add(0,a,b,rc=-641)
 add(0,b'u',b'p',cap=9,rc=-642)
 for a in [b'abc',b'a.b_C-~/+==',b'a=']:add(1,a)
 for a in [b'=',b'a=b',b'a b',b'a\r\nX:y',b'a\x80']:add(1,a,rc=-641)
 add(1,b'',rc=-640);add(1,b'abc',cap=9,rc=-642)
 for a,b in [(b'',b''),(b'a b',b'c+d&=%~'),(b'name',b'one\r\ntwo'),(b'utf8','München €'.encode()),(b'raw',bytes(range(128)))]:
  for cap in [1,2,3,7,512]:add(2,a,b,cap=cap,separator=1 if cap==2 else 0)
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global f.WebForm
Global Dim a.a[256]
Global Dim b.a[256]
Global Dim result.a[1024]
Procedure Run(index.i,kind.i,an.i,bn.i,cap.i,separator.i)
 Define i.i,p.i,rc.i,query.i,wipe.i,total.i,k.i,probe.i,loops.i
 p=$E1C00100+index*1024
 For i=0 To an-1 : Read.a a[i] : Next
 For i=0 To bn-1 : Read.a b[i] : Next
 For i=0 To 1023 : result[i]=$A5 : Next
 If kind=0
  query=WebCredentialBasic(@a[0],an,@b[0],bn,0,0)
  rc=WebCredentialBasic(@a[0],an,@b[0],bn,@result[0],cap)
 ElseIf kind=1
  query=WebCredentialBearer(@a[0],an,0,0)
  rc=WebCredentialBearer(@a[0],an,@result[0],cap)
 Else
  rc=WebFormInit(@f,@a[0],an,@b[0],bn,separator) : query=rc
  probe=WebFormOutput(@f,0,0)
  While f\phase<>4 And loops<1024
   k=WebFormOutput(@f,@result[total],cap)
   If k<0 : rc=k : Break : EndIf
   total=total+k : loops=loops+1
  Wend
  If total<>query Or probe<>0 Or f\phase<>4 : rc=-999 : EndIf
 EndIf
 PokeI(p,rc) : PokeI(p+8,query)
 For i=0 To 767 : PokeA(p+32+i,result[i]) : Next
 wipe=WebCredentialWipe(@result[0],768)
 For i=0 To 767 : If result[i]<>0 : wipe=-998 : EndIf : Next
 PokeI(p+16,wipe)
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57435631)
'''
 s+=f' PokeI($E1C00008,{len(cases)})\n'
 for i,c in enumerate(cases):s+=f' Restore Case{i}\n Run({i},{c["kind"]},{len(bytes.fromhex(c["a"]))},{len(bytes.fromhex(c["b"]))},{c["cap"]},{c["separator"]})\n'
 s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(cases):s+=f'Case{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['a']+c['b']) or b'\0'))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
