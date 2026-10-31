; SPDX-License-Identifier: MIT
; QUIC v1 transport parameters, RFC 9000 sections 7.3/7.4/18.2.
; Caller owns immutable input, job and separate entry storage. No allocation or
; I/O. One Step reads one parameter, with at most 64 duplicate comparisons.
; Only consume entries after completion; TLS must still authenticate the peer.
XIncludeFile "Anvil/Network/quic_wire.pbi"
#QUIC_PARAMETER_ARGUMENT=-3381
#QUIC_PARAMETER_TRUNCATED=-3382
#QUIC_PARAMETER_VALUE=-3383
#QUIC_PARAMETER_DUPLICATE=-3384
#QUIC_PARAMETER_ROLE=-3385
#QUIC_PARAMETER_LIMIT=-3386
#QUIC_PARAMETER_MISSING=-3387
#QUIC_PARAMETER_CONNECTION_ID=-3388
#QUIC_PARAMETER_STATE=-3389
Structure QuicParameter
 id.i
 offset.i
 bytes.i
 value.i
EndStructure
Structure QuicParameters
 phase.i
 result.i
 source.i
 bytes.i
 cursor.i
 entries.i
 capacity.i
 count.i
 server.i
 seen.i
 initialBytes.i
EndStructure
Procedure.i quicp_Finish(*s.QuicParameters,rc.i)
 *s\phase=0 : *s\result=rc : ProcedureReturn rc
EndProcedure
Procedure.i quicp_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicp_Separate(a.i,an.i,b.i,bn.i)
 If an>0 And bn>0 And a<b+bn And b<a+an : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; Zero-initialize job before first use. Explicit local resource limits are
; 16384 input bytes and 64 parameters, including unknown extension parameters.
Procedure.i QuicParametersBegin(*s.QuicParameters,source.i,bytes.i,server.i,entries.i,capacity.i)
 Define n.i,i.i
 If quicp_Span(*s,SizeOf(QuicParameters))=0 Or bytes<0 Or bytes>16384 Or server<0 Or server>1 Or capacity<1 Or capacity>64 : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 n=capacity*SizeOf(QuicParameter)
 If quicp_Span(source,bytes)=0 Or quicp_Span(entries,n)=0 : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 If quicp_Separate(*s,SizeOf(QuicParameters),source,bytes)=0 Or quicp_Separate(*s,SizeOf(QuicParameters),entries,n)=0 Or quicp_Separate(source,bytes,entries,n)=0 : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 If *s\phase<>0 : ProcedureReturn #QUIC_PARAMETER_STATE : EndIf
 For i=0 To SizeOf(QuicParameters)-1 : PokeA(*s+i,0) : Next
 *s\source=source : *s\bytes=bytes : *s\entries=entries : *s\capacity=capacity : *s\server=server : *s\phase=1
 ProcedureReturn 0
EndProcedure
Procedure.i QuicParametersStep(*s.QuicParameters)
 Define p.i,id.i,n.i,bytes.i,value.i,i.i,rc.i,*e.QuicParameter
 If *s=0 : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 If *s\phase=0
  If *s\result=0 : ProcedureReturn #QUIC_PARAMETER_STATE : EndIf
  ProcedureReturn *s\result
 EndIf
 If *s\cursor=*s\bytes
  If (*s\seen & (1<<15))=0 Or (*s\server And (*s\seen & 1)=0) : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_MISSING) : EndIf
  If (*s\seen & (1<<13))<>0 And *s\initialBytes=0 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  ProcedureReturn quicp_Finish(*s,1)
 EndIf
 p=*s\cursor
 n=QuicIntegerRead(*s\source+p,*s\bytes-p,@id)
 If n<0 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_TRUNCATED) : EndIf
 p=p+n : n=QuicIntegerRead(*s\source+p,*s\bytes-p,@bytes)
 If n<0 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_TRUNCATED) : EndIf
 p=p+n
 If bytes>*s\bytes-p : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_TRUNCATED) : EndIf
 For i=0 To *s\count-1
  *e=*s\entries+i*SizeOf(QuicParameter)
  If *e\id=id : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_DUPLICATE) : EndIf
 Next
 If *s\count=*s\capacity : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_LIMIT) : EndIf
 If *s\server=0 And (id=0 Or id=2 Or id=13 Or id=16) : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_ROLE) : EndIf
 value=-1
 If id=1 Or (id>=3 And id<=11) Or id=14
  n=QuicIntegerRead(*s\source+p,bytes,@value)
  If n<0 Or n<>bytes : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  If id=3 And value<1200 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  If (id=8 Or id=9) And value>(1<<60) : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  If id=10 And value>20 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  If id=11 And value>=16384 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  If id=14 And value<2 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
 ElseIf id=0 Or id=15 Or id=16
  If bytes>20 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
 ElseIf id=2
  If bytes<>16 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
 ElseIf id=12
  If bytes<>0 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
 ElseIf id=13
  If bytes<42 Or bytes>61 : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
  n=PeekA(*s\source+p+24)
  If n<1 Or n>20 Or bytes<>41+n : ProcedureReturn quicp_Finish(*s,#QUIC_PARAMETER_VALUE) : EndIf
 EndIf
 *e=*s\entries+*s\count*SizeOf(QuicParameter)
 *e\id=id : *e\offset=p : *e\bytes=bytes : *e\value=value
 *s\count=*s\count+1 : *s\cursor=p+bytes
 If id<=16 : *s\seen=*s\seen | (1<<id) : EndIf
 If id=15 : *s\initialBytes=bytes : EndIf
 ProcedureReturn 0
EndProcedure
; Lookup is unavailable for pending, failed or cancelled input.
Procedure.i QuicParametersFind(*s.QuicParameters,id.i)
 Define i.i,*e.QuicParameter
 If *s=0 : ProcedureReturn 0 : EndIf
 If *s\phase<>0 Or *s\result<>1 : ProcedureReturn 0 : EndIf
 For i=0 To *s\count-1
  *e=*s\entries+i*SizeOf(QuicParameter)
  If *e\id=id : ProcedureReturn *e : EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure QuicParametersCancel(*s.QuicParameters)
 If *s<>0 : *s\phase=0 : *s\result=#QUIC_PARAMETER_STATE : EndIf
EndProcedure
Procedure.i quicp_Id(*s.QuicParameters,id.i,expected.i,bytes.i)
 Define *e.QuicParameter,i.i,d.i
 *e=QuicParametersFind(*s,id)
 If *e=0 : ProcedureReturn #QUIC_PARAMETER_MISSING : EndIf
 If *e\bytes<>bytes : ProcedureReturn #QUIC_PARAMETER_CONNECTION_ID : EndIf
 For i=0 To bytes-1 : d=d | (PeekA(expected+i) ! PeekA(*s\source+*e\offset+i)) : Next
 If d<>0 : ProcedureReturn #QUIC_PARAMETER_CONNECTION_ID : EndIf
 ProcedureReturn 1
EndProcedure
; Bind parameters to connection IDs actually observed during the handshake.
; For a server peer, original is the client's FIRST Initial DCID; initial is
; the server's FIRST Initial SCID; retry is its Retry SCID, only if usedRetry=1.
; For a client peer only initial is compared. This does not verify TLS identity.
Procedure.i QuicParametersCheckIds(*s.QuicParameters,initial.i,initialBytes.i,original.i,originalBytes.i,retry.i,retryBytes.i,usedRetry.i)
 Define rc.i
 If *s=0 Or initialBytes<0 Or initialBytes>20 Or originalBytes<0 Or originalBytes>20 Or retryBytes<0 Or retryBytes>20 Or usedRetry<0 Or usedRetry>1 : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 If (initialBytes>0 And initial=0) Or (originalBytes>0 And original=0) Or (retryBytes>0 And retry=0) : ProcedureReturn #QUIC_PARAMETER_ARGUMENT : EndIf
 If *s\phase<>0 Or *s\result<>1 : ProcedureReturn #QUIC_PARAMETER_STATE : EndIf
 rc=quicp_Id(*s,15,initial,initialBytes) : If rc<>1 : ProcedureReturn rc : EndIf
 If *s\server
  rc=quicp_Id(*s,0,original,originalBytes) : If rc<>1 : ProcedureReturn rc : EndIf
  If usedRetry
   ProcedureReturn quicp_Id(*s,16,retry,retryBytes)
  ElseIf QuicParametersFind(*s,16)<>0
   ProcedureReturn #QUIC_PARAMETER_CONNECTION_ID
  EndIf
 EndIf
 ProcedureReturn 1
EndProcedure
