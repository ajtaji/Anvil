; Native scanout is linear XRGB8888 in the orientation seen by the guest.
Procedure.i ScrCapturePixel(fb.i,pitch.i,rot.i,panelW.i,panelH.i,x.i,y.i)
 ProcedureReturn PeekL(fb+y*pitch+x*4)&$FFFFFFFF
EndProcedure

XIncludeFile "Anvil/Core/screenshot_stream.pbi"

XIncludeFile "Anvil/Core/screenshot_reliable.pbi"

Procedure.i ZentajiScreenshotFront()
 If zngUp=0 Or zngFault<>0 Or zngSuspended<>0 Or zngPainting<>0
  PrintN("!! screenshot needs an active console display.") : ProcedureReturn 0
 EndIf
 If zngDrainFrame()<>1 Or zngPresented=0 Or ZentajiGraphicsDisplayOwned()<>1 Or zgdPending<>0 Or zgdEnabled=0
  PrintN("!! screenshot could not acquire the presented frame.") : ProcedureReturn 0
 EndIf
 ; Ctrl-C checks pump prompt services. Hold the producer until the final row
 ; so neither a resize nor the animated banner can replace this plane.
 zngPainting=1
 ProcedureReturn zgdBase+zgdShown*zgdSpan
EndProcedure

Procedure CmdPic()
 Protected fb.i=ZentajiScreenshotFront()
 If fb=0 : ProcedureReturn : EndIf
 AnvilScreenshotStream(fb,zgdWidth,zgdHeight,zgdPitch,0,zgdWidth,zgdHeight,4)
 zngPainting=0
EndProcedure

Procedure ZentajiCmdPicR()
 Protected fb.i
 If NetConsoleOn()=0 Or NetConsolePeerOk()=0
  PrintN("!! pr needs an active UDP console peer. Use tools/pmfshot_wifi.py from the host.") : ProcedureReturn
 EndIf
 fb=ZentajiScreenshotFront()
 If fb=0 : ProcedureReturn : EndIf
 AnvilScreenshotReliable(fb,zgdWidth,zgdHeight,zgdPitch,0,zgdWidth,zgdHeight)
 zngPainting=0
EndProcedure
