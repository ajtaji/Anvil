Procedure combinedCapture(imageBase.i,imagePitch.i,frame.i)
 Define x.i,y.i
 For y=0 To 63
  For x=0 To 63 : PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(imageBase+y*imagePitch+x*4)) : Next
 Next
EndProcedure
Procedure.i combinedDrawProof(phys.i,dev.i,queue.i,pool.i,renderPass.i,framebuffer.i,imageBase.i,imagePitch.i)
 Define rc.i,i.i,j.i,beforeVertices.i,beforeDraws.i,beforeFree.i,unchanged.i=1
 SafetyWatchdogStart(15)
 NeonFontSetup(#NEON_FONT_UI,1,0)
 For i=0 To 15 : PokeA($E1C01800+i,PeekA(neon_fbits+(65-32)*16+i)) : Next
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 220 : EndIf
 For i=0 To 4095
  rc=Neon_Box(i%64,i/64,1,1,Neon_RGBA(255,0,0,255))
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 221 : EndIf
 Next
 PokeI($E1C01008,4096)
 For i=0 To 2047
  If i=2047
   rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",Neon_RGBA(0,255,0,255))
  Else
   rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",Neon_RGBA(255,255,255,255))
  EndIf
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 222 : EndIf
 Next
 PokeI($E1C01010,2048)
 beforeVertices=nvcVertices : beforeDraws=nvcDrawCount : beforeFree=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+beforeVertices*24+i,$A5) : Next
 rc=Neon_Box(1,1,1,1,Neon_RGBA(0,0,255,255))
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY : NeonVkChromeAbort() : ProcedureReturn 223 : EndIf
 If nvcVertices<>beforeVertices Or nvcDrawCount<>beforeDraws Or avkRecordedDrawFreeCount<>beforeFree : unchanged=0 : EndIf
 For i=0 To 15
  If PeekA(nvcMapped+beforeVertices*24+i)<>$A5 : unchanged=0 : EndIf
 Next
 PokeI($E1C01018,beforeDraws) : PokeI($E1C01020,beforeVertices) : PokeI($E1C01028,beforeFree)
 PokeI($E1C01030,rc) : PokeI($E1C01038,unchanged)
 If unchanged=0 : NeonVkChromeAbort() : ProcedureReturn 224 : EndIf
 SafetyWatchdogPet()
 rc=NeonVkChromeEnd()
 SafetyWatchdogPet()
 PokeI($E1C01040,rc)
 If rc<>0 : ProcedureReturn 225 : EndIf
 If NeonVkChromePresentConsume()<>1 : ProcedureReturn 226 : EndIf
 combinedCapture(imageBase,imagePitch,0)
 SafetyWatchdogPet()
 NeonVkChromeDestroy()
 PokeI($E1C01048,avkRecordedDrawFreeCount)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,renderPass,framebuffer,800,1280,2,4)
 If rc<>0 : ProcedureReturn 227 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc<>0 : ProcedureReturn 228 : EndIf
 rc=Neon_Box(0,0,1,1,Neon_RGBA(0,0,255,255))
 If rc=0 : rc=Neon_Box(1,0,1,1,Neon_RGBA(255,255,255,255)) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 229 : EndIf
 beforeVertices=nvcVertices : beforeDraws=nvcDrawCount : beforeFree=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+beforeVertices*24+i,$5A) : Next
 rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",Neon_RGBA(0,255,0,255))
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY : NeonVkChromeAbort() : ProcedureReturn 230 : EndIf
 If nvcVertices<>beforeVertices Or nvcDrawCount<>beforeDraws Or avkRecordedDrawFreeCount<>beforeFree : unchanged=0 : EndIf
 For i=0 To 15
  If PeekA(nvcMapped+beforeVertices*24+i)<>$5A : unchanged=0 : EndIf
 Next
 PokeI($E1C01050,beforeDraws) : PokeI($E1C01058,beforeVertices) : PokeI($E1C01060,beforeFree)
 PokeI($E1C01068,rc) : PokeI($E1C01070,unchanged)
 If unchanged=0 : NeonVkChromeAbort() : ProcedureReturn 231 : EndIf
 rc=NeonVkChromeEnd()
 If rc<>0 : ProcedureReturn 232 : EndIf
 If NeonVkChromePresentConsume()<>1 : ProcedureReturn 233 : EndIf
 combinedCapture(imageBase,imagePitch,1)
 ProcedureReturn 0
EndProcedure
