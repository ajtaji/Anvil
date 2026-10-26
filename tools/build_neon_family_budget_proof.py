#!/usr/bin/env python3
"""Build native-unit Neon family capacity evidence; requires the physical Pi 4."""
from pathlib import Path
import os, subprocess, sys, json, hashlib

import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build the returning physical Pi 4 separate-family capacity proof; never executes it.')
ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler')
args=ap.parse_args();r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper=r'''Global Dim familyState.i[8]

Procedure familySnap()
 Define i.i
 familyState[0]=nvcFlatDraws : familyState[1]=nvcFlatVertices
 familyState[2]=nvcTexDraws : familyState[3]=nvcTexVertices
 familyState[4]=nvcVertices : familyState[5]=nvcDrawCount
 familyState[6]=avkRecordedDrawFreeCount : familyState[7]=AnvilVkFaultCode()
 For i=0 To 15 : PokeA(nvcMapped+nvcVertices*24+i,$A5) : Next
EndProcedure

Procedure.i familySame()
 Define i.i
 If familyState[0]<>nvcFlatDraws Or familyState[1]<>nvcFlatVertices Or familyState[2]<>nvcTexDraws Or familyState[3]<>nvcTexVertices : ProcedureReturn 0 : EndIf
 If familyState[4]<>nvcVertices Or familyState[5]<>nvcDrawCount Or familyState[6]<>avkRecordedDrawFreeCount Or familyState[7]<>AnvilVkFaultCode() : ProcedureReturn 0 : EndIf
 For i=0 To 15
  If PeekA(nvcMapped+nvcVertices*24+i)<>$A5 : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure.i familyLiveMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure familyCapture(base.i,pitch.i,frame.i)
 Define x.i,y.i,px.i,py.i
 For y=0 To 63
  For x=0 To 63
   If nvcRotation=90 : px=nvcLogicalH-1-y : py=x
   ElseIf nvcRotation=180 : px=nvcLogicalW-1-x : py=nvcLogicalH-1-y
   ElseIf nvcRotation=270 : px=y : py=nvcLogicalW-1-x
   Else : px=x : py=y : EndIf
   PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(base+py*pitch+px*4))
  Next
 Next
EndProcedure

Procedure.i familyBudgetProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,j.i,rc.i,first.i,font.i,oldVerts.i,oldError.i,rects.i,cost.i,turn.i,lw.i,lh.i
 Define Dim text.a[102]
 Define pixel.l, particle.NvcParticle
 NeonVkChromeDestroy()
 SafetyWatchdogStart(15)
 PokeI($E1C01008,1)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,6144,65536)
 PokeI($E1C011A0,rc) : PokeI($E1C011A8,nvcCreateStage)
 If rc<>0 : ProcedureReturn 291 : EndIf
 ; Compare logical bitmap costs against the native rectangle emitter itself.
 oldVerts=neon_nVerts : oldError=neon_err
 For font=0 To 1
  For i=32 To 126
   neon_nVerts=0 : rects=neon_GlyphRects(i,0,0,font)
   If nvcBitmapGlyphCost(i,font)<>rects*6 Or neon_nVerts<>rects*6 : ProcedureReturn 292 : EndIf
  Next
 Next
 neon_nVerts=oldVerts : neon_err=oldError
 PokeI($E1C01010,190)
 cost=nvcBitmapGlyphCost(65,#NEON_FONT_UI) : PokeI($E1C01018,cost)
 For i=0 To 15 : PokeA($E1C01200+i,neon_GlyphRow(65,i,0)) : Next
 ; Both draw families fill the common 6144 rows independently, then Abort.
 SafetyWatchdogPet()
 PokeI($E1C01008,2)
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 293 : EndIf
 For i=1 To 4096
  rc=Neon_Box(0,0,1,1,$FFFF0000)
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 294 : EndIf
 Next
 familySnap()
 rc=Neon_Box(0,0,1,1,$FFFF0000)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 295 : EndIf
 For i=1 To 2048
  rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FF00FF00)
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 296 : EndIf
 Next
 If nvcFlatDraws<>4096 Or nvcTexDraws<>2048 Or nvcDrawCount<>6144 : NeonVkChromeAbort() : ProcedureReturn 297 : EndIf
 familySnap()
 rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FF00FF00)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 298 : EndIf
 PokeI($E1C01020,nvcFlatDraws) : PokeI($E1C01028,nvcTexDraws)
 PokeI($E1C01030,nvcFlatVertices) : PokeI($E1C01038,nvcTexVertices)
 rc=NeonVkChromeAbort()
 If rc<>0 Or avkRecordedDrawFreeCount<>6144 Or nvcFlatDraws<>0 Or nvcTexDraws<>0 Or nvcFlatVertices<>0 Or nvcTexVertices<>0 : ProcedureReturn 299 : EndIf
 ; Exhaust texture records first, proving a subsequent flat record still fits.
 SafetyWatchdogPet()
 PokeI($E1C01008,3)
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 300 : EndIf
 For i=1 To 2048
  rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FF00FF00)
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 301 : EndIf
 Next
 familySnap()
 rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FF00FF00)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 302 : EndIf
 rc=Neon_Box(0,0,1,1,$FFFF0000)
 If rc<>0 Or nvcFlatDraws<>1 Or nvcTexDraws<>2048 : NeonVkChromeAbort() : ProcedureReturn 303 : EndIf
 rc=NeonVkChromeAbort()
 If rc<>0 : ProcedureReturn 304 : EndIf
 ; Fill all 262144 native flat input units. Physical lowering is separate.
 SafetyWatchdogPet()
 PokeI($E1C01008,4)
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=NeonVkChromeBoxBatchBegin() : EndIf
 If rc<>0 : ProcedureReturn 305 : EndIf
 For i=1 To 43690
  rc=Neon_Box(0,0,1,1,$FFFF0000)
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 306 : EndIf
 Next
 familySnap()
 rc=Neon_Box(0,0,1,1,$FFFF0000)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 307 : EndIf
 rc=NeonVkChromeBoxBatchEnd()
 If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 308 : EndIf
 For i=1 To 4 : NeonFanPoint(0,0) : Next
 If nvcFlatVertices<>262144 : NeonVkChromeAbort() : ProcedureReturn 309 : EndIf
 familySnap() : NeonFanPoint(0,0)
 If nvcPathError<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 310 : EndIf
 rc=NeonFanEnd($FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY : NeonVkChromeAbort() : ProcedureReturn 311 : EndIf
 familySnap() : rc=Neon_Text(#NEON_FONT_UI,0,0,"A A",$FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 312 : EndIf
 rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FFFFFFFF)
 If rc<>0 Or nvcTexVertices<>6 : NeonVkChromeAbort() : ProcedureReturn 313 : EndIf
 PokeI($E1C01040,nvcFlatVertices) : PokeI($E1C01048,nvcTexVertices)
 rc=NeonVkChromeAbort()
 If rc<>0 : ProcedureReturn 314 : EndIf
 ; 163*100+84 visible cells exactly fill 98304 textured vertices.
 SafetyWatchdogPet()
 PokeI($E1C01008,5)
 For i=0 To 99 : text[i]=65 : Next : text[100]=0
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 315 : EndIf
 For i=1 To 163
  rc=Neon_TextTex(#NEON_FONT_UI,0,0,@text[0],$FFFFFFFF)
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 316 : EndIf
 Next
 text[84]=0
 rc=Neon_TextTex(#NEON_FONT_UI,0,0,@text[0],$FFFFFFFF)
 If rc<>0 Or nvcTexVertices<>98304 Or nvcTexDraws<>164 : NeonVkChromeAbort() : ProcedureReturn 317 : EndIf
 familySnap() : rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A A",$FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 318 : EndIf
 rc=Neon_Box(0,0,1,1,$FFFF0000)
 If rc<>0 Or nvcFlatVertices<>6 : NeonVkChromeAbort() : ProcedureReturn 319 : EndIf
 PokeI($E1C01050,nvcFlatVertices) : PokeI($E1C01058,nvcTexVertices)
 rc=NeonVkChromeAbort()
 If rc<>0 : ProcedureReturn 320 : EndIf
 NeonVkChromeDestroy()
 ; Four actual GPU frames verify logical clips, no-ops and repeated fan use.
 For turn=0 To 3
  SafetyWatchdogPet()
  PokeI($E1C01008,6+turn)
  rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,32,64)
  If rc<>0 : ProcedureReturn 321 : EndIf
  lw=800 : lh=1280 : If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(fb,lw,lh,800,1280,pitch,turn*90)
  If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
  If rc<>0 : ProcedureReturn 322 : EndIf
  familySnap()
  rc=Neon_Box(0,0,8,8,0)
  If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,0,"A",0) : EndIf
  If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,0,"   ",$FFFFFFFF) : EndIf
  If rc=0 : rc=Neon_Text(#NEON_FONT_UI,-8000,0,"A",$FFFFFFFF) : EndIf
  Neon_ScissorSet(48,0,8,8)
  If rc=0 : rc=Neon_Box(0,0,8,8,$FFFFFFFF) : EndIf
  If rc=0 : rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FFFFFFFF) : EndIf
  Neon_ScissorClear()
  If rc<>0 Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 323 : EndIf
  Neon_ScissorSet(6,6,4,4)
  rc=Neon_Box(4,4,8,8,$FFFF0000)
  Neon_ScissorClear()
  If rc=0 : rc=Neon_Text(#NEON_FONT_UI,4,20,"A A",$FF00FF00) : EndIf
  If rc=0 : rc=Neon_TextTex(#NEON_FONT_UI,4,40,"A A",$FF0000FF) : EndIf
  If rc=0 : rc=NeonFanBegin() : EndIf
  NeonFanPoint(40,4) : NeonFanPoint(48,4) : NeonFanPoint(48,12) : NeonFanPoint(40,12)
  If rc=0 : rc=NeonFanOutline($FFFFFF00) : EndIf
  If rc=0 : rc=NeonFanOutline($FFFFFF00) : EndIf
  If rc=0 : rc=NeonFanEnd($FF00FFFF) : EndIf
  If rc=0 : rc=NeonLinesBegin() : EndIf
  NeonLine(4,60,28,60)
  If rc=0 : rc=NeonLinesEnd($FFFFFFFF) : EndIf
  If rc<>0 Or nvcFlatDraws<>6 Or nvcFlatVertices<>12+cost*2 Or nvcTexDraws<>1 Or nvcTexVertices<>18 Or nvcVertices<>94 : NeonVkChromeAbort() : ProcedureReturn 324 : EndIf
  PokeI($E1C01060+turn*40,nvcFlatDraws) : PokeI($E1C01068+turn*40,nvcFlatVertices)
  PokeI($E1C01070+turn*40,nvcTexDraws) : PokeI($E1C01078+turn*40,nvcTexVertices)
  PokeI($E1C01080+turn*40,nvcVertices)
  rc=NeonVkChromeEnd()
  If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 325 : EndIf
  familyCapture(base,pitch,turn)
  NeonVkChromeDestroy()
 Next
 SafetyWatchdogPet()
 PokeI($E1C01008,10)
 pixel=$FFFFFFFF
 rc=NeonVkChromeSpriteSource(@pixel,1,1)
 If rc=0 : rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,32,64) : EndIf
 If rc=0 : rc=NeonVkChromeImageSpriteReplace(@pixel,1,1) : EndIf
 particle\x=-32 : particle\y=-32 : particle\width=1 : particle\height=1 : particle\colour=$FFFFFFFF : particle\ignoreCamera=1
 If rc=0 : rc=NeonVkChromeParticlesPrepare(@particle,1) : EndIf
 If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc<>0 : ProcedureReturn 327 : EndIf
 ; Seed only a private diagnostic ledger to exercise less common entry-point
 ; refusal boundaries cheaply. The real maximum loads were exercised above.
 nvcTexVertices=98304 : familySnap()
 rc=NeonVkChromeSprite(-32,-32,0,0,1,1,1,1,$FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 328 : EndIf
 rc=NeonVkChromeSpriteTransform(-32,-32,0,0,1,1,1,1,$FFFFFFFF,0,0,0,65536,1)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 329 : EndIf
 rc=NeonVkChromeImageSpriteDraw(-32,-32,0,0,1,1,1,1,$FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 330 : EndIf
 rc=NeonVkChromeParticlesDrawPrepared()
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 331 : EndIf
 nvcTexVertices=0
 rc=NeonVkChromeSprite(-32,-32,0,0,1,1,1,1,$FFFFFFFF)
 If rc=0 : rc=NeonVkChromeSpriteTransform(-32,-32,0,0,1,1,1,1,$FFFFFFFF,0,0,0,65536,1) : EndIf
 If rc=0 : rc=NeonVkChromeImageSpriteDraw(-32,-32,0,0,1,1,1,1,$FFFFFFFF) : EndIf
 If rc=0 : rc=NeonVkChromeParticlesDrawPrepared() : EndIf
 If rc<>0 Or nvcTexDraws<>4 Or nvcTexVertices<>24 : NeonVkChromeAbort() : ProcedureReturn 332 : EndIf
 rc=NeonVkChromeSpriteBatchBegin()
 If rc=0 : rc=NeonVkChromeSpriteBatchAdd(1,-32,-32,0,0,1,1,1,1,$FFFFFFFF,0,0,0,65536,1) : EndIf
 If rc=0 : rc=NeonVkChromeSpriteBatchAdd(1,-32,-32,0,0,1,1,1,1,$FFFFFFFF,0,0,0,65536,1) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 333 : EndIf
 nvcTexVertices=98298 : familySnap() : rc=NeonVkChromeSpriteBatchEnd()
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 334 : EndIf
 nvcTexVertices=24 : rc=NeonVkChromeSpriteBatchEnd()
 If rc<>0 Or nvcTexVertices<>36 Or nvcTexDraws<>6 : NeonVkChromeAbort() : ProcedureReturn 335 : EndIf
 nvcFlatVertices=262144 : familySnap() : first=NeonVkChromeLinesReserve(1)
 If first<>-1 Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 336 : EndIf
 rc=NeonVkChromeTextAngled(#NEON_FONT_UI,-32,-32,"A",$FFFFFFFF,65536,0)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or familySame()=0 : NeonVkChromeAbort() : ProcedureReturn 337 : EndIf
 nvcFlatVertices=0 : first=NeonVkChromeLinesReserve(1)
 If first<0 : NeonVkChromeAbort() : ProcedureReturn 338 : EndIf
 NeonVkChromeLineQuadAt(NeonVkChromeVertexAddress(first),-32,-32,-30,-32)
 rc=NeonVkChromeLinesDraw(first,1,$FFFFFFFF)
 If rc=0 : rc=NeonVkChromeTextAngled(#NEON_FONT_UI,-32,-32,"A",$FFFFFFFF,65536,0) : EndIf
 If rc<>0 Or nvcFlatDraws<>2 Or nvcFlatVertices<>6+cost Or nvcVertices<>48 Or nvcDrawCount<>8 : NeonVkChromeAbort() : ProcedureReturn 339 : EndIf
 PokeI($E1C01300,7) : PokeI($E1C01308,nvcFlatVertices) : PokeI($E1C01310,nvcTexVertices)
 rc=NeonVkChromeAbort()
 If rc<>0 : ProcedureReturn 340 : EndIf
 ; The clear-only backend sentinel consumes no logical family units.
 SafetyWatchdogPet()
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=Neon_Text(#NEON_FONT_UI,0,0,"   ",$FFFFFFFF) : EndIf
 If rc<>0 Or nvcVertices<>0 Or nvcDrawCount<>0 : NeonVkChromeAbort() : ProcedureReturn 341 : EndIf
 rc=NeonVkChromeEnd()
 If rc<>0 Or nvcVertices<>6 Or nvcDrawCount<>1 Or nvcFlatDraws<>0 Or nvcTexDraws<>0 Or nvcFlatVertices<>0 Or nvcTexVertices<>0 : ProcedureReturn 342 : EndIf
 If NeonVkChromePresentConsume()<>1 : ProcedureReturn 343 : EndIf
 familyCapture(base,pitch,4)
 NeonVkChromeDestroy()
 PokeI($E1C01008,11)
 If nvcFlatDraws<>0 Or nvcFlatVertices<>0 Or nvcTexDraws<>0 Or nvcTexVertices<>0 : ProcedureReturn 326 : EndIf
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
s = s.replace(needle,'  PokeI($E1C01000,familyBudgetProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n'+needle,1)
s += '''
Procedure.i Main(services.i)
 Define report.i,i.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=BulkDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,familyLiveMemory())
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
