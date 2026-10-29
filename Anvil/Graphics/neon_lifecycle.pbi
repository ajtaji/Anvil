; SPDX-License-Identifier: MIT
; Shared Neon lifecycle policy and callback ownership. Include with exactly
; one native provider for the six typed operations below. Hardware flags are
; read-only snapshots; shared code never reads a board GPU-owner field.
; Native operation bodies retain their existing synchronization/contracts.
XIncludeFile "Anvil/Graphics/neon_frontend.pbi"

#NEON_NATIVE_LIFECYCLE_OWNER = 1
#NEON_NATIVE_LIFECYCLE_FRAME = 2
Declare.i NeonHardwareLifecycleFlags()
Declare NeonHardwareCoordinateReset()
Declare.i NeonHardwareInit()
Declare.i NeonHardwareShutdown()
Declare.i NeonHardwareFrameBegin(colour.i)
Declare.i NeonHardwareFrameEnd()

Global neon_inFrame.i  = 0
Global gNeonLifecycleMode.i       = #NEON_BACKEND_NATIVE
Global gNeonLifecyclePrepared.i   = 0
Global gNeonPreparedOwnerPending.i = 0
Declare.i nlf_LifecycleInitUnbound()
Declare.i nlf_LifecycleBeginUnbound(colour.i)
Declare.i nlf_LifecycleEndUnbound()
Declare.i nlf_LifecycleShutdownUnbound()
Global gNeonLifecycleInit.i       = @nlf_LifecycleInitUnbound
Global gNeonLifecycleBegin.i      = @nlf_LifecycleBeginUnbound
Global gNeonLifecycleEnd.i        = @nlf_LifecycleEndUnbound
Global gNeonLifecycleShutdown.i   = @nlf_LifecycleShutdownUnbound
Global gNeonLifecycleError.i      = 0
; A failed init/teardown still owns its callback and partial resource family.
Global gNeonLifecycleCleanupPending.i = 0

Procedure.i nlf_LifecycleInitUnbound()
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i nlf_LifecycleBeginUnbound(colour.i)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i nlf_LifecycleEndUnbound()
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i nlf_LifecycleShutdownUnbound()
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure nlf_LifecycleRestoreNative()
  gNeonLifecycleInit = @nlf_LifecycleInitUnbound
  gNeonLifecycleBegin = @nlf_LifecycleBeginUnbound
  gNeonLifecycleEnd = @nlf_LifecycleEndUnbound
  gNeonLifecycleShutdown = @nlf_LifecycleShutdownUnbound
  gNeonLifecycleError = #NEON_OK
  gNeonLifecycleMode = #NEON_BACKEND_NATIVE
  gNeonLifecyclePrepared = 0
  gNeonLifecycleCleanupPending = 0
EndProcedure

Procedure.i NeonLifecyclePreparedOwnerPending()
  ProcedureReturn gNeonPreparedOwnerPending
EndProcedure

Procedure.i nlf_PreparedInitRollback()
  Protected r.i
  If gNeonLifecyclePrepared = 0 Or gNeonLifecycleShutdown = 0
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  r = gNeonLifecycleShutdown()
  If r <> #NEON_OK
    gNeonLifecycleError = r
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  NeonDrawBackendClear()
  nlf_LifecycleRestoreNative()
  neon_inFrame = 0
  gNeonReady = 1
  gNeonPreparedOwnerPending = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonLifecycleInstall(initProc.i, beginProc.i, endProc.i, shutdownProc.i)
  If gNeonLifecycleCleanupPending <> 0 Or gNeonReady <> 0 Or neon_inFrame <> 0 Or (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_OWNER) <> 0
    NeonFrontendError(#NEON_ERR_BACKEND)
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  If initProc = 0 Or beginProc = 0 Or endProc = 0 Or shutdownProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  gNeonLifecycleInit = initProc
  gNeonLifecycleBegin = beginProc
  gNeonLifecycleEnd = endProc
  gNeonLifecycleShutdown = shutdownProc
  gNeonLifecycleError = #NEON_OK
  gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
  gNeonLifecyclePrepared = 0
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonLifecycleInstallPrepared(initProc.i, beginProc.i, endProc.i, shutdownProc.i)
  If gNeonLifecycleCleanupPending <> 0 Or gNeonLifecycleMode <> #NEON_BACKEND_NATIVE Or gNeonReady = 0 Or (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_OWNER) = 0 Or neon_inFrame <> 0 Or (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_FRAME) <> 0 Or NeonDrawBackendActive() = 0
    NeonFrontendError(#NEON_ERR_BACKEND)
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  If initProc = 0 Or beginProc = 0 Or endProc = 0 Or shutdownProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  gNeonLifecycleInit = initProc
  gNeonLifecycleBegin = beginProc
  gNeonLifecycleEnd = endProc
  gNeonLifecycleShutdown = shutdownProc
  gNeonLifecycleError = #NEON_OK
  gNeonLifecyclePrepared = 1
  gNeonPreparedOwnerPending = 0
  gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonLifecycleUseNative()
  If gNeonLifecycleCleanupPending <> 0 Or gNeonReady <> 0 Or neon_inFrame <> 0 Or (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_OWNER) <> 0
    NeonFrontendError(#NEON_ERR_BACKEND)
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  nlf_LifecycleRestoreNative()
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonLifecycleBackend()
  ProcedureReturn gNeonLifecycleMode
EndProcedure

Procedure.i NeonInit()
  Protected r.i, rollbackRc.i
  If gNeonLifecycleCleanupPending <> 0
    NeonFrontendError(#NEON_ERR_BACKEND)
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  gNeonReady = 0
  NeonFrontendError(#NEON_OK)
  NeonHardwareCoordinateReset()

  If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
    If gNeonLifecycleInit = 0
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    gNeonLifecycleCleanupPending = 1
    r = gNeonLifecycleInit()
    gNeonLifecycleError = r
    If r <> #NEON_OK
      If gNeonLifecyclePrepared <> 0
        rollbackRc = nlf_PreparedInitRollback()
        If rollbackRc = #NEON_OK : gNeonLifecycleError = r : EndIf
      EndIf
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    If NeonDrawBackendActive() = 0
      gNeonLifecycleError = #NEON_ERR_BACKEND
      If gNeonLifecyclePrepared <> 0
        rollbackRc = nlf_PreparedInitRollback()
        If rollbackRc = #NEON_OK : gNeonLifecycleError = #NEON_ERR_BACKEND : EndIf
      ElseIf gNeonLifecycleShutdown <> 0
        rollbackRc = gNeonLifecycleShutdown()
        If rollbackRc = #NEON_OK
          gNeonLifecycleCleanupPending = 0
        Else
          gNeonLifecycleError = rollbackRc
        EndIf
      EndIf
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    gNeonReady = 1
    gNeonLifecycleCleanupPending = 0
    ProcedureReturn #NEON_OK
  EndIf

  ProcedureReturn NeonHardwareInit()
EndProcedure

Procedure.i NeonShutdown()
  Protected r.i
  NeonHardwareCoordinateReset()
  If gNeonReady = 0 And gNeonLifecycleCleanupPending = 0 And (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_OWNER) = 0
    ProcedureReturn #NEON_OK
  EndIf
  If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
    If gNeonLifecycleShutdown = 0
      gNeonLifecycleCleanupPending = 1
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    r = gNeonLifecycleShutdown()
    gNeonLifecycleError = r
    If r <> #NEON_OK
      gNeonLifecycleCleanupPending = 1
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    gNeonLifecycleCleanupPending = 0
    NeonDrawBackendClear()
    neon_inFrame = 0
    If gNeonLifecyclePrepared <> 0
      ; The caller still owns the Vulkan device/target and must destroy them
      ; before releasing the native V3D context it lent to this adapter.
      nlf_LifecycleRestoreNative()
      gNeonReady = 1
      gNeonPreparedOwnerPending = 1
    Else
      gNeonReady = 0
    EndIf
    NeonFrontendError(#NEON_OK)
    ProcedureReturn #NEON_OK
  EndIf
  ProcedureReturn NeonHardwareShutdown()
EndProcedure

Procedure.i NeonFrameBegin(colour.i)
  Protected r.i

  If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
    If gNeonLifecycleCleanupPending <> 0
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    If gNeonReady = 0
      NeonFrontendError(#NEON_ERR_ARENA)
      ProcedureReturn #NEON_ERR_ARENA
    EndIf
    If neon_inFrame <> 0
      NeonFrontendError(#NEON_ERR_INFRAME)
      ProcedureReturn #NEON_ERR_INFRAME
    EndIf
    If gNeonLifecycleBegin = 0
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    r = gNeonLifecycleBegin(colour)
    gNeonLifecycleError = r
    If r <> #NEON_OK
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    neon_inFrame = 1
    ProcedureReturn #NEON_OK
  EndIf

  If neon_inFrame <> 0
    NeonFrontendError(#NEON_ERR_INFRAME)
    ProcedureReturn #NEON_ERR_INFRAME
  EndIf
  r = NeonHardwareFrameBegin(colour)
  If r <> #NEON_OK : NeonFrontendError(r) : EndIf
  If r = #NEON_OK : neon_inFrame = 1 : EndIf
  ProcedureReturn r
EndProcedure

Procedure.i NeonFrameEnd()
  Protected r.i

  If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL
    If gNeonLifecycleCleanupPending <> 0
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    If neon_inFrame = 0
      NeonFrontendError(#NEON_ERR_NOFRAME)
      ProcedureReturn #NEON_ERR_NOFRAME
    EndIf
    If gNeonLifecycleEnd = 0
      neon_inFrame = 0
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    r = gNeonLifecycleEnd()
    gNeonLifecycleError = r
    neon_inFrame = 0
    If r <> #NEON_OK
      NeonFrontendError(#NEON_ERR_BACKEND)
      ProcedureReturn #NEON_ERR_BACKEND
    EndIf
    NeonFrontendError(#NEON_OK)
    ProcedureReturn #NEON_OK
  EndIf

  If neon_inFrame = 0
    NeonFrontendError(#NEON_ERR_NOFRAME)
    ProcedureReturn #NEON_ERR_NOFRAME
  EndIf
  r = NeonHardwareFrameEnd()
  If r <> #NEON_OK : NeonFrontendError(r) : EndIf
  neon_inFrame = 0
  ProcedureReturn r
EndProcedure

; Read-only cleanup obligation; only successful cleanup releases it.
Procedure.i NeonLifecycleCleanupPending()
  ProcedureReturn gNeonLifecycleCleanupPending
EndProcedure
