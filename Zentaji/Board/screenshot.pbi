; Native scanout is linear XRGB8888 in the orientation seen by the guest.
Procedure.i ScrCapturePixel(fb.i,pitch.i,rot.i,panelW.i,panelH.i,x.i,y.i)
 ProcedureReturn PeekL(fb+y*pitch+x*4)&$FFFFFFFF
EndProcedure

XIncludeFile "Anvil/Core/screenshot_stream.pbi"

Procedure CmdPic()
 Protected fb.i
 If zngUp=0 Or zngFault<>0 Or zngSuspended<>0 Or zngPainting<>0
  PrintN("!! screenshot needs an active console display.") : ProcedureReturn
 EndIf
 If zngDrainFrame()<>1 Or zngPresented=0 Or ZentajiGraphicsDisplayOwned()<>1 Or zgdPending<>0 Or zgdEnabled=0
  PrintN("!! screenshot could not acquire the presented frame.") : ProcedureReturn
 EndIf
 ; Ctrl-C checks pump prompt services. Hold the producer until the final row
 ; so neither a resize nor the animated banner can replace this plane.
 zngPainting=1
 fb=zgdBase+zgdShown*zgdSpan
 AnvilScreenshotStream(fb,zgdWidth,zgdHeight,zgdPitch,0,zgdWidth,zgdHeight,4)
 zngPainting=0
EndProcedure
