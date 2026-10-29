; Bounded, allocation-free IPv6 packet view and fixed-header emission.
; RFC 8200 sections 3, 4.2-4.7; RFC 5095 treats type zero as unrecognized.
; No link, neighbor, socket or checksum state.
; Source/destination validity and transport checks belong to the endpoint.
XIncludeFile "Anvil/Network/byte_order.pbi"
#IPV6_PACKET_ARGUMENT = -700
#IPV6_PACKET_SHORT = -701
#IPV6_PACKET_VERSION = -702
#IPV6_PACKET_EXTENSION = -703
#IPV6_PACKET_FRAGMENT = -704
#IPV6_PACKET_OPTION = -705
#IPV6_PACKET_ROUTE = -706
#IPV6_PACKET_LIMIT = -707
Structure IPv6PacketView
 packet.i
 packetBytes.i
 source.i
 destination.i
 payload.i
 payloadBytes.i
 protocol.i
 hopLimit.i
 trafficClass.i
 flowLabel.i
 errorOffset.i
 optionAction.i
EndStructure

; Returns 0 or a negative reason. Only errorOffset/optionAction are usable
; after failure. Unknown options expose their required discard/ICMP action
; to the endpoint; they are never silently accepted. At most eight extensions.
; Atomic fragments are accepted, other fragments require reassembly elsewhere.
; Jumbo Payload, ESP and AH are not supported by this view.
Procedure.i IPv6PacketParse(packet.i,bytes.i,*view.IPv6PacketView)
 Define size.i,at.i,nextHeader.i,extensions.i,kind.i,length.i,end.i,opt.i,n.i,word.i,i.i,fragment.i
 If *view=0 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If packet<>0 And bytes>0
  If *view<packet+bytes And packet<*view+SizeOf(IPv6PacketView) : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 EndIf
 For i=0 To SizeOf(IPv6PacketView)-1 : PokeA(*view+i,0) : Next
 If packet=0 Or bytes<0 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If bytes<40 : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
 If (PeekA(packet)>>4)<>6 : ProcedureReturn #IPV6_PACKET_VERSION : EndIf
 size=NetReadBE16(packet+4)+40
 If size>bytes : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
 at=40 : nextHeader=PeekA(packet+6) : extensions=0 : fragment=0
 Repeat
  kind=nextHeader
  If kind<>0 And kind<>60 And kind<>43 And kind<>44 : Break : EndIf
  *view\errorOffset=at
  extensions=extensions+1
  If extensions>8 : ProcedureReturn #IPV6_PACKET_LIMIT : EndIf
  If at+8>size : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
  If kind=0 And at<>40 : ProcedureReturn #IPV6_PACKET_EXTENSION : EndIf
  nextHeader=PeekA(packet+at)
  If kind=44
   If fragment<>0 : ProcedureReturn #IPV6_PACKET_EXTENSION : EndIf
   fragment=1
   word=NetReadBE16(packet+at+2)
   If (word & $FFF9)<>0 : ProcedureReturn #IPV6_PACKET_FRAGMENT : EndIf
   length=8
  Else
   length=(PeekA(packet+at+1)+1)*8
   If length>size-at : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
   If kind=43
    If PeekA(packet+at+3)<>0
     *view\errorOffset=at+2 : ProcedureReturn #IPV6_PACKET_ROUTE
    EndIf
   Else
    end=at+length : opt=at+2
    While opt<end
     *view\errorOffset=opt
     word=PeekA(packet+opt)
     If word=0
      opt=opt+1
     Else
      If opt+2>end : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
      n=PeekA(packet+opt+1)
      If n>end-opt-2 : ProcedureReturn #IPV6_PACKET_SHORT : EndIf
      ; PadN (1) and unknown skip-action options are safe to skip here.
      If (word & $C0)<>0
       *view\optionAction=word>>6 : ProcedureReturn #IPV6_PACKET_OPTION
      EndIf
      opt=opt+n+2
     EndIf
    Wend
   EndIf
  EndIf
  at=at+length
 ForEver
 *view\errorOffset=at
 If nextHeader=50 Or nextHeader=51 : ProcedureReturn #IPV6_PACKET_EXTENSION : EndIf
 *view\packet=packet : *view\packetBytes=size
 *view\source=packet+8 : *view\destination=packet+24
 *view\payload=packet+at : *view\payloadBytes=size-at
 If nextHeader=59 : *view\payloadBytes=0 : EndIf
 *view\protocol=nextHeader : *view\hopLimit=PeekA(packet+7)
 word=NetReadBE32(packet)
 *view\trafficClass=(word>>20)&255 : *view\flowLabel=word&$FFFFF
 *view\errorOffset=0
 ProcedureReturn 0
EndProcedure

; Writes exactly 40 header bytes, leaves payload to the caller. Returns 40
; or ARGUMENT; refusal writes nothing. Address spans must not overlap output.
Procedure.i IPv6PacketHeader(out.i,capacity.i,source.i,destination.i,payloadBytes.i,protocol.i,hops.i,traffic.i,flow.i)
 Define i.i,word.i
 If out=0 Or source=0 Or destination=0 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If capacity<40 Or payloadBytes<0 Or payloadBytes>65535 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If protocol<0 Or protocol>255 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If hops<0 Or hops>255 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If traffic<0 Or traffic>255 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If flow<0 Or flow>$FFFFF : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If out<source+16 And source<out+40 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 If out<destination+16 And destination<out+40 : ProcedureReturn #IPV6_PACKET_ARGUMENT : EndIf
 word=$60000000|(traffic<<20)|flow
 NetWriteBE32(out,word) : NetWriteBE16(out+4,payloadBytes)
 PokeA(out+6,protocol) : PokeA(out+7,hops)
 For i=0 To 15
  PokeA(out+8+i,PeekA(source+i)) : PokeA(out+24+i,PeekA(destination+i))
 Next
 ProcedureReturn 40
EndProcedure
