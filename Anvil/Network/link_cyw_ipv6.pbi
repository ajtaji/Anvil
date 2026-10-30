; CYW43 device adapter for the shared IPv6 service. Compose link_cyw_tx and
; cyw43_multicast first. One bounded control request per Prepare call, only
; between receive dispatches. Existing multicast entries are retained.
Global ipv6cywEpochSeen.i,ipv6cywPhase.i,ipv6cywCount.i,ipv6cywError.i
Global Dim ipv6cywMacs.a[174]
Global Dim ipv6cywReadback.a[174]
Procedure.i IPv6CywGeneration(kind.i)
 If kind<>#HW_LINK_WIFI : ProcedureReturn 0 : EndIf
 If linkCywTxRefresh()=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn linkCywTxEpoch
EndProcedure
Procedure.i ipv6cyw_Add(mac.i)
 Define i.i
 For i=0 To ipv6cywCount-1
  If IPv6EndpointBytesEqual(@ipv6cywMacs[i*6],mac,6)<>0 : ProcedureReturn 0 : EndIf
 Next
 If ipv6cywCount>=29 : ProcedureReturn -790 : EndIf
 For i=0 To 5 : ipv6cywMacs[ipv6cywCount*6+i]=PeekA(mac+i) : Next
 ipv6cywCount=ipv6cywCount+1 : ProcedureReturn 0
EndProcedure
Procedure.i IPv6CywPrepare(kind.i,generation.i,address.i)
 Define mac.q,rc.i,i.i,j.i,found.i,value.i
 If kind<>#HW_LINK_WIFI Or generation<=0 : ProcedureReturn -790 : EndIf
 If generation<>IPv6CywGeneration(kind) : ProcedureReturn -801 : EndIf
 If generation<>ipv6cywEpochSeen
  ipv6cywEpochSeen=generation : ipv6cywPhase=0 : ipv6cywCount=0 : ipv6cywError=0
 EndIf
 If ipv6cywError<>0 : ProcedureReturn ipv6cywError : EndIf
 rc=0
 If ipv6cywPhase=0
  rc=Cyw43MulticastGet(@ipv6cywMacs[0],29,100)
  If rc>=0
   ipv6cywCount=rc
   mac=0 : PokeA(@mac,51) : PokeA(@mac+1,51) : PokeA(@mac+5,1)
   rc=ipv6cyw_Add(@mac)
   If rc=0
    PokeA(@mac+2,255)
    For i=0 To 2 : PokeA(@mac+3+i,PeekA(address+13+i)) : Next
    rc=ipv6cyw_Add(@mac)
   EndIf
   If rc=0 : ipv6cywPhase=1 : EndIf
  EndIf
 ElseIf ipv6cywPhase=1
  rc=Cyw43MulticastSet(@ipv6cywMacs[0],ipv6cywCount,100)
  If rc=0 : ipv6cywPhase=2 : EndIf
 ElseIf ipv6cywPhase=2
  rc=Cyw43MulticastGet(@ipv6cywReadback[0],29,100)
  If rc>=0
   If rc<>ipv6cywCount
    rc=-791
   Else
    rc=0
    For i=0 To ipv6cywCount-1
     found=0
     For j=0 To ipv6cywCount-1
      If IPv6EndpointBytesEqual(@ipv6cywMacs[i*6],@ipv6cywReadback[j*6],6)<>0 : found=1 : EndIf
     Next
     If found=0 : rc=-791 : EndIf
    Next
   EndIf
   If rc=0 : ipv6cywPhase=3 : EndIf
  EndIf
 ElseIf ipv6cywPhase=3
  rc=Cyw43NeighborOffload(0,100)
  If rc=0 : ipv6cywPhase=4 : EndIf
 ElseIf ipv6cywPhase=4
  rc=Cyw43GetIovarData(?ipv6cyw_Ndoe,4,9,100)
  If rc=0
   If Cyw43ReplyI32(@value)<>1 Or value<>0
    rc=-791
   Else
    ipv6cywPhase=5
   EndIf
  EndIf
 EndIf
 If rc<0 : ipv6cywError=rc : ProcedureReturn rc : EndIf
 If ipv6cywPhase=5 : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
DataSection
ipv6cyw_Ndoe:
 Data.a 110,100,111,101,0
EndDataSection
