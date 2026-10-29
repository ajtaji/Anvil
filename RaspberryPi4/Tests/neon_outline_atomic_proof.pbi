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


Global Dim outlineBufferSeed.i[4]

Procedure.i outlineCreateSmall(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,draws.i,quads.i)
 Define rc.i
 NeonVkChromeDestroy()
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,draws,quads)
 If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
 If rc=0 : rc=NeonFanBegin() : EndIf
 ProcedureReturn rc
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define rc.i,i.i,old.i,slots.i,draws.i,rows.i,buffer.i,before.i,unchanged.i
 Define ci.VkBufferCreateInfo
 SafetyWatchdogStart(15)
 ; One available raw record cannot hold an outline's two records.
 rc=outlineCreateSmall(phys,dev,queue,pool,rp,fb,1,16)
 If rc<>0 : ProcedureReturn 781 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4)
 rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
 rc=NeonFanOutline($FFFFFFFF) : unchanged=1
 For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : unchanged=0 : EndIf : Next
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or unchanged<>1 Or nvcVertices<>0 Or nvcDrawCount<>0 Or avkRecordedDrawFreeCount<>rows Or nvcOutlineBuffer<>0 Or nvcOutlinePointsUsed<>0 Or Neon_Verts()<>2 : NeonVkChromeAbort() : ProcedureReturn 782 : EndIf
 PokeI($E1C01100,rc) : PokeI($E1C01108,unchanged)
 rc=NeonVkChromeAbort() : If rc<>0 : ProcedureReturn 783 : EndIf
 ; Exact 144-byte data buffer: four points occupy128bytes/six slots.
 SafetyWatchdogPet() : rc=outlineCreateSmall(phys,dev,queue,pool,rp,fb,4,1)
 If rc<>0 : ProcedureReturn 784 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(4,28)
 rc=NeonFanOutline($FFFFFFFF)
 If rc<>0 Or nvcVertices<>6 : NeonVkChromeAbort() : ProcedureReturn 785 : EndIf
 For i=0 To 143 : PokeA($E1C00600+i,PeekA(nvcMapped+i)) : Next
 old=nvcFanIndexedClose
 For i=0 To 23 : PokeA($E1C00700+i,PeekA(nvcOutlineMapped+old*4+i)) : Next
 slots=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount : buffer=nvcOutlineBuffer
 NeonFanPoint(8,20) : rc=NeonFanOutline($FF00FF00) : unchanged=1
 For i=0 To 143 : If PeekA($E1C00600+i)<>PeekA(nvcMapped+i) : unchanged=0 : EndIf : Next
 For i=0 To 23 : If PeekA($E1C00700+i)<>PeekA(nvcOutlineMapped+old*4+i) : unchanged=0 : EndIf : Next
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or unchanged<>1 Or nvcVertices<>slots Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or nvcOutlinePointsUsed<>4 Or nvcOutlineClosingsUsed<>1 Or nvcOutlineBuffer<>buffer Or Neon_Verts()<>5 Or nvcPathCount<>5 : NeonVkChromeAbort() : ProcedureReturn 786 : EndIf
 PokeI($E1C01110,rc) : PokeI($E1C01118,unchanged)
 rc=NeonVkChromeAbort() : If rc<>0 : ProcedureReturn 787 : EndIf
 ; An unchanged repeat also preflights BOTH raw rows without touching cache.
 SafetyWatchdogPet() : rc=outlineCreateSmall(phys,dev,queue,pool,rp,fb,3,16)
 If rc<>0 : ProcedureReturn 788 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4) : rc=NeonFanOutline($FFFFFFFF)
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 789 : EndIf
 slots=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount : buffer=nvcOutlineBuffer : old=nvcFanIndexedClose
 rc=NeonFanOutline($FFFF0000)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>slots Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or nvcOutlinePointsUsed<>2 Or nvcOutlineClosingsUsed<>1 Or nvcFanIndexedClose<>old Or nvcOutlineBuffer<>buffer : NeonVkChromeAbort() : ProcedureReturn 790 : EndIf
 PokeI($E1C01120,rc) : PokeI($E1C01128,1)
 rc=NeonFanEnd($FF00FF00) : If rc=0 : rc=Neon_Box(50,50,4,4,$FF00FF00) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 791 : EndIf
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 792 : EndIf
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 ; Buffer-table failure precedes any index-memory or command publication.
 SafetyWatchdogPet() : rc=outlineCreateSmall(phys,dev,queue,pool,rp,fb,8,16)
 If rc<>0 : ProcedureReturn 793 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4)
 ci\sType=#VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO : ci\size=16 : ci\usage=#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT
 For i=0 To 3
  rc=vkCreateBuffer(dev,@ci,0,@outlineBufferSeed[i])
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 794 : EndIf
 Next
 before=streamMemory() : rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
 rc=NeonFanOutline($FFFFFFFF) : unchanged=1
 For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : unchanged=0 : EndIf : Next
 If rc<>#VK_ERROR_TOO_MANY_OBJECTS Or unchanged<>1 Or streamMemory()<>before Or nvcVertices<>0 Or nvcDrawCount<>0 Or avkRecordedDrawFreeCount<>rows Or nvcOutlineBuffer|nvcOutlineMemory|nvcOutlineMapped|nvcOutlineListPipeline|nvcOutlineFanPipeline : NeonVkChromeAbort() : ProcedureReturn 795 : EndIf
 For i=0 To 3
  If avkBufSlot(outlineBufferSeed[i])=0 : NeonVkChromeAbort() : ProcedureReturn 796 : EndIf
  vkDestroyBuffer(dev,outlineBufferSeed[i],0)
 Next
 PokeI($E1C01130,rc) : PokeI($E1C01138,unchanged)
 AnvilVkFaultClear()
 rc=NeonFanOutline($FF00FF00) : If rc=0 : rc=NeonFanEnd($FFFFFFFF) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 797 : EndIf
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 798 : EndIf
 streamCapture(base,pitch,1) : PokeI($E1C01008,2)
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
