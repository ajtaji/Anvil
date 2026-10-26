#!/usr/bin/env python3
"""Build native owner-state evidence without executing it."""
from pathlib import Path
import os, subprocess, sys, json, hashlib

import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build the returning physical Pi 4 public owner-state proof; never executes it.')
ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler')
args=ap.parse_args();r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper=r'''Procedure stateRecord(address.i)
 PokeI(address,Neon_Draws()) : PokeI(address+8,Neon_Boxes())
 PokeI(address+16,Neon_Glyphs()) : PokeI(address+24,Neon_Runs())
 PokeI(address+32,Neon_Verts()) : PokeI(address+40,Neon_TexDraws())
 PokeI(address+48,Neon_TexGlyphs()) : PokeI(address+56,Neon_TexVerts())
 PokeI(address+64,Neon_Clipped())
EndProcedure
Procedure.i stateLiveMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure
Procedure.i stateProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define rc.i,i.i,query.i,writer.i,oldReady.i,oldHW.i,oldQuads.i,verts.i,draws.i,rows.i
 NeonVkChromeDestroy()
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,64)
 If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc=0 : rc=Neon_Box(4,4,8,8,$FFFF0000) : EndIf
 If rc=0 : rc=Neon_Text(#NEON_FONT_UI,4,20,"A A",$FF00FF00) : EndIf
 If rc=0 : rc=Neon_TextTex(#NEON_FONT_UI,4,40,"A A",$FF0000FF) : EndIf
 If rc<>0 : ProcedureReturn 351 : EndIf
 stateRecord($E1C01020)
 PokeI($E1C01008,nvcFlatDraws) : PokeI($E1C01010,nvcFlatVertices)
 PokeI($E1C01018,nvcTexVertices)
 oldQuads=nvcMaxVertexQuads : nvcMaxVertexQuads=6
 verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+nvcVertices*24+i,$A5) : Next
 rc=Neon_Text(#NEON_FONT_UI,4,20,"A A",$FFFFFFFF)
 nvcMaxVertexQuads=oldQuads
 stateRecord($E1C01220)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or verts<>nvcVertices Or draws<>nvcDrawCount Or rows<>avkRecordedDrawFreeCount : NeonVkChromeAbort() : ProcedureReturn 354 : EndIf
 For i=0 To 15
  If PeekA(nvcMapped+nvcVertices*24+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 355 : EndIf
 Next
 rc=NeonVkChromeBoxBatchBegin()
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 352 : EndIf
 Neon_ScissorSet(12,12,4,4)
 PokeI($E1C010B0,Neon_ScissorOn()) : PokeI($E1C010B8,nvcClipW)
 PokeI($E1C010C0,Neon_Error()) : PokeI($E1C010C8,NeonVkChromeError())
 rc=NeonVkChromeBoxBatchEnd()
 Neon_ScissorClear()
 If rc=0 : rc=NeonVkChromeEnd() : EndIf
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 353 : EndIf
 stateRecord($E1C01100)
 For i=0 To 4095 : PokeL($E2400000+i*4,PeekL(base+(i/64)*pitch+(i%64)*4)) : Next
 For i=0 To 15 : PokeA($E1C01200+i,neon_GlyphRow(65,i,0)) : Next
 ; No-op and clipping counters retain the native distinction: flat blank
 ; glyphs count as considered glyphs, without rectangles or vertices.
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,0,"   ",$FFFFFFFF) : EndIf
 If rc=0 : rc=Neon_Box(0,0,1,1,0) : EndIf
 If rc=0 : rc=Neon_Box(0,0,0,1,0) : EndIf
 If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,2000,"A",$FFFFFFFF) : EndIf
 If rc=0 : rc=Neon_TextTex(#NEON_FONT_UI,0,2000,"A",$FFFFFFFF) : EndIf
 Neon_ScissorSet(6,6,4,4)
 If rc=0 : rc=Neon_Box(0,0,1,1,$FFFFFFFF) : EndIf
 If rc=0 : rc=Neon_TextTex(#NEON_FONT_UI,-1000,0,"A",$FFFFFFFF) : EndIf
 If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,32,"A",$FFFFFFFF) : EndIf
 If rc<>0 Or Neon_ScissorOn()<>1 : NeonVkChromeAbort() : ProcedureReturn 356 : EndIf
 Neon_ScissorClear()
 stateRecord($E1C01400)
 If Neon_ScissorOn()<>0 Or Neon_Glyphs()<>3 Or Neon_Clipped()<>5 Or nvcVertices<>0 Or nvcDrawCount<>0 : NeonVkChromeAbort() : ProcedureReturn 357 : EndIf
 rc=NeonVkChromeAbort() : stateRecord($E1C01450)
 If rc<>0 Or Neon_Clipped()<>0 Or Neon_Glyphs()<>0 Or Neon_ScissorOn()<>0 Or Neon_Error()<>0 : ProcedureReturn 358 : EndIf
 ; Frontend validation and owner failures must update one public error in
 ; order; native GPU work must not overwrite that owner with private state.
 rc=NeonFontUse(0,8,16,32,126)
 If rc<>#NEON_ERR_FONT Or Neon_Error()<>#NEON_ERR_FONT : ProcedureReturn 359 : EndIf
 rc=NeonRebindSurface(0,800,1280,3200,4096000,#V3D_OFMT_RGBA8,45)
 If rc<>#NEON_ERR_ARGS Or Neon_Error()<>#NEON_ERR_ARGS : ProcedureReturn 371 : EndIf
 query=gNeonStateQuery : writer=gNeonStateError
 rc=NeonStateBackendInstall(@NeonVkChromeState,0)
 If rc<>#NEON_ERR_ARGS Or Neon_Error()<>#NEON_ERR_ARGS Or gNeonStateQuery<>query Or gNeonStateError<>writer Or NeonStateBackendActive()<>1 : ProcedureReturn 360 : EndIf
 rc=NeonVkChromeBox(0,0,1,1,$FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_STATE Or Neon_Error()<>#NEON_VK_CHROME_ERR_STATE : ProcedureReturn 361 : EndIf
 If NeonVkChromeState(999)<>#NEON_ERR_ARGS Or Neon_Error()<>#NEON_VK_CHROME_ERR_STATE : ProcedureReturn 362 : EndIf
 oldReady=nvcReady : oldHW=gNeonReady
 nvcReady=0
 If Neon_Ready()<>0 Or NeonHardwareReady()<>1 Or avkBackendCaps()=0 : nvcReady=oldReady : gNeonReady=oldHW : ProcedureReturn 363 : EndIf
 nvcReady=1 : gNeonReady=0
 If Neon_Ready()<>1 Or NeonHardwareReady()<>0 Or avkBackendCaps()<>0 : nvcReady=oldReady : gNeonReady=oldHW : ProcedureReturn 364 : EndIf
 nvcReady=oldReady : gNeonReady=oldHW
 ; Native fallback is independent data, not a copy of the renderer ledger.
 neon_nDraws=101 : neon_nBoxes=102 : neon_nGlyphs=103 : neon_nRuns=104 : neon_nVerts=105
 neon_nTDraws=106 : neon_nTGlyphs=107 : neon_nTVerts=108 : neon_nClipped=109 : neon_err=77
 rc=NeonStateBackendInstall(0,0)
 stateRecord($E1C01500)
 If rc<>0 Or NeonStateBackendActive()<>0 Or Neon_Error()<>77 : ProcedureReturn 365 : EndIf
 rc=NeonStateBackendInstall(@NeonVkChromeState,@NeonVkChromeStateError)
 If rc<>0 Or Neon_Draws()<>0 Or Neon_Error()<>#NEON_VK_CHROME_ERR_STATE : ProcedureReturn 366 : EndIf
 ; Replacing the complete draw family clears the old query pair atomically.
 rc=NeonDrawBackendInstall(@NeonVkChromeBox,@NeonVkChromeText,@NeonVkChromeTextTex,@NeonVkChromeScissorSet,@NeonVkChromeScissorClear,@NeonVkChromeFanBegin,@NeonVkChromeFanPoint,@NeonVkChromeFanEnd,@NeonVkChromeFanOutline,@NeonVkChromeLinesBegin,@NeonVkChromeLine,@NeonVkChromeLinesEnd)
 If rc<>0 Or NeonStateBackendActive()<>0 Or gNeonStateQuery<>@neon_StateQueryUnbound Or gNeonStateError<>@neon_StateErrorUnbound : ProcedureReturn 367 : EndIf
 rc=NeonMeasureBackendInstall(@NeonVkChromeMeasureWidth,@NeonVkChromeMeasureLineHeight)
 If rc=0 : rc=NeonStateBackendInstall(@NeonVkChromeState,@NeonVkChromeStateError) : EndIf
 If rc<>0 Or Neon_Draws()<>0 : ProcedureReturn 368 : EndIf
 NeonVkChromeDestroy()
 stateRecord($E1C01580)
 If NeonStateBackendActive()<>0 Or Neon_Draws()<>101 Or gNeonStateQuery<>@neon_StateQueryUnbound Or gNeonStateError<>@neon_StateErrorUnbound : ProcedureReturn 369 : EndIf
 rc=NeonStateBackendInstall(@NeonVkChromeState,@NeonVkChromeStateError)
 If rc<>#NEON_ERR_ARGS Or NeonStateBackendActive()<>0 Or Neon_Error()<>#NEON_ERR_ARGS : ProcedureReturn 370 : EndIf
 PokeI($E1C01300,6)
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
s = s.replace(needle,'  PokeI($E1C01000,stateProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n'+needle,1)
s += '''
Procedure.i Main(services.i)
 Define report.i,i.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=BulkDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,stateLiveMemory())
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
