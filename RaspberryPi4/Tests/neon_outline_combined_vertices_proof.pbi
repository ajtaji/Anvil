Global Dim streamX0.i[8]
Global Dim streamY0.i[8]
Global Dim streamX1.i[8]
Global Dim streamY1.i[8]
Global Dim streamSeed.i[5]
Global Dim streamLayoutSeed.i[7]

Procedure streamSegments()
 streamX0[0]=4 : streamY0[0]=4 : streamX1[0]=28 : streamY1[0]=4
 streamX0[1]=28 : streamY0[1]=8 : streamX1[1]=4 : streamY1[1]=8
 streamX0[2]=4 : streamY0[2]=12 : streamX1[2]=4 : streamY1[2]=28
 streamX0[3]=8 : streamY0[3]=28 : streamX1[3]=8 : streamY1[3]=12
 streamX0[4]=12 : streamY0[4]=12 : streamX1[4]=12 : streamY1[4]=12
 streamX0[5]=20 : streamY0[5]=16 : streamX1[5]=52 : streamY1[5]=24
 streamX0[6]=20 : streamY0[6]=32 : streamX1[6]=28 : streamY1[6]=60
 streamX0[7]=60 : streamY0[7]=44 : streamX1[7]=28 : streamY1[7]=36
EndProcedure

Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure streamCapture(base.i,pitch.i,frame.i)
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


Procedure.i outlineUsedBytes()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+avkMemSize[i] : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,quads.i=74639,accepted.i,slots.i,rows.i,draws.i,unchanged.i=1,start.i,before.i,guard.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 If quads>#NEON_VK_CHROME_MAX_VERTEX_QUADS : quads=#NEON_VK_CHROME_MAX_VERTEX_QUADS : EndIf
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,10240,quads)
 If rc<>0 : PokeI($E1C01310,rc) : ProcedureReturn 791 : EndIf
 NeonFontSetup(#NEON_FONT_UI,1,0)
 For i=0 To 15 : PokeA($E1C01800+i,PeekA(neon_fbits+(65-32)*16+i)) : Next
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 792 : EndIf
 For i=0 To #NEON_MAX_VERTS-4
  NeonFanPoint(-64,-64)
  If (i & 8191)=0 : SafetyWatchdogPet() : EndIf
 Next
 NeonFanPoint(28,-64) : NeonFanPoint(28,28) : NeonFanPoint(-64,28)
 before=outlineUsedBytes() : SafetyWatchdogPet()
 rc=NeonFanOutline($FFFFFFFF)
 If rc=0 : rc=NeonFanEnd($FF00FF00) : EndIf
 If rc<>0 : PokeI($E1C01310,rc) : NeonVkChromeAbort() : ProcedureReturn 793 : EndIf
 For i=0 To #NEON_MAX_TDRAWS-1
  slots=nvcVertices : rows=avkRecordedDrawFreeCount : draws=nvcDrawCount
  rc=Neon_TextTex(#NEON_FONT_UI,0,0,"AAAAAAAA",$FFFFFF00)
  If rc<>0 : Break : EndIf
  accepted=accepted+1
  If (i & 127)=0 : SafetyWatchdogPet() : EndIf
 Next
 If accepted<#NEON_MAX_TDRAWS
  For i=0 To 15 : PokeA(nvcMapped+slots*24+i,$A5) : Next
  rc=Neon_TextTex(#NEON_FONT_UI,0,0,"AAAAAAAA",$FFFFFF00)
  If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>slots Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows : unchanged=0 : EndIf
  For i=0 To 15 : If PeekA(nvcMapped+slots*24+i)<>$A5 : unchanged=0 : EndIf : Next
 Else
  slots=nvcVertices
  For i=0 To 15 : PokeA(nvcMapped+slots*24+i,$A5) : Next
 EndIf
 PokeI($E1C01010,Neon_Verts()) : PokeI($E1C01018,accepted) : PokeI($E1C01020,Neon_TexVerts())
 PokeI($E1C01028,nvcDrawCount) : PokeI($E1C01030,nvcVertices) : PokeI($E1C01038,rc)
 PokeI($E1C01040,unchanged) : PokeI($E1C01048,quads) : PokeI($E1C01050,before)
 PokeI($E1C01058,outlineUsedBytes()) : PokeI($E1C01068,avkRecordedDrawFreeCount)
 PokeI($E1C01070,nvcOutlinePointsUsed) : PokeI($E1C01078,nvcOutlineClosingsUsed)
 If accepted<#NEON_MAX_TDRAWS
  If quads<>65536 Or accepted<>910 Or unchanged<>1 Or Neon_Verts()<>262144 Or Neon_TexVerts()<>43680 Or nvcVertices<>393206 : NeonVkChromeAbort() : ProcedureReturn 794 : EndIf
  rc=NeonVkChromeAbort() : NeonVkChromeDestroy() : ProcedureReturn rc
 EndIf
 If accepted<>2048 Or Neon_Verts()<>262144 Or Neon_TexVerts()<>98304 Or nvcVertices<>447830 Or nvcDrawCount<>2051 : NeonVkChromeAbort() : ProcedureReturn 795 : EndIf
 guard=nvcMapped+slots*24
 SafetyWatchdogPet() : start=Micros() : rc=NeonVkChromeEnd() : PokeI($E1C01060,Micros()-start)
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01318,rc) : ProcedureReturn 796 : EndIf
 For i=0 To 15 : If PeekA(guard+i)<>$A5 : ProcedureReturn 797 : EndIf : Next
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 NeonVkChromeDestroy() : ProcedureReturn 0
EndProcedure
