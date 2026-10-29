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
 Define rc.i,before.i,rows.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,16)
 If rc<>0 : ProcedureReturn 721 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 722 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
 before=streamMemory() : rows=avkRecordedDrawFreeCount
 rc=NeonFanOutline($FFFFFFFF)
 PokeI($E1C01008,rc) : PokeI($E1C01010,streamMemory()-before) : PokeI($E1C01018,nvcVertices)
 PokeI($E1C01020,nvcDrawCount) : PokeI($E1C01028,Neon_Verts()) : PokeI($E1C01030,nvcPathCount)
 PokeI($E1C01038,#ANVIL_VK_MAX_PIPELINES) : PokeI($E1C01040,avkRecordedDrawFreeCount-rows)
 If rc<>#VK_ERROR_TOO_MANY_OBJECTS Or streamMemory()<>before Or nvcVertices<>0 Or nvcDrawCount<>0 Or Neon_Draws()<>0 Or Neon_Verts()<>4 Or nvcPathCount<>4 Or avkRecordedDrawFreeCount<>rows Or nvcOutlineBuffer|nvcOutlineMemory|nvcOutlineMapped|nvcOutlineListPipeline|nvcOutlineFanPipeline : NeonVkChromeAbort() : ProcedureReturn 723 : EndIf
 If nvcReady<>1 Or NeonDrawBackendActive()<>1 Or avkPipeSlot(nvcPipeline)=0 Or avkPipeSlot(nvcFanPipeline)=0 Or avkPipeSlot(nvcLinePipeline)=0 : NeonVkChromeAbort() : ProcedureReturn 724 : EndIf
 rc=NeonVkChromeAbort() : NeonVkChromeDestroy()
 ProcedureReturn rc
EndProcedure
