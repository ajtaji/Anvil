; Controlled CPU proof of lifecycle binder configuration and callback ownership.
; No native renderer or GPU code is linked. Native work is forbidden here;
; the four work callbacks count unexpected calls and refuse them.
XIncludeFile "Anvil/Graphics/neon_lifecycle.pbi"
XIncludeFile "Anvil/Graphics/float_bits.pbi"
XIncludeFile "Anvil/Graphics/neon_colour.pbi"
Global binderNativeCalls.i
Procedure.i NeonHardwareLifecycleFlags()
 ProcedureReturn 0
EndProcedure
Procedure NeonHardwareCoordinateReset()
EndProcedure
Procedure.i NeonHardwareInit()
 binderNativeCalls=binderNativeCalls+1
 ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
Procedure.i NeonHardwareShutdown()
 binderNativeCalls=binderNativeCalls+1
 ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
Procedure.i NeonHardwareFrameBegin(colour.i)
 binderNativeCalls=binderNativeCalls+1
 ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
Procedure.i NeonHardwareFrameEnd()
 binderNativeCalls=binderNativeCalls+1
 ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Global fakeCreateRc.i
Global fakeCreateCount.i
Global fakeDestroyCount.i
Global fakeDestroyRc.i
Global fakeBeginCount.i
Global fakeEndCount.i
Global fakeClear0.i
Global fakeClear1.i
Global fakeClear2.i
Global fakeClear3.i

Procedure.i FakeBox(x.i, y.i, w.i, h.i, colour.i) : ProcedureReturn #NEON_OK : EndProcedure
Procedure.i FakeText(font.i, x.i, y.i, *s, colour.i) : ProcedureReturn #NEON_OK : EndProcedure
Procedure.i FakeTextTex(font.i, x.i, y.i, *s, colour.i) : ProcedureReturn #NEON_OK : EndProcedure
Procedure FakeScissorSet(x.i, y.i, w.i, h.i) : EndProcedure
Procedure FakeScissorClear() : EndProcedure
Procedure.i FakeFanBegin() : ProcedureReturn #NEON_OK : EndProcedure
Procedure FakeFanPoint(x.i, y.i) : EndProcedure
Procedure.i FakeFanEnd(colour.i) : ProcedureReturn #NEON_OK : EndProcedure
Procedure.i FakeFanOutline(colour.i) : ProcedureReturn #NEON_OK : EndProcedure
Procedure.i FakeLinesBegin() : ProcedureReturn #NEON_OK : EndProcedure
Procedure FakeLine(x0.i, y0.i, x1.i, y1.i) : EndProcedure
Procedure.i FakeLinesEnd(colour.i) : ProcedureReturn #NEON_OK : EndProcedure

Procedure.i NeonVkChromeCreate(physicalDevice.i, device.i, queue.i, commandPool.i, renderPass.i, framebuffer.i, width.i, height.i, maxQuads.i)
  fakeCreateCount = fakeCreateCount + 1
  If fakeCreateRc <> 0 : ProcedureReturn fakeCreateRc : EndIf
  If NeonDrawBackendInstall(@FakeBox, @FakeText, @FakeTextTex, @FakeScissorSet, @FakeScissorClear, @FakeFanBegin, @FakeFanPoint, @FakeFanEnd, @FakeFanOutline, @FakeLinesBegin, @FakeLine, @FakeLinesEnd) <> #NEON_OK
    ProcedureReturn 99
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i NeonVkChromeBegin(*clearValue)
  fakeBeginCount = fakeBeginCount + 1
  fakeClear0 = PeekL(*clearValue + 0) : fakeClear1 = PeekL(*clearValue + 4)
  fakeClear2 = PeekL(*clearValue + 8) : fakeClear3 = PeekL(*clearValue + 12)
  ProcedureReturn 0
EndProcedure

Procedure.i NeonVkChromeEnd()
  fakeEndCount = fakeEndCount + 1
  ProcedureReturn 0
EndProcedure

Procedure NeonVkChromeDestroy()
  fakeDestroyCount = fakeDestroyCount + 1
  NeonDrawBackendClear()
EndProcedure

Procedure.i NeonVkChromeDestroyChecked()
  If fakeDestroyRc <> 0 : ProcedureReturn fakeDestroyRc : EndIf
  NeonVkChromeDestroy()
  ProcedureReturn 0
EndProcedure

XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_lifecycle.pbi"

Procedure.i NeonVkLifecycleBinderGate()
  Define cfg.NeonVkLifecycleConfig
  Protected want.i
  cfg\physicalDevice = 1 : cfg\device = 2 : cfg\queue = 3 : cfg\commandPool = 4
  cfg\renderPass = 5 : cfg\framebuffer = 6 : cfg\width = 64 : cfg\height = 64 : cfg\maxQuads = 4096
  If NeonVkLifecycleConfigure(@cfg) <> #NEON_OK : ProcedureReturn 1 : EndIf
  fakeCreateRc = 7
  If NeonInit() <> #NEON_ERR_BACKEND Or Neon_Ready() <> 0 Or fakeCreateCount <> 1 Or fakeDestroyCount <> 0 Or NeonDrawBackendActive() <> 0 : ProcedureReturn 2 : EndIf
  If NeonLifecycleCleanupPending() <> 1 : ProcedureReturn 21 : EndIf
  fakeDestroyRc = 7
  If NeonShutdown() <> #NEON_ERR_BACKEND Or fakeDestroyCount <> 0 Or NeonVkLifecycleConfigured() <> 1 : ProcedureReturn 22 : EndIf
  If NeonLifecycleUseNative() <> #NEON_ERR_BACKEND Or NeonLifecycleCleanupPending() <> 1 : ProcedureReturn 23 : EndIf
  fakeDestroyRc = 0
  If NeonShutdown() <> #NEON_OK Or fakeDestroyCount <> 1 Or NeonLifecycleCleanupPending() <> 0 : ProcedureReturn 24 : EndIf
  If NeonVkLifecycleConfigure(@cfg) <> #NEON_OK : ProcedureReturn 25 : EndIf
  fakeCreateRc = 0
  If NeonInit() <> #NEON_OK Or Neon_Ready() = 0 Or NeonDrawBackendActive() = 0 : ProcedureReturn 3 : EndIf
  want = (Neon_R($A10203A4) << 0)
  If NeonFrameBegin($A10203A4) <> #NEON_OK Or fakeBeginCount <> 1 : ProcedureReturn 4 : EndIf
  If fakeClear0 <> GraphicsF32ByteBits(Neon_R($A10203A4)) : ProcedureReturn 51 : EndIf
  If fakeClear1 <> GraphicsF32ByteBits(Neon_G($A10203A4)) : ProcedureReturn 52 : EndIf
  If fakeClear2 <> GraphicsF32ByteBits(Neon_B($A10203A4)) : ProcedureReturn 53 : EndIf
  If fakeClear3 <> GraphicsF32ByteBits(Neon_A($A10203A4)) : ProcedureReturn 54 : EndIf
  If NeonFrameEnd() <> #NEON_OK Or fakeEndCount <> 1 : ProcedureReturn 6 : EndIf
  fakeDestroyRc = 7
  If NeonShutdown() <> #NEON_ERR_BACKEND Or Neon_Ready() = 0 Or NeonDrawBackendActive() = 0 Or NeonVkLifecycleConfigured() <> 1 : ProcedureReturn 71 : EndIf
  fakeDestroyRc = 0
  If NeonShutdown() <> #NEON_OK Or Neon_Ready() <> 0 Or NeonDrawBackendActive() <> 0 Or NeonVkLifecycleConfigured() <> 0 : ProcedureReturn 7 : EndIf
  If NeonLifecycleUseNative() <> #NEON_OK : ProcedureReturn 8 : EndIf
  If binderNativeCalls <> 0 : ProcedureReturn 9 : EndIf
  ProcedureReturn 0
EndProcedure
