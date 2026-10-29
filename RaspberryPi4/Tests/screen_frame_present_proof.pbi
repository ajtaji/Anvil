; Controlled-provider execution of the actual DSI presentation owner.
; No HVS registers, DMA channel, display buffer or GPU are accessed.
#SCR_SRC_DSI = 2
#MON_FB_SCAN = $1000
#MON_FB_DRAW = $2000
#MON_FB_PANEL_W = 800
#MON_FB_PANEL_H = 1280
Global gScrSrc.i, gScrDsiUp.i, gDma.i
Global tcSafe.i, tcUp.i, tcPending.i, tcFront.i, tcW.i, tcH.i
Global tcDmaReady.i, tcDmaOk.i, tcBeginOk.i, tcLatch.i, tcHf.i, tcVf.i
Global tcBegins.i, tcCopies.i, tcDst.i, tcSrc.i, tcBytes.i, tcRequested.i
Global tcArgHf.i, tcArgVf.i, tcTicks.i, tcDelay.i, tcIdles.i
Procedure.i DisplayMemorySafe() : ProcedureReturn tcSafe : EndProcedure
Procedure.i HvsIsUp() : ProcedureReturn tcUp : EndProcedure
Procedure.i HvsFlipPending() : ProcedureReturn tcPending : EndProcedure
Procedure.i HvsWidth() : ProcedureReturn tcW : EndProcedure
Procedure.i HvsHeight() : ProcedureReturn tcH : EndProcedure
Procedure.i HvsFb() : ProcedureReturn tcFront : EndProcedure
Procedure.i HvsHFlip() : ProcedureReturn tcHf : EndProcedure
Procedure.i HvsVFlip() : ProcedureReturn tcVf : EndProcedure
Procedure.i DmaReady() : ProcedureReturn tcDmaReady : EndProcedure
Procedure.i ScrGpuBytes() : ProcedureReturn 4096000 : EndProcedure
Procedure DmaCacheRange(base.i,bytes.i) : EndProcedure
Procedure.i DmaCopy(dst.i,src.i,bytes.i)
 tcCopies=tcCopies+1 : tcDst=dst : tcSrc=src : tcBytes=bytes
 ProcedureReturn tcDmaOk
EndProcedure
Procedure.i HvsFlipBegin(base.i,hf.i,vf.i)
 tcBegins=tcBegins+1 : tcRequested=base : tcArgHf=hf : tcArgVf=vf
 If tcBeginOk=0 Or tcPending<>0 : ProcedureReturn 0 : EndIf
 tcPending=1 : ProcedureReturn 1
EndProcedure
Procedure.i HvsFlipResolve()
 If tcPending=0 : ProcedureReturn 1 : EndIf
 If tcDelay>0 : tcDelay=tcDelay-1 : ProcedureReturn 0 : EndIf
 If tcLatch=0 : ProcedureReturn 0 : EndIf
 tcFront=tcRequested : tcPending=0 : ProcedureReturn 1
EndProcedure
Procedure.i Ticks() : tcTicks=tcTicks+1 : ProcedureReturn tcTicks : EndProcedure
Procedure.i TickHz() : ProcedureReturn 100 : EndProcedure
Procedure TcIdle() : tcIdles=tcIdles+1 : EndProcedure
XIncludeFile "RaspberryPi4/Board/screen_frame_present.pi4"

Procedure TcReset()
 gScrSrc=2 : gScrDsiUp=1 : gDma=1 : tcSafe=1 : tcUp=1
 tcPending=0 : tcFront=#MON_FB_SCAN : tcW=800 : tcH=1280
 tcDmaReady=1 : tcDmaOk=1 : tcBeginOk=1 : tcLatch=1 : tcHf=0 : tcVf=0
 tcBegins=0 : tcCopies=0 : tcDst=0 : tcSrc=0 : tcBytes=0 : tcRequested=0
 tcArgHf=0 : tcArgVf=0 : tcTicks=0 : tcDelay=0 : tcIdles=0
 *gScrFrameWaitIdle=0
 gScrFrameOwned=0 : gScrFramePresentN=0 : gScrFrameRestoreN=0 : gScrFrameTimeoutN=0
EndProcedure

Procedure TcRecord(id.i,rc.i,second.i)
 Define at.i
 at=#TC_REPORT+64+(id-1)*144
 PokeI(at,id) : PokeI(at+8,rc) : PokeI(at+16,second)
 PokeI(at+24,tcFront) : PokeI(at+32,gScrFrameOwned) : PokeI(at+40,tcPending)
 PokeI(at+48,tcBegins) : PokeI(at+56,tcCopies)
 PokeI(at+64,tcDst) : PokeI(at+72,tcSrc) : PokeI(at+80,tcBytes)
 PokeI(at+88,gScrFramePresentN) : PokeI(at+96,gScrFrameRestoreN)
 PokeI(at+104,gScrFrameTimeoutN) : PokeI(at+112,tcArgHf) : PokeI(at+120,tcArgVf)
 PokeI(at+128,tcRequested) : PokeI(at+136,ScrFrameBack())
EndProcedure

Procedure.i Main(services.i)
 Define rc.i,other.i,i.i
 For i=0 To 4095 : PokeA(#TC_REPORT+i,0) : Next
 TcReset() : gScrDsiUp=0 : rc=ScrFrameRestore() : TcRecord(1,rc,0)
 TcReset() : rc=ScrFrameFront() : other=ScrFrameBack() : TcRecord(2,rc,other)
 TcReset() : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(3,rc,0)
 TcReset() : rc=ScrFramePublish(#MON_FB_SCAN) : TcRecord(4,rc,0)
 TcReset() : tcPending=1 : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(5,rc,0)
 TcReset() : rc=ScrFrameCloneBack() : TcRecord(6,rc,0)
 TcReset() : tcDmaOk=0 : rc=ScrFrameCloneBack() : TcRecord(7,rc,0)
 TcReset() : tcLatch=0 : rc=ScrFramePublish(#MON_FB_DRAW) : other=ScrFrameRestore() : TcRecord(8,rc,other)
 TcReset() : gScrFrameOwned=1 : tcFront=#MON_FB_DRAW : rc=ScrFrameRestore() : TcRecord(9,rc,0)
 TcReset() : gScrFrameOwned=1 : tcFront=#MON_FB_DRAW : tcDmaOk=0 : rc=ScrFrameRestore() : TcRecord(10,rc,0)
 TcReset() : gScrFrameOwned=1 : tcFront=#MON_FB_DRAW : tcBeginOk=0 : rc=ScrFrameRestore() : TcRecord(11,rc,0)
 TcReset() : gScrFrameOwned=1 : tcPending=1 : rc=ScrFrameRestore() : TcRecord(12,rc,0)
 TcReset() : tcHf=1 : tcVf=1 : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(13,rc,0)
 TcReset() : tcW=799 : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(14,rc,0)
 TcReset() : tcDmaReady=0 : rc=ScrFrameCloneBack() : TcRecord(15,rc,0)
 TcReset() : gScrDsiUp=0 : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(16,rc,0)
 TcReset() : tcDelay=3 : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(17,rc,tcIdles)
 TcReset() : tcDelay=3 : *gScrFrameWaitIdle=@TcIdle : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(18,rc,tcIdles)
 TcReset() : tcLatch=0 : *gScrFrameWaitIdle=@TcIdle : rc=ScrFramePublish(#MON_FB_DRAW) : TcRecord(19,rc,tcIdles)
 *gScrFrameWaitIdle=0
 PokeI(#TC_REPORT,$44534650) : PokeI(#TC_REPORT+8,0)
 PokeI(#TC_REPORT+16,#PMF_CHIP) : PokeI(#TC_REPORT+24,19)
 PokeI(#TC_REPORT+32,18) : PokeI(#TC_REPORT+40,1)
 PokeI(#TC_REPORT+56,$50465344)
 ProcedureReturn 0
EndProcedure
