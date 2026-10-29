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

Procedure.i streamMixed(base.i,pitch.i,fb.i)
 Define turn.i,path.i,j.i,rc.i,first.i,p.i,lw.i,lh.i,row.i
 For turn=0 To 3
  lw=800 : lh=1280 : If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(fb,lw,lh,800,1280,pitch,turn*90)
  If rc<>0 : ProcedureReturn 601 : EndIf
  For path=0 To 1
   SafetyWatchdogPet()
   rc=NeonVkChromeBegin(@nwClear[0])
   If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,0,0,0,0,1,1,64,64,$FFFF0000) : EndIf
   If rc=0 : rc=Neon_Box(2,2,60,60,$FF000080) : EndIf
   Neon_ScissorSet(8,8,40,40)
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 602 : EndIf
   If path=0
    rc=NeonLinesBegin()
    For j=0 To 7 : NeonLine(streamX0[j],streamY0[j],streamX1[j],streamY1[j]) : Next
    If rc=0 : rc=NeonLinesEnd($80FFFFFF) : EndIf
   Else
    first=NeonVkChromeLinesReserve(8)
    If first<0 : NeonVkChromeAbort() : ProcedureReturn 603 : EndIf
    p=NeonVkChromeVertexAddress(first)
    For j=0 To 7 : NeonVkChromeLineQuadAt(p+j*144,streamX0[j],streamY0[j],streamX1[j],streamY1[j]) : Next
    rc=NeonVkChromeLinesDraw(first,8,$80FFFFFF)
   EndIf
   If rc=0 : rc=Neon_Box(40,16,8,8,$FF00FF00) : EndIf
   Neon_ScissorClear()
   If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,52,52,0,0,1,1,8,8,$FFFFFF00) : EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 604 : EndIf
   row=$E1C00400+(turn*2+path)*48
   PokeI(row,Neon_Draws()) : PokeI(row+8,Neon_Verts())
   PokeI(row+16,Neon_TexDraws()) : PokeI(row+24,Neon_TexVerts())
   PokeI(row+32,NeonVkChromeDrawCount()) : PokeI(row+40,NeonVkChromeVertexCount())
   If Neon_Draws()<>3 Or Neon_Verts()<>(28+32*path) Or Neon_TexDraws()<>2 Or Neon_TexVerts()<>12 Or NeonVkChromeDrawCount()<>5 Or NeonVkChromeVertexCount()<>(35+37*path) : NeonVkChromeAbort() : ProcedureReturn 605 : EndIf
   rc=NeonVkChromeEnd()
   If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 606 : EndIf
   streamCapture(base,pitch,turn*2+path)
   PokeI($E1C01008,turn*2+path+1)
  Next
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,j.i,rc.i,slot.i,rows.i,verts.i,draws.i,before.i,start.i
 Define pixel.l,ci.VkBufferCreateInfo,li.VkPipelineLayoutCreateInfo
 streamSegments()
 NeonVkChromeDestroy()
 SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,6144,65536)
 PokeI($E1C01300,rc) : PokeI($E1C01308,nvcCreateStage)
 If rc<>0 : ProcedureReturn 607 : EndIf
 pixel=$FFFFFFFF
 rc=NeonVkChromeImageSpriteReplaceBGRAId(1,@pixel,1,1)
 If rc<>0 : ProcedureReturn 608 : EndIf
 rc=streamMixed(base,pitch,fb)
 If rc<>0 : ProcedureReturn rc : EndIf
 SafetyWatchdogPet()
 rc=NeonVkChromeRebind(fb,800,1280,800,1280,pitch,0)
 If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,56,4,0,0,1,1,4,4,$FFFF0000) : EndIf
 If rc=0 : rc=NeonLinesBegin() : EndIf
 If rc<>0 : ProcedureReturn 609 : EndIf
 ; Earlier lines are valid, fully clipped primitives. Visible terminal
 ; instances make a uint16 or other truncated instance range fail its pixels.
 For i=0 To #NEON_MAX_VERTS/2-9
  NeonLine(-64,-64,-63,-64)
  If (i & 8191)=0 : SafetyWatchdogPet() : EndIf
 Next
 For i=0 To 7 : NeonLine(streamX0[i],streamY0[i],streamX1[i],streamY1[i]) : Next
 If nvcPathCount<>262144 Or Neon_Verts()<>262144 Or nvcPathError<>0 : NeonVkChromeAbort() : ProcedureReturn 610 : EndIf
 PokeI($E1C01010,nvcPathCount)
 SafetyWatchdogPet() : start=Micros()
 rc=NeonLinesEnd($FFFFFFFF)
 PokeI($E1C01068,Micros()-start)
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 611 : EndIf
 If nvcVertices<>174769 Or Neon_Draws()<>1 : NeonVkChromeAbort() : ProcedureReturn 612 : EndIf
 slot=avkRecordedDraw[avkCbDrawHead[avkCmdSlot(nvcCommand)]]\next
 PokeI($E1C01200,avkRecordedDraw[slot]\vertexCount) : PokeI($E1C01208,avkRecordedDraw[slot]\instanceCount)
 PokeI($E1C01210,avkRecordedDraw[slot]\firstVertex) : PokeI($E1C01218,avkRecordedDraw[slot]\vertexOffset[1])
 PokeI($E1C01220,Bool(avkRecordedDraw[slot]\pipeline=nvcLinePipeline))
 If avkRecordedDraw[slot]\vertexCount<>4 Or avkRecordedDraw[slot]\instanceCount<>131072 Or avkRecordedDraw[slot]\vertexOffset[1]<>144 Or avkRecordedDraw[slot]\pipeline<>nvcLinePipeline : NeonVkChromeAbort() : ProcedureReturn 613 : EndIf
 rc=NeonVkChromeImageSpriteDrawId(1,56,12,0,0,1,1,4,4,$FF00FF00)
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 614 : EndIf
 PokeI($E1C01018,nvcVertices) : PokeI($E1C01020,Neon_Draws()) : PokeI($E1C01028,Neon_Verts())
 PokeI($E1C01030,Neon_TexDraws()) : PokeI($E1C01038,Neon_TexVerts())
 If nvcVertices<>174775 Or nvcDrawCount<>3 Or Neon_TexDraws()<>2 Or Neon_TexVerts()<>12 : NeonVkChromeAbort() : ProcedureReturn 615 : EndIf
 verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+nvcVertices*24+i,$A5) : Next
 rc=NeonLinesBegin() : NeonLine(0,0,1,1) : rc=NeonLinesEnd($FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>verts Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or Neon_Verts()<>262144 : NeonVkChromeAbort() : ProcedureReturn 616 : EndIf
 For i=0 To 15 : If PeekA(nvcMapped+nvcVertices*24+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 617 : EndIf : Next
 PokeI($E1C01040,1)
 SafetyWatchdogPet() : start=Micros()
 rc=NeonVkChromeEnd() : PokeI($E1C01070,Micros()-start)
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 618 : EndIf
 streamCapture(base,pitch,8) : PokeI($E1C01008,9)
 PokeI($E1C01060,131072)
 NeonVkChromeDestroy()
 If nvcLinePipeline|nvcLineLayout|nvcLineSelector|nvcLineSelectorMemory : ProcedureReturn 619 : EndIf
 PokeI($E1C01058,1)
 ; Exhaust the buffer table precisely at the new selector allocation.
 SafetyWatchdogPet() : before=streamMemory()
 ci\sType=#VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO : ci\size=16 : ci\usage=#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT
 For i=0 To 4
  rc=vkCreateBuffer(dev,@ci,0,@streamSeed[i])
  If rc<>0 : ProcedureReturn 620 : EndIf
 Next
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,3,1)
 PokeI($E1C01240,rc) : PokeI($E1C01248,streamMemory()-before)
 If rc<>#VK_ERROR_TOO_MANY_OBJECTS Or NeonDrawBackendActive()<>0 Or nvcDevice<>0 Or streamMemory()<>before Or nvcLinePipeline|nvcLineLayout|nvcLineSelector|nvcLineSelectorMemory : ProcedureReturn 621 : EndIf
 For i=0 To 4
  If avkBufSlot(streamSeed[i])=0 : ProcedureReturn 622 : EndIf
  vkDestroyBuffer(dev,streamSeed[i],0)
 Next
 AnvilVkFaultClear()
 ; Exhaust layouts after the new selector buffer and memory have succeeded.
 li\sType=#VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
 For i=0 To 6
  rc=vkCreatePipelineLayout(dev,@li,0,@streamLayoutSeed[i])
  If rc<>0 : ProcedureReturn 629 : EndIf
 Next
 SafetyWatchdogPet()
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,3,1)
 PokeI($E1C01250,rc) : PokeI($E1C01258,streamMemory()-before)
 If rc<>#VK_ERROR_TOO_MANY_OBJECTS Or NeonDrawBackendActive()<>0 Or nvcDevice<>0 Or streamMemory()<>before Or nvcLinePipeline|nvcLineLayout|nvcLineSelector|nvcLineSelectorMemory : ProcedureReturn 630 : EndIf
 For i=0 To 6
  If avkLaySlot(streamLayoutSeed[i])=0 : ProcedureReturn 631 : EndIf
  vkDestroyPipelineLayout(dev,streamLayoutSeed[i],0)
 Next
 AnvilVkFaultClear()
 SafetyWatchdogPet()
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,3,1)
 If rc<>0 : ProcedureReturn 623 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonLinesBegin() : EndIf
 If rc<>0 : ProcedureReturn 624 : EndIf
 For i=0 To 4 : NeonLine(streamX0[i],streamY0[i],streamX1[i],streamY1[i]) : Next
 rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
 rc=NeonLinesEnd($FFFFFFFF)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>0 Or nvcDrawCount<>0 Or rows<>avkRecordedDrawFreeCount : NeonVkChromeAbort() : ProcedureReturn 625 : EndIf
 For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 626 : EndIf : Next
 PokeI($E1C01048,1)
 rc=NeonVkChromeAbort() : If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc=0 : rc=NeonLinesBegin() : EndIf
 For i=0 To 3 : NeonLine(streamX0[i],streamY0[i],streamX1[i],streamY1[i]) : Next
 If rc=0 : rc=NeonLinesEnd($FFFFFFFF) : EndIf
 If rc<>0 Or nvcVertices<>6 Or nvcDrawCount<>1 Or Neon_Verts()<>8 : NeonVkChromeAbort() : ProcedureReturn 627 : EndIf
 rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 628 : EndIf
 streamCapture(base,pitch,9) : PokeI($E1C01008,10) : PokeI($E1C01050,1)
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
