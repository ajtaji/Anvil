; SPDX-License-Identifier: MIT
; Independent RFC9001 section4.1.3 TLS-to-CRYPTO output ownership.
; Compose full shared TLS before this adapter. Begin uses the selected TLS
; connection; caller serializes it through normal TLS hooks. Step only copies
; owned output, so other TLS contexts may run after Begin returns.
XIncludeFile "Anvil/Network/quic_crypto_send.pbi"
#QUIC_OUTPUT_TLS=-3491
#QUIC_OUTPUT_STATE=-3492
#QUIC_OUTPUT_CANCELLED=-3493
Structure QuicTlsOutput
 phase.i
 result.i
 stream.i
 output.i
 bytes.i
 copied.i
 offset.i
 level.i
EndStructure
Procedure.i quicto_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicto_Overlap(a.i,n.i,b.i,m.i)
 If n>0 And m>0 And a<b+m And b<a+n : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i quicto_Fail(*j.QuicTlsOutput,rc.i)
 Define *s.QuicCryptoTx
 *s=*j\stream : *s\phase=3
 *j\phase=-1 : *j\result=rc : ProcedureReturn rc
EndProcedure
; 1=message built and awaiting copy,0=no ready QUIC output,negative=refusal.
; Preflight checks the conservative TLS bound against both output and retained
; capacity BEFORE advancing TLS. Refusal here leaves TLS/job/stream unchanged.
; Buffers must also be independent of TLS's own private working storage.
Procedure.i QuicTlsOutputBegin(*j.QuicTlsOutput,*s.QuicCryptoTx,output.i,capacity.i)
 Define need.i,level.i,n.i,i.i
 If quicto_Span(*j,SizeOf(QuicTlsOutput))=0 Or quicto_Span(*s,SizeOf(QuicCryptoTx))=0 Or quicto_Span(output,capacity)=0 : ProcedureReturn #QUIC_TX_ARGUMENT : EndIf
 If *j\phase=1 Or *j\phase=3 Or *s\phase<>1 : ProcedureReturn #QUIC_OUTPUT_STATE : EndIf
 If quicto_Overlap(*j,SizeOf(QuicTlsOutput),*s,SizeOf(QuicCryptoTx)) Or quicto_Overlap(output,capacity,*j,SizeOf(QuicTlsOutput)) Or quicto_Overlap(output,capacity,*s,SizeOf(QuicCryptoTx)) : ProcedureReturn #QUIC_TX_ARGUMENT : EndIf
 If quicto_Overlap(*j,SizeOf(QuicTlsOutput),*s\data,*s\capacity) Or quicto_Overlap(*j,SizeOf(QuicTlsOutput),*s\states,*s\capacity/4) Or quicto_Overlap(output,capacity,*s\data,*s\capacity) Or quicto_Overlap(output,capacity,*s\states,*s\capacity/4) : ProcedureReturn #QUIC_TX_ARGUMENT : EndIf
 need=Tls13QuicOutputCapacity() : If need=0 : ProcedureReturn 0 : EndIf
 level=0 : If Tls13State=#TLS13_ST_SEND_FINISHED : level=2 : EndIf
 If *s\level<>level : ProcedureReturn #QUIC_OUTPUT_STATE : EndIf
 If capacity<need : ProcedureReturn #QUIC_TX_CAPACITY : EndIf
 If need>*s\capacity-(*s\tail-*s\base) : ProcedureReturn #QUIC_TX_LIMIT : EndIf
 If *s\tail>#QUIC_INTEGER_MAX-need : ProcedureReturn #QUIC_TX_RANGE : EndIf
 For i=0 To SizeOf(QuicTlsOutput)-1 : PokeA(*j+i,0) : Next
 ; The synchronous builder can yield. Do not expose a copy-ready job until
 ; it returns a complete message; callbacks cannot reenter this same job.
 *j\phase=3 : *j\stream=*s : *j\output=output : *j\offset=*s\tail : *j\level=level
 If level=0 : n=Tls13BuildClientHello(output,capacity) : Else : n=Tls13BuildClientFinished(output,capacity) : EndIf
 If n<=0 Or n>need : ProcedureReturn quicto_Fail(*j,#QUIC_OUTPUT_TLS) : EndIf
 *j\bytes=n : *j\phase=1 : ProcedureReturn 1
EndProcedure
; Return newly retained bytes<=256;0 after completion. Output remains immutable
; and this job has exclusive append ownership through completion. TLS builders
; have already advanced: a copy error/cancellation poisons the stream and requires
; connection close, never rebuilding the message or rolling the transcript back.
; Build/crypto work in Begin retains existing TLS hooks, not a wall-time bound.
Procedure.i QuicTlsOutputStep(*j.QuicTlsOutput)
 Define *s.QuicCryptoTx,n.i,rc.i
 If quicto_Span(*j,SizeOf(QuicTlsOutput))=0 : ProcedureReturn #QUIC_TX_ARGUMENT : EndIf
 If *j\phase=2 : ProcedureReturn 0 : EndIf
 If *j\phase=-1 : ProcedureReturn *j\result : EndIf
 If *j\phase<>1 : ProcedureReturn #QUIC_OUTPUT_STATE : EndIf
 *s=*j\stream
 If *s\phase<>1 Or *s\level<>*j\level Or *s\tail<>*j\offset+*j\copied : ProcedureReturn quicto_Fail(*j,#QUIC_OUTPUT_STATE) : EndIf
 n=*j\bytes-*j\copied : If n>256 : n=256 : EndIf
 rc=QuicCryptoTxAppend(*s,*j\output+*j\copied,n)
 If rc<>n : ProcedureReturn quicto_Fail(*j,#QUIC_OUTPUT_STATE) : EndIf
 *j\copied=*j\copied+n : If *j\copied=*j\bytes : *j\phase=2 : EndIf
 ProcedureReturn n
EndProcedure
Procedure.i QuicTlsOutputCancel(*j.QuicTlsOutput)
 If quicto_Span(*j,SizeOf(QuicTlsOutput))=0 : ProcedureReturn #QUIC_TX_ARGUMENT : EndIf
 If *j\phase<>1 : ProcedureReturn #QUIC_OUTPUT_STATE : EndIf
 ProcedureReturn quicto_Fail(*j,#QUIC_OUTPUT_CANCELLED)
EndProcedure
