; SPDX-License-Identifier: MIT
; Independent RFC 9001 section 4.1.3 receive-level handoff.
; Include the complete shared TLS implementation before this adapter.
; Caller selects the receive stream for the restored TLS connection and feeds
; only authenticated packet contents. Connection ownership is not implicit.
XIncludeFile "Anvil/Network/quic_crypto_stream.pbi"
#QUIC_RX_TLS=-3431
; Returns accepted bytes (at most256), zero for an empty/gapped/sealed stream,
; or a terminal negative error. Close the connection on any negative result.
; TLS may already have accepted bytes when a level-transition check fails.
; Phase3 poisons this receive stream until Init; it cannot be fed again.
; Input slicing does not bound certificate verification time: install the
; normal cooperative TLS hooks and preserve exclusive connection ownership.
Procedure.i QuicCryptoTlsStep(*s.QuicCryptoRx)
 Define view.QuicCryptoSlice,n.i,rc.i,changed.i
 If *s<=0 Or *s>$7FFFFFFFFFFFFFFF-SizeOf(QuicCryptoRx) : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=QuicCryptoRxPeek(*s,256,@view)
 If n<0 : ProcedureReturn n : EndIf
 If n=0 : ProcedureReturn 0 : EndIf
 n=Tls13FeedQuic(*s\level,view\data,view\bytes)
 If n<=0 Or n>view\bytes
  *s\phase=3 : *s\offered=0 : ProcedureReturn #QUIC_RX_TLS
 EndIf
 rc=QuicCryptoRxConsume(*s,n)
 If rc<0 : *s\phase=3 : *s\offered=0 : ProcedureReturn rc : EndIf
 changed=0
 If *s\level=0 And Tls13State<>#TLS13_ST_WAIT_SH : changed=1 : EndIf
 If *s\level=2 And (Tls13State=#TLS13_ST_SEND_FINISHED Or Tls13State=#TLS13_ST_CONNECTED) : changed=1 : EndIf
 If changed<>0
  rc=QuicCryptoRxSeal(*s)
  If rc<0 : *s\phase=3 : *s\offered=0 : ProcedureReturn rc : EndIf
 EndIf
 ProcedureReturn n
EndProcedure
; Terminal receive abandonment. Caller stops the TLS coroutine before freeing
; storage and closes the connection; accepted transcript bytes are not undone.
Procedure.i QuicCryptoTlsAbandon(*s.QuicCryptoRx)
 If *s<=0 Or *s>$7FFFFFFFFFFFFFFF-SizeOf(QuicCryptoRx) : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *s\phase<>1 And *s\phase<>2 And *s\phase<>3 : ProcedureReturn #QUIC_RX_STATE : EndIf
 *s\phase=3 : *s\offered=0
 ProcedureReturn 0
EndProcedure
