"""Compile shared exFAT regression and buffered-checksum timing for physical Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=[0,1,255,256,511,512,513,4096,8192,32768]
    names=['Anvil/Storage/exfat.pbi','Anvil/Storage/fat32.pbi','Anvil/Storage/filesystem.pbi','RaspberryPi4/Tests/exfat_emitted_gate.pi4','Anvil/Hal/aarch64_counter.pbi','RaspberryPi4/Lib/mmu.pi4']
    s=(root/names[3]).read_text(encoding='utf8').replace('Procedure.i Main()','Procedure.i GateMain()')
    s=s.replace('Global gateFlushes.i','Global gateFailLba.i=-1\nGlobal gateFlushes.i').replace('  gateReads = gateReads + 1','  If gateFailLba>=lba And gateFailLba<lba+count : ProcedureReturn 0 : EndIf\n  gateReads = gateReads + 1')
    # Legacy fixture buffers expressed inclusive maxima; provide their intended counts.
    for before,after in [('[#GATE_BYTES - 1]','[#GATE_BYTES]'),('[1399]','[1400]'),('[1023]','[1024]'),('[4607]','[4608]')]:s=s.replace(before,after)
    s='XIncludeFile "Anvil/Hal/aarch64_counter.pbi"\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+s
    s+=r'''
Procedure.i OldChecksum()
  Define sum.i
  Define off.i
  Define b.i
  sum = 0
  off = 0
  While off < exfat_upcaseLength
    b = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    If b < 0
      ProcedureReturn -1
    EndIf
    sum = (exfat_Ror32(sum) + b) & $FFFFFFFF
    off = off + 1
  Wend
  ProcedureReturn sum
EndProcedure

Procedure.i Main()
 Define rc.i,i.i,j.i,n.i,start.i,slow.i,fast.i,old.i,new.i,p.i,reads.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 9999 : EndIf
 MmuEnableCached()
 PokeI($E1C00000,$58464331)
 rc=GateMain() : PokeI($E1C00008,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn rc : EndIf
 GateFormat() : ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(0)
 rc=ExFatMount(1) : If rc=0 : MmuDisableCachedFlushed() : ProcedureReturn 9000+ExFatLastError() : EndIf
 For i=10 To 73 : exfat_Put32(@gateDisk[0]+25*512,i*4,i+1) : Next
 exfat_Put32(@gateDisk[0]+25*512,73*4,$FFFFFFFF)
 For i=0 To 32767 : gateDisk[35*512+i]=(i*37+19) & 255 : Next
 exfat_upcaseCluster=10
 exfat_upcaseLength=0 : p=$E1C00100+0*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=1 : p=$E1C00100+1*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=255 : p=$E1C00100+2*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=256 : p=$E1C00100+3*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=511 : p=$E1C00100+4*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=512 : p=$E1C00100+5*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=513 : p=$E1C00100+6*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=4096 : p=$E1C00100+7*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=8192 : p=$E1C00100+8*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=32768 : p=$E1C00100+9*64
 exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start
 exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start
 PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)
 exfat_upcaseLength=1024 : gateFailLba=36 : exfat_DropCaches()
 PokeI($E1C00018,exfat_UpcaseTableChecksum()) : gateFailLba=-1
 PokeI($E1C00010,A64CounterFrequency())
 MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
'''
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
