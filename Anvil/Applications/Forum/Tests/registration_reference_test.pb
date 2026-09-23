; Deterministic reference transactions and opaque crypto handles ONLY.
; No cryptography, email delivery or production database is implemented here.
Declare.i ForumRegServicesReady()
Declare.i ForumRegNow()
Declare.i ForumRegCanonicalEmail(email.i)
Declare.i ForumRegRandomToken(bytes.i)
Declare.i ForumRegTokenDigest(token.i)
Declare.i ForumRegPasswordVerifier(password.i)
Declare.i ForumRegStoreChallenge(identity.i, origin.i, token.i, digest.i, now.i, expiry.i)
Declare.i ForumRegAdmitRedeem(origin.i, now.i)
Declare.i ForumRegConsumeAndCreate(digest.i, verifier.i, origin.i, now.i)
Declare ForumRegRelease(handle.i)
XIncludeFile "../registration.pbi"
Global clock.i=1000, ready.i=1, crypto.i=1, storage.i=1, admit.i=1
Global nextToken.i=100, liveDigest.i, issued.i, expires.i, consumed.i
Global accounts.i, outbox.i, requests.i, originRequests.i, verifies.i
Global checks.i, failures.i, releases.i

Procedure Check(value.i)
  checks+1
  If value=0 : failures+1 : EndIf
EndProcedure
Procedure ResetStore()
  liveDigest=0 : issued=0 : expires=0 : consumed=0
  accounts=0 : outbox=0 : requests=0 : originRequests=0
  clock=1000 : ready=1 : crypto=1 : storage=1 : admit=1 : verifies=0
EndProcedure
Procedure.i ForumRegServicesReady() : ProcedureReturn ready : EndProcedure
Procedure.i ForumRegNow() : ProcedureReturn clock : EndProcedure
Procedure.i ForumRegCanonicalEmail(email.i) : ProcedureReturn email : EndProcedure
Procedure.i ForumRegRandomToken(bytes.i)
  If crypto=0 Or bytes<>32 : ProcedureReturn 0 : EndIf
  nextToken+1 : ProcedureReturn nextToken
EndProcedure
Procedure.i ForumRegTokenDigest(token.i)
  If crypto=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn token+10000
EndProcedure
Procedure.i ForumRegPasswordVerifier(password.i)
  verifies+1
  If crypto=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 55555
EndProcedure
Procedure ForumRegRelease(handle.i) : releases+1 : EndProcedure
Procedure.i ForumRegAdmitRedeem(origin.i, now.i) : ProcedureReturn admit : EndProcedure
Procedure.i ForumRegStoreChallenge(identity.i, origin.i, token.i, digest.i, now.i, expiry.i)
  If storage=0 : ProcedureReturn -1 : EndIf
  ; Reference serialized transaction. Real store must enforce this across threads.
  originRequests+1
  If accounts<>0 Or originRequests>#FORUM_REG_ORIGIN_LIMIT : ProcedureReturn 0 : EndIf
  If liveDigest<>0 And now-issued<#FORUM_REG_RESEND_WAIT : ProcedureReturn 0 : EndIf
  If requests>=#FORUM_REG_IDENTITY_LIMIT : ProcedureReturn 0 : EndIf
  requests+1 : liveDigest=digest : issued=now : expires=expiry : consumed=0
  outbox+1
  ProcedureReturn 1
EndProcedure
Procedure.i ForumRegConsumeAndCreate(digest.i, verifier.i, origin.i, now.i)
  If storage=0 : ProcedureReturn -1 : EndIf
  If liveDigest=0 Or digest<>liveDigest Or consumed<>0 Or now<issued Or now>=expires Or accounts<>0
    ProcedureReturn 0
  EndIf
  consumed=1 : accounts+1
  ProcedureReturn 1
EndProcedure

Define first.i, second.i, i.i
ResetStore()
ready=0 : Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_UNAVAILABLE)) : Check(Bool(accounts=0 And outbox=0))
ready=1 : clock=0 : Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_CLOCK))
clock=1000 : crypto=0 : Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_CRYPTO))
Check(Bool(accounts=0 And outbox=0))
ResetStore()
Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_PENDING)) : first=nextToken
Check(Bool(accounts=0 And outbox=1 And verifies=0))
Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_DENIED))
Check(Bool(outbox=1 And accounts=0))
Check(Bool(ForumRegRedeem(first+900,9,1)=#FORUM_REG_DENIED))
Check(Bool(accounts=0))
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_VERIFIED))
Check(Bool(accounts=1))
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_DENIED))
Check(Bool(accounts=1))
Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_DENIED))
Check(Bool(outbox=1))
ResetStore()
ForumRegBegin(1,1) : first=nextToken : clock+60
Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_PENDING)) : second=nextToken
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_DENIED))
clock=expires : Check(Bool(ForumRegRedeem(second,9,1)=#FORUM_REG_DENIED))
Check(Bool(accounts=0))
ResetStore()
For i=1 To 5 : Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_PENDING)) : clock+60 : Next
Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_DENIED)) : Check(Bool(accounts=0 And outbox=5))
ResetStore()
originRequests=20 : Check(Bool(ForumRegBegin(1,1)=#FORUM_REG_DENIED))
ResetStore()
ForumRegBegin(1,1) : first=nextToken : storage=0
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_STORAGE))
Check(Bool(accounts=0 And consumed=0))
storage=1 : admit=0 : verifies=0
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_DENIED)) : Check(Bool(verifies=0))
admit=1
; Two contenders at the serialized commit boundary: one winner, one replay.
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_VERIFIED))
Check(Bool(ForumRegRedeem(first,9,1)=#FORUM_REG_DENIED)) : Check(Bool(accounts=1))
For i=-5 To 3 : Check(Bool(ForumRegPublicReply(i)=1)) : Next
Check(Bool(ForumRegImportDisposition(0,1,1)=#FORUM_REG_IMPORT_REFUSE))
Check(Bool(ForumRegImportDisposition(1,1,1)=#FORUM_REG_IMPORT_VERIFIED))
Check(Bool(ForumRegImportDisposition(1,0,1)=#FORUM_REG_IMPORT_QUARANTINE))
Check(Bool(ForumRegImportDisposition(1,1,0)=#FORUM_REG_IMPORT_QUARANTINE))
OpenConsole()
PrintN("Registration domain reference checks="+Str(checks)+" failures="+Str(failures))
End failures
