; SPDX-License-Identifier: MIT
; Returning application: pure retained UI and service calls, no hardware copy.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_retained.pbi"
Global Dim nsaArena.q[2048]
Procedure.i NsaNoText(x.i,y.i,text.i,colour.i,pixels.i,background.i)
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Procedure.i NsaNoEnd()
  ProcedureReturn #NEON_SERVICE_ERR_UNBOUND
EndProcedure
Global nsaChecks.i,nsaFailure.i,nsaConsole.i=@NsaNoText,nsaFrameEnd.i=@NsaNoEnd,nsaMessageAt.i

Procedure NsaAppend(*text)
  Define i.i
  While PeekA(*text + i) <> 0 And nsaMessageAt < 180
    PokeA(#NSA_REPORT + 1024 + nsaMessageAt,PeekA(*text + i))
    i = i + 1 : nsaMessageAt = nsaMessageAt + 1
  Wend
EndProcedure
Procedure NsaNumber(value.i)
  Define place.i = 1000000000
  If value < 0 : NsaAppend("invalid") : ProcedureReturn : EndIf
  While place > 1 And value < place : place = place / 10 : Wend
  While place > 0 And nsaMessageAt < 180
    PokeA(#NSA_REPORT + 1024 + nsaMessageAt,48 + value / place)
    nsaMessageAt = nsaMessageAt + 1 : value = value % place : place = place / 10
  Wend
EndProcedure

Procedure NsaCheck(actual.i,expected.i)
  nsaChecks = nsaChecks + 1
  PokeI(#NSA_REPORT + 128 + nsaChecks * 16,actual)
  PokeI(#NSA_REPORT + 136 + nsaChecks * 16,expected)
  If actual <> expected And nsaFailure = 0 : nsaFailure = nsaChecks : EndIf
EndProcedure

Procedure.i Main(services.i)
  Define i.i,rc.i,font.i,context.i,button.i
  For i = 0 To 4095 Step 8 : PokeI(#NSA_REPORT + i,0) : Next
  PokeI(#NSA_REPORT,$4E534131) : PokeI(#NSA_REPORT + 8,1)
  If services = 0 : ProcedureReturn 100 : EndIf
  If (PeekL(services) & $FFFFFFFF) <> $53564E41 : ProcedureReturn 100 : EndIf
  PokeI(#NSA_REPORT + 32,PeekL(services + 4)) : PokeI(#NSA_REPORT + 40,PeekL(services + 8))
  If PeekL(services + 4) <> 1 Or PeekL(services + 8) < 8
    NsaAppend("Anvil's service table is ") : NsaNumber(PeekL(services + 4)) : NsaAppend(".") : NsaNumber(PeekL(services + 8))
    NsaAppend("; this Neon application needs 1.8. Update Anvil before running it.")
    ; A different major may change every slot signature; record only then.
    If PeekL(services + 4) = 1 And PeekL(services + 12) > 30
      nsaConsole = PeekI(services + 16 + 30 * 8) : nsaFrameEnd = PeekI(services + 16 + 28 * 8)
      nsaConsole(10,140,#NSA_REPORT + 1024,$FFFFFFFF,16,$FF000000) : nsaFrameEnd()
    EndIf
    ProcedureReturn 101
  EndIf
  NsaCheck(NeonServiceBind(services,#NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS),0)
  If nsaFailure <> 0 : ProcedureReturn nsaFailure : EndIf
  NsaCheck(NeonServiceOpen(),0)
  If nsaFailure <> 0 : ProcedureReturn nsaFailure : EndIf
  context = NeonServiceContext()
  NsaCheck(Bool(context > 0),1)
  PokeI(#NSA_REPORT + 48,context)
  PokeI(#NSA_REPORT + 56,NeonServiceWidth()) : PokeI(#NSA_REPORT + 64,NeonServiceHeight())
  NsaCheck(Bool(NeonServiceWidth() > 0),1) : NsaCheck(Bool(NeonServiceHeight() > 0),1)
  font = NeonServiceFontRegister(4,0,24)
  NsaCheck(Bool(font > 3),1) : PokeI(#NSA_REPORT + 72,font)
  NsaCheck(NeonRetainedConfigure(@nsaArena[0],16384,16,128),0)
  NsaCheck(NeonServiceRetainedInstall(),0)
  NsaCheck(NeonRetainedViewport(0.0,0.0,MathFFromInt(NeonServiceWidth()),MathFFromInt(NeonServiceHeight()),MathFFromInt(NeonServiceWidth()),MathFFromInt(NeonServiceHeight())),0)
  NsaCheck(NeonRetainedFontSet(font),0)
  NsaCheck(Bool(NeonRetainedAddLabel(1,60.0,60.0,"Neon on Anvil - resident Vulkan") > 0),1)
  button = NeonRetainedAddButton(2,60.0,140.0,360.0,64.0,"Start",0,0)
  NsaCheck(Bool(button > 0),1)
  NsaCheck(NeonRetainedPrepare(),0)
  ; Abort an unsubmitted frame, then draw a fresh complete frame.
  NsaCheck(NeonServiceBegin(0.02,0.04,0.08,1.0),0)
  NsaCheck(NeonServiceAbort(),0)
  NsaCheck(NeonServiceBegin(0.02,0.04,0.08,1.0),0)
  NsaCheck(NeonServiceBox(500.0,140.0,140.0,64.0,0.0,0.75,0.5,1.0),0)
  NsaCheck(NeonServicePolygon(570.0,300.0,65.0,65.0,12,0.9,0.4,0.1,1.0,1),0)
  NsaCheck(NeonRetainedDrawUI(0.0),0)
  NsaCheck(NeonServiceEnd(),0)
  NsaCheck(NeonServiceFrameOpen(),0)
  NsaCheck(NeonServiceProviderError(),0)
  PokeI(#NSA_REPORT + 16,nsaFailure) : PokeI(#NSA_REPORT + 24,nsaChecks)
  PokeI(#NSA_REPORT + 80,NeonServiceContext()) : PokeI(#NSA_REPORT + 88,NeonServiceReady())
  ; Deliberately leave the application open: the returning monitor captures
  ; this frame first, then must retire its resident owner before console reuse.
  ProcedureReturn nsaFailure
EndProcedure
