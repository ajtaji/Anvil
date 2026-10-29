; SPDX-License-Identifier: MIT
; Shared resident provider over DrbgAutoSeed/AutoReseed/Generate.
; Include after the shared DRBG and its hardware entropy adapter.
; Calls are serialized by RandomService, core0 only. Never a weak fallback.
; Preserve SHA/HMAC working state across calls made between TLS advances.
Global Dim secRandomSaved.i[59]
Global randomDrbgInitialized.i,randomDrbgBytes.i
Procedure randomDrbgCopy(dst.i,src.i,n.i)
  Define i.i
  For i=0 To n-1 : PokeA(dst+i,PeekA(src+i)) : Next
EndProcedure
Procedure randomDrbgSave()
  Sha256Snapshot(@secRandomSaved[0])
  randomDrbgCopy(@secRandomSaved[0]+104,@secHmacIpad[0],104)
  randomDrbgCopy(@secRandomSaved[0]+208,@secHmacOpad[0],104)
  randomDrbgCopy(@secRandomSaved[0]+312,@secHmacBlk[0],64)
  randomDrbgCopy(@secRandomSaved[0]+376,@secHmacKeyBuf[0],32)
  randomDrbgCopy(@secRandomSaved[0]+408,@secHmacInner[0],32)
  randomDrbgCopy(@secRandomSaved[0]+440,@secHmacMac[0],32)
EndProcedure
Procedure randomDrbgRestore()
  Define i.i
  Sha256Restore(@secRandomSaved[0])
  randomDrbgCopy(@secHmacIpad[0],@secRandomSaved[0]+104,104)
  randomDrbgCopy(@secHmacOpad[0],@secRandomSaved[0]+208,104)
  randomDrbgCopy(@secHmacBlk[0],@secRandomSaved[0]+312,64)
  randomDrbgCopy(@secHmacKeyBuf[0],@secRandomSaved[0]+376,32)
  randomDrbgCopy(@secHmacInner[0],@secRandomSaved[0]+408,32)
  randomDrbgCopy(@secHmacMac[0],@secRandomSaved[0]+440,32)
  For i=0 To 58 : secRandomSaved[i]=0 : Next
EndProcedure
Procedure.i RandomDrbgReady()
  Define rc.i
  If randomDrbgInitialized<>0 And DrbgSeeded()<>0 And randomDrbgBytes<1048576
    ProcedureReturn 1
  EndIf
  If DrbgEntropyAvailable()<>1 : ProcedureReturn -1 : EndIf
  randomDrbgSave()
  If randomDrbgInitialized=0 Or DrbgSeeded()=0
    rc=DrbgAutoSeed()
  Else
    rc=DrbgAutoReseed()
  EndIf
  randomDrbgRestore()
  If rc<>#DRBG_OK : ProcedureReturn -1 : EndIf
  randomDrbgInitialized=1 : randomDrbgBytes=0 : ProcedureReturn 1
EndProcedure
Procedure.i RandomDrbgGenerate(dst.i,n.i)
  Define rc.i
  If dst<=0 Or n<1 Or n>4096 : ProcedureReturn -1 : EndIf
  If RandomDrbgReady()<>1 : ProcedureReturn -1 : EndIf
  randomDrbgSave()
  rc=DrbgGenerate(dst,n)
  randomDrbgRestore()
  If rc=n : randomDrbgBytes=randomDrbgBytes+n : EndIf
  ProcedureReturn rc
EndProcedure
