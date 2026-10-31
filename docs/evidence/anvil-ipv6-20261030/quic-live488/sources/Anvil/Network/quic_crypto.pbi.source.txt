; SPDX-License-Identifier: MIT
; Independently implemented QUIC v1 AES-128-GCM protection policy, RFC 9001
; sections 5.1-5.4 and 5.8: https://www.rfc-editor.org/rfc/rfc9001.html
; Compose shared SHA256/HMAC/HKDF, AES/GCM and GCM jobs before this module.
; No second cipher implementation. Key derivation moves one HKDF operation per
; Step; packet jobs move one existing bounded GCM operation per Step.
XIncludeFile "Anvil/Network/quic_wire.pbi"
#QUIC_CRYPTO_ARGUMENT=-3341
#QUIC_CRYPTO_BUSY=-3342
#QUIC_CRYPTO_AUTH=-3343
#QUIC_CRYPTO_RESERVED=-3344
#QUIC_CRYPTO_CANCELLED=-3345
#QUIC_CRYPTO_STATE=-3346
#QUIC_CRYPTO_MAX_PACKET=65527
Structure QuicKeys
 secret0.q
 secret1.q
 secret2.q
 secret3.q
 key0.q
 key1.q
 iv0.q
 iv1.q
 hp0.q
 hp1.q
 ready.i
EndStructure
Structure QuicKeyJob
 phase.i
 keys.i
 side.i
 idBytes.i
 id0.q
 id1.q
 id2.q
 initial0.q
 initial1.q
 initial2.q
 initial3.q
EndStructure

Procedure QuicKeysWipe(*keys.QuicKeys)
 Define i.i
 If *keys=0 : ProcedureReturn : EndIf
 For i=0 To SizeOf(QuicKeys)-1 : PokeA(*keys+i,0) : Next
EndProcedure

Procedure QuicKeyJobCancel(*j.QuicKeyJob)
 Define i.i
 If *j=0 : ProcedureReturn : EndIf
 If *j\phase>0 : QuicKeysWipe(*j\keys) : EndIf
 For i=0 To SizeOf(QuicKeyJob)-1 : PokeA(*j+i,0) : Next
EndProcedure

; Zero-initialize job and keys before first use. Keys belong exclusively to
; this job until completion. side0=client Initial keys, side1=server.
Procedure.i QuicInitialKeysBegin(*j.QuicKeyJob,*keys.QuicKeys,id.i,bytes.i,side.i)
 Define i.i
 If *j=0 Or *keys=0 Or id=0 Or bytes<1 Or bytes>20 Or side<0 Or side>1 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If *j\phase<>0 : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 QuicKeysWipe(*keys) : *j\keys=*keys : *j\side=side : *j\idBytes=bytes
 For i=0 To bytes-1 : PokeA(@*j\id0+i,PeekA(id+i)) : Next
 *j\phase=1 : ProcedureReturn 0
EndProcedure

; TLS traffic-secret adapter for AES-128-GCM/SHA256. Cipher-suite negotiation,
; generation/key-phase ownership and packet-number uniqueness belong to owner.
Procedure.i QuicTrafficKeysBegin(*j.QuicKeyJob,*keys.QuicKeys,secret.i,bytes.i)
 Define i.i
 If *j=0 Or *keys=0 Or secret=0 Or bytes<>32 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If *j\phase<>0 : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 ; secret must not alias keys: the caller retains its own TLS secret.
 QuicKeysWipe(*keys) : *j\keys=*keys
 For i=0 To 31 : PokeA(@*keys\secret0+i,PeekA(secret+i)) : Next
 *j\phase=3 : ProcedureReturn 0
EndProcedure

Procedure.i QuicKeyJobStep(*j.QuicKeyJob)
 Define *keys.QuicKeys,rc.i,label.i
 If *j=0 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If *j\phase=0 : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
 *keys=*j\keys
 Select *j\phase
  Case 1
   HkdfExtract(?quic_v1_salt,20,@*j\id0,*j\idBytes,@*j\initial0)
  Case 2
   label="client in" : If *j\side=1 : label="server in" : EndIf
   rc=HkdfExpandLabel(@*j\initial0,32,label,9,0,0,@*keys\secret0,32)
  Case 3 : rc=HkdfExpandLabel(@*keys\secret0,32,"quic key",8,0,0,@*keys\key0,16)
  Case 4 : rc=HkdfExpandLabel(@*keys\secret0,32,"quic iv",7,0,0,@*keys\iv0,12)
  Case 5 : rc=HkdfExpandLabel(@*keys\secret0,32,"quic hp",7,0,0,@*keys\hp0,16)
 EndSelect
 If rc<0 : QuicKeyJobCancel(*j) : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
 *j\phase=*j\phase+1
 If *j\phase=6
  *j\phase=0 : QuicKeyJobCancel(*j) : *keys\ready=1 : ProcedureReturn 1
 EndIf
 ProcedureReturn 0
EndProcedure

Structure QuicPacketJob
 phase.i
 result.i
 packet.i
 packetBytes.i
 numberOffset.i
 numberBytes.i
 number.i
 plainOffset.i
 plainBytes.i
 encrypt.i
 reserved.i
 first.i
 original.q
 hp0.q
 hp1.q
 nonce0.q
 nonce1.q
 mask0.q
 mask1.q
EndStructure
Global quicCryptoOwner.i
; Bind to Tls13RecInvalidateCipher when TLS records share these AES globals.
; Called only at crypto operation boundaries, never from inside a primitive.
Global *QuicCipherInvalidateHook

Procedure quicc_Invalidate()
 If QuicCipherInvalidateHook<>0 : QuicCipherInvalidateHook() : EndIf
EndProcedure
Procedure quicc_RestoreHeader(*j.QuicPacketJob)
 Define i.i
 PokeA(*j\packet,*j\first)
 For i=0 To 3 : PokeA(*j\packet+*j\numberOffset+i,PeekA(@*j\original+i)) : Next
EndProcedure
Procedure.i quicc_Finish(*j.QuicPacketJob,rc.i)
 Define i.i
 For i=0 To 47 : PokeA(@*j\hp0+i,0) : Next
 *j\phase=0 : *j\result=rc : quicCryptoOwner=0
 ProcedureReturn rc
EndProcedure
Procedure.i quicc_Mask(*j.QuicPacketJob)
 quicc_Invalidate()
 If AesSetKey(@*j\hp0,16)=0 : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
 AesEncryptBlock(*j\packet+*j\numberOffset+4,@*j\mask0)
 AesWipe() : ProcedureReturn 1
EndProcedure

; In-place packet job. packet includes 16 tag bytes (space reserved on encrypt).
; On decrypt, largestOrNumber is last AUTHENTICATED largest PN (-1 initially);
; on encrypt it is the full UNIQUE packet number under this key. Buffers and job
; remain exclusively owned until terminal result. No network transmission or
; plaintext consumption while pending. One job shares the existing GCM owner.
; Authentication failure restores the original wire packet, exposing no plaintext.
Procedure.i QuicPacketJobBegin(*j.QuicPacketJob,*keys.QuicKeys,packet.i,bytes.i,shortIdBytes.i,largestOrNumber.i,encrypt.i)
 Define h.QuicPacketHeader,i.i,rc.i,n.i,mask.i,low.i
 If *j=0 Or *keys=0 Or packet=0 Or bytes<1 Or bytes>#QUIC_CRYPTO_MAX_PACKET Or encrypt<0 Or encrypt>1 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If quicCryptoOwner<>0 Or GcmJobBusy()<>0 : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 If *keys\ready<>1 : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
 If largestOrNumber< -1 Or largestOrNumber>#QUIC_INTEGER_MAX Or (encrypt=1 And largestOrNumber<0) : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 rc=QuicPacketRead(@h,packet,bytes,shortIdBytes) : If rc<>1 : ProcedureReturn rc : EndIf
 If h\kind=#QUIC_PACKET_RETRY Or h\kind=#QUIC_PACKET_NEGOTIATION : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 For i=0 To SizeOf(QuicPacketJob)-1 : PokeA(*j+i,0) : Next
 *j\packet=packet : *j\packetBytes=h\packetBytes : *j\numberOffset=h\numberOffset : *j\encrypt=encrypt : *j\first=PeekA(packet)
 For i=0 To 3 : PokeA(@*j\original+i,PeekA(packet+h\numberOffset+i)) : Next
 For i=0 To 15 : PokeA(@*j\hp0+i,PeekA(@*keys\hp0+i)) : Next
 mask=15 : If h\kind=#QUIC_PACKET_SHORT : mask=31 : EndIf
 If encrypt=0
  rc=quicc_Mask(*j)
  If rc<0 : ProcedureReturn quicc_Finish(*j,rc) : EndIf
  PokeA(packet,PeekA(packet) ! (PeekA(@*j\mask0) & mask))
 EndIf
 n=(PeekA(packet) & 3)+1 : *j\numberBytes=n
 low=0
 For i=0 To n-1
  If encrypt=0 : PokeA(packet+h\numberOffset+i,PeekA(packet+h\numberOffset+i) ! PeekA(@*j\mask0+1+i)) : EndIf
  low=(low<<8)|PeekA(packet+h\numberOffset+i)
 Next
 mask=12 : If h\kind=#QUIC_PACKET_SHORT : mask=24 : EndIf
 *j\reserved=PeekA(packet) & mask
 If encrypt
  rc=1
  If low<>(largestOrNumber & ((1 << (n*8))-1)) Or *j\reserved<>0 : rc=#QUIC_CRYPTO_ARGUMENT : EndIf
  *j\number=largestOrNumber
 Else
  rc=QuicPacketNumberRead(low,n,largestOrNumber,@*j\number)
 EndIf
 If rc<0
  If encrypt=0 : quicc_RestoreHeader(*j) : EndIf
  ProcedureReturn quicc_Finish(*j,rc)
 EndIf
 *j\plainOffset=h\numberOffset+n : *j\plainBytes=h\packetBytes-*j\plainOffset-16
 For i=0 To 11 : PokeA(@*j\nonce0+i,PeekA(@*keys\iv0+i)) : Next
 For i=0 To 7 : PokeA(@*j\nonce0+11-i,PeekA(@*j\nonce0+11-i) ! ((*j\number >> (i*8)) & 255)) : Next
 quicc_Invalidate()
 If encrypt
  rc=GcmJobBeginEncrypt(@*keys\key0,16,@*j\nonce0,packet,*j\plainOffset,packet+*j\plainOffset,*j\plainBytes,packet+*j\plainOffset,packet+h\packetBytes-16)
 Else
  rc=GcmJobBeginDecrypt(@*keys\key0,16,@*j\nonce0,packet,*j\plainOffset,packet+*j\plainOffset,*j\plainBytes,packet+*j\plainOffset,packet+h\packetBytes-16)
 EndIf
 If rc<>0
  If encrypt=0 : quicc_RestoreHeader(*j) : EndIf
  ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_STATE)
 EndIf
 quicCryptoOwner=*j : *j\phase=1 : ProcedureReturn 0
EndProcedure

; Retry uses caller-owned contiguous storage: one ODCID-length byte, that many
; original destination ID bytes (0..20), then the complete Retry wire packet,
; including 16 reserved tag bytes. Only the wire packet is transmitted. Keeping
; this prefix in receive headroom avoids an unbounded packet copy at admission.
; writeTag=0 verifies without mutation; writeTag=1 creates the outgoing tag.
; RFC v1 constants are public: this integrity check does NOT verify peer identity.
Procedure.i QuicRetryJobBegin(*j.QuicPacketJob,pseudo.i,bytes.i,writeTag.i)
 Define h.QuicPacketHeader,n.i,packet.i,count.i,rc.i,i.i
 If *j=0 Or pseudo=0 Or bytes<18 Or bytes>#QUIC_CRYPTO_MAX_PACKET+21 Or writeTag<0 Or writeTag>1 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If quicCryptoOwner<>0 Or GcmJobBusy()<>0 : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 n=PeekA(pseudo)
 If n>20 Or n>=bytes-1 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 packet=pseudo+1+n : count=bytes-1-n
 If count>#QUIC_CRYPTO_MAX_PACKET : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 rc=QuicPacketRead(@h,packet,count,0) : If rc<>1 : ProcedureReturn rc : EndIf
 If h\kind<>#QUIC_PACKET_RETRY : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 For i=0 To SizeOf(QuicPacketJob)-1 : PokeA(*j+i,0) : Next
 *j\packet=packet : *j\packetBytes=count : *j\plainOffset=count-16 : *j\encrypt=2+writeTag
 quicc_Invalidate()
 rc=GcmJobBeginEncrypt(?quic_v1_retry_key,16,?quic_v1_retry_nonce,pseudo,bytes-16,0,0,0,@*j\mask0)
 If rc<>0 : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_STATE) : EndIf
 quicCryptoOwner=*j : *j\phase=2 : ProcedureReturn 0
EndProcedure

; Shared Step/Cancel for packet protection and Retry integrity jobs.
Procedure.i QuicPacketJobStep(*j.QuicPacketJob)
 Define rc.i,i.i,mask.i
 If *j=0 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If *j\phase=0
  If *j\result=0 : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
  ProcedureReturn *j\result
 EndIf
 If quicCryptoOwner<>*j : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 quicc_Invalidate() : rc=GcmJobStep()
 If rc=0
  If *j\encrypt=0 And *j\reserved<>0 And GcmJobAuthenticated()<>0
   GcmJobCancel() : quicc_RestoreHeader(*j)
   ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_RESERVED)
  EndIf
  ProcedureReturn 0
 EndIf
 If rc<0 : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_STATE) : EndIf
 If *j\phase=2
  If GcmJobResult<>1 : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_STATE) : EndIf
  rc=0
  For i=0 To 15
   If *j\encrypt=3
    PokeA(*j\packet+*j\packetBytes-16+i,PeekA(@*j\mask0+i))
   Else
    rc=rc | (PeekA(*j\packet+*j\packetBytes-16+i) ! PeekA(@*j\mask0+i))
   EndIf
  Next
  If rc<>0 : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_AUTH) : EndIf
  ProcedureReturn quicc_Finish(*j,1)
 EndIf
 If GcmJobResult<>1
  quicc_RestoreHeader(*j) : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_AUTH)
 EndIf
 If *j\encrypt
  rc=quicc_Mask(*j)
  If rc<0 : ProcedureReturn quicc_Finish(*j,rc) : EndIf
  mask=15 : If (*j\first & 128)=0 : mask=31 : EndIf
  PokeA(*j\packet,PeekA(*j\packet) ! (PeekA(@*j\mask0) & mask))
  For i=0 To *j\numberBytes-1 : PokeA(*j\packet+*j\numberOffset+i,PeekA(*j\packet+*j\numberOffset+i) ! PeekA(@*j\mask0+1+i)) : Next
 EndIf
 ProcedureReturn quicc_Finish(*j,1)
EndProcedure

; Explicit cancellation is immediate, retaining no key. Caller must discard any
; partially processed packet. A different owner is never cancelled.
Procedure.i QuicPacketJobCancel(*j.QuicPacketJob)
 If *j=0 : ProcedureReturn #QUIC_CRYPTO_ARGUMENT : EndIf
 If quicCryptoOwner<>*j : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 GcmJobCancel() : ProcedureReturn quicc_Finish(*j,#QUIC_CRYPTO_CANCELLED)
EndProcedure

DataSection
quic_v1_salt:
 Data.a $38,$76,$2C,$F7,$F5,$59,$34,$B3,$4D,$17,$9A,$E6,$A4,$C8,$0C,$AD,$CC,$BB,$7F,$0A
quic_v1_retry_key:
 Data.a $BE,$0C,$69,$0B,$9F,$66,$57,$5A,$1D,$76,$6B,$54,$E3,$68,$C8,$4E
quic_v1_retry_nonce:
 Data.a $46,$15,$99,$D3,$5D,$63,$2B,$F2,$23,$98,$25,$BB
EndDataSection
