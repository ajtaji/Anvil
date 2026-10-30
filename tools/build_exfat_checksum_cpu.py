"""Compile shared exFAT regression and buffered-checksum timing for physical Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=[0,1,2,3,4,5,7,8,9,15,16,17,31,32,33,127,128,129,255,256,511,512,513,4095,4096,4097,8192,32768]
    names=['Anvil/Storage/exfat.pbi','Anvil/Storage/fat32.pbi','Anvil/Storage/filesystem.pbi','RaspberryPi4/Tests/exfat_emitted_gate.pi4','Anvil/Hal/aarch64_counter.pbi','RaspberryPi4/Lib/mmu.pi4']
    names.append('Anvil/Storage/exfat_profile.pbi')
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


Procedure.i OldValidate()
  Define cp.i
  Define off.i
  Define lo.i
  Define hi.i
  Define word.i
  Define skip.i
  cp = 0
  off = 0
  While off + 1 < exfat_upcaseLength And cp < 65536
    lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
    If lo < 0 Or hi < 0
      ProcedureReturn 0
    EndIf
    word = lo | (hi << 8)
    off = off + 2
    If word = $FFFF
      If off + 1 >= exfat_upcaseLength
        If cp = $FFFF
          cp = cp + 1
          Break
        EndIf
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
      hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
      If lo < 0 Or hi < 0
        ProcedureReturn 0
      EndIf
      skip = lo | (hi << 8)
      off = off + 2
      If skip = 0 Or cp + skip > 65536
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      cp = cp + skip
    Else
      cp = cp + 1
    EndIf
  Wend
  If cp <> 65536 Or off <> exfat_upcaseLength
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i OldBuildFast()
  Define cp.i
  Define off.i
  Define word.i
  Define skip.i
  Define lo.i
  Define hi.i
  Define endCp.i
  cp = 0
  off = 0
  While cp < 256 And off + 1 < exfat_upcaseLength
    lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
    If lo < 0 Or hi < 0
      ProcedureReturn 0
    EndIf
    word = lo | (hi << 8)
    off = off + 2
    If word = $FFFF
      If off + 1 >= exfat_upcaseLength
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
      hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
      If lo < 0 Or hi < 0
        ProcedureReturn 0
      EndIf
      skip = lo | (hi << 8)
      off = off + 2
      If skip = 0 Or cp + skip > 65536
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      endCp = cp + skip
      If endCp > 256
        endCp = 256
      EndIf
      While cp < endCp
        exfat_upcaseFast[cp] = cp
        cp = cp + 1
      Wend
    Else
      exfat_upcaseFast[cp] = word
      cp = cp + 1
    EndIf
  Wend
  If cp <> 256
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
  EndIf
  ; Microsoft defines mandatory mappings for the first 128 code points.
  cp = 0
  While cp < 128
    If cp >= 97 And cp <= 122
      If exfat_upcaseFast[cp] <> cp - 32
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
    ElseIf exfat_upcaseFast[cp] <> cp
      ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
    EndIf
    cp = cp + 1
  Wend
  exfat_upcaseFastReady = 1
  ProcedureReturn 1
EndProcedure
Procedure PrepareTable(prefix.i)
 Define i.i,v.i
 For i=0 To prefix-1
  v=i : If i>=97 And i<=122 : v=i-32 : EndIf
  exfat_Put16(@gateDisk[0]+35*512,i*2,v)
 Next
 exfat_Put16(@gateDisk[0]+35*512,prefix*2,$FFFF)
 exfat_Put16(@gateDisk[0]+35*512,prefix*2+2,65535-prefix)
 exfat_Put16(@gateDisk[0]+35*512,prefix*2+4,$FFFF)
 exfat_upcaseLength=prefix*2+6 : exfat_DropCaches()
EndProcedure
Procedure ValidationRow(index.i)
 Define p.i,t.i,rc.i
 p=$E1C01000+index*64
 exfat_DropCaches() : t=A64CounterReadOrdered() : rc=OldValidate()
 PokeI(p,rc) : PokeI(p+16,A64CounterReadOrdered()-t)
 exfat_DropCaches() : t=A64CounterReadOrdered() : rc=exfat_ValidateUpcase()
 PokeI(p+8,rc) : PokeI(p+24,A64CounterReadOrdered()-t)
EndProcedure
Procedure.i ProofPartialDirectoryWrite(lba.i,count.i,dst.i)
 PokeA(@gateDisk[0]+lba*512,166) : ProcedureReturn 0
EndProcedure
Procedure.i ProofDirectoryCache()
 Define i.i,base.i,before.i,rc.i
 GateFormat() : ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(@GateWriter)
 If ExFatMount(1)=0 : ProcedureReturn 1 : EndIf
 exfat_sectorsPerCluster=8 : exfat_blocksPerCluster=8 : exfat_bytesPerCluster=4096 : exfat_clusterCount=128
 base=exfat_partLba+exfat_heapOffset
 For i=0 To 12287 : PokeA(@gateDisk[0]+base*512+i,(i/512) & 255) : Next
 exfat_DropCaches()
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>0 : ProcedureReturn 2 : EndIf
 If exfat_DirRead(3,2,4096,0,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 3 : EndIf
 If exfat_StreamRead(4,2,4096,0,@gateBig[0],512)<>512 : ProcedureReturn 4 : EndIf
 before=gateReads
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>0 : ProcedureReturn 5 : EndIf
 If exfat_DirRead(3,2,4096,0,@gateRead[0])=0 Or gateRead[0]<>8 Or gateReads<>before : ProcedureReturn 6 : EndIf
 If exfat_DirRead(2,0,8192,0,@gateRead[0])=0 Or gateReads<=before : ProcedureReturn 7 : EndIf
 before=gateReads
 If exfat_DirRead(2,2,512,0,@gateRead[0])=0 Or gateReads<=before : ProcedureReturn 8 : EndIf
 If exfat_DirRead(2,2,512,16,@gateRead[0])<>0 Or ExFatLastError()<>#EXFAT_E_BOUNDS : ProcedureReturn 9 : EndIf
 If exfat_DirRead(2,2,8192,255,@gateRead[0])=0 Or gateRead[0]<>15 : ProcedureReturn 10 : EndIf
 If exfat_DirRead(2,2,8192,0,0)<>0 : ProcedureReturn 11 : EndIf
 If exfat_SetFatEntry(2,3)=0 Or exfat_FlushFat()=0 : ProcedureReturn 20 : EndIf
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 21 : EndIf
 before=gateWrites
 If exfat_SetFatEntry(2,4)=0 Or gateWrites<>before : ProcedureReturn 22 : EndIf
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>16 : ProcedureReturn 23 : EndIf
 ExFatSetRangeWriter(0)
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 24 : EndIf
 ExFatSetRangeWriter(@GateWriter)
 PokeA(@gateDisk[0]+base*512,88) : ExFatSetRangeReader(@GateReader)
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>88 : ProcedureReturn 12 : EndIf
 exfat_Copy(@gateBig[0],@gateDisk[0]+base*512,512) : gateBig[0]=123
 If exfat_WriteBlocks(base,1,@gateBig[0])=0 : ProcedureReturn 13 : EndIf
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>123 : ProcedureReturn 14 : EndIf
 ExFatSetRangeWriter(@ProofPartialDirectoryWrite)
 If exfat_WriteBlocks(base,1,@gateBig[0])<>0 : ProcedureReturn 15 : EndIf
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or (gateRead[0] & 255)<>166 : ProcedureReturn 16 : EndIf
 exfat_DropCaches() : exfat_error=0 : exfat_dirty=1 : exfat_ioFailed=0 : gateFailLba=base+1
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or (gateRead[0] & 255)<>166 : ProcedureReturn 17 : EndIf
 If exfat_error<>0 Or exfat_ioFailed<>0 : ProcedureReturn 18 : EndIf
 If exfat_DirRead(2,2,8192,16,@gateRead[0])<>0 Or exfat_ioFailed<>1 : ProcedureReturn 19 : EndIf
 gateFailLba=-1 : exfat_dirty=0 : exfat_ioFailed=0 : ExFatSetRangeWriter(0)
 ProcedureReturn 0
EndProcedure
Global profileTestClock.i
Procedure.i ProofProfileClock()
 profileTestClock=profileTestClock+10 : ProcedureReturn profileTestClock
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,j.i,n.i,start.i,slow.i,fast.i,old.i,new.i,p.i,reads.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 9999 : EndIf
 MmuEnableCached()
 PokeI($E1C00000,$58464333)
 PokeI($E1C00040,ExFatProfileBegin())
 ExFatProfileSetClock(@ProofProfileClock)
 start=ExFatProfileBegin() : ExFatProfileEnd(0,start)
 start=ExFatProfileBegin() : ExFatProfileEnd(0,start)
 ExFatProfileEnd(-1,0) : ExFatProfileEnd(7,0) : ExFatProfileEnd(0,-1) : ExFatProfileEnd(0,999)
 PokeI($E1C00048,ExFatProfileValue(0,0))
 PokeI($E1C00050,ExFatProfileValue(0,1))
 PokeI($E1C00058,ExFatProfileValue(0,2))
 ExFatProfileSetClock(0) : PokeI($E1C00060,ExFatProfileValue(0,0))
 PokeI($E1C00068,ExFatProfileValue(7,0))
 rc=GateMain() : PokeI($E1C00008,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn rc : EndIf
 rc=ProofDirectoryCache() : PokeI($E1C00080,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 9500+rc : EndIf
 GateFormat() : ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(0)
 rc=ExFatMount(1) : If rc=0 : MmuDisableCachedFlushed() : ProcedureReturn 9000+ExFatLastError() : EndIf
 For i=10 To 73 : exfat_Put32(@gateDisk[0]+25*512,i*4,i+1) : Next
 exfat_Put32(@gateDisk[0]+25*512,73*4,$FFFFFFFF)
 For i=0 To 32767 : gateDisk[35*512+i]=(i*37+19) & 255 : Next
 exfat_upcaseCluster=10
__CHECKSUM_ROWS__
 exfat_upcaseLength=1024 : gateFailLba=36 : exfat_DropCaches()
 PokeI($E1C00018,exfat_UpcaseTableChecksum()) : gateFailLba=-1
 PrepareTable(255) : ValidationRow(0)
 PokeI($E1C01020,exfat_BuildFastUpcase()) : PokeI($E1C01028,exfat_upcaseFast[255] & $FFFF)
 PrepareTable(4095) : ValidationRow(1)
 PrepareTable(4095) : exfat_upcaseLength=8194 : ValidationRow(2)
 PrepareTable(4095) : exfat_Put16(@gateDisk[0]+35*512,8192,0) : ValidationRow(3)
 PrepareTable(4095) : exfat_Put16(@gateDisk[0]+35*512,8192,65535) : ValidationRow(4)
 PrepareTable(4095) : exfat_upcaseLength=8198 : ValidationRow(5)
 PrepareTable(4095) : gateFailLba=36 : ValidationRow(6) : gateFailLba=-1
 PrepareTable(255) : exfat_Put16(@gateDisk[0]+35*512,194,97) : exfat_DropCaches()
 PokeI($E1C00020,OldBuildFast()) : exfat_DropCaches() : PokeI($E1C00028,exfat_BuildFastUpcase())
 PokeI($E1C00010,A64CounterFrequency())
 MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
'''
    rows=[]
    for i,n in enumerate(cases):
        rows.append(f" exfat_upcaseLength={n} : p=$E1C00100+{i}*64\n"
            " exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start\n"
            " exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start\n"
            " PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)\n")
    s=s.replace('__CHECKSUM_ROWS__', ''.join(rows))
    names.append('tools/build_exfat_checksum_cpu.py')
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
