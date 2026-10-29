"""Build physical IPv6 address parsing/formatting/prefix qualification."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 valid=['::','::1','1::','2001:db8::1','FE80:0:0:0:1234:0:0:1','1:0:0:2:0:0:3:4','::ffff:192.0.2.128','0:0:0:0:0:ffff:192.0.2.1','1:2:3:4:5:6:7:8','::192.0.2.1','2001:db8:0:1:1:1:1:1']
 rng=random.Random(426)
 for i in range(40):
  a=ipaddress.IPv6Address(rng.getrandbits(128));valid.extend([a.compressed,a.exploded.upper()])
 invalid=['',':',':::','1:','1::2::3','1:2:3:4:5:6:7','1:2:3:4:5:6:7:8:9','1:2:3:4:5:6:7:8::','::1:2:3:4:5:6:7:8','12345::','-1::','::g',' ::1','::1 ','[::1]','fe80::1%2','::1/128','::ffff:192.0.2.256','::ffff:192.0.2','::ffff:192.00.2.1','::ffff:192.0.2.1.5','::ffff:192.0.2.1:2','1:2:3:4:5:6:192.0.2.1::','::ffff:1.2.3.-1','::ffff:1.2.3.','::ffff:.1.2.3','1:2:3:4:5:6:7::8','::00000','::0x1']
 cases=[]
 for t in valid:
  a=ipaddress.IPv6Address(t);formatted=a.compressed
  if a.ipv4_mapped is not None:formatted='::ffff:'+format((int(a)>>16)&65535,'x')+':'+format(int(a)&65535,'x')
  cases.append(dict(text=t,valid=True,address=a.packed.hex(),formatted=formatted))
 for t in invalid:
  try:ipaddress.IPv6Address(t)
  except ValueError:pass
  else:assert '%' in t,t
  cases.append(dict(text=t,valid=False))
 s='\n'.join('XIncludeFile "'+names[i]+'"' for i in [0,2])+'\n'+r'''
Global wtable.i
Global *pet
Global Dim address.a[32]
Global Dim other.a[16]
Global Dim formatted.a[64]
Global Dim shortbuf.a[64]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure AddressFixture(index.i,text.i,n.i)
 Define p.i,i.i,rc.i,fmt.i,measure.i,small.i,guards.i,score.i
 p=$E1C00100+index*256
 For i=0 To 31 : address[i]=$A5 : Next
 For i=0 To 63 : formatted[i]=$A5 : shortbuf[i]=$A5 : Next
 rc=IPv6AddressParse(text,n,@address[0])
 PokeI(p,rc)
 guards=1
 For i=16 To 31 : If address[i]<>$A5 : guards=0 : EndIf : Next
 If rc=0
  measure=IPv6AddressFormat(@address[0],0,0)
  small=IPv6AddressFormat(@address[0],@shortbuf[0],measure)
  fmt=IPv6AddressFormat(@address[0],@formatted[0],64)
  For i=0 To 63 : If shortbuf[i]<>$A5 : guards=0 : EndIf : Next
  For i=0 To 15 : other[i]=address[i] : Next
  score=0
  For i=0 To 128 : rc=IPv6AddressPrefix(@address[0],@other[0],i) : score=score+rc : Next
  other[15]=other[15]!1
  rc=IPv6AddressPrefix(@address[0],@other[0],127) : If rc=1 : score=score+1 : EndIf
  rc=IPv6AddressPrefix(@address[0],@other[0],128) : If rc=0 : score=score+1 : EndIf
  rc=IPv6AddressPrefix(@address[0],@other[0],129) : If rc=-1 : score=score+1 : EndIf
  rc=IPv6AddressPrefix(@address[0],@other[0],-1) : If rc=-1 : score=score+1 : EndIf
  PokeI(p+8,fmt) : PokeI(p+16,measure) : PokeI(p+24,small) : PokeI(p+40,score)
 Else
  For i=0 To 15 : If address[i]<>$A5 : guards=0 : EndIf : Next
 EndIf
 PokeI(p+32,guards)
 For i=0 To 15 : PokeA(p+64+i,address[i]) : Next
 For i=0 To 63 : PokeA(p+96+i,formatted[i]) : Next
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$49503631)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,c in enumerate(cases):s+=f' AddressFixture({i},?IPv6Vector{i},{len(c["text"])})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(cases):s+=f'IPv6Vector{i}:\n Data.a '+','.join(str(x) for x in c['text'].encode()+b'XYZ')+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
