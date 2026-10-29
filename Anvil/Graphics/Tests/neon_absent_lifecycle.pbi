; SPDX-License-Identifier: MIT
XIncludeFile "Anvil/Graphics/neon_lifecycle_absent.pbi"
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
Global nlaReport.i,nlaCount.i,nlaFailure.i
Procedure NlaCheck(value.i,wanted.i)
  PokeI(nlaReport+256+nlaCount*16,value)
  PokeI(nlaReport+264+nlaCount*16,wanted)
  nlaCount=nlaCount+1
  If value<>wanted And nlaFailure=0 : nlaFailure=nlaCount : EndIf
EndProcedure
Procedure.i NeonAbsentLifecycleProof(report.i)
  If (report & 7)<>0 Or NeonByteSpan(report,1024)=0 : ProcedureReturn #NEON_ERR_ARGS : EndIf
  nlaReport=report : nlaCount=0 : nlaFailure=0
  PokeI(report,$4E4C4131)
  NlaCheck(NeonHardwareLifecycleFlags(),0)
  NlaCheck(NeonLifecycleBackend(),0)
  NlaCheck(NeonInit(),16)
  NlaCheck(NeonHardwareLifecycleFlags(),0)
  NlaCheck(NeonFrameBegin($FF000000),16)
  NlaCheck(NeonFrameEnd(),10)
  NlaCheck(NeonLifecycleCleanupPending(),0)
  NlaCheck(NeonShutdown(),0)
  NlaCheck(NeonHardwareLifecycleFlags(),0)
  NlaCheck(NeonInit(),16)
  NlaCheck(NeonShutdown(),0)
  NlaCheck(NeonDrawBackendActive(),0)
  PokeI(report+8,nlaFailure) : PokeI(report+16,nlaCount)
  ProcedureReturn nlaFailure
EndProcedure
