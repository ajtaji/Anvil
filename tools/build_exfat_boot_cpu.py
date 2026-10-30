"""Compile boot-region range-read and rejection checks for physical Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def checksum(data,size):
 value=0
 for i,b in enumerate(data[:11*size]):
  if i not in (106,107,112):value=(((value>>1)|((value&1)<<31))+b)&0xffffffff
 return value

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(exist_ok=False,parents=True)
 names=['Anvil/Storage/exfat.pbi','Anvil/Hal/aarch64_counter.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global Dim media.a[98304]
Global reads.i,lastCount.i,lastLba.i,failRead.i
Procedure.i ProofBootRead(lba.i,count.i,dst.i)
 Define i.i
 reads=reads+1 : lastCount=count : lastLba=lba
 If failRead : ProcedureReturn 0 : EndIf
 If lba<0 Or count<1 Or (lba+count)*512>98304 : ProcedureReturn 0 : EndIf
 For i=0 To count*512-1 Step 8 : PokeI(dst+i,PeekI(@media[0]+lba*512+i)) : Next
 ProcedureReturn 1
EndProcedure
Procedure ResetMedia(src.i,size.i)
 Define i.i
 For i=0 To 12*size-1 Step 8
  PokeI(@media[0]+i,PeekI(src+i)) : PokeI(@media[0]+12*size+i,PeekI(src+i))
 Next
 exfat_bytesPerSector=size : exfat_blocksPerSector=size/512
 exfat_partLba=0 : exfat_partBlocks=24*size/512 : exfat_volumeBlocks=exfat_partBlocks
 exfat_error=0 : reads=0 : lastCount=0 : lastLba=0 : failRead=0
EndProcedure
Procedure.i Main(services.i)
 Define i.i,p.i,rc.i,began.i,cost.i
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 9999 : EndIf
 MmuEnableCached()
 For i=0 To 16383 : PokeA($E1C00000+i,165) : Next
 PokeI($E1C00000,$424F4F54) : PokeI($E1C00008,A64CounterFrequency())
 ExFatSetRangeReader(@ProofBootRead)
'''
 data=[];cases=[]
 for size in [512,1024,2048,4096]:
  raw=bytearray(12*size);raw[:11]=b'\xeb\x76\x90EXFAT   ';struct.pack_into('<H',raw,510,0xaa55)
  for sector in range(1,9):struct.pack_into('<I',raw,(sector+1)*size-4,0xaa550000)
  raw[9*size+17]=0x73;raw[10*size+31]=0xd6
  struct.pack_into('<I',raw,11*size,checksum(raw,size));raw[11*size:]=raw[11*size:11*size+4]*(size//4)
  vals=struct.unpack('<'+'Q'*(len(raw)//8),raw)
  data.append('boot'+str(size)+':\n'+'\n'.join('Data.i '+','.join('$%016X'%v for v in vals[i:i+8]) for i in range(0,len(vals),8)))
  tests=[('valid',None,False,1,0),('flags-low',106,False,1,0),('flags-high',107,False,1,0),('usage',112,False,1,0),('checksum-first',11*size,False,0,7),('checksum-last',12*size-4,False,0,7),('data',9*size+17,False,0,7),('jump',0,True,0,6),('name',3,True,0,6),('reserved',11,True,0,6),('boot-signature',510,True,0,6),('extended-first',2*size-4,True,0,6),('extended-last',9*size-4,True,0,6),('read-failure',None,False,0,2),('bounds',None,False,0,25)]
  for base in [0,12]:
   for kind,offset,recalc,rc,error in tests:
    index=len(cases);calls=0 if kind=='bounds' else 1
    cases.append(dict(index=index,sector_bytes=size,base=base,kind=kind,result=rc,error=error,calls=calls,blocks=12*size//512 if calls else 0,lba=base*size//512 if calls else 0))
    s+=f' ResetMedia(?boot{size},{size})\n'
    changed=bytearray(raw)
    if offset is not None:
     changed[offset]^=1;s+=f' PokeA(@media[0]+{base*size+offset},{changed[offset]})\n'
    if recalc:s+=f' For i=0 To {size-1} Step 4 : PokeL(@media[0]+{(base+11)*size}+i,${checksum(changed,size):08X}) : Next\n'
    if kind=='read-failure':s+=' failRead=1\n'
    if kind=='bounds':s+=f' exfat_volumeBlocks={(base+11)*size//512}\n'
    s+=f''' began=A64CounterReadOrdered() : rc=exfat_CheckBootRegion({base}) : cost=A64CounterReadOrdered()-began
 p=$E1C00200+{index}*64
 PokeI(p,rc) : PokeI(p+8,exfat_error) : PokeI(p+16,reads)
 PokeI(p+24,lastCount) : PokeI(p+32,lastLba) : PokeI(p+40,cost)
'''
 s+=' MmuDisableCachedFlushed() : ProcedureReturn 0\nEndProcedure\nDataSection\n'+'\n'.join(data)+'\nEndDataSection\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1600:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
