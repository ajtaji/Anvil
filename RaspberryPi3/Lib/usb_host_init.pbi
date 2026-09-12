; Original Pi3 DWC2 host bring-up over the ordered adapter, not enumeration.
; Register facts: pinned raspberrypi/linux 7d182693, dwc2 core/hcd/hw/params.
; Include native adapter, then usb_host_core, then this file. No DMA/IRQ enable.
Global p3usb_host_state.i
Global p3usb_host_error.i

Procedure.i Pi3UsbHostWait(offset.i,mask.i,want.i,limit.i)
  Protected began.i=Pi3UsbTime()
  Protected now.i
  Protected n.i
  If began<0
  ProcedureReturn 0
  EndIf
  For n=0 To 1999999
    If (Pi3UsbRead(offset)&mask)=want
    ProcedureReturn 1
    EndIf
    now=Pi3UsbTime()
    If now<began Or now-began>=limit
    ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3UsbHostDelay(delay.i)
  Protected began.i=Pi3UsbTime()
  Protected now.i
  Protected n.i
  If began<0
  ProcedureReturn 0
  EndIf
  For n=0 To 1999999
    now=Pi3UsbTime()
    If now<began
    ProcedureReturn 0
    EndIf
    If now-began>=delay
    ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3UsbHostInit()
  Protected hw.i
  Protected width.i
  Protected cfg.i
  Protected desired.i
  Protected depth.i
  Protected rx.i=774
  Protected np.i
  Protected periodic.i
  Protected n.i
  Protected channels.i
  p3usb_host_error=0
  If p3usb_host_state<>0 Or p3usb_state<>0
  p3usb_host_error=-30
  ProcedureReturn 0
  EndIf
  If Pi3UsbPowerAcquire()=0
  p3usb_host_error=-31
  ProcedureReturn 0
  EndIf
  If Pi3UsbCoreReset()=0
  p3usb_host_error=p3usb_error
  ProcedureReturn 0
  EndIf
  p3usb_host_state=-1 ; from here the controller is consumed even on refusal
  hw=Pi3UsbRead($48)
  If ((hw>>3)&3)<>2 Or ((hw>>6)&3)=0 Or ((hw>>6)&3)=2 Or (hw&$80000)=0
    p3usb_host_error=-32
    ProcedureReturn 0
  EndIf
  width=(Pi3UsbRead($50)>>14)&3
  If width=3
  p3usb_host_error=-32
  ProcedureReturn 0
  EndIf
  cfg=Pi3UsbRead($0C)
  desired=(cfg&~$400A0058)|$20000007 ; UTMI, high-speed, force host; no ULPI FS/LS
  If width=1
  desired=desired|8
  EndIf
  If desired<>cfg
    Pi3UsbWrite($0C,desired)
    If Pi3UsbRead($0C)<>desired
    p3usb_host_error=-33
    ProcedureReturn 0
    EndIf
    If Pi3UsbCoreResetMode(1)=0
    p3usb_host_error=p3usb_error
    ProcedureReturn 0
    EndIf
  EndIf
  ; ID debounce can delay host mode after reset. Require measured host mode.
  If Pi3UsbHostWait($14,1,1,200000)=0
  p3usb_host_error=-34
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($E00,0) ; restart PHY clock before host configuration
  If Pi3UsbRead($E00)<>0
  p3usb_host_error=-33
  ProcedureReturn 0
  EndIf
  cfg=Pi3UsbRead($400)&~$800007 ; buffer DMA, 30/60MHz clock, high-speed capable
  Pi3UsbWrite($400,cfg)
  If Pi3UsbRead($400)<>cfg
  p3usb_host_error=-33
  ProcedureReturn 0
  EndIf
  depth=(Pi3UsbRead($4C)>>16)&$FFFF
  np=(Pi3UsbRead($28)>>16)&$FFFF
  periodic=(Pi3UsbRead($100)>>16)&$FFFF
  If np<16 Or periodic<16 Or depth<rx Or np>depth-rx Or periodic>depth-rx-np
    p3usb_host_error=-35
    ProcedureReturn 0
  EndIf
  Pi3UsbWrite($24,rx)
  Pi3UsbWrite($28,(np<<16)|rx)
  Pi3UsbWrite($100,(periodic<<16)|(rx+np))
  If Pi3UsbRead($24)<>rx Or Pi3UsbRead($28)<>((np<<16)|rx) Or Pi3UsbRead($100)<>((periodic<<16)|(rx+np))
    p3usb_host_error=-33
    ProcedureReturn 0
  EndIf
  If Pi3UsbWait($80000000,$80000000)=0
  p3usb_host_error=-4
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($10,$420) ; all TX FIFOs, then RX; never start while AHB busy
  If Pi3UsbHostWait($10,$20,0,10000)=0 Or Pi3UsbHostDelay(1)=0
  p3usb_host_error=-36
  ProcedureReturn 0
  EndIf
  If Pi3UsbWait($80000000,$80000000)=0
  p3usb_host_error=-4
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($10,$10)
  If Pi3UsbHostWait($10,$10,0,10000)=0 Or Pi3UsbHostDelay(1)=0
  p3usb_host_error=-36
  ProcedureReturn 0
  EndIf
  cfg=(Pi3UsbRead(0)&~$400)|$C ; no HNP; host VBUS valid override
  Pi3UsbWrite(0,cfg)
  Pi3UsbWrite($18,0)
  Pi3UsbWrite($418,0)
  channels=((hw>>14)&15)+1
  For n=0 To channels-1
  Pi3UsbWrite($50C+n*$20,0)
  Next
  cfg=(Pi3UsbRead(8)&~$3F)|$10 ; BCM burst setting; DMA and global IRQ remain off
  Pi3UsbWrite(8,cfg)
  If Pi3UsbRead(8)<>cfg
  p3usb_host_error=-33
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($440,Pi3UsbPortControl(Pi3UsbRead($440),$1000,0))
  If (Pi3UsbRead($440)&$1000)=0
  p3usb_host_error=-33
  ProcedureReturn 0
  EndIf
  p3usb_host_state=1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UsbRootPortReset()
  Protected port.i
  Protected channel.i
  Protected channels.i
  p3usb_host_error=0
  If p3usb_host_state<>1
  p3usb_host_error=-30
  ProcedureReturn 0
  EndIf
  If (Pi3UsbRead(8)&$21)<>0
    p3usb_host_error=-3
    ProcedureReturn 0
  EndIf
  channels=((Pi3UsbRead($48)>>14)&15)+1
  For channel=0 To channels-1
    If (Pi3UsbRead($500+channel*$20)&$80000000)<>0
      p3usb_host_error=-3
      ProcedureReturn 0
    EndIf
  Next
  port=Pi3UsbRead($440)
  If (port&1)=0 Or (port&$10)<>0
  p3usb_host_error=-37
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($440,Pi3UsbPortControl(port,$1100,$C0))
  If (Pi3UsbRead($440)&$1100)<>$1100
    p3usb_host_error=-33
    p3usb_host_state=-1
    ProcedureReturn 0
  EndIf
  If Pi3UsbHostDelay(50000)=0
  p3usb_host_error=-38
  p3usb_host_state=-1
  ProcedureReturn 0
  EndIf
  Pi3UsbWrite($440,Pi3UsbPortControl(Pi3UsbRead($440),0,$100))
  If (Pi3UsbRead($440)&$100)<>0
    p3usb_host_error=-33
    p3usb_host_state=-1
    ProcedureReturn 0
  EndIf
  If Pi3UsbHostWait($440,5,5,100000)=0
  p3usb_host_error=-39
  ProcedureReturn 0
  EndIf
  port=Pi3UsbRead($440)
  If (port&$10)<>0 Or ((port>>17)&3)=3
  p3usb_host_error=-37
  ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
