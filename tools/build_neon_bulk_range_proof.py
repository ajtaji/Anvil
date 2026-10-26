#!/usr/bin/env python3
"""Build bounded bulk geometry preflight evidence on physical Pi 4."""
from pathlib import Path
import os, subprocess, sys, json, hashlib

import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build the returning physical Pi 4 bulk-range preflight proof; never executes it.')
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--compiler')
args=ap.parse_args()
r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper = '''
Procedure.i bulkRangeLive()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure
Procedure.i bulkRangeProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,first.i,verts.i,draws.i,rows.i,fault.i,value.i,bad.i
 Define Dim values.i[8]
 NeonVkChromeDestroy()
 PokeI($E1C01190,NeonVkChromeLinesDraw(0,0,$FFFFFFFF))
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,4,4)
 If rc<>0 : ProcedureReturn 271 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 272 : EndIf
 For i=0 To 591 : PokeA(nvcMapped+i,$A5) : Next
 values[0]=0 : values[1]=-1 : values[2]=5 : values[3]=$2000000000000000
 values[4]=$2AAAAAAAAAAAAAAB : values[5]=$7FFFFFFFFFFFFFFF : values[6]=$4000000000000000
 values[7]=$5555555555555556
 For i=0 To 7
  verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount
  rc=NeonVkChromeLinesReserve(values[i])
  PokeI($E1C01020+i*24,values[i]) : PokeI($E1C01028+i*24,rc) : PokeI($E1C01030+i*24,nvcVertices-verts)
  If rc<>-1 Or nvcVertices<>verts Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows : bad=bad+1 : EndIf
  ; Observe arithmetic only. No write uses the refused/invalid range.
  nvcVertices=verts
 Next
 PokeI($E1C01008,bad)
 first=NeonVkChromeLinesReserve(2)
 If first<>0 Or nvcVertices<>12 : NeonVkChromeAbort() : ProcedureReturn 273 : EndIf
 For i=0 To 15 : PokeA(nvcMapped+12*24+i,$A5) : Next
 ; Invalid draws must refuse before recording or changing any cursor.
 values[0]=-1 : values[1]=13 : values[2]=7 : values[3]=0
 For i=0 To 3
  verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount : fault=AnvilVkFaultCode()
  value=1 : If i=3 : value=$2000000000000000 : EndIf
  rc=NeonVkChromeLinesDraw(values[i],value,$FFFFFFFF)
  PokeI($E1C01100+i*32,values[i]) : PokeI($E1C01108+i*32,value) : PokeI($E1C01110+i*32,rc)
  PokeI($E1C01118+i*32,nvcDrawCount-draws)
  If rc<>#NEON_VK_CHROME_ERR_ARGS Or nvcVertices<>verts Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or AnvilVkFaultCode()<>fault
   PokeI($E1C01010,PeekI($E1C01010)+1)
  EndIf
 Next
 For i=0 To 591
  If PeekA(nvcMapped+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 280 : EndIf
 Next
 PokeI($E1C01198,1)
 PokeI($E1C011A0,NeonVkChromeLinesDraw(12,0,$FFFFFFFF))
 PokeI($E1C011A8,NeonVkChromeLinesDraw(0,-1,$FFFFFFFF))
 rc=NeonVkChromeBoxBatchBegin()
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 281 : EndIf
 PokeI($E1C011B0,NeonVkChromeLinesDraw(0,1,$FFFFFFFF))
 rc=NeonVkChromeBoxBatchEnd()
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 282 : EndIf
 ; Discard the diagnostic command, including rejected baseline recordings.
 rc=NeonVkChromeAbort()
 If rc<>0 : ProcedureReturn 274 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 275 : EndIf
 first=NeonVkChromeLinesReserve(4)
 If first<>0 Or nvcVertices<>24 : NeonVkChromeAbort() : ProcedureReturn 276 : EndIf
 NeonVkChromeLineQuadAt(NeonVkChromeVertexAddress(0),4,8,28,8)
 NeonVkChromeLineQuadAt(NeonVkChromeVertexAddress(6),4,24,28,24)
 NeonVkChromeLineQuadAt(NeonVkChromeVertexAddress(12),4,40,28,40)
 NeonVkChromeLineQuadAt(NeonVkChromeVertexAddress(18),4,56,28,56)
 rc=NeonVkChromeLinesDraw(0,2,$FFFF0000)
 If rc=0 : rc=NeonVkChromeLinesDraw(12,2,$FF00FF00) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 277 : EndIf
 PokeI($E1C01018,nvcVertices) : PokeI($E1C01180,nvcDrawCount)
 rc=NeonVkChromeEnd()
 If rc<>0 : ProcedureReturn 278 : EndIf
 If NeonVkChromePresentConsume()<>1 : ProcedureReturn 279 : EndIf
 For i=0 To 4095 : PokeL($E2400000+i*4,PeekL(base+(i/64)*pitch+(i%64)*4)) : Next
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
'''
s = (r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
s = s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1)
at = s.index('Procedure.i Main()')
s = s[:at]+helper+'\n'+s[at:]
s = s.replace('Procedure.i Main()', 'Procedure.i BulkDiagnosticMain()', 1)
needle = '  ; Destroy the production adapter first:'
assert s.count(needle)==1
s = s.replace(needle,'  PokeI($E1C01000,bulkRangeProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n'+needle,1)
s += '''
Procedure.i Main(services.i)
 Define report.i,i.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=BulkDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,bulkRangeLive())
 If PeekL($E1C00004)<>0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
'''
(d/'helper.pi4').write_text(helper,encoding='utf8')
(d/'proof.pi4').write_text(s,encoding='utf8')
env=os.environ.copy(); env['PMF_ROOT']=str(r)
exe=str(resolve_compiler(args.compiler))
q=subprocess.run([exe,'--compile',str((d/'proof.pi4').resolve()),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str((d/'proof.img').resolve())],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
(d/'compile.txt').write_text(q.stdout+q.stderr)
print((q.stdout+q.stderr)[-1200:]); assert q.returncode==0
p=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2))
