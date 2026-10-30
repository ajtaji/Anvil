; NIST SP 800-38D sections 7.1 and 7.2; uses the existing BearSSL-derived AES/GHASH
; primitives (licenses/BearSSL-LICENSE.txt). Scheduling and private state here
; are separate from those primitives; no upstream code is copied here.
; Bounded AES-GCM encryption/decryption with a 96-bit nonce. Include aes and gcm first.
; One job owns its copied key, nonce, tag, H and accumulator. Each step moves
; at most 256 bytes and retains no dependency on shared AES/GHASH scratch.
; Input/AAD/output spans stay alive until completion or cancellation. Cipher
; and plaintext may be identical, otherwise they must not overlap. The caller
; must not modify inputs during a job. No plaintext is written before the
; complete authentication tag matches. Cancellation does not erase caller data.
; Begin/Step: 0 pending, 1 complete, negative refused. Result: 1 authentic,
; 0 forged, -1 cancelled/idle. A second Begin returns -2 without changing owner.
Global gcmj_encrypt.i,gcmj_tagOut.i
Global GcmJobResult.i=-1
Global gcmj_phase.i,gcmj_keyBytes.i,gcmj_aad.i,gcmj_aadBytes.i
Global gcmj_cipher.i,gcmj_plain.i,gcmj_bytes.i,gcmj_offset.i
Global Dim gcmj_key.a[32]
Global Dim gcmj_nonce.a[12]
Global Dim gcmj_tag.a[16]
Global Dim gcmj_h.a[16]
Global Dim gcmj_y.a[16]

Procedure GcmJobCancel()
 Define i.i
 For i=0 To 31 : gcmj_key[i]=0 : Next
 For i=0 To 11 : gcmj_nonce[i]=0 : Next
 For i=0 To 15 : gcmj_tag[i]=0 : gcmj_h[i]=0 : gcmj_y[i]=0 : Next
 gcmj_encrypt=0 : gcmj_tagOut=0
 gcmj_phase=0 : gcmj_keyBytes=0 : gcmj_aad=0 : gcmj_aadBytes=0
 gcmj_cipher=0 : gcmj_plain=0 : gcmj_bytes=0 : gcmj_offset=0
 GcmJobResult=-1
EndProcedure

Procedure.i gcmj_Begin(key.i,keyBytes.i,nonce.i,aad.i,aadBytes.i,cipher.i,bytes.i,plain.i,tag.i,encrypt.i)
 Define i.i
 If gcmj_phase<>0 : ProcedureReturn -2 : EndIf
 GcmJobCancel()
 If key=0 Or nonce=0 Or tag=0 : ProcedureReturn -1 : EndIf
 If keyBytes<>16 And keyBytes<>24 And keyBytes<>32 : ProcedureReturn -1 : EndIf
 ; The underlying length encoder accepts 32-bit byte counts.
 If bytes<0 Or bytes>$FFFFFFFF Or aadBytes<0 Or aadBytes>$FFFFFFFF : ProcedureReturn -1 : EndIf
 If aadBytes>0 And aad=0 : ProcedureReturn -1 : EndIf
 If bytes>0
  If cipher=0 Or plain=0 : ProcedureReturn -1 : EndIf
  If cipher<>plain
   If cipher<plain+bytes And plain<cipher+bytes : ProcedureReturn -1 : EndIf
  EndIf
 EndIf
 If encrypt<>0
  If tag<plain+bytes And plain<tag+16 : ProcedureReturn -1 : EndIf
  If tag<cipher+bytes And cipher<tag+16 : ProcedureReturn -1 : EndIf
 EndIf
 gcmj_encrypt=encrypt : gcmj_tagOut=tag
 For i=0 To keyBytes-1 : gcmj_key[i]=PeekA(key+i) : Next
 For i=0 To 11 : gcmj_nonce[i]=PeekA(nonce+i) : Next
 If encrypt=0
  For i=0 To 15 : gcmj_tag[i]=PeekA(tag+i) : Next
 EndIf
 gcmj_keyBytes=keyBytes : gcmj_aad=aad : gcmj_aadBytes=aadBytes
 gcmj_cipher=cipher : gcmj_plain=plain : gcmj_bytes=bytes
 If GcmInit(@gcmj_key[0],keyBytes)=0 : GcmJobCancel() : ProcedureReturn -1 : EndIf
 For i=0 To 15 : gcmj_h[i]=secGcmH[i] : Next
 GcmWipe() : AesWipe()
 gcmj_phase=1
 ProcedureReturn 0
EndProcedure

Procedure.i GcmJobBeginDecrypt(key.i,keyBytes.i,nonce.i,aad.i,aadBytes.i,cipher.i,bytes.i,plain.i,tag.i)
 ProcedureReturn gcmj_Begin(key,keyBytes,nonce,aad,aadBytes,cipher,bytes,plain,tag,0)
EndProcedure

; Tag is written only on completion and must not overlap either data span.
; Encryption inputs are plaintext; output is ciphertext. Cancellation may
; leave partial ciphertext, which must not be sent without the final tag.
Procedure.i GcmJobBeginEncrypt(key.i,keyBytes.i,nonce.i,aad.i,aadBytes.i,plain.i,bytes.i,cipher.i,tag.i)
 ProcedureReturn gcmj_Begin(key,keyBytes,nonce,aad,aadBytes,plain,bytes,cipher,tag,1)
EndProcedure

Procedure.i GcmJobStep()
 Define n.i,i.i,diff.i,rc.i
 If gcmj_phase=0 : ProcedureReturn -1 : EndIf
 If gcmj_phase=1 Or gcmj_phase=2
  If gcmj_phase=1 : n=gcmj_aadBytes-gcmj_offset : Else : n=gcmj_bytes-gcmj_offset : EndIf
  If n>256 : n=256 : EndIf
  If n>0
   If gcmj_phase=1
    GhashRun(@gcmj_y[0],@gcmj_h[0],gcmj_aad+gcmj_offset,n)
   ElseIf gcmj_encrypt<>0
    rc=AesCtrInit(@gcmj_key[0],gcmj_keyBytes)
    rc=AesCtrCore(@gcmj_nonce[0],2+(gcmj_offset/16),gcmj_cipher+gcmj_offset,gcmj_plain+gcmj_offset,n)
    AesWipe()
    GhashRun(@gcmj_y[0],@gcmj_h[0],gcmj_plain+gcmj_offset,n)
   Else
    GhashRun(@gcmj_y[0],@gcmj_h[0],gcmj_cipher+gcmj_offset,n)
   EndIf
   gcmj_offset=gcmj_offset+n
  EndIf
  If gcmj_phase=1
   If gcmj_offset=gcmj_aadBytes : gcmj_phase=2 : gcmj_offset=0 : EndIf
  Else
   If gcmj_offset=gcmj_bytes : gcmj_phase=3 : gcmj_offset=0 : EndIf
  EndIf
  ProcedureReturn 0
 EndIf
 If gcmj_phase=3
  GcmBuildLenBlock(gcmj_aadBytes,gcmj_bytes)
  GhashRun(@gcmj_y[0],@gcmj_h[0],@GcmLenBlk[0],16)
  rc=AesCtrInit(@gcmj_key[0],gcmj_keyBytes)
  rc=AesCtrCore(@gcmj_nonce[0],1,@gcmj_y[0],@gcmj_y[0],16)
  AesWipe()
  If gcmj_encrypt<>0
   For i=0 To 15 : PokeA(gcmj_tagOut+i,gcmj_y[i]) : Next
   GcmJobCancel() : GcmJobResult=1 : ProcedureReturn 1
  EndIf
  diff=0
  For i=0 To 15 : diff=diff | (gcmj_y[i] ! gcmj_tag[i]) : Next
  If diff<>0
   GcmJobCancel() : GcmJobResult=0 : ProcedureReturn 1
  EndIf
  gcmj_phase=4
  ProcedureReturn 0
 EndIf
 n=gcmj_bytes-gcmj_offset : If n>256 : n=256 : EndIf
 If n>0
  rc=AesCtrInit(@gcmj_key[0],gcmj_keyBytes)
  rc=AesCtrCore(@gcmj_nonce[0],2+(gcmj_offset/16),gcmj_cipher+gcmj_offset,gcmj_plain+gcmj_offset,n)
  AesWipe()
  gcmj_offset=gcmj_offset+n
 EndIf
 If gcmj_offset=gcmj_bytes
  GcmJobCancel() : GcmJobResult=1 : ProcedureReturn 1
 EndIf
 ProcedureReturn 0
EndProcedure
