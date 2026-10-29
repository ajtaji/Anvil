; SPDX-License-Identifier: MIT
; Returning CPU diagnostic: only run when the MMU owner hands over cold caches.
Global ncoChecks.i,ncoFailure.i
Global Dim ncoBuffer.q[32]
Procedure NcoCheck(value.i,expected.i)
  PokeI($E1C00100+ncoChecks*16,value)
  PokeI($E1C00108+ncoChecks*16,expected)
  ncoChecks=ncoChecks+1
  If value<>expected And ncoFailure=0 : ncoFailure=ncoChecks : EndIf
EndProcedure
Procedure.i NcoRun()
  Protected i.i,base.i,nc.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$4E434F31) : PokeI($E1C00008,MmuSctlr())
  If (MmuSctlr() & 5)<>0 : ProcedureReturn 198 : EndIf
  base=@ncoBuffer[0]
  NcoCheck(V3dCacheOffGet(),0)
  NcoCheck(V3dCacheOffSkips(),0)
  V3dCacheRange(base,0) : V3dCacheRange(base,-1)
  V3dCacheRange(base,64)
  NcoCheck(V3dCacheOffSkips(),0)
  V3dSetCacheOff(-1)
  NcoCheck(V3dCacheOffGet(),1)
  V3dCacheRange(base,0) : V3dCacheRange(base,-1)
  NcoCheck(V3dCacheOffSkips(),0)
  V3dCacheRange(base,64)
  NcoCheck(V3dCacheOffSkips(),1)
  NcoCheck(V3dCacheBatchBegin(),1)
  NcoCheck(V3dCacheBatchRange(base,64),1)
  NcoCheck(V3dCacheBatchRange(base+64,64),1)
  NcoCheck(V3dCacheBatchEnd(),2)
  NcoCheck(V3dCacheOffSkips(),3)
  NcoCheck(V3dCacheBatchEnd(),-1)
  NcoCheck(V3dCacheBatchBegin(),1)
  NcoCheck(V3dCacheBatchRange(base,64),1)
  NcoCheck(V3dCacheBatchRange(-1,64),0)
  NcoCheck(V3dCacheBatchRange(base,64),0)
  NcoCheck(V3dCacheBatchEnd(),-1)
  NcoCheck(V3dCacheOffSkips(),4)
  NcoCheck(V3dCacheBatchBegin(),1)
  NcoCheck(V3dCacheBatchBegin(),0)
  NcoCheck(V3dCacheBatchEnd(),-1)
  V3dSetCacheOff(0)
  NcoCheck(V3dCacheOffGet(),0)
  V3dCacheRange(base,64)
  NcoCheck(V3dCacheOffSkips(),4)
  nc=V3dUncachedSkips()
  NcoCheck(V3dDeclareUncached(base,base+128),1)
  V3dCacheRange(base,64)
  NcoCheck(V3dUncachedSkips()-nc,1)
  V3dCacheRange(base,192)
  NcoCheck(V3dUncachedSkips()-nc,1)
  NcoCheck(V3dCacheOffSkips(),4)
  V3dClearUncached()
  V3dCacheRange(base,64)
  NcoCheck(V3dUncachedSkips()-nc,1)
  NcoCheck(V3dCacheOffGet(),0)
  PokeI($E1C00010,ncoFailure) : PokeI($E1C00018,ncoChecks)
  PokeI($E1C00020,MmuSctlr())
  ProcedureReturn ncoFailure
EndProcedure
