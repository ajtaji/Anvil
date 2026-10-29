"""Compile physical streaming/framing tests with split input and backpressure."""
from pathlib import Path
import argparse,json,hashlib,subprocess,os,re
from pmf_compiler import resolve_compiler

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 # Wire, HEAD, error, final status, decoded bytes, reusable, consumed on success.
 cases=[]
 def add(wire,body=b'',status=200,reuse=1,error=0,head=0,consumed=None):
  if isinstance(wire,str):wire=wire.encode()
  cases.append(dict(wire=list(wire),head=head,error=error,status=status,body=list(body),reusable=reuse,consumed=len(wire) if consumed is None else consumed))
 add('HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc',b'abc')
 add('HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc',b'abc')
 add('HTTP/1.1 200 OK\r\nContent-Length: 3, 3\r\n\r\nabc',b'abc')
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3;note=deadbeef\r\nabc\r\n0\r\nX-End: yes\r\n\r\n',b'abc')
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;note="a\\\"b"\r\nx\r\n2\r\nyz\r\n0\r\n\r\n',b'xyz')
 add('HTTP/1.1 103 Early Hints\r\nLink: </x>\r\n\r\nHTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx',b'x')
 add('HTTP/1.1 200 OK\r\n\r\nabc',b'abc',reuse=0)
 add('HTTP/1.0 200 OK\r\nContent-Length: 1\r\n\r\nx',b'x',reuse=0)
 add('HTTP/1.0 200 OK\r\nContent-Length: 1\r\nConnection: keep-alive\r\n\r\nx',b'x')
 add('HTTP/1.1 204 No Content\r\n\r\n',status=204)
 add('HTTP/1.1 304 Not Modified\r\nContent-Length: 123\r\n\r\n',status=304)
 add('HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\n',head=1)
 base=b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx';add(base+b'NEXT',b'x',consumed=len(base))
 add('HTTP/1.1 200 OK\r\nConnection: keep-alive, CLOSE\r\nContent-Length: 0\r\n\r\n',reuse=0)
 add(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n\x00\xff\x01',b'\x00\xff\x01')
 add('HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nab',b'ab',error=-524,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n',error=-524,reuse=0)
 add('HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 4\r\n\r\n',error=-522,reuse=0)
 add('HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n',error=-522,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: xchunked\r\n\r\n',error=-525,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip, chunked\r\n\r\n',error=-525,reuse=0)
 add('HTTP/1.1 200 OK\r\nContent-Length: 9223372036854775808\r\n\r\n',error=-522,reuse=0)
 add('HTTP/1.1 200 OK\r\n Bad: folded\r\n\r\n',error=-521,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx!\n0\r\n\r\n',b'x',error=-521,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nContent-Length: 1\r\n\r\n',error=-522,reuse=0)
 add('HTTP/1.1 101 Switching Protocols\r\n\r\n',status=101,error=-526,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1z\r\nx\r\n0\r\n\r\n',error=-521,reuse=0)
 add('HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;\r\nx\r\n0\r\n\r\n',error=-521,reuse=0)
 s=(r/'Anvil/Network/web_response.pbi').read_text(encoding='utf8')+'''
Global response.WebResponse
Global Dim lineBytes.a[512]
Global Dim headerBytes.a[2048]
Global Dim outputBytes.a[64]
Procedure Record(index.i,source.i,bytes.i,head.i,mode.i)
 Define pos.i,out.i,offered.i,capacity.i,rc.i,p.i,i.i,steps.i,blocked.i
 For i=0 To 63 : outputBytes[i]=0 : Next
 rc=WebResponseInit(@response,@lineBytes[0],512,@headerBytes[0],2048,head)
 While pos<bytes And response\\state<>#WEB_RESPONSE_DONE And rc>=0
  offered=bytes-pos : capacity=64-out
  If mode=1 : offered=1 : EndIf
  If mode=2
   If offered>7 : offered=7 : EndIf
   capacity=1
   If blocked=0 : capacity=0 : EndIf
  EndIf
  rc=WebResponseFeed(@response,source+pos,offered,@outputBytes[out],capacity)
  out=out+response\\written : pos=pos+response\\consumed
  If rc=0 And response\\written=0 : blocked=1 : Else : blocked=0 : EndIf
  steps=steps+1
  If steps>2000 : rc=-999 : Break : EndIf
 Wend
 If rc>=0 : rc=WebResponseEof(@response) : EndIf
 p=$E1C00100+index*160
 For i=0 To 159 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,response\\status) : PokeI(p+16,response\\state)
 PokeI(p+24,response\\bodyBytes) : PokeI(p+32,pos) : PokeI(p+40,response\\reusable)
 PokeI(p+48,out)
 For i=0 To 63 : PokeA(p+64+i,outputBytes[i]) : Next
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57525331)
'''
 for i,c in enumerate(cases):
  for mode in range(3):s+=f' Record({i*3+mode},?wire{i},{len(c["wire"])},{c["head"]},{mode})\n'
 s+=f' PokeI($E1C00008,{len(cases)*3})\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(cases):s+=f'wire{i}:\n Data.a '+','.join(map(str,c['wire']))+'\n'
 s+='EndDataSection\n';p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1500:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
 p=d/'proof.img.pmf';names=['Anvil/Network/web_response.pbi']
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':main()
