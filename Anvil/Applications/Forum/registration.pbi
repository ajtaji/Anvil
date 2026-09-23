; Verified-first registration domain. Dependencies are supplied before this include.
; Handles below are opaque service-owned values, not persistent plaintext secrets.
; This module creates no user IDs and contains no crypto or storage implementation.
#FORUM_REG_PENDING = 1
#FORUM_REG_VERIFIED = 2
#FORUM_REG_DENIED = 3
#FORUM_REG_UNAVAILABLE = -1
#FORUM_REG_CLOCK = -2
#FORUM_REG_INPUT = -3
#FORUM_REG_CRYPTO = -4
#FORUM_REG_STORAGE = -5
#FORUM_REG_TTL = 900
#FORUM_REG_RESEND_WAIT = 60
#FORUM_REG_IDENTITY_LIMIT = 5
#FORUM_REG_ORIGIN_LIMIT = 20
#FORUM_REG_LIMIT_WINDOW = 3600
#FORUM_REG_IMPORT_REFUSE = 0
#FORUM_REG_IMPORT_VERIFIED = 1
#FORUM_REG_IMPORT_QUARANTINE = 2

Procedure.i ForumRegPublicReply(internalResult.i)
  ; An acknowledgement is never a statement that an account exists or login works.
  ; The server logs the distinct internal result without email/token/password data.
  ProcedureReturn 1
EndProcedure

Procedure.i ForumRegBegin(email.i, trustedOrigin.i)
  Define now.i
  Define identity.i
  Define token.i
  Define digest.i
  Define stored.i
  If ForumRegServicesReady() <> 1
    ProcedureReturn #FORUM_REG_UNAVAILABLE
  EndIf
  now = ForumRegNow()
  If now <= 0 Or now > $7FFFFFFFFFFFF000
    ProcedureReturn #FORUM_REG_CLOCK
  EndIf
  identity = ForumRegCanonicalEmail(email)
  If identity = 0 Or trustedOrigin = 0
    If identity <> 0 : ForumRegRelease(identity) : EndIf
    ProcedureReturn #FORUM_REG_INPUT
  EndIf
  ; Cryptographic service guarantees at least 256 unpredictable bits.
  token = ForumRegRandomToken(32)
  If token = 0
    ForumRegRelease(identity)
    ProcedureReturn #FORUM_REG_CRYPTO
  EndIf
  digest = ForumRegTokenDigest(token)
  If digest = 0
    ForumRegRelease(token)
    ForumRegRelease(identity)
    ProcedureReturn #FORUM_REG_CRYPTO
  EndIf
  ; One transaction applies identity/origin limits, checks existing accounts,
  ; supersedes an old challenge only when allowed, and persists pending+outbox.
  ; Returns 1 for queued, 0 for deliberately suppressed, negative on storage error.
  ; Raw token is sealed in mail outbox; pending lookup stores only its digest.
  stored = ForumRegStoreChallenge(identity, trustedOrigin, token, digest, now, now + #FORUM_REG_TTL)
  ForumRegRelease(digest)
  ForumRegRelease(token)
  ForumRegRelease(identity)
  If stored < 0
    ProcedureReturn #FORUM_REG_STORAGE
  EndIf
  If stored = 0
    ProcedureReturn #FORUM_REG_DENIED
  EndIf
  If stored <> 1
    ProcedureReturn #FORUM_REG_STORAGE
  EndIf
  ProcedureReturn #FORUM_REG_PENDING
EndProcedure

Procedure.i ForumRegRedeem(token.i, password.i, trustedOrigin.i)
  Define now.i
  Define digest.i
  Define verifier.i
  Define result.i
  If ForumRegServicesReady() <> 1
    ProcedureReturn #FORUM_REG_UNAVAILABLE
  EndIf
  now = ForumRegNow()
  If now <= 0 Or now > $7FFFFFFFFFFFF000
    ProcedureReturn #FORUM_REG_CLOCK
  EndIf
  If token = 0 Or password = 0 Or trustedOrigin = 0
    ProcedureReturn #FORUM_REG_INPUT
  EndIf
  ; Limit before expensive crypto. Origin is supplied by trusted transport,
  ; never accepted as an arbitrary user-provided header or form field.
  If ForumRegAdmitRedeem(trustedOrigin, now) <> 1
    ProcedureReturn #FORUM_REG_DENIED
  EndIf
  digest = ForumRegTokenDigest(token)
  If digest = 0
    ProcedureReturn #FORUM_REG_CRYPTO
  EndIf
  verifier = ForumRegPasswordVerifier(password)
  If verifier = 0
    ForumRegRelease(digest)
    ProcedureReturn #FORUM_REG_CRYPTO
  EndIf
  ; THIS is the only account creation boundary. Storage atomically verifies
  ; digest, issued <= now < expiry, unused/current challenge and unique email;
  ; then consumes proof and inserts verified account+verifier in one commit.
  ; Concurrent redemption must have exactly one successful commit. No UID may
  ; become visible before this commit; transaction failure leaves no account.
  result = ForumRegConsumeAndCreate(digest, verifier, trustedOrigin, now)
  ForumRegRelease(verifier)
  ForumRegRelease(digest)
  If result < 0
    ProcedureReturn #FORUM_REG_STORAGE
  EndIf
  If result = 1
    ProcedureReturn #FORUM_REG_VERIFIED
  EndIf
  If result <> 0
    ProcedureReturn #FORUM_REG_STORAGE
  EndIf
  ProcedureReturn #FORUM_REG_DENIED
EndProcedure

Procedure.i ForumRegImportDisposition(trustedSnapshot.i, emailProof.i, hasCanonicalEmail.i)
  ; Classification only; this never creates, updates, deletes or authenticates.
  ; Proof means source-version-specific verified-email metadata, not a role,
  ; provider name, social login, administrator flag or merely a nonempty email.
  If trustedSnapshot <> 1
    ProcedureReturn #FORUM_REG_IMPORT_REFUSE
  EndIf
  If emailProof = 1 And hasCanonicalEmail = 1
    ProcedureReturn #FORUM_REG_IMPORT_VERIFIED
  EndIf
  ; Preserve legacy identifiers/content in quarantine, outside active users,
  ; memberships, public user lists and login. Existing source users are not deleted.
  ProcedureReturn #FORUM_REG_IMPORT_QUARANTINE
EndProcedure
