; Host radios share the network device's optional control window.
; A pending operation survives a monitor prompt so pairing can wait for its UI.
Procedure HwHostRadioCommand(bluetooth.i,op.i,arg.i)
 Protected base.i=#ZEN_ETH_BASE,kind.i=1,request.i,state.i,size.i,i.i,ch.i,word.q,deadline.q
 If bluetooth : kind=2 : EndIf
 If PeekQ(base+$C0)<>$31444152
  PrintN("Host radios are unavailable. A live machine needs radios host or radios manage.")
  ProcedureReturn
 EndIf
 state=PeekQ(base+$D0)
 If op=5
  If state=0 Or PeekQ(base+$F0)/16<>kind
   PrintN("There is no result for this radio.") : ProcedureReturn
  EndIf
 Else
  If state=1 : PrintN("A radio operation is pending. Use its result command.") : ProcedureReturn : EndIf
  request=kind*16+op
  PokeQ(base+$D8,0)
  If arg<>0
   While PeekA(arg+i)<>0
    If i>=255 : PrintN("Radio argument exceeds 255 bytes.") : ProcedureReturn : EndIf
    PokeQ(base+$E0,PeekA(arg+i)&255) : i=i+1
   Wend
  EndIf
  PokeQ(base+$C8,request)
 EndIf
 deadline=HwMicros()+1000000
 While PeekQ(base+$D0)=1 And HwMicros()<deadline
  delayMicroseconds(10000)
 Wend
 If PeekQ(base+$D0)=1
  If bluetooth : PrintN("Bluetooth operation pending. Type bt result.")
  Else : PrintN("Wi-Fi operation pending. Type wifi result.") : EndIf
  ProcedureReturn
 EndIf
 size=PeekQ(base+$D8)
 If size<1 Or size>8192 : PrintN("Host radio response is unavailable.") : ProcedureReturn : EndIf
 For i=0 To size-1
  If (i&7)=0 : word=PeekQ(base+$1000+i) : EndIf
  ch=(word>>((i&7)*8))&255
  If ch=10 : PrintNl()
  ElseIf ch>=32 And ch<127 : PrintChar(ch)
  EndIf
 Next
EndProcedure
