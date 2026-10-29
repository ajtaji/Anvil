; Pi4 console transaction bodies/tail with explicit controlled providers.
; No renderer, DMA, GPU or display hardware is linked by this composition.
Global cpPending.i,cpCopyOk.i,cpConsumeOk.i,cpValidateOk.i,cpBeginRc.i,cpRenderRc.i,cpDrawRc.i
Global cpMainRebindRc.i,cpReady.i,cpQuarantine.i,cpQuiet.i,cpCopySawPending.i,cpCopySawTarget.i
Global cpCopyCalls.i,cpConsumes.i,cpMatches.i,cpMainRebinds.i,cpFailovers.i,cpBannerReleases.i
Global cpIdleCalls.i,cpReleases.i,cpEventsUsed.i,cpFault.i,cpTicks.i
Global Dim cpEvents.i[16]

Procedure CpEvent(event.i)
 If cpEventsUsed>=16 : cpFault=cpFault+1 : ProcedureReturn : EndIf
 cpEvents[cpEventsUsed]=event : cpEventsUsed=cpEventsUsed+1
EndProcedure

; @CP_COMPOSITION@

Procedure CpCapture(id.i,result.i)
 Define base.i,i.i
 base=#CP_REPORT+64+(id-1)*256
 PokeI(base,id) : PokeI(base+8,result)
 PokeI(base+16,cpPending) : PokeI(base+24,avcDisplayCopyPending)
 PokeI(base+32,cpCopyCalls) : PokeI(base+40,cpConsumes)
 PokeI(base+48,cpMatches) : PokeI(base+56,cpMainRebinds)
 PokeI(base+64,cpFailovers) : PokeI(base+72,cpCopySawPending) : PokeI(base+80,cpCopySawTarget)
 PokeI(base+88,cpBannerReleases) : PokeI(base+96,cpIdleCalls)
 PokeI(base+104,avcDeviceUnsafe) : PokeI(base+112,avcDevice) : PokeI(base+120,cpReleases)
 For i=0 To 15 : PokeI(base+128+i*8,cpEvents[i]) : Next
EndProcedure

Procedure.i ConsolePresentOrderProof()
 Define rc.i,i.i
 CpReset() : rc=CpFullTail() : CpCapture(1,rc)
 CpReset() : cpCopyOk=0 : rc=CpFullTail() : CpCapture(2,rc)
 CpReset() : cpValidateOk=0 : rc=CpFullTail() : CpCapture(3,rc)
 CpReset() : cpConsumeOk=0 : rc=CpFullTail() : CpCapture(4,rc)
 CpReset() : cpDrawRc=1 : rc=CpFullTail() : CpCapture(5,rc)
 CpReset() : rc=avcPumpBannerOnly() : CpCapture(6,rc)
 CpReset() : cpCopyOk=0 : rc=avcPumpBannerOnly() : CpCapture(7,rc)
 CpReset() : avcBanReady=0 : rc=avcPumpBannerOnly() : CpCapture(8,rc)
 CpReset() : cpBeginRc=-1 : rc=avcPumpBannerOnly() : CpCapture(9,rc)
 CpReset() : cpRenderRc=1 : rc=avcPumpBannerOnly() : CpCapture(10,rc)
 CpReset() : cpMainRebindRc=-1 : rc=avcPumpBannerOnly() : CpCapture(11,rc)
 For i=12 To 14
  CpReset() : cpPending=1 : avcDisplayCopyPending=1
  avcDevice=201 : avcPool=202 : avcFramebuffer=203
  If i=12 : cpQuiet=0 : EndIf
  If i=13 : cpQuarantine=1 : EndIf
  rc=VulkanConsoleDestroy() : CpCapture(i,rc)
 Next
 ProcedureReturn cpFault
EndProcedure
