"""Build live A/AAAA resolution through the resident ABI, preserving warm cache checks."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Core/payload_net.pbi','Anvil/Hal/abi.pbi','Anvil/Hal/abi_version.pbi','Anvil/Network/dns_codec.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+r'''
Global table.i
Global *livePet,*liveTime,*service,*dns4,*dns6
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure ProofDnsQuery(index.i,kind.i)
 Define p.i,rc.i,start.i
 p=$E1C00100+index*64 : start=liveTime()/1000
 Repeat
  livePet()
  If kind=28
   rc=dns6("one.one.one.one",p+24)
  Else
   rc=dns4("one.one.one.one")
  EndIf
  If rc<>-110 And rc<>-103 : Break : EndIf
  If liveTime()/1000-start>=6000 : rc=-999 : Break : EndIf
  service(1)
 ForEver
 PokeI(p,kind) : PokeI(p+8,rc) : PokeI(p+16,liveTime()/1000-start)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$444E5336)
 If table=0 : ProcedureReturn 2 : EndIf
 PokeI($E1C00008,PeekL(table+8))
 If PeekL(table)<>$53564E41 Or PeekL(table+8)<12 Or PeekL(table+12)<90 : ProcedureReturn 3 : EndIf
 livePet=PeekI(table+16+6*8) : liveTime=PeekI(table+16+11*8)
 service=PeekI(table+16+85*8) : dns4=PeekI(table+16+75*8) : dns6=PeekI(table+16+89*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 4 : EndIf
 MmuEnableCached()
 For i=0 To 3 : ProofDnsQuery(i*2,28) : ProofDnsQuery(i*2+1,1) : Next
 PokeI($E1C00010,dns6("one.one.one.one",0))
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=dict(host='one.one.one.one',queries=8)),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
