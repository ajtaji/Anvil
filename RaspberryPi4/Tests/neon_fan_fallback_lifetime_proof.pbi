; Returning hardware proof of immutable direct-fan index ranges and reuse.
; Native triangle-fan capability is withheld by the test composition only.
Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure streamCapture(base.i,pitch.i,frame.i)
 Define x.i,y.i
 For y=0 To 63
  For x=0 To 63
   PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(base+y*pitch+x*4))
  Next
 Next
EndProcedure

Procedure.i lifetimeFan(x.i,y.i,w.i,h.i,colour.i)
 Define rc.i
 rc=NeonFanBegin() : If rc<>0 : ProcedureReturn rc : EndIf
 NeonFanPoint(x,y) : NeonFanPoint(x+w,y) : NeonFanPoint(x+w,y+h) : NeonFanPoint(x,y+h)
 ProcedureReturn NeonFanEnd(colour)
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,indexBuffer.i,rows.i,memory.i,vertices.i,draws.i,indices.i,guard.i
 Define Dim saved.l[6]
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 If (avkBackendCaps() & #ANVIL_VK_CAP_TRIANGLE_FAN)<>0 : ProcedureReturn 901 : EndIf
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,16)
 If rc<>0 Or nvcFanPipeline<>0 : ProcedureReturn 902 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc<>0 : ProcedureReturn 903 : EndIf
 rc=lifetimeFan(4,4,16,16,$FF00FF00) : If rc<>0 : ProcedureReturn 904 : EndIf
 indexBuffer=nvcFanListBuffer
 If indexBuffer=0 Or nvcFanListIndicesUsed<>6 : ProcedureReturn 905 : EndIf
 For i=0 To 5 : saved[i]=PeekL(nvcFanListMapped+i*4) : Next
 rc=Neon_Box(24,4,12,16,$FF0000FF) : If rc<>0 : ProcedureReturn 906 : EndIf
 rc=lifetimeFan(40,4,16,16,$FFFF0000) : If rc<>0 : ProcedureReturn 907 : EndIf
 If nvcVertices<>14 Or nvcFanListIndicesUsed<>12 Or nvcDrawCount<>3 Or nvcOutlineBuffer<>0 : ProcedureReturn 908 : EndIf
 PokeI($E1C01018,nvcVertices) : PokeI($E1C01020,nvcFanListIndicesUsed)
 For i=0 To 5
  If PeekL(nvcFanListMapped+i*4)<>saved[i] : ProcedureReturn 909 : EndIf
 Next
 For i=0 To 11 : PokeL($E1C01200+i*4,PeekL(nvcFanListMapped+i*4)) : Next
 PokeI($E1C01028,1) : PokeI($E1C01060,PeekL(nvcFanListMapped)) : PokeI($E1C01068,PeekL(nvcFanListMapped+24))
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 910 : EndIf
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 ; Abort a valid recorded fan, then reuse the same lazy allocation.
 SafetyWatchdogPet() : rc=NeonVkChromeBegin(@nwClear[0]) : If rc<>0 Or nvcFanListIndicesUsed<>0 : ProcedureReturn 911 : EndIf
 rc=lifetimeFan(0,0,64,64,$FFFF0000) : If rc<>0 : ProcedureReturn 912 : EndIf
 rc=NeonVkChromeAbort()
 If rc<>0 Or nvcFanListIndicesUsed<>0 Or nvcVertices<>0 Or nvcDrawCount<>0 Or NeonVkChromePresentConsume()<>0 : ProcedureReturn 913 : EndIf
 PokeI($E1C01030,1)
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc<>0 : ProcedureReturn 914 : EndIf
 rc=lifetimeFan(8,24,16,16,$FF00FFFF) : If rc<>0 : ProcedureReturn 915 : EndIf
 rc=Neon_Box(52,24,8,16,$FFFF00FF) : If rc<>0 : ProcedureReturn 916 : EndIf
 rc=lifetimeFan(32,24,16,16,$FFFFFF00) : If rc<>0 : ProcedureReturn 917 : EndIf
 If nvcFanListBuffer<>indexBuffer Or nvcVertices<>14 Or nvcFanListIndicesUsed<>12 : ProcedureReturn 918 : EndIf
 PokeI($E1C01038,1)
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 919 : EndIf
 streamCapture(base,pitch,1) : PokeI($E1C01008,2)
 NeonVkChromeDestroy()
 ; A second fan must refuse before overwriting either existing index data
 ; or the next vertex/index guards in a caller-selected six-vertex arena.
 SafetyWatchdogPet() : rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,4,1)
 If rc<>0 : ProcedureReturn 920 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc<>0 : ProcedureReturn 921 : EndIf
 rc=lifetimeFan(4,4,16,16,$FF00FF00) : If rc<>0 : ProcedureReturn 922 : EndIf
 indexBuffer=nvcFanListBuffer : vertices=nvcVertices : draws=nvcDrawCount : indices=nvcFanListIndicesUsed
 rows=avkRecordedDrawFreeCount : memory=streamMemory() : guard=nvcMapped+vertices*24
 For i=0 To 5 : saved[i]=PeekL(nvcFanListMapped+i*4) : Next
 For i=0 To 15 : PokeA(guard+i,$A5) : PokeA(nvcFanListMapped+24+i,$5A) : Next
 rc=NeonFanBegin() : If rc<>0 : ProcedureReturn 923 : EndIf
 NeonFanPoint(32,4) : NeonFanPoint(48,4) : NeonFanPoint(48,20)
 rc=NeonFanEnd($FFFF0000) : PokeI($E1C01040,rc)
 If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>vertices Or nvcDrawCount<>draws Or nvcFanListIndicesUsed<>indices Or nvcFanListBuffer<>indexBuffer Or avkRecordedDrawFreeCount<>rows Or streamMemory()<>memory : ProcedureReturn 924 : EndIf
 For i=0 To 5 : If PeekL(nvcFanListMapped+i*4)<>saved[i] : ProcedureReturn 925 : EndIf : Next
 For i=0 To 15 : If PeekA(guard+i)<>$A5 Or PeekA(nvcFanListMapped+24+i)<>$5A : ProcedureReturn 926 : EndIf : Next
 PokeI($E1C01048,1)
 rc=NeonVkChromeAbort()
 If rc<>0 Or nvcFanListIndicesUsed<>0 Or nvcVertices<>0 Or nvcDrawCount<>0 : ProcedureReturn 927 : EndIf
 PokeI($E1C01050,1)
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc<>0 : ProcedureReturn 928 : EndIf
 rc=lifetimeFan(8,8,16,16,$FF0000FF) : If rc<>0 : ProcedureReturn 929 : EndIf
 If nvcFanListBuffer<>indexBuffer Or nvcFanListIndicesUsed<>6 Or PeekL(nvcFanListMapped)<>0 : ProcedureReturn 930 : EndIf
 PokeI($E1C01058,1)
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 931 : EndIf
 streamCapture(base,pitch,2) : PokeI($E1C01008,3)
 NeonVkChromeDestroy() : PokeI($E1C01078,$464C4946)
 ProcedureReturn 0
EndProcedure
