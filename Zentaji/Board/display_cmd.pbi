; Snapshot the display before Anvil acquires it, so the boot values remain
; available even after a mode change or an application returns.
Global zdStartup.i,zdBootMode.i,zdBootW.i,zdBootH.i,zdBootHz.i,zdBootFormat.i,zdBootPitch.i,zdBootPower.i
Procedure ZentajiRememberDisplay()
 If (PeekQ(#ZEN_GFX_DISPLAY)&$FFFF)<>13 : ProcedureReturn : EndIf
 zdBootMode=PeekQ(#ZEN_GFX_DISPLAY+$40)
 zdBootW=PeekQ(#ZEN_GFX_DISPLAY+$50) : zdBootH=PeekQ(#ZEN_GFX_DISPLAY+$58)
 zdBootHz=PeekQ(#ZEN_GFX_DISPLAY+$60) : zdBootFormat=PeekQ(#ZEN_GFX_DISPLAY+$68)
 zdBootPitch=PeekQ(#ZEN_GFX_DISPLAY+$70) : zdBootPower=PeekQ(#ZEN_GFX_DISPLAY+$10)&1
 zdStartup=1
EndProcedure

Procedure zdSayMode(mode.i,w.i,h.i,rate.i,format.i,pitch.i,power.i)
 Print("mode=") : PrintDec(mode) : Print(" pixels=") : PrintDec(w) : Print("x") : PrintDec(h)
 Print(" refresh_mHz=") : PrintDec(rate) : Print(" format=") : PrintDec(format)
 Print(" stride=") : PrintDec(pitch) : Print(" enabled=") : PrintDec(power) : PrintNl()
EndProcedure

Procedure zdLive()
 Protected request.q=PeekQ(#ZEN_GFX_DISPLAY+$B0),active.q=PeekQ(#ZEN_GFX_DISPLAY+$B8)
 PrintN("Zentaji native display")
 zdSayMode(PeekQ(#ZEN_GFX_DISPLAY+$40),PeekQ(#ZEN_GFX_DISPLAY+$50),PeekQ(#ZEN_GFX_DISPLAY+$58),PeekQ(#ZEN_GFX_DISPLAY+$60),PeekQ(#ZEN_GFX_DISPLAY+$68),PeekQ(#ZEN_GFX_DISPLAY+$70),PeekQ(#ZEN_GFX_DISPLAY+$10)&1)
 Print("host_request=") : PrintDec(request&$FFFFFFFF) : Print("x") : PrintDec((request>>32)&$FFFFFFFF)
 Print(" accepted=") : PrintDec(active&$FFFFFFFF) : Print("x") : PrintDec((active>>32)&$FFFFFFFF)
 Print(" shown=") : PrintDec(PeekQ(#ZEN_GFX_DISPLAY+$90))
 Print(" vsync=") : PrintDec(PeekQ(#ZEN_GFX_DISPLAY+$98)) : PrintNl()
EndProcedure

; Eight native Vulkan bars at the current window size. The retained frame
; can still be inspected through shot or sr after the prompt has returned.
Procedure.i zdPattern()
 Protected band.i,left.i,right.i,bits.i,colour.i,rc.i,kept.i,deadline.q
 If zngUp=0 Or zngBlanked<>0 Or zngSuspended<>0 Or zngPainting<>0 Or zngFault<>0 : ProcedureReturn 0 : EndIf
 If zngDrainFrame()<>1 Or ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn 0 : EndIf
 If NeonVkChromeAsync(1)<>0 : ProcedureReturn 0 : EndIf
 zngPainting=1
 rc=NeonVkChromeBegin(@zngClear[0])
 If rc=0
  For band=0 To 7
   left=band*znsWidth/8 : right=(band+1)*znsWidth/8 : bits=7-band
   colour=Neon_RGB(((bits>>2)&1)*255,((bits>>1)&1)*255,(bits&1)*255)
   rc=NeonVkChromeBox(left,0,right-left,znsHeight,colour)
   If rc<>0 : Break : EndIf
  Next
  If rc=0 : rc=NeonVkChromeEnd() : EndIf
 EndIf
 If rc<>0
  NeonVkChromeAbort() : NeonVkChromeAsync(0)
  zngPainting=0 : zngPresented=0 : ConGridMarkAll() : ProcedureReturn 0
 EndIf
 If zngDrainFrame()<>1 : ProcedureReturn 0 : EndIf
 zngPainting=1
 If zgdPending=0 And ZentajiGraphicsDisplayOwned()<>0
  kept=ZentajiKeptCopy(zgdBase+zgdShown*zgdSpan,#MON_SHOT_WHO_PAYLOAD,0)
 EndIf
 deadline=HwMicros()+1000000
 While HwMicros()<deadline And HwPromptIdleReady()<>0
  HwPromptIdleWait()
 Wend
 zngPainting=0 : zngPresented=0 : zngCursorRow=-1 : ConGridMarkAll()
 ProcedureReturn kept
EndProcedure

Procedure ZentajiCmdDisplay()
 SkipSpace() : gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt : SkipSpace()
 If zdStartup=0 : PrintN("!! this machine has no native display connector.") : ProcedureReturn : EndIf
 If gLine[gPos]<>0 : PrintN("!! this display operation takes no further arguments.") : ProcedureReturn : EndIf
 If gWordLen=0 Or WordIs("status")<>0 Or WordIs("panel")<>0 Or WordIs("host")<>0 Or WordIs("pipe")<>0 Or WordIs("regs")<>0
  zdLive()
 ElseIf WordIs("id")<>0
  Print("Zentaji display device ID=$") : PutHex16(PeekQ(#ZEN_GFX_DISPLAY)) : PrintNl()
 ElseIf WordIs("snapshot")<>0
  PrintN("Display state before Anvil acquired the connector:")
  zdSayMode(zdBootMode,zdBootW,zdBootH,zdBootHz,zdBootFormat,zdBootPitch,zdBootPower)
 ElseIf WordIs("power")<>0
  Print("Native display output enabled=") : PrintDec(PeekQ(#ZEN_GFX_DISPLAY+$10)&1) : PrintNl()
 ElseIf WordIs("up")<>0 Or WordIs("on")<>0 Or WordIs("off")<>0
  If zngUp=0 : PrintN("!! the native graphics console is unavailable.") : ProcedureReturn : EndIf
  ZentajiScreenSet(Bool(WordIs("off")=0))
 ElseIf WordIs("pattern")<>0
  If zdPattern()<>0
   Print("Native colour bars kept as picture ") : PrintDec(zkSequence) : PrintN(". Use shot or sr.")
  Else
   PrintN("!! the native display could not present and retain the test pattern.")
  EndIf
 Else
  PrintN("Use display status, id, snapshot, power, up, off or pattern.")
  PrintN("Zentaji connects to the host window. DSI lane and power-rail operations require a physical DSI controller.")
 EndIf
EndProcedure
