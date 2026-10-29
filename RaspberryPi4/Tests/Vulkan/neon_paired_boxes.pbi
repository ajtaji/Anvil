; Identical public box workload on native Neon and the Vulkan lifecycle.
#NP_REPORT=$E1C02000
#NP_PIXELS=$E2800000
#NP_BYTES=4096000
Global npFailure.i
Procedure.i NpFinish(rc.i)
 MmuDisableCachedFlushed()
 If rc<>0 : npFailure=rc : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i NpFrames(kind.i,base.i,pitch.i)
 Protected i.i,frame.i,rc.i,t0.i,t1.i,t2.i,out.i,dest.i,beforeDraws.i,colour.i,phase.i
 If pitch<>3200 : ProcedureReturn 201 : EndIf
 If (MmuSctlr() & $1005)<>0 : ProcedureReturn 202 : EndIf
 MmuClearNc() : MmuAddNc($03000000,$04200000)
 rc=MmuBuildTables($E2530000) : If rc<>0 : ProcedureReturn rc : EndIf
 MmuEnableCached()
 If (MmuSctlr() & $1005)<>$1005 : ProcedureReturn NpFinish(203) : EndIf
 PokeI(#NP_REPORT+24,#NP_SCENE)
 For frame=0 To 3
  beforeDraws=avkBackendDraws()
  t0=V3dTicks() : rc=NeonFrameBegin($FF000000)
  If rc<>0 : ProcedureReturn NpFinish(rc) : EndIf
  Neon_ScissorClear()
  For i=0 To 3504
   If #NP_SCENE=1
    phase=(i/64) % 2
    If (i % 64)=0 : Neon_ScissorSet(20+phase*12,18+phase*8,70,50) : EndIf
    colour=$FF224466
    If ((i/8) % 3)=1 : colour=$FF6688AA : EndIf
    If ((i/8) % 3)=2 : colour=$FFCC8844 : EndIf
    rc=Neon_Box(16+(i % 11)*3,14+((i/11) % 7)*4,80,60,colour)
   Else
    rc=Neon_Box((i-(i/100)*100)*7,(i/100)*7,4,4,$FF303030)
   EndIf
   If rc<>0 : NeonFrameEnd() : ProcedureReturn NpFinish(rc) : EndIf
  Next
  Neon_ScissorClear()
  t1=V3dTicks() : rc=NeonFrameEnd() : t2=V3dTicks()
  If rc<>0 : ProcedureReturn NpFinish(rc) : EndIf
  out=#NP_REPORT+64+(kind*4+frame)*64
  PokeI(out,kind) : PokeI(out+8,frame)
  PokeI(out+16,t1-t0) : PokeI(out+24,t2-t1)
  PokeI(out+32,Neon_Boxes()) : PokeI(out+40,Neon_Error())
  PokeI(out+48,MmuSctlr() & $1005)
  If kind=1
   PokeI(out+56,NeonVkChromePresentConsume())
   PokeI(#NP_REPORT+1344+frame*32,AnvilVkV3dLastBatchCount())
   PokeI(#NP_REPORT+1344+frame*32+8,AnvilVkV3dLastListCount())
   PokeI(#NP_REPORT+1344+frame*32+16,AnvilVkV3dLastListPrimitives())
   PokeI(#NP_REPORT+1344+frame*32+24,avkBackendDraws()-beforeDraws)
   ; Existing backend phase clocks, copied after synchronous completion.
   For i=0 To 5 : PokeI(#NP_REPORT+1024+frame*64+i*8,avkV3dProf[i]) : Next
   PokeI(#NP_REPORT+1024+frame*64+48,avkV3dLastCacheInputRanges)
   PokeI(#NP_REPORT+1024+frame*64+56,avkV3dLastCacheMergedRanges)
   PokeI(#NP_REPORT+1280+frame*16,avkV3dProf[6])
   PokeI(#NP_REPORT+1280+frame*16+8,avkV3dProf[7])
  EndIf
 Next
 dest=#NP_PIXELS+kind*#NP_BYTES
 For i=0 To #NP_BYTES-8 Step 8 : PokeI(dest+i,PeekI(base+i)) : Next
 PokeI(#NP_REPORT+kind*8,1)
 ProcedureReturn NpFinish(0)
EndProcedure
