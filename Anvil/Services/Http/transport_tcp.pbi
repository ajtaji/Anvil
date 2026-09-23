; Native queued-listener adapter. Requires tcp.pi4 queued acceptance APIs.
; One network service owner. Every operation restores TcpCurrent. No TcpInit.
; Children keep their own generation and drain state; listener never converts
; into an accepted child, and TIME-WAIT is never shortened by this service.
Global ht_owned.i
Global ht_socket.i
Global ht_port.i
Global ht_listener.i
Global ht_serial.i
Global ht_live.i
Global ht_clock.i
Global Dim ht_handle.i[#TCP_SOCKETS]
Global Dim ht_epoch.i[#TCP_SOCKETS]
Global Dim ht_draining.i[#TCP_SOCKETS]
Global Dim ht_close_start.i[#TCP_SOCKETS]

Procedure.i HtStart(port.i)
  Protected keep.i
  Protected slot.i
  Protected result.i
  If ht_owned <> 0 Or port < 1 Or port > 65535 : ProcedureReturn 0 : EndIf
  keep = TcpCurrent()
  slot = TcpAlloc()
  If slot < 0 : ProcedureReturn 0 : EndIf
  result = TcpListenQueued(port)
  If result = #NET_TCP_OK
    ht_listener = TcpListenerGeneration()
    If ht_listener <> 0
      ht_owned = 1
      ht_socket = slot
      ht_port = port
    Else
      TcpUnlisten()
    EndIf
  EndIf
  TcpUse(keep)
  ProcedureReturn ht_owned
EndProcedure

Procedure.i HtFind(handle.i)
  Protected slot.i
  If handle <= 0 : ProcedureReturn -1 : EndIf
  For slot = 0 To #TCP_SOCKETS - 1
    If ht_handle[slot] = handle : ProcedureReturn slot : EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i HtService(now.i)
  Protected keep.i
  Protected slot.i
  Protected state.i
  If now < ht_clock : ProcedureReturn 0 : EndIf
  ht_clock = now
  keep = TcpCurrent()
  TcpPoll(0)
  If ht_owned
    TcpUse(ht_socket)
    If TcpListeningPort() <> ht_port Or TcpListenerGeneration() <> ht_listener
      ht_owned = 0
    EndIf
  EndIf
  For slot = 0 To #TCP_SOCKETS - 1
    If ht_handle[slot] <> 0
      TcpUse(slot)
      If TcpGeneration() <> ht_epoch[slot] Or TcpState() = #TCP_CLOSED
        ht_handle[slot] = 0
        ht_live = ht_live - 1
      EndIf
    EndIf
    If ht_draining[slot]
      TcpUse(slot)
      state = TcpState()
      If TcpGeneration() <> ht_epoch[slot] Or state = #TCP_CLOSED
        ht_draining[slot] = 0
      ElseIf state <> #TCP_TIME_WAIT And now - ht_close_start[slot] >= 10000
        TcpAbort()
        ht_draining[slot] = 0
      EndIf
    EndIf
  Next
  TcpUse(keep)
  ProcedureReturn 1
EndProcedure

Procedure.i HtAccept()
  Protected keep.i
  Protected slot.i
  Protected result.i
  If ht_owned = 0 Or ht_serial >= 2147483647 : ProcedureReturn 0 : EndIf
  keep = TcpCurrent()
  TcpUse(ht_socket)
  If TcpListenerGeneration() <> ht_listener Or TcpListeningPort() <> ht_port
    TcpUse(keep)
    ProcedureReturn -1
  EndIf
  slot = TcpAccept(ht_socket)
  If slot >= 0
    TcpUse(slot)
    If TcpGeneration() <> 0
      ht_serial = ht_serial + 1
      ht_handle[slot] = ht_serial
      ht_epoch[slot] = TcpGeneration()
      ht_draining[slot] = 0
      ht_live = ht_live + 1
      result = ht_serial
    Else
      TcpAbort()
    EndIf
  EndIf
  TcpUse(keep)
  ProcedureReturn result
EndProcedure

Procedure.i HtRead(handle.i, output.i, count.i)
  Protected keep.i
  Protected slot.i
  Protected result.i
  Protected state.i
  slot = HtFind(handle)
  If slot < 0 Or output = 0 Or count <= 0 : ProcedureReturn -1 : EndIf
  keep = TcpCurrent()
  TcpUse(slot)
  result = -1
  If TcpGeneration() = ht_epoch[slot]
    state = TcpState()
    If state = #TCP_ESTABLISHED Or state = #TCP_CLOSE_WAIT
      If TcpAvailable() > 0
        result = TcpRead(output, count)
      ElseIf state = #TCP_ESTABLISHED
        result = 0
      EndIf
    EndIf
  EndIf
  TcpUse(keep)
  ProcedureReturn result
EndProcedure

Procedure.i HtWrite(handle.i, input.i, count.i)
  Protected keep.i
  Protected slot.i
  Protected result.i
  Protected state.i
  slot = HtFind(handle)
  If slot < 0 Or input = 0 Or count <= 0 : ProcedureReturn -1 : EndIf
  keep = TcpCurrent()
  TcpUse(slot)
  result = -1
  If TcpGeneration() = ht_epoch[slot]
    state = TcpState()
    If state = #TCP_ESTABLISHED Or state = #TCP_CLOSE_WAIT
      result = TcpSend(input, count)
    EndIf
  EndIf
  TcpUse(keep)
  ProcedureReturn result
EndProcedure

Procedure HtClose(handle.i)
  Protected keep.i
  Protected slot.i
  slot = HtFind(handle)
  If slot < 0
    ProcedureReturn
  EndIf
  keep = TcpCurrent()
  TcpUse(slot)
  If TcpGeneration() = ht_epoch[slot]
    If TcpClose() = #NET_TCP_OK
      ht_draining[slot] = 1
      ht_close_start[slot] = ht_clock
    EndIf
  EndIf
  ht_handle[slot] = 0
  ht_live = ht_live - 1
  TcpUse(keep)
EndProcedure

Procedure HtStop()
  Protected keep.i
  Protected slot.i
  keep = TcpCurrent()
  If ht_owned
    TcpUse(ht_socket)
    If TcpListenerGeneration() = ht_listener And TcpListeningPort() = ht_port
      TcpUnlisten()
    EndIf
  EndIf
  For slot = 0 To #TCP_SOCKETS - 1
    If ht_handle[slot] <> 0 Or ht_draining[slot] <> 0
      TcpUse(slot)
      If TcpGeneration() = ht_epoch[slot] And TcpState() <> #TCP_TIME_WAIT
        TcpAbort()
      EndIf
      ht_handle[slot] = 0
      ht_draining[slot] = 0
    EndIf
  Next
  ht_owned = 0
  ht_live = 0
  TcpUse(keep)
EndProcedure
