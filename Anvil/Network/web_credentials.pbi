; Explicit HTTP Authorization values, RFC 7617 section 2 / RFC 6750 section 2.1.
; Caller owns destination and input. Values are not NUL terminated; return the
; byte count for WebRequestHeader. Use only with verified HTTPS. This does not
; acquire tokens, retry a challenge, choose a realm, or retain credentials.
; Basic takes already encoded credential bytes; username cannot contain ':'.
; UTF-8 normalization/charset negotiation belongs to the application.
#WEB_CREDENTIAL_ARGUMENT=-640
#WEB_CREDENTIAL_SYNTAX=-641
#WEB_CREDENTIAL_LIMIT=-642

Procedure.i wcBase64(c.i)
 If c<26 : ProcedureReturn 65+c : EndIf
 If c<52 : ProcedureReturn 97+c-26 : EndIf
 If c<62 : ProcedureReturn 48+c-52 : EndIf
 If c=62 : ProcedureReturn 43 : EndIf
 ProcedureReturn 47
EndProcedure

; A null output with zero capacity measures a valid value without writing it.
; Any refusal leaves the output unchanged. Nonempty inputs/output must be
; disjoint, and remain alive until this call returns.
Procedure.i WebCredentialBasic(user.i,userBytes.i,password.i,passwordBytes.i,dst.i,capacity.i)
 Define i.i,c.i,n.i,need.i,p.i,acc.i,bits.i,j.i,text.i
 If userBytes<0 Or passwordBytes<0 Or userBytes>2048 Or passwordBytes>2048 Or capacity<0 Or (userBytes>0 And user=0) Or (passwordBytes>0 And password=0) Or (capacity>0 And dst=0)
  ProcedureReturn #WEB_CREDENTIAL_ARGUMENT
 EndIf
 For i=0 To userBytes-1
  c=PeekA(user+i) & 255
  If c<32 Or c=127 Or c=58 : ProcedureReturn #WEB_CREDENTIAL_SYNTAX : EndIf
 Next
 For i=0 To passwordBytes-1
  c=PeekA(password+i) & 255
  If c<32 Or c=127 : ProcedureReturn #WEB_CREDENTIAL_SYNTAX : EndIf
 Next
 n=userBytes+passwordBytes+1 : need=6+((n+2)/3)*4
 If dst=0 And capacity=0 : ProcedureReturn need : EndIf
 If capacity<need : ProcedureReturn #WEB_CREDENTIAL_LIMIT : EndIf
 text="Basic "
 For i=0 To 5 : PokeA(dst+i,PeekA(text+i)) : Next
 p=6
 For i=0 To n-1
  If i<userBytes
   c=PeekA(user+i) & 255
  ElseIf i=userBytes
   c=58
  Else
   c=PeekA(password+i-userBytes-1) & 255
  EndIf
  acc=(acc<<8) | c : bits=bits+8
  While bits>=6
   bits=bits-6 : PokeA(dst+p,wcBase64((acc>>bits) & 63)) : p=p+1
  Wend
  acc=acc & ((1<<bits)-1)
 Next
 If bits>0 : PokeA(dst+p,wcBase64((acc<<(6-bits)) & 63)) : p=p+1 : EndIf
 While p<need : PokeA(dst+p,61) : p=p+1 : Wend
 ProcedureReturn need
EndProcedure

Procedure.i WebCredentialBearer(token.i,bytes.i,dst.i,capacity.i)
 Define i.i,c.i,padding.i,text.i
 If token=0 Or bytes<1 Or bytes>8192-7 Or capacity<0 Or (capacity>0 And dst=0) : ProcedureReturn #WEB_CREDENTIAL_ARGUMENT : EndIf
 For i=0 To bytes-1
  c=PeekA(token+i) & 255
  If c=61
   If i=0 : ProcedureReturn #WEB_CREDENTIAL_SYNTAX : EndIf
   padding=1
  Else
   If padding : ProcedureReturn #WEB_CREDENTIAL_SYNTAX : EndIf
   If (c<65 Or c>90) And (c<97 Or c>122) And (c<48 Or c>57) And c<>45 And c<>46 And c<>95 And c<>126 And c<>43 And c<>47
    ProcedureReturn #WEB_CREDENTIAL_SYNTAX
   EndIf
  EndIf
 Next
 If dst=0 And capacity=0 : ProcedureReturn bytes+7 : EndIf
 If capacity<bytes+7 : ProcedureReturn #WEB_CREDENTIAL_LIMIT : EndIf
 text="Bearer "
 For i=0 To 6 : PokeA(dst+i,PeekA(text+i)) : Next
 For i=0 To bytes-1 : PokeA(dst+7+i,PeekA(token+i)) : Next
 ProcedureReturn bytes+7
EndProcedure

Procedure.i WebCredentialWipe(dst.i,bytes.i)
 Define i.i
 If bytes<0 Or bytes>8192 Or (bytes>0 And dst=0) : ProcedureReturn #WEB_CREDENTIAL_ARGUMENT : EndIf
 For i=0 To bytes-1 : PokeA(dst+i,0) : Next
 ProcedureReturn 0
EndProcedure
