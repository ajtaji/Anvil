; Shared lifecycle policy with a controlled native provider. No GPU library,
; register access or native graphics execution is linked by this composition.
XIncludeFile "Anvil/Graphics/neon_lifecycle.pbi"

Global lcpFlags.i,lcpCoordResets.i,lcpNativeInitRc.i,lcpNativeShutdownRc.i
Global lcpNativeBeginRc.i,lcpNativeEndRc.i,lcpNativeInits.i,lcpNativeShutdowns.i
Global lcpNativeBegins.i,lcpNativeEnds.i,lcpBeginColour.i
Global lcpExtInitRc.i,lcpExtBeginRc.i,lcpExtEndRc.i,lcpExtShutdownRc.i
Global lcpExtInits.i,lcpExtBegins.i,lcpExtEnds.i,lcpExtShutdowns.i
Global lcpRecords.i,lcpFailures.i,lcpSkipHooks.i

Procedure.i NeonHardwareLifecycleFlags() : ProcedureReturn lcpFlags : EndProcedure
Procedure NeonHardwareCoordinateReset() : lcpCoordResets=lcpCoordResets+1 : EndProcedure
Procedure.i NeonHardwareInit()
 lcpNativeInits=lcpNativeInits+1
 If lcpNativeInitRc=0 : gNeonReady=1 : lcpFlags=1 : Else : NeonFrontendError(lcpNativeInitRc) : EndIf
 ProcedureReturn lcpNativeInitRc
EndProcedure
Procedure.i NeonHardwareShutdown()
 lcpNativeShutdowns=lcpNativeShutdowns+1
 If lcpNativeShutdownRc=0 : gNeonReady=0 : neon_inFrame=0 : gNeonPreparedOwnerPending=0 : lcpFlags=0 : Else : NeonFrontendError(lcpNativeShutdownRc) : EndIf
 ProcedureReturn lcpNativeShutdownRc
EndProcedure
Procedure.i NeonHardwareFrameBegin(colour.i)
 lcpNativeBegins=lcpNativeBegins+1 : lcpBeginColour=colour
 If lcpNativeBeginRc=0 : lcpFlags=lcpFlags | 2 : EndIf
 ProcedureReturn lcpNativeBeginRc
EndProcedure
Procedure.i NeonHardwareFrameEnd()
 lcpNativeEnds=lcpNativeEnds+1 : lcpFlags=lcpFlags & (~2)
 ProcedureReturn lcpNativeEndRc
EndProcedure

Procedure.i LcpBox(x.i,y.i,w.i,h.i,c.i) : ProcedureReturn 0 : EndProcedure
Procedure.i LcpText(f.i,x.i,y.i,*s,c.i) : ProcedureReturn 0 : EndProcedure
Procedure LcpScissor(x.i,y.i,w.i,h.i) : EndProcedure
Procedure LcpClear() : EndProcedure
Procedure.i LcpBegin() : ProcedureReturn 0 : EndProcedure
Procedure LcpPoint(x.i,y.i) : EndProcedure
Procedure.i LcpEnd(c.i) : ProcedureReturn 0 : EndProcedure
Procedure LcpLine(x.i,y.i,a.i,b.i) : EndProcedure
Procedure.i LcpHooks()
 ProcedureReturn NeonDrawBackendInstall(@LcpBox,@LcpText,@LcpText,@LcpScissor,@LcpClear,@LcpBegin,@LcpPoint,@LcpEnd,@LcpEnd,@LcpBegin,@LcpLine,@LcpEnd)
EndProcedure
Procedure.i LcpInit()
 lcpExtInits=lcpExtInits+1
 If lcpExtInitRc=0 And lcpSkipHooks=0 : LcpHooks() : EndIf
 ProcedureReturn lcpExtInitRc
EndProcedure
Procedure.i LcpFrameBegin(c.i) : lcpExtBegins=lcpExtBegins+1 : ProcedureReturn lcpExtBeginRc : EndProcedure
Procedure.i LcpFrameEnd() : lcpExtEnds=lcpExtEnds+1 : ProcedureReturn lcpExtEndRc : EndProcedure
Procedure.i LcpShutdown() : lcpExtShutdowns=lcpExtShutdowns+1 : ProcedureReturn lcpExtShutdownRc : EndProcedure

Procedure LcpCheck(tag.i,value.i,wanted.i)
 If lcpRecords>=500 : lcpFailures=999 : ProcedureReturn : EndIf
 PokeI(#LCP_REPORT+64+lcpRecords*16,tag) : PokeI(#LCP_REPORT+72+lcpRecords*16,value)
 lcpRecords=lcpRecords+1
 If value<>wanted : lcpFailures=lcpFailures+1 : EndIf
EndProcedure
Procedure.i LcpSame(a.i,b.i)
 If a=b : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure LcpReset()
 ; Independent CPU-case setup, not a production recovery or quarantine API.
 lcpFlags=0 : gNeonReady=0 : neon_inFrame=0 : gNeonPreparedOwnerPending=0
 gNeonLifecycleCleanupPending=0 : lcpSkipHooks=0
 NeonDrawBackendClear() : NeonLifecycleUseNative() : NeonFrontendError(0)
 lcpCoordResets=0 : lcpNativeInitRc=0 : lcpNativeShutdownRc=0 : lcpNativeBeginRc=0 : lcpNativeEndRc=0
 lcpNativeInits=0 : lcpNativeShutdowns=0 : lcpNativeBegins=0 : lcpNativeEnds=0
 lcpExtInitRc=0 : lcpExtBeginRc=0 : lcpExtEndRc=0 : lcpExtShutdownRc=0
 lcpExtInits=0 : lcpExtBegins=0 : lcpExtEnds=0 : lcpExtShutdowns=0
EndProcedure
Procedure LcpPrepared()
 LcpReset() : gNeonReady=1 : lcpFlags=1 : LcpHooks()
EndProcedure

Procedure.i SharedLifecycleProof()
 Define ready.i,frame.i,flags.i,active.i,mode.i,which.i,caseId.i,tag.i,rc.i,want.i,wantMode.i,prepared.i
 Define init.i,begin.i,finish.i,shutdown.i,before.i
 ; The original unprepared guard ignores hardware-frame alone, but refuses
 ; logical readiness, logical frame or native ownership. Test all16 inputs.
 For ready=0 To 1
  For frame=0 To 1
   For flags=0 To 3
    LcpReset() : gNeonReady=ready : neon_inFrame=frame : lcpFlags=flags
    want=0 : If ready<>0 Or frame<>0 Or (flags & 1)<>0 : want=16 : EndIf
    rc=NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
    tag=1000+caseId*10 : wantMode=0 : If want=0 : wantMode=1 : EndIf
    LcpCheck(tag,rc,want) : LcpCheck(tag+1,NeonLifecycleBackend(),wantMode) : LcpCheck(tag+2,gNeonLifecyclePrepared,0)
    caseId=caseId+1
   Next
  Next
 Next
 ; Prepared selection is allowed only for native mode, ready/native owner,
 ; no logical/hardware frame and a complete active draw family:64 inputs.
 caseId=0
 For mode=0 To 1
  For ready=0 To 1
   For frame=0 To 1
    For flags=0 To 3
     For active=0 To 1
      LcpReset()
      If mode<>0 : NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown) : EndIf
      If active<>0 : LcpHooks() : EndIf
      gNeonReady=ready : neon_inFrame=frame : lcpFlags=flags : gNeonPreparedOwnerPending=1
      want=16 : If mode=0 And ready=1 And frame=0 And flags=1 And active=1 : want=0 : EndIf
      rc=NeonLifecycleInstallPrepared(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
      tag=2000+caseId*10 : wantMode=mode : prepared=0 : before=1
      If want=0 : wantMode=1 : prepared=1 : before=0 : EndIf
      LcpCheck(tag,rc,want) : LcpCheck(tag+1,NeonLifecycleBackend(),wantMode)
      LcpCheck(tag+2,gNeonLifecyclePrepared,prepared) : LcpCheck(tag+3,NeonLifecyclePreparedOwnerPending(),before)
      caseId=caseId+1
     Next
    Next
   Next
  Next
 Next
 ; Missing callbacks preserve an installed family and prepared inputs.
 For which=0 To 3
  LcpReset() : NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
  init=@LcpInit : begin=@LcpFrameBegin : finish=@LcpFrameEnd : shutdown=@LcpShutdown
  If which=0 : init=0 : ElseIf which=1 : begin=0 : ElseIf which=2 : finish=0 : Else : shutdown=0 : EndIf
  rc=NeonLifecycleInstall(init,begin,finish,shutdown) : tag=2700+which*10
  LcpCheck(tag,rc,15) : LcpCheck(tag+1,LcpSame(gNeonLifecycleInit,@LcpInit),1) : LcpCheck(tag+2,NeonLifecycleBackend(),1)
  LcpPrepared() : gNeonPreparedOwnerPending=1 : before=gNeonLifecycleInit
  rc=NeonLifecycleInstallPrepared(init,begin,finish,shutdown) : tag=2800+which*10
  LcpCheck(tag,rc,15) : LcpCheck(tag+1,LcpSame(gNeonLifecycleInit,before),1) : LcpCheck(tag+2,NeonLifecyclePreparedOwnerPending(),1)
 Next
 ; Native dispatch and duplicate/no-frame failures.
 LcpReset() : lcpNativeInitRc=1
 LcpCheck(3000,NeonInit(),1) : LcpCheck(3001,gNeonReady,0) : LcpCheck(3002,lcpCoordResets,1) : LcpCheck(3003,Neon_Error(),1)
 lcpNativeInitRc=0 : LcpCheck(3004,NeonInit(),0) : LcpCheck(3005,gNeonReady,1) : LcpCheck(3006,lcpCoordResets,2)
 LcpCheck(3007,NeonFrameBegin($1234),0) : LcpCheck(3008,neon_inFrame,1) : LcpCheck(3009,NeonFrameBegin(0),11) : LcpCheck(3010,lcpNativeBegins,1)
 LcpCheck(3011,NeonFrameEnd(),0) : LcpCheck(3012,neon_inFrame,0) : LcpCheck(3013,NeonFrameEnd(),10)
 lcpNativeShutdownRc=6 : LcpCheck(3014,NeonShutdown(),6) : LcpCheck(3015,gNeonReady,1) : LcpCheck(3016,lcpFlags,1)
 lcpNativeShutdownRc=0 : LcpCheck(3017,NeonShutdown(),0) : LcpCheck(3018,gNeonReady,0) : LcpCheck(3019,lcpFlags,0)
 LcpCheck(3020,lcpNativeShutdowns,2) : LcpCheck(3021,lcpCoordResets,4) : LcpCheck(3022,lcpNativeInits,2)
 ; External callback failures must preserve/release the established owner.
 LcpReset() : LcpCheck(3100,NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),0)
 lcpExtInitRc=7 : LcpCheck(3101,NeonInit(),16) : LcpCheck(3102,gNeonLifecycleError,7) : LcpCheck(3103,gNeonReady,0)
 LcpCheck(3090,NeonLifecycleCleanupPending(),1) : LcpCheck(3091,NeonShutdown(),0) : LcpCheck(3092,NeonLifecycleCleanupPending(),0)
 lcpExtInitRc=0 : LcpCheck(3104,NeonInit(),0) : LcpCheck(3105,gNeonReady,1)
 LcpCheck(3106,NeonFrameBegin(0),0) : LcpCheck(3107,NeonFrameBegin(0),11)
 lcpExtEndRc=8 : LcpCheck(3108,NeonFrameEnd(),16) : LcpCheck(3109,neon_inFrame,0)
 lcpExtBeginRc=9 : LcpCheck(3110,NeonFrameBegin(0),16) : LcpCheck(3111,neon_inFrame,0)
 lcpExtShutdownRc=10 : LcpCheck(3112,NeonShutdown(),16) : LcpCheck(3113,gNeonReady,1) : LcpCheck(3114,NeonDrawBackendActive(),1)
 lcpExtShutdownRc=0 : LcpCheck(3115,NeonShutdown(),0) : LcpCheck(3116,gNeonReady,0) : LcpCheck(3117,NeonDrawBackendActive(),0)
 LcpCheck(3118,NeonLifecycleUseNative(),0) : LcpCheck(3119,NeonLifecycleBackend(),0)
 LcpCheck(3120,lcpExtInits,2) : LcpCheck(3121,lcpExtBegins,2) : LcpCheck(3122,lcpExtEnds,1) : LcpCheck(3123,lcpExtShutdowns,3)
 ; Failed prepared rollback retains the external owner/context metadata.
 LcpPrepared() : LcpCheck(3200,NeonLifecycleInstallPrepared(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),0)
 lcpExtInitRc=7 : lcpExtShutdownRc=8 : LcpCheck(3201,NeonInit(),16)
 LcpCheck(3202,NeonLifecycleBackend(),1) : LcpCheck(3203,gNeonLifecyclePrepared,1) : LcpCheck(3204,gNeonReady,0)
 LcpCheck(3205,NeonLifecyclePreparedOwnerPending(),0) : LcpCheck(3206,NeonDrawBackendActive(),1) : LcpCheck(3207,gNeonLifecycleError,8)
 ; Retry a failed prepared rollback through the retained external owner.
 LcpCheck(3250,NeonLifecycleCleanupPending(),1) : LcpCheck(3251,NeonInit(),16)
 LcpCheck(3252,lcpExtInits,1) : lcpExtShutdownRc=0
 LcpCheck(3253,NeonShutdown(),0) : LcpCheck(3254,lcpExtShutdowns,2)
 LcpCheck(3255,NeonLifecycleCleanupPending(),0) : LcpCheck(3256,NeonLifecycleBackend(),0)
 LcpCheck(3257,gNeonLifecyclePrepared,0) : LcpCheck(3258,gNeonReady,1)
 LcpCheck(3259,NeonLifecyclePreparedOwnerPending(),1) : LcpCheck(3260,NeonDrawBackendActive(),0)
 LcpCheck(3261,lcpFlags,1) : LcpCheck(3262,NeonShutdown(),0)
 LcpCheck(3263,lcpFlags,0) : LcpCheck(3264,gNeonReady,0)
 LcpCheck(3265,NeonLifecyclePreparedOwnerPending(),0) : LcpCheck(3266,lcpNativeShutdowns,1)
 ; Successful rollback returns the borrowed native context without release.
 LcpPrepared() : LcpCheck(3210,NeonLifecycleInstallPrepared(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),0)
 lcpExtInitRc=7 : LcpCheck(3211,NeonInit(),16) : LcpCheck(3212,NeonLifecycleBackend(),0) : LcpCheck(3213,gNeonLifecyclePrepared,0)
 LcpCheck(3214,gNeonReady,1) : LcpCheck(3215,NeonLifecyclePreparedOwnerPending(),1) : LcpCheck(3216,NeonDrawBackendActive(),0) : LcpCheck(3217,gNeonLifecycleError,7)
 LcpCheck(3218,NeonShutdown(),0) : LcpCheck(3219,gNeonReady,0) : LcpCheck(3220,NeonLifecyclePreparedOwnerPending(),0) : LcpCheck(3221,lcpNativeShutdowns,1)
 ; A successful prepared lifecycle likewise returns, then releases, native.
 LcpPrepared() : LcpCheck(3230,NeonLifecycleInstallPrepared(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),0)
 LcpCheck(3231,NeonInit(),0) : LcpCheck(3232,NeonFrameBegin(0),0) : LcpCheck(3233,NeonFrameEnd(),0) : LcpCheck(3234,NeonShutdown(),0)
 LcpCheck(3235,NeonLifecycleBackend(),0) : LcpCheck(3236,gNeonReady,1) : LcpCheck(3237,NeonLifecyclePreparedOwnerPending(),1)
 LcpCheck(3238,NeonDrawBackendActive(),0) : LcpCheck(3239,lcpFlags,1) : LcpCheck(3240,NeonShutdown(),0)
 LcpCheck(3241,gNeonReady,0) : LcpCheck(3242,NeonLifecyclePreparedOwnerPending(),0) : LcpCheck(3243,lcpNativeShutdowns,1)
 ; Failed init owns cleanup even when readiness and native ownership are zero.
 LcpReset() : NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
 lcpExtInitRc=7 : lcpExtShutdownRc=8
 LcpCheck(3300,NeonInit(),16) : LcpCheck(3301,NeonLifecycleCleanupPending(),1)
 LcpCheck(3302,gNeonReady,0) : LcpCheck(3303,lcpExtInits,1)
 LcpCheck(3304,NeonLifecycleUseNative(),16)
 LcpCheck(3305,NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),16)
 LcpCheck(3306,NeonLifecycleInstallPrepared(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown),16)
 LcpCheck(3307,NeonInit(),16) : LcpCheck(3308,lcpExtInits,1)
 LcpCheck(3309,NeonShutdown(),16) : LcpCheck(3310,lcpExtShutdowns,1)
 LcpCheck(3311,NeonLifecycleCleanupPending(),1) : LcpCheck(3312,gNeonReady,0)
 LcpCheck(3313,gNeonLifecycleError,8)
 lcpExtShutdownRc=0
 LcpCheck(3314,NeonShutdown(),0) : LcpCheck(3315,lcpExtShutdowns,2)
 LcpCheck(3316,NeonLifecycleCleanupPending(),0) : LcpCheck(3317,gNeonLifecycleError,0)
 LcpCheck(3318,NeonLifecycleBackend(),1) : LcpCheck(3319,NeonDrawBackendActive(),0)
 LcpCheck(3320,NeonLifecycleUseNative(),0) : LcpCheck(3321,NeonLifecycleBackend(),0)
 ; Successful init without draw hooks attempts rollback and retains its failure.
 LcpReset() : NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
 lcpSkipHooks=1 : lcpExtShutdownRc=8
 LcpCheck(3340,NeonInit(),16) : LcpCheck(3341,lcpExtShutdowns,1)
 LcpCheck(3342,NeonLifecycleCleanupPending(),1) : LcpCheck(3343,gNeonReady,0)
 LcpCheck(3344,gNeonLifecycleError,8) : LcpCheck(3345,NeonLifecycleUseNative(),16)
 lcpExtShutdownRc=0
 LcpCheck(3346,NeonShutdown(),0) : LcpCheck(3347,lcpExtShutdowns,2)
 LcpCheck(3348,NeonLifecycleCleanupPending(),0) : LcpCheck(3349,NeonDrawBackendActive(),0)
 LcpCheck(3350,NeonLifecycleUseNative(),0)
 ; Failed teardown of an active owner blocks both frame callbacks and init.
 LcpReset() : NeonLifecycleInstall(@LcpInit,@LcpFrameBegin,@LcpFrameEnd,@LcpShutdown)
 LcpCheck(3360,NeonInit(),0) : lcpExtShutdownRc=8
 LcpCheck(3361,NeonShutdown(),16) : LcpCheck(3362,NeonLifecycleCleanupPending(),1)
 LcpCheck(3363,gNeonReady,1) : LcpCheck(3364,NeonFrameBegin(0),16)
 LcpCheck(3365,lcpExtBegins,0) : LcpCheck(3366,NeonFrameEnd(),16)
 LcpCheck(3367,lcpExtEnds,0) : LcpCheck(3368,NeonInit(),16)
 LcpCheck(3369,lcpExtInits,1) : LcpCheck(3370,NeonLifecycleUseNative(),16)
 lcpExtShutdownRc=0
 LcpCheck(3371,NeonShutdown(),0) : LcpCheck(3372,NeonLifecycleCleanupPending(),0)
 LcpCheck(3373,gNeonReady,0) : LcpCheck(3374,NeonLifecycleUseNative(),0)
 ProcedureReturn lcpFailures
EndProcedure
