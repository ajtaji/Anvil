; Physical direct triangle-list fallback: full native point quota and an
; explicitly small allocation. The builder masks only the backend capability.
Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure streamCapture(base.i,pitch.i)
 Define x.i,y.i
 For y=0 To 63
  For x=0 To 63
   PokeL($E2400000+(y*64+x)*4,PeekL(base+y*pitch+x*4))
  Next
 Next
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,rows.i,guard.i,slots.i,draws.i,before.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,10240,65536)
 If rc<>0 : ProcedureReturn 801 : EndIf
 If nvcFanPipeline<>0 Or (avkBackendCaps() & #ANVIL_VK_CAP_TRIANGLE_FAN)<>0 : ProcedureReturn 802 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 803 : EndIf
 For i=0 To #NEON_MAX_VERTS-4
  NeonFanPoint(-64,-64)
  If (i & 8191)=0 : SafetyWatchdogPet() : EndIf
 Next
 NeonFanPoint(28,-64) : NeonFanPoint(28,28) : NeonFanPoint(-64,28)
 rows=avkRecordedDrawFreeCount : before=streamMemory()
 For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
 SafetyWatchdogPet() : rc=NeonFanEnd($FF00FF00)
 PokeI($E1C01010,rc) : PokeI($E1C01018,nvcVertices)
 If #FAN_EXPECT_OLD_REFUSAL<>0
  If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>0 Or nvcDrawCount<>0 Or Neon_Draws()<>0 Or Neon_Verts()<>262144 Or avkRecordedDrawFreeCount<>rows Or streamMemory()<>before : ProcedureReturn 804 : EndIf
  For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : ProcedureReturn 805 : EndIf : Next
  rc=NeonVkChromeAbort() : NeonVkChromeDestroy()
 Else
  If rc<>0 Or nvcVertices<>262144 Or nvcDrawCount<>1 Or Neon_Draws()<>1 Or Neon_Verts()<>262144 Or nvcFanListIndicesUsed<>786426 Or nvcOutlineBuffer<>0 : PokeI($E1C01310,rc) : ProcedureReturn 806 : EndIf
  ; The fan consumes the entire flat-point quota. Mixed following draws
  ; are checked separately by the four-rotation topology proof.
  guard=nvcMapped+nvcVertices*24
  For i=0 To 15 : PokeA(guard+i,$A5) : Next
  PokeI($E1C01020,nvcVertices) : PokeI($E1C01028,nvcDrawCount)
  SafetyWatchdogPet() : rc=NeonVkChromeEnd()
  If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01318,rc) : ProcedureReturn 808 : EndIf
  For i=0 To 15 : If PeekA(guard+i)<>$A5 : ProcedureReturn 809 : EndIf : Next
  streamCapture(base,pitch) : PokeI($E1C01008,1)
  NeonVkChromeDestroy()
 EndIf
 ; A caller requesting one quad cannot hold seven ordinary vertices. The
 ; rejection must precede allocation, mapped writes or command publication.
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,4,1)
 If rc<>0 : ProcedureReturn 810 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 811 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(16,28) : NeonFanPoint(4,28)
 NeonFanPoint(4,20) : NeonFanPoint(4,12)
 slots=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount : before=streamMemory()
 guard=nvcMapped
 For i=0 To 15 : PokeA(guard+i,$A5) : Next
 rc=NeonFanEnd($FFFF0000)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>slots Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or streamMemory()<>before Or nvcFanListBuffer<>0 Or Neon_Draws()<>0 Or Neon_Verts()<>7 : ProcedureReturn 812 : EndIf
 For i=0 To 15 : If PeekA(guard+i)<>$A5 : ProcedureReturn 813 : EndIf : Next
 PokeI($E1C01030,rc) : PokeI($E1C01038,1)
 rc=NeonVkChromeAbort() : NeonVkChromeDestroy()
 ProcedureReturn rc
EndProcedure
