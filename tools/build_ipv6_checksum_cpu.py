"""Build physical shared Internet/IPv6 checksum qualification."""
from pathlib import Path
import argparse,hashlib,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/internet_checksum.pbi']
 rng=random.Random(333);cases=[];vectors=[]
 def checksum(b):
  b=b+b'\0' if len(b)%2 else b
  n=sum(int.from_bytes(b[i:i+2],'big') for i in range(0,len(b),2))
  while n>65535:n=(n&65535)+(n>>16)
  return n^65535
 for n in [0,1,2,3,4,5,7,8,15,16,17,127,1280,1500,65535]:
  src=rng.randbytes(16);dst=rng.randbytes(16);data=rng.randbytes(n);proto=58
  vectors.append(src+dst+data)
  expected=checksum(src+dst+n.to_bytes(4,'big')+bytes([0,0,0,proto])+data)
  for align in range(4):cases.append(dict(vector=len(vectors)-1,bytes=n,align=align,expected=expected,generic=checksum(data)))
 s='\n'.join('XIncludeFile "'+names[i]+'"' for i in [0,2])+'\n'+r'''
Global wtable.i
Global *pet
Global Dim buffer.a[65540]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure ChecksumFixture(index.i,data.i,n.i,alignment.i)
 Define i.i,p.i,result.i,generic.i,sum.i,guards.i
 p=$E1C00100+index*128
 For i=0 To 65539 : buffer[i]=$A5 : Next
 For i=0 To n-1 : buffer[alignment+i]=PeekA(data+32+i) : Next
 result=IPv6TransportChecksum(data,data+16,58,@buffer[alignment],n)
 sum=InternetChecksumSum16(@buffer[alignment],n,0) : generic=InternetChecksumFinish(sum)
 guards=1
 For i=0 To alignment-1 : If buffer[i]<>$A5 : guards=0 : EndIf : Next
 For i=alignment+n To 65539 : If buffer[i]<>$A5 : guards=0 : EndIf : Next
 PokeI(p,result) : PokeI(p+8,generic) : PokeI(p+16,guards)
 PokeI(p+24,@buffer[alignment]&3)
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$49503633)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,c in enumerate(cases):s+=f' ChecksumFixture({i},?IPv6ChecksumVector{c["vector"]},{c["bytes"]},{c["align"]})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,p in enumerate(vectors):
  s+=f'IPv6ChecksumVector{i}:\n'
  for j in range(0,len(p),24):s+=' Data.a '+','.join(str(x) for x in p[j:j+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
