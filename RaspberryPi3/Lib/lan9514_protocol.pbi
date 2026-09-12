; Original LAN9514/SMSC95xx USB register and Ethernet framing foundation.
; Register facts: raspberrypi/linux 7d1826930811232688a50c99c540fbb137aed081
; drivers/net/usb/smsc95xx.c and smsc95xx.h. No driver implementation copied.
; Pure byte packing only. No USB transfer, MAC/PHY setup or Ethernet claim.
; Caller owns every span.  This first path deliberately leaves checksum
; offload disabled so received and transmitted frame boundaries stay explicit.

#P3_LAN_ID_REV       = $000
#P3_LAN_INT_STS      = $008
#P3_LAN_TX_CFG       = $010
#P3_LAN_HW_CFG       = $014
#P3_LAN_PM_CTRL      = $020
#P3_LAN_LED_GPIO_CFG = $024
#P3_LAN_AFC_CFG      = $02C
#P3_LAN_MAC_CR       = $100
#P3_LAN_ADDRH        = $104
#P3_LAN_ADDRL        = $108
#P3_LAN_MII_ADDR     = $114
#P3_LAN_MII_DATA     = $118
#P3_LAN_FLOW         = $11C

#P3_LAN_HW_CFG_LRST = $00000008
#P3_LAN_HW_CFG_SRST = $00000001
#P3_LAN_TX_CFG_ON   = $00000004
#P3_LAN_MAC_TXEN    = $00000008
#P3_LAN_MAC_RXEN    = $00000004

#P3_LAN_TX_FIRST = $00002000
#P3_LAN_TX_LAST  = $00001000
#P3_LAN_RX_ERROR = $00008000
#P3_LAN_RX_LENGTH_MASK = $3FFF0000

Global p3lan_error.i
Global p3lan_rx_frame.i
Global p3lan_rx_length.i
Global p3lan_rx_consumed.i

Procedure.i Pi3LanRegisterSetup(setup.i, reg.i, reading.i)
  p3lan_error=0
  If setup=0 Or reg<0 Or reg>$FFFF Or (reg & 3)<>0
    p3lan_error=-1
    ProcedureReturn 0
  EndIf
  If reading<>0 And reading<>1 : p3lan_error=-1 : ProcedureReturn 0 : EndIf
  If reading
    PokeA(setup,$C0) : PokeA(setup+1,$A1)
  Else
    PokeA(setup,$40) : PokeA(setup+1,$A0)
  EndIf
  PokeA(setup+2,0) : PokeA(setup+3,0)
  PokeA(setup+4,reg & 255) : PokeA(setup+5,(reg>>8)&255)
  PokeA(setup+6,4) : PokeA(setup+7,0)
  ProcedureReturn 1
EndProcedure

Procedure Pi3LanWriteLe32(address.i,value.i)
  PokeA(address,value & 255)
  PokeA(address+1,(value >> 8) & 255)
  PokeA(address+2,(value >> 16) & 255)
  PokeA(address+3,(value >> 24) & 255)
EndProcedure

Procedure.i Pi3LanReadLe32(address.i)
  If address=0 : p3lan_error=-1 : ProcedureReturn 0 : EndIf
  ProcedureReturn (PeekA(address) & 255) | ((PeekA(address+1) & 255) << 8) | ((PeekA(address+2) & 255) << 16) | ((PeekA(address+3) & 255) << 24)
EndProcedure

Procedure.i Pi3LanIdSupported(idRevision.i)
  Protected chip.i=(idRevision >> 16) & $FFFF
  ; The Pi 3 Model B device tree binds 0424:ec00.  Its SMSC95xx register
  ; identity is EC00 (LAN9512/9514 family); the USB hub itself is 0424:9514.
  If chip=$EC00 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

; Build one bulk-OUT record.  The frame is copied after the two little-endian
; command words; hardware padding and FCS generation remain enabled.
Procedure.i Pi3LanTxFrame(output.i,capacity.i,frame.i,frameLength.i)
  Protected n.i
  p3lan_error=0
  If output=0 Or frame=0 : p3lan_error=-1 : ProcedureReturn 0 : EndIf
  If frameLength<14 Or frameLength>1518 : p3lan_error=-2 : ProcedureReturn 0 : EndIf
  If capacity<frameLength+8 : p3lan_error=-3 : ProcedureReturn 0 : EndIf
  Pi3LanWriteLe32(output,frameLength | #P3_LAN_TX_FIRST | #P3_LAN_TX_LAST)
  Pi3LanWriteLe32(output+4,frameLength)
  For n=0 To frameLength-1
    PokeA(output+8+n,PeekA(frame+n))
  Next
  ProcedureReturn frameLength+8
EndProcedure

; Decode one bulk-IN record from an aggregate.  The SMSC95xx prefix is four
; status bytes plus the configured two-byte RX offset.  Frame length includes
; the four-byte FCS, which is excluded from the exported Ethernet frame.
Procedure.i Pi3LanRxFrame(input.i,available.i)
  Protected status.i
  Protected wireLength.i
  Protected rounded.i
  p3lan_error=0 : p3lan_rx_frame=0 : p3lan_rx_length=0 : p3lan_rx_consumed=0
  If input=0 : p3lan_error=-1 : ProcedureReturn 0 : EndIf
  If available<6 : p3lan_error=-3 : ProcedureReturn 0 : EndIf
  status=Pi3LanReadLe32(input)
  wireLength=(status & #P3_LAN_RX_LENGTH_MASK) >> 16
  If (status & #P3_LAN_RX_ERROR)<>0 : p3lan_error=-4 : ProcedureReturn 0 : EndIf
  If wireLength<18 Or wireLength>1522 : p3lan_error=-5 : ProcedureReturn 0 : EndIf
  If wireLength>available-6 : p3lan_error=-3 : ProcedureReturn 0 : EndIf
  rounded=(wireLength+2+3) & $FFFFFFFC
  If 4+rounded>available : p3lan_error=-3 : ProcedureReturn 0 : EndIf
  p3lan_rx_frame=input+6
  p3lan_rx_length=wireLength-4
  p3lan_rx_consumed=4+rounded
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3LanErrorCode()
  ProcedureReturn p3lan_error
EndProcedure
