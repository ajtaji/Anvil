; Payload-side datagram binding. Requires ABI1.15, 208 or more slots.
; Call UdpPayloadService from the foreground event loop. No driver code.
XIncludeFile "Anvil/Hal/service_errors.pbi"
XIncludeFile "Anvil/Network/udp_socket_types.pbi"
Global Dim udpapiSlots.i[8]
Procedure.i UdpPayloadBind(table.i)
 Define i.i,header.i
 For i=0 To 7 : udpapiSlots[i]=0 : Next
 If IPv6UdpSpanValid(table,1680)=0 : ProcedureReturn #SVC_EABI : EndIf
 If PeekI(table)<>$153564E41 : ProcedureReturn #SVC_EABI : EndIf
 header=PeekI(table+8)
 If (header & $FFFFFFFF)<15 Or ((header>>32)&$FFFFFFFF)<208 : ProcedureReturn #SVC_EABI : EndIf
 For i=0 To 7
  If PeekI(table+16+(200+i)*8)<=0 : ProcedureReturn #SVC_EABI : EndIf
 Next
 For i=0 To 7 : udpapiSlots[i]=PeekI(table+16+(200+i)*8) : Next
 ProcedureReturn 0
EndProcedure
Procedure.i UdpPayloadOpen(family.i,kind.i,port.i)
 Define *fn
 *fn=udpapiSlots[0]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(family,kind,port)
EndProcedure
Procedure.i UdpPayloadSendTo(handle.i,peer.i,data.i,bytes.i)
 Define *fn
 *fn=udpapiSlots[1]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle,peer,data,bytes)
EndProcedure
Procedure.i UdpPayloadReceive(handle.i,info.i,data.i,capacity.i)
 Define *fn
 *fn=udpapiSlots[2]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle,info,data,capacity)
EndProcedure
Procedure.i UdpPayloadPeek(handle.i,info.i)
 Define *fn
 *fn=udpapiSlots[3]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle,info)
EndProcedure
Procedure.i UdpPayloadStatus(handle.i,status.i)
 Define *fn
 *fn=udpapiSlots[4]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle,status)
EndProcedure
Procedure.i UdpPayloadClose(handle.i)
 Define *fn
 *fn=udpapiSlots[5]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle)
EndProcedure
Procedure.i UdpPayloadService()
 Define *fn
 *fn=udpapiSlots[6]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn()
EndProcedure
Procedure.i UdpPayloadDiscard(handle.i)
 Define *fn
 *fn=udpapiSlots[7]
 If *fn=0 : ProcedureReturn #SVC_EABI : EndIf
 ProcedureReturn fn(handle)
EndProcedure
