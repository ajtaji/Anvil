; CYW43 multicast filter control. Independent firmware-interface facts from
; Linux v6.12 brcmfmac core.c _brcmf_set_multicast_list and
; brcmf_configure_arp_nd_offload: mcast_list is LE32 count then six-byte MACs;
; ndoe is a separate 32-bit switch. No upstream implementation copied.
; Compose cyw43.pbi first. Serialized control-plane calls only; never from RX.
; These controls do not alter allmulti, promiscuous mode or IPv4 ARP offload.
; The owner preserves other memberships and renews them after radio generation
; changes. A successful set is firmware acceptance, not proof of reception.
#CYW43_MULTICAST_MAX = 29
#CYW43_MULTICAST_ARGUMENT = -790
#CYW43_MULTICAST_REPLY = -791
Procedure.i cyw43mc_Span(p.i,n.i)
 If p<=0 Or n<=0 : ProcedureReturn 0 : EndIf
 If p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i cyw43mc_List(p.i,count.i)
 Define i.i,j.i,k.i,broadcast.i,same.i
 If count<0 Or count>#CYW43_MULTICAST_MAX : ProcedureReturn 0 : EndIf
 If count=0 : ProcedureReturn 1 : EndIf
 If cyw43mc_Span(p,count*6)=0 : ProcedureReturn 0 : EndIf
 For i=0 To count-1
  If (PeekA(p+i*6)&1)=0 : ProcedureReturn 0 : EndIf
  broadcast=1
  For k=0 To 5
   If PeekA(p+i*6+k)<>255 : broadcast=0 : EndIf
  Next
  If broadcast<>0 : ProcedureReturn 0 : EndIf
  For j=0 To i-1
   same=1
   For k=0 To 5
    If PeekA(p+i*6+k)<>PeekA(p+j*6+k) : same=0 : EndIf
   Next
   If same<>0 : ProcedureReturn 0 : EndIf
  Next
 Next
 ProcedureReturn 1
EndProcedure

; Replaces the complete device list. Zero count clears it. Copy into private
; wire storage before touching the driver's argument scratch. At most 29 MACs
; fit its 192-byte command buffer including name, NUL and count.
Procedure.i Cyw43MulticastSet(macs.i,count.i,timeoutMs.i)
 Define Dim wire.a[178]
 Define i.i
 If timeoutMs<1 Or timeoutMs>100 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If cyw43mc_List(macs,count)=0 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 For i=0 To 3 : wire[i]=(count>>(i*8))&255 : Next
 For i=0 To count*6-1 : wire[4+i]=PeekA(macs+i) : Next
 ProcedureReturn Cyw43SetIovarData(?cyw43mc_Name,10,@wire[0],4+count*6,timeoutMs)
EndProcedure

; Copies the entire validated firmware list to caller storage, returns count.
; Output capacity is in MAC entries. Refusal leaves output untouched; no RX
; pointer escapes. The call itself can reuse the driver's control RX scratch,
; so output must not point inside that scratch. Empty result requires no copy.
Procedure.i Cyw43MulticastGet(out.i,capacity.i,timeoutMs.i)
 Define rc.i,p.i,n.i,count.i,i.i
 If capacity<1 Or capacity>#CYW43_MULTICAST_MAX : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If cyw43mc_Span(out,capacity*6)=0 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If out<@cyw43_rx[0]+#CYW43_RXBUF And @cyw43_rx[0]<out+capacity*6 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If out<@cyw43_arg[0]+#CYW43_ARGBUF And @cyw43_arg[0]<out+capacity*6 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If timeoutMs<1 Or timeoutMs>100 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 rc=Cyw43GetIovarData(?cyw43mc_Name,10,178,timeoutMs)
 If rc<>0 : ProcedureReturn rc : EndIf
 p=Cyw43ReplyPtr() : n=Cyw43ReplyLen()
 If n<4 Or n>#CYW43_RXBUF Or p<@cyw43_rx[0] : ProcedureReturn #CYW43_MULTICAST_REPLY : EndIf
 If p>@cyw43_rx[0]+#CYW43_RXBUF-n : ProcedureReturn #CYW43_MULTICAST_REPLY : EndIf
 count=PeekA(p)|(PeekA(p+1)<<8)|(PeekA(p+2)<<16)|(PeekA(p+3)<<24)
 If count>capacity Or count>#CYW43_MULTICAST_MAX : ProcedureReturn #CYW43_MULTICAST_REPLY : EndIf
 If count*6>n-4 : ProcedureReturn #CYW43_MULTICAST_REPLY : EndIf
 If cyw43mc_List(p+4,count)=0 : ProcedureReturn #CYW43_MULTICAST_REPLY : EndIf
 For i=0 To count*6-1 : PokeA(out+i,PeekA(p+4+i)) : Next
 ProcedureReturn count
EndProcedure

; Set zero before host-owned IPv6 DAD/neighbor handling. This intentionally
; leaves the independent IPv4 ARP offload settings untouched. The owner checks
; return status and radio generation, and never infers success from timeout.
Procedure.i Cyw43NeighborOffload(enabled.i,timeoutMs.i)
 If enabled<>0 And enabled<>1 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 If timeoutMs<1 Or timeoutMs>100 : ProcedureReturn #CYW43_MULTICAST_ARGUMENT : EndIf
 ProcedureReturn Cyw43SetIovarU32(?cyw43mc_Ndoe,4,enabled,timeoutMs)
EndProcedure
DataSection
cyw43mc_Name:
 Data.a 109,99,97,115,116,95,108,105,115,116,0
cyw43mc_Ndoe:
 Data.a 110,100,111,101,0
EndDataSection
