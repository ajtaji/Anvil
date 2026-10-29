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


Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,frame.i,rc.i,first.i,p.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,16)
 PokeI($E1C01300,rc) : PokeI($E1C01308,nvcCreateStage)
 If rc<>0 : ProcedureReturn 711 : EndIf
 For frame=0 To 1
  SafetyWatchdogPet() : rc=NeonVkChromeBegin(@nwClear[0])
  If rc<>0 : ProcedureReturn 712 : EndIf
  If frame=0
   rc=NeonFanBegin()
   NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
   If rc=0 : rc=NeonFanOutline($FFFFFFFF) : EndIf
   PokeI($E1C01310,rc)
   PokeI($E1C01010,nvcVertices)
   If rc=0 : rc=NeonFanOutline($FFFFFFFF) : EndIf
   PokeI($E1C01018,nvcVertices) : PokeI($E1C01028,nvcOutlinePointsUsed) : PokeI($E1C01030,nvcOutlineClosingsUsed)
   If rc=0 : rc=NeonFanEnd($FF00FF00) : EndIf
   PokeI($E1C01020,nvcVertices) : PokeI($E1C01038,Neon_Draws()) : PokeI($E1C01040,Neon_Verts()) : PokeI($E1C01048,nvcDrawCount)
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 716 : EndIf
   If nvcVertices<>6 Or nvcOutlinePointsUsed<>4 Or nvcOutlineClosingsUsed<>1 Or Neon_Draws()<>3 Or Neon_Verts()<>4 Or nvcDrawCount<>5 : NeonVkChromeAbort() : ProcedureReturn 713 : EndIf
  Else
   For i=0 To 1
    first=NeonVkChromeLinesReserve(4) : If first<0 : NeonVkChromeAbort() : ProcedureReturn 714 : EndIf
    p=NeonVkChromeVertexAddress(first)
    NeonVkChromeLineQuadAt(p,4,4,28,4) : NeonVkChromeLineQuadAt(p+144,28,4,28,28)
    NeonVkChromeLineQuadAt(p+288,28,28,4,28) : NeonVkChromeLineQuadAt(p+432,4,28,4,4)
    rc=NeonVkChromeLinesDraw(first,4,$FFFFFFFF)
    If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 715 : EndIf
   Next
   rc=NeonFanBegin()
   NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
   If rc=0 : rc=NeonFanEnd($FF00FF00) : EndIf
  EndIf
  If rc<>0 : NeonVkChromeAbort() : PokeI($E1C01310,rc) : ProcedureReturn 716 : EndIf
  SafetyWatchdogPet() : rc=NeonVkChromeEnd()
  If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01318,rc) : ProcedureReturn 717 : EndIf
  streamCapture(base,pitch,frame) : PokeI($E1C01008,frame+1)
 Next
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
