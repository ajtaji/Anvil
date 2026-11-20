; Optional cooperative checkpoints return 1 to continue and 0 to cancel.
; Synchronous users continue through the same arithmetic without a scheduler.
Procedure.i crypto_ContinueWork() : ProcedureReturn 1 : EndProcedure
Procedure.i CryptoProgressCheck(callback.i)
 Protected *resume=@crypto_ContinueWork
 If callback<>0 : *resume=callback : EndIf
 ProcedureReturn resume()
EndProcedure
