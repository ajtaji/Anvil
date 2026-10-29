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
 Define i.i,rc.i,rows.i,before.i,start.i,slots.i,close.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,10240,65536)
 If rc<>0 : ProcedureReturn 751 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 752 : EndIf
 For i=0 To #NEON_MAX_VERTS-4
  NeonFanPoint(-64,-64)
  If (i & 8191)=0 : SafetyWatchdogPet() : EndIf
 Next
 NeonFanPoint(28,-64) : NeonFanPoint(28,28) : NeonFanPoint(-64,28)
 PokeI($E1C01010,nvcPathCount)
 before=outlineUsedBytes() : rows=avkRecordedDrawFreeCount
 PokeI($E1C01060,before)
 For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
 SafetyWatchdogPet() : start=Micros() : rc=NeonFanOutline($FFFFFFFF)
 PokeI($E1C01018,rc) : PokeI($E1C01020,nvcVertices) : PokeI($E1C01070,Micros()-start)
 If rc<>0
  If rc<>#VK_ERROR_OUT_OF_DEVICE_MEMORY Or outlineUsedBytes()<>before Or nvcVertices<>0 Or nvcDrawCount<>0 Or Neon_Draws()<>0 Or Neon_Verts()<>#NEON_MAX_VERTS Or nvcPathCount<>#NEON_MAX_VERTS Or avkRecordedDrawFreeCount<>rows Or nvcOutlineBuffer|nvcOutlineMemory|nvcOutlineMapped|nvcOutlineListPipeline|nvcOutlineFanPipeline : NeonVkChromeAbort() : ProcedureReturn 753 : EndIf
  For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 754 : EndIf : Next
  PokeI($E1C01068,outlineUsedBytes())
  rc=NeonVkChromeAbort() : NeonVkChromeDestroy()
  ProcedureReturn rc
 EndIf
 If nvcVertices<>349526 Or nvcOutlinePointsUsed<>#NEON_MAX_VERTS Or nvcOutlineClosingsUsed<>1 Or nvcDrawCount<>2 Or Neon_Draws()<>1 : NeonVkChromeAbort() : ProcedureReturn 755 : EndIf
 slots=nvcVertices : close=nvcFanIndexedClose
 For i=0 To 15 : PokeA(nvcMapped+slots*24+i,$A5) : Next
 SafetyWatchdogPet() : rc=NeonFanOutline($FFFFFFFF)
 PokeI($E1C01028,nvcVertices)
 If rc<>0 Or nvcVertices<>slots Or nvcOutlineClosingsUsed<>1 Or nvcFanIndexedClose<>close Or nvcOutlinePointsUsed<>#NEON_MAX_VERTS : NeonVkChromeAbort() : ProcedureReturn 756 : EndIf
 SafetyWatchdogPet() : rc=NeonFanEnd($FF00FF00)
 PokeI($E1C01030,nvcVertices) : PokeI($E1C01038,Neon_Draws()) : PokeI($E1C01040,Neon_Verts()) : PokeI($E1C01048,nvcDrawCount)
 PokeI($E1C01050,nvcOutlinePointsUsed) : PokeI($E1C01058,nvcOutlineClosingsUsed) : PokeI($E1C01068,outlineUsedBytes())
 If rc<>0 Or nvcVertices<>slots Or Neon_Draws()<>3 Or Neon_Verts()<>#NEON_MAX_VERTS Or nvcDrawCount<>5 : NeonVkChromeAbort() : ProcedureReturn 757 : EndIf
 For i=0 To 15 : If PeekA(nvcMapped+slots*24+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 758 : EndIf : Next
 SafetyWatchdogPet() : start=Micros() : rc=NeonVkChromeEnd() : PokeI($E1C01078,Micros()-start)
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01310,rc) : ProcedureReturn 759 : EndIf
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
