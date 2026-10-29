Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure
Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define rc.i,x.i,y.i
 PokeI($E1C01010,NeonHardwareLifecycleFlags())
 rc=NeonVkChromeLifecycleInstallPrepared() : PokeI($E1C01018,rc) : If rc<>0 : ProcedureReturn 941 : EndIf
 rc=NeonInit() : PokeI($E1C01020,rc) : If rc<>0 : ProcedureReturn 942 : EndIf
 PokeI($E1C01028,NeonLifecycleBackend()) : PokeI($E1C01030,Neon_Ready())
 rc=NeonFrameBegin($FF1A334D) : PokeI($E1C01038,rc) : If rc<>0 : ProcedureReturn 943 : EndIf
 rc=Neon_Box(4,4,24,24,$FF00FF00) : PokeI($E1C01040,rc) : If rc<>0 : ProcedureReturn 944 : EndIf
 rc=NeonFrameEnd() : PokeI($E1C01048,rc) : If rc<>0 : ProcedureReturn 945 : EndIf
 rc=NeonVkChromePresentConsume() : PokeI($E1C01050,rc) : If rc<>1 : ProcedureReturn 946 : EndIf
 For y=0 To 63 : For x=0 To 63 : PokeL($E2400000+(y*64+x)*4,PeekL(base+y*pitch+x*4)) : Next : Next
 PokeI($E1C01008,1)
 rc=NeonShutdown() : PokeI($E1C01058,rc) : If rc<>0 : ProcedureReturn 947 : EndIf
 PokeI($E1C01060,NeonLifecycleBackend()) : PokeI($E1C01068,NeonLifecyclePreparedOwnerPending())
 PokeI($E1C01070,NeonHardwareLifecycleFlags()) : PokeI($E1C01078,$4C43484F)
 If NeonVkChromeReady()<>0 Or NeonDrawBackendActive()<>0 Or NeonLifecyclePreparedOwnerPending()<>1 Or NeonHardwareLifecycleFlags()<>1 : ProcedureReturn 948 : EndIf
 ProcedureReturn 0
EndProcedure
