"""Compile independent HPACK vectors for physical Anvil qualification."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=json.loads((root/'tools/hpack_cases.json').read_text())['cases']
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/byte_order.pbi','Anvil/Network/hpack_tables.pbi','Anvil/Network/hpack_decode.pbi']
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/hpack_decode.pbi"\n'+r'''
Global d.HpackDecoder
Global table.i
Global *pet,*clock
Global Dim wire.a[32768]
Global Dim storage.a[16386]
Global Dim field.a[8194]
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure Run(index.i,reset.i,bytes.i,limit.i,listLimit.i,shrink.i)
 Define i.i,rc.i,p.i,at.i,n.i,start.i,cost.i,worst.i
 pet()
 p=$E1C00000+index*16384 : at=p+128
 If reset<>0
  storage[0]=$A5 : storage[16385]=$A5 : field[0]=$A5 : field[8193]=$A5
  PokeI(p,HpackInit(@d,@storage[1],16384))
 EndIf
 For i=0 To bytes-1 : Read.a wire[i] : Next
 If shrink<>0 : PokeI(p+112,HpackSetLimit(@d,0)) : EndIf
 If limit>=0 : PokeI(p+112,HpackSetLimit(@d,limit)) : EndIf
 rc=HpackBegin(@d,@wire[0],bytes,@field[1],8192,listLimit)
 n=0 : worst=0
 If rc=0
  Repeat
   start=clock() : rc=HpackNext(@d) : cost=clock()-start
   If cost>worst : worst=cost : EndIf
   If rc=1
    If at+24+d\nameLength+d\valueLength>p+16384 : rc=-99 : Break : EndIf
    PokeI(at,d\nameLength) : PokeI(at+8,d\valueLength) : PokeI(at+16,d\sensitive) : at=at+24
    For i=0 To d\nameLength-1 : PokeA(at+i,PeekA(d\name+i)) : Next
    at=at+d\nameLength
    For i=0 To d\valueLength-1 : PokeA(at+i,PeekA(d\value+i)) : Next
    at=at+d\valueLength : n=n+1
   EndIf
  Until rc<=0
 EndIf
 PokeI(p+8,rc) : PokeI(p+16,HpackNext(@d)) : PokeI(p+24,d\size) : PokeI(p+32,d\maximum)
 PokeI(p+40,d\entries) : PokeI(p+48,d\used) : PokeI(p+56,d\cursor) : PokeI(p+64,d\listSize)
 PokeI(p+72,n) : PokeI(p+80,at-p-128)
 PokeI(p+88,storage[0]|(storage[16385]<<8)) : PokeI(p+96,field[0]|(field[8193]<<8))
 PokeI(p+104,worst)
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i
 pet=PeekI(table+16+6*8) : clock=PeekI(table+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 1048575 : PokeA($E1C00000+i,0) : Next
 Restore hpVectors
'''
 for i,c in enumerate(rows):s+=f'Run({i},{int(c["reset"])},{len(bytes.fromhex(c["blob"]))},{c["limit"]},{c["list_limit"]},{int(c.get("shrink_first",False))})\n'
 s+=' MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\nhpVectors:\n'
 data=b''.join(bytes.fromhex(c['blob']) for c in rows)
 for i in range(0,len(data),24):s+=' Data.a '+','.join(str(v) for v in data[i:i+24])+'\n'
 s+='EndDataSection\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1cfffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
