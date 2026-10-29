#!/usr/bin/env python3
"""Build the complete native fan input limit on physical Pi 4."""
from pathlib import Path
import os, subprocess, sys, json, hashlib

import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build the physical Pi 4 full native point-boundary proof; never executes it.')
ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler')
args=ap.parse_args();r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper=r'''Procedure.i pointLiveMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure
Procedure.i pointProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,mode.i,verts.i,draws.i,rows.i
 mode=Bool(#NEON_VK_CHROME_MAX_PATH_POINTS=#NEON_MAX_VERTS)
 NeonVkChromeDestroy()
 SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,4,(#NEON_MAX_VERTS+5)/6)
 If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 381 : EndIf
 ; Every early triangle is degenerate. Only the final two triangles fill
 ; the rectangle, independently of the maximum input count being tested.
 For i=0 To #NEON_MAX_VERTS-4 : NeonFanPoint(4,4) : Next
 NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
 PokeI($E1C01008,mode) : PokeI($E1C01010,nvcPathCount)
 PokeI($E1C01018,Neon_Verts()) : PokeI($E1C01020,nvcPathError)
 PokeI($E1C01028,#NEON_VK_CHROME_MAX_PATH_POINTS)
 If nvcPathX[0]<>4 Or nvcPathY[0]<>4 : NeonVkChromeAbort() : ProcedureReturn 382 : EndIf
 If mode<>0
  If nvcPathX[nvcPathCount-1]<>4 Or nvcPathY[nvcPathCount-1]<>28 : NeonVkChromeAbort() : ProcedureReturn 382 : EndIf
 EndIf
 PokeI($E1C01030,1)
 If mode<>0
  If nvcPathCount<>262144 Or Neon_Verts()<>262144 Or nvcPathError<>0 : NeonVkChromeAbort() : ProcedureReturn 383 : EndIf
 Else
  If nvcPathCount<>4096 Or nvcPathError<>#NEON_VK_CHROME_ERR_CAPACITY : NeonVkChromeAbort() : ProcedureReturn 384 : EndIf
 EndIf
 SafetyWatchdogPet()
 rc=NeonFanEnd($FF00FF00) : PokeI($E1C01038,rc)
 If mode=0
  If rc<>#NEON_VK_CHROME_ERR_CAPACITY : NeonVkChromeAbort() : ProcedureReturn 385 : EndIf
  rc=NeonVkChromeAbort()
  If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
  If rc=0 : rc=NeonFanBegin() : EndIf
  NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
  If rc=0 : rc=NeonFanEnd($FF00FF00) : EndIf
 EndIf
 If rc<>0 Or nvcDrawCount<>1 : NeonVkChromeAbort() : ProcedureReturn 386 : EndIf
 PokeI($E1C01040,nvcVertices) : PokeI($E1C01048,Neon_Draws())
 If mode<>0
  If nvcVertices<>262144 : NeonVkChromeAbort() : ProcedureReturn 387 : EndIf
  verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount
  For i=0 To 15 : PokeA(nvcMapped+nvcVertices*24+i,$A5) : Next
  rc=NeonFanBegin() : NeonFanPoint(0,0) : rc=NeonFanEnd($FFFF0000)
  If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>verts Or nvcDrawCount<>draws Or rows<>avkRecordedDrawFreeCount Or Neon_Verts()<>262144 : NeonVkChromeAbort() : ProcedureReturn 388 : EndIf
  For i=0 To 15
   If PeekA(nvcMapped+nvcVertices*24+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 389 : EndIf
  Next
  If nvcPathX[0]<>4 Or nvcPathY[0]<>4 : NeonVkChromeAbort() : ProcedureReturn 389 : EndIf
  PokeI($E1C01050,1)
 EndIf
 SafetyWatchdogPet()
 rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 390 : EndIf
 For i=0 To 4095 : PokeL($E2400000+i*4,PeekL(base+(i/64)*pitch+(i%64)*4)) : Next
 If mode<>0
  ; Check the same line staging boundary with a deliberately small output
  ; buffer. Production compact lines now fit the normal full-size buffer.
  SafetyWatchdogPet()
  NeonVkChromeDestroy()
  rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,4,1)
  If rc<>0 : ProcedureReturn 396 : EndIf
  rc=NeonVkChromeBegin(@nwClear[0])
  If rc=0 : rc=NeonLinesBegin() : EndIf
  If rc<>0 : ProcedureReturn 391 : EndIf
  For i=1 To #NEON_MAX_VERTS/2 : NeonLine(4,4,28,4) : Next
  PokeI($E1C01060,nvcPathCount) : PokeI($E1C01068,nvcPathError)
  PokeI($E1C01070,(nvcPathCount/2)*6)
  If nvcPathCount<>262144 Or nvcPathError<>0 Or Neon_Verts()<>262144 : NeonVkChromeAbort() : ProcedureReturn 392 : EndIf
  rows=avkRecordedDrawFreeCount
  For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
  rc=NeonLinesEnd($FFFFFFFF)
  PokeI($E1C01078,rc) : PokeI($E1C01080,nvcVertices)
  If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>0 Or nvcDrawCount<>0 Or rows<>avkRecordedDrawFreeCount : NeonVkChromeAbort() : ProcedureReturn 393 : EndIf
  For i=0 To 15
   If PeekA(nvcMapped+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 394 : EndIf
  Next
  PokeI($E1C01088,1)
  PokeI($E1C01090,nvcMaxVertexQuads*6) : PokeI($E1C01098,2)
  rc=NeonVkChromeAbort()
  If rc<>0 : ProcedureReturn 395 : EndIf
 EndIf
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
'''
s = (r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
s=s.replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01400000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $017E8000')
s = s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1)
at = s.index('Procedure.i Main()')
s = s[:at]+helper+'\n'+s[at:]
s = s.replace('Procedure.i Main()', 'Procedure.i BulkDiagnosticMain()', 1)
needle = '  ; Destroy the production adapter first:'
assert s.count(needle)==1
s = s.replace(needle,'  PokeI($E1C01000,pointProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n'+needle,1)
s += '''
Procedure.i Main(services.i)
 Define report.i,i.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=BulkDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,pointLiveMemory())
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
