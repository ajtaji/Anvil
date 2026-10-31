; Shared IPv6 address representation: exactly 16 network-order bytes.
; RFC 4291 section 2.2 input; RFC 5952 section 4 hexadecimal output.
; No allocation, global scratch, resolver, interface or device dependency.
; Scope identifiers, URI brackets and prefix suffixes belong to their callers.
XIncludeFile "Anvil/Network/byte_order.pbi"
Structure IPv6AddressStorage
 high.q
 low.q
EndStructure

Procedure.i ipv6a_Hex(c.i)
 If c>=48 And c<=57 : ProcedureReturn c-48 : EndIf
 If c>=65 And c<=70 : ProcedureReturn c-55 : EndIf
 If c>=97 And c<=102 : ProcedureReturn c-87 : EndIf
 ProcedureReturn -1
EndProcedure

; 0 success, -1 invalid input. Output is untouched on refusal.
; The explicit input span and 16-byte output must not overlap.
Procedure.i IPv6AddressParse(text.i,bytes.i,out.i)
 Define tmp.IPv6AddressStorage
 Define i.i,n.i,gap.i,compressed.i,start.i,digits.i,value.i,c.i,k.i,dot.i,part.i
 If text=0 Or out=0 : ProcedureReturn -1 : EndIf
 If bytes<2 Or bytes>45 : ProcedureReturn -1 : EndIf
 If out<text+bytes And text<out+16 : ProcedureReturn -1 : EndIf
 tmp\high=0 : tmp\low=0 : i=0 : n=0 : compressed=-1
 If PeekA(text)=58
  If PeekA(text+1)<>58 : ProcedureReturn -1 : EndIf
  compressed=0 : i=2
 EndIf
 While i<bytes
  If n>=16 : ProcedureReturn -1 : EndIf
  start=i : dot=0
  While i<bytes
   c=PeekA(text+i)
   If c=58 : Break : EndIf
   If c=46 : dot=1 : EndIf
   i=i+1
  Wend
  If dot<>0
   If n>12 Or i<>bytes : ProcedureReturn -1 : EndIf
   i=start
   For part=0 To 3
    start=i : value=0 : digits=0
    While i<bytes
     c=PeekA(text+i)
     If c=46 : Break : EndIf
     If c<48 Or c>57 Or digits>=3 : ProcedureReturn -1 : EndIf
     value=value*10+c-48 : digits=digits+1 : i=i+1
    Wend
    If digits=0 Or value>255 : ProcedureReturn -1 : EndIf
    If digits>1
     If PeekA(text+start)=48 : ProcedureReturn -1 : EndIf
    EndIf
    PokeA(@tmp+n,value) : n=n+1
    If part<3
     If i>=bytes : ProcedureReturn -1 : EndIf
     i=i+1
    Else
     If i<>bytes : ProcedureReturn -1 : EndIf
    EndIf
   Next
   Break
  EndIf
  digits=i-start
  If digits<1 Or digits>4 : ProcedureReturn -1 : EndIf
  value=0
  For k=start To i-1
   c=ipv6a_Hex(PeekA(text+k))
   If c<0 : ProcedureReturn -1 : EndIf
   value=(value<<4)|c
  Next
  NetWriteBE16(@tmp+n,value) : n=n+2
  If i<bytes
   i=i+1
   If i=bytes : ProcedureReturn -1 : EndIf
   If PeekA(text+i)=58
    If compressed>=0 : ProcedureReturn -1 : EndIf
    compressed=n : i=i+1
   EndIf
  EndIf
 Wend
 If compressed>=0
  gap=16-n
  If gap<2 : ProcedureReturn -1 : EndIf
  k=n-1
  While k>=compressed
   PokeA(@tmp+k+gap,PeekA(@tmp+k)) : k=k-1
  Wend
  For k=compressed To compressed+gap-1 : PokeA(@tmp+k,0) : Next
 Else
  If n<>16 : ProcedureReturn -1 : EndIf
 EndIf
 For k=0 To 15 : PokeA(out+k,PeekA(@tmp+k)) : Next
 ProcedureReturn 0
EndProcedure

; Lowercase hex with longest/first zero run compressed; no single-zero
; compression. IPv4-embedded addresses also use hexadecimal here.
; Returns bytes excluding NUL; null output/capacity0 measures. Short output
; returns -2 without writing. A successful write includes the trailing NUL.
Procedure.i IPv6AddressFormat(address.i,out.i,capacity.i)
 Define i.i,j.i,best.i,run.i,longest.i,value.i,digit.i,shift.i,started.i,count.i,pass.i,c.i
 If address=0 Or capacity<0 : ProcedureReturn -1 : EndIf
 If out=0 And capacity<>0 : ProcedureReturn -1 : EndIf
 If out<>0
  If out<address+16 And address<out+capacity : ProcedureReturn -1 : EndIf
 EndIf
 best=-1 : longest=1 : i=0
 While i<8
  If NetReadBE16(address+i*2)=0
   j=i+1
   While j<8
    If NetReadBE16(address+j*2)<>0 : Break : EndIf
    j=j+1
   Wend
   run=j-i
   If run>longest : best=i : longest=run : EndIf
   i=j
  Else
   i=i+1
  EndIf
 Wend
 For pass=0 To 1
  count=0 : i=0
  While i<8
   If i=best
    If pass=1 : PokeA(out+count,58) : PokeA(out+count+1,58) : EndIf
    count=count+2 : i=i+longest
   Else
    If i>0 And i<>best+longest
     If pass=1 : PokeA(out+count,58) : EndIf
     count=count+1
    EndIf
    value=NetReadBE16(address+i*2) : started=0 : shift=12
    While shift>=0
     digit=(value>>shift)&15
     If digit<>0 Or started<>0 Or shift=0
      c=digit+48 : If digit>9 : c=digit+87 : EndIf
      If pass=1 : PokeA(out+count,c) : EndIf
      count=count+1 : started=1
     EndIf
     shift=shift-4
    Wend
    i=i+1
   EndIf
  Wend
  If pass=0
   If out=0 : ProcedureReturn count : EndIf
   If capacity<=count : ProcedureReturn -2 : EndIf
  EndIf
 Next
 PokeA(out+count,0)
 ProcedureReturn count
EndProcedure

; Prefix length 0..128, result 1 match, 0 different, -1 invalid.
Procedure.i IPv6AddressPrefix(a.i,b.i,bits.i)
 Define i.i,whole.i,rest.i,mask.i,aa.i,bb.i
 If a=0 Or b=0 : ProcedureReturn -1 : EndIf
 If bits<0 Or bits>128 : ProcedureReturn -1 : EndIf
 whole=bits/8 : rest=bits%8
 For i=0 To whole-1
  If PeekA(a+i)<>PeekA(b+i) : ProcedureReturn 0 : EndIf
 Next
 If rest<>0
  mask=($FF<<(8-rest))&$FF
  aa=PeekA(a+whole)&mask : bb=PeekA(b+whole)&mask
  If aa<>bb : ProcedureReturn 0 : EndIf
 EndIf
 ProcedureReturn 1
EndProcedure
