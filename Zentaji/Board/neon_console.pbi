EnableFloatingPoint
XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Anvil/Graphics/neon_frontend.pbi"
XIncludeFile "Anvil/Graphics/neon_lifecycle_absent.pbi"
XIncludeFile "Anvil/Graphics/neon_colour.pbi"
XIncludeFile "Anvil/Graphics/neon_atlas_raster.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_backend.pbi"
#ANVIL_VULKAN_BACKEND=3
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"
XIncludeFile "Zentaji/Lib/Vulkan/vk_zentaji_present.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_lifecycle.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_font_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_sprite_port.pbi"
; Existing immutable data asset only; no Pi 4 hardware module is included.
XIncludeFile "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"

XIncludeFile "Zentaji/Board/neon_surface.pbi"
XIncludeFile "Zentaji/Board/neon_resize.pbi"
XIncludeFile "Anvil/Graphics/anvil_logo.pbi"
XIncludeFile "Anvil/Core/build_identity.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_banner.pbi"
XIncludeFile "Anvil/Core/font_cmd.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_resident_state.pbi"

Global zngUp.i,zngFault.i,zngLineHeight.i,zngSuspended.i
Global zngFont.NeonVkPortFontRef
#ZNG_CONSOLE_TOP=128
Global zngBanner.NeonVkBannerArgs
Global zngPresented.i,zngPainting.i,zngCursorRow.i=-1,zngCursorPen.i
Global zngClockSecond.i=-2,zngClockDirty.i
Global Dim zngClockText.a[128]
Global Dim zngClear.l[4]
Global Dim zngAtlas.a[#NEON_ATLAS_MAXBYTES]
Global Dim zngUV.a[4096]
Global Dim zngBitmap.a[95*16]
Global Dim zngRow.a[514]
Global Dim zngRun.a[514]
Global Dim zngPrefix.a[514]
Global Dim zngPair.a[3]

; The shared grid wraps with the same pair positioning used by Neon text.
; No separate terminal model or rasterizer lives in this board adapter.
Procedure.i ScreenProportionalAdvance(previous.i,current.i)
 Protected single.i,total.i
 If current<32 Or current>126 : ProcedureReturn 0 : EndIf
 zngPair[0]=current : zngPair[1]=0
 single=NeonVkChromeMeasureWidthControls(zngFont\face,@zngPair[0],0,1)
 If previous<32 Or previous>126 : ProcedureReturn single : EndIf
 zngPair[0]=previous
 total=NeonVkChromeMeasureWidthControls(zngFont\face,@zngPair[0],0,1)
 zngPair[1]=current : zngPair[2]=0
 ProcedureReturn NeonVkChromeMeasureWidthControls(zngFont\face,@zngPair[0],0,1)-total
EndProcedure
XIncludeFile "Anvil/Core/console_grid.pbi"
Global Dim zngRows.a[#CON_MAXROWS]

Procedure.i zngRunX(row.i,col.i)
 Protected i.i,whole.i,first.i
 For i=0 To col : zngPrefix[i]=ConGridCell(row,i) : Next
 zngPrefix[col+1]=0
 whole=NeonVkChromeMeasureWidthControls(zngFont\face,@zngPrefix[0],0,1)
 zngPair[0]=ConGridCell(row,col) : zngPair[1]=0
 first=NeonVkChromeMeasureWidthControls(zngFont\face,@zngPair[0],0,1)
 ProcedureReturn whole-first
EndProcedure
; The caption owner guarantees at most127 bytes. Keep a stable copy through
; preparation/submission: nested idle services must not change warmed text.
; A second transition asks the shared pump for work without marking text rows.
Procedure.i zngClockPoll()
 Protected seconds.i,*text,i.i,changed.i,length.i
 If zngPainting<>0 : ProcedureReturn 1 : EndIf
 seconds=WallClockNow()
 If seconds=zngClockSecond : ProcedureReturn 1 : EndIf
 *text=WallClockCaption()
 While length<128 And PeekA(*text+length)<>0 : length=length+1 : Wend
 If length>=128 : ProcedureReturn 0 : EndIf
 For i=0 To length
  If zngClockText[i]<>PeekA(*text+i) : changed=1 : EndIf
 Next
 For i=0 To length : zngClockText[i]=PeekA(*text+i) : Next
 zngClockSecond=seconds
 If changed<>0 : zngClockDirty=1 : gConDirty=1 : EndIf
 ProcedureReturn 1
EndProcedure
; Use Anvil's existing banner composition and immutable logo, not an app UI.
; Warm all title/caption glyphs while idle; drawing inside a frame never rasterizes.
Procedure.i zngBannerPrepare()
 zngBanner\width=znsWidth : zngBanner\height=znsHeight
 zngBanner\logoWidth=#ANVIL_PIC_W : zngBanner\logoHeight=#ANVIL_PIC_H
 zngBanner\platformText="bare-metal monitor   -   Zentaji   -   Zentaji64"
 zngBanner\buildText=AnvilBuildLabel(#ANVIL_BUILD,#ANVIL_BUILD_DATE,#ANVIL_BUILD_TIME)
 zngBanner\clockText=@zngClockText[0] : zngBanner\glintActive=0
 If NeonVkChromeFontHeightSet(#NEON_FONT_BOLD,48)<>0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeFontHeightSet(#NEON_FONT_SMALL,16)<>0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeWarmTrueTypeText(48,"PureMetal Forge")<0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeWarmTrueTypeText(16,zngBanner\platformText)<0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeWarmTrueTypeText(16,zngBanner\buildText)<0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeWarmTrueTypeText(16,zngBanner\clockText)<0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeWarmTrueTypeText(16,"A N V I L")<0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; The first frame clears the attachment and draws the shared header. Later
; transactions LOAD that completed attachment, clear/repaint only dirty rows,
; and retain every other pixel. Cursor movement restores both its old and new
; rows so deleting text or moving over ink cannot leave a trail. The bundled
;16-pixel face fits the measured line box; each dirty row is restored in full.
; This is the same public Chrome transaction layer used by the Pi4 monitor.
Procedure zngPaint()
 Protected row.i,col.i,count.i,style.i,x.f,y.f,r.f,g.f,b.f,cursor.i,pen.i
 Protected full.i,moved.i,rows.i,py.i,clock.i
 If zngUp=0 Or zngSuspended<>0 Or zngFault<>0 Or zngPainting<>0 : ProcedureReturn : EndIf
 If zngClockPoll()<>1 : zngFault=10 : ProcedureReturn : EndIf
 zngPainting=1
 cursor=ConGridCurR()-ConViewTop() : pen=gConCurPen
 full=Bool(zngPresented=0 Or ConGridFullClear()<>0)
 moved=Bool(cursor<>zngCursorRow Or pen<>zngCursorPen)
 clock=zngClockDirty
 ; Warm every changed run before either frame transaction begins.
 For row=0 To ConGridRows()-1
  zngRows[row]=Bool(full<>0 Or ConGridRowDirty(row)<>0 Or (moved<>0 And (row=cursor Or row=zngCursorRow)))
  If zngRows[row]<>0
   rows=rows+1 : ConGridRowText(row,@zngRow[0])
   If NeonVkPortFontWarm(@zngFont,@zngRow[0])<>0 : zngFault=1 : zngPainting=0 : ProcedureReturn : EndIf
  EndIf
 Next
 If full<>0
  If zngBannerPrepare()<>1 : zngFault=8 : zngPainting=0 : ProcedureReturn : EndIf
 ElseIf clock<>0
  If NeonVkChromeFontHeightSet(#NEON_FONT_SMALL,16)<>0 : zngFault=8 : zngPainting=0 : ProcedureReturn : EndIf
  If NeonVkChromeWarmTrueTypeText(16,@zngClockText[0])<0 : zngFault=8 : zngPainting=0 : ProcedureReturn : EndIf
 EndIf
 If full=0 And rows=0 And clock=0 : ConGridClearDirty() : zngPainting=0 : ProcedureReturn : EndIf
 If full<>0
  If NeonVkChromeBegin(@zngClear[0])<>0 : zngFault=2 : zngPainting=0 : ProcedureReturn : EndIf
  If NeonVkBannerRender(@zngBanner)<>0 : zngFault=9 : zngPainting=0 : ProcedureReturn : EndIf
 Else
  If NeonVkChromeBeginLoad()<>0 : zngFault=2 : zngPainting=0 : ProcedureReturn : EndIf
  If clock<>0
   If NeonVkBannerClockRender(@zngBanner,1)<>0 : zngFault=9 : zngPainting=0 : ProcedureReturn : EndIf
  EndIf
 EndIf
 For row=0 To ConGridRows()-1
  If zngRows[row]<>0
   py=#ZNG_CONSOLE_TOP+row*zngLineHeight
   If full=0
    If NeonVkChromeBox(0,py,znsWidth,zngLineHeight,Neon_RGB(6,9,14))<>0 : zngFault=4 : zngPainting=0 : ProcedureReturn : EndIf
   EndIf
   col=0
   While col<ConGridCols()
    style=ConGridCellStyle(row,col) : count=ConGridStyleRunText(row,col,@zngRun[0])
    If count<1 : zngFault=3 : zngPainting=0 : ProcedureReturn : EndIf
    If zngRun[0]<>0
     x=8.0+MathFFromInt(zngRunX(row,col))/65536.0 : y=MathFFromInt(py)
     r=0.85 : g=0.87 : b=0.91
     If style=#UART_SCREEN_STYLE_PROMPT : r=0.35 : g=0.85 : b=0.95 : EndIf
     If NeonVkPortFontText(@zngFont,x,y,@zngRun[0],r,g,b,1.0,1,1)<>0 : zngFault=4 : zngPainting=0 : ProcedureReturn : EndIf
    EndIf
    col=col+count
   Wend
  EndIf
 Next
 If cursor>=0 And cursor<ConGridRows()
  x=8.0+MathFFromInt(pen)/65536.0 : y=MathFFromInt(#ZNG_CONSOLE_TOP+(cursor+1)*zngLineHeight-2)
  If NeonVkPortBox(x,y,2.0,1.0,0.35,0.85,0.95,1.0,1,1)<>0 : zngFault=5 : zngPainting=0 : ProcedureReturn : EndIf
 EndIf
 If NeonVkChromeEnd()<>0 : zngFault=6 : zngPainting=0 : ProcedureReturn : EndIf
 If ZentajiNeonSurfacePresent()<>1 : zngFault=7 : zngPainting=0 : ProcedureReturn : EndIf
 zngPresented=1 : zngCursorRow=cursor : zngCursorPen=pen : zngClockDirty=0
 ConGridClearDirty() ; native monitor frame checkpoint
 zngPainting=0
EndProcedure
Procedure.i ZentajiNeonConsoleStart()
 Protected cols.i,rows.i
 If zngUp<>0 Or zenMemoryGraphicsBase=0 : ProcedureReturn 0 : EndIf
 neon_texSrc=@zngAtlas[0] : neon_glyphUV=@zngUV[0]
 If NeonBitmapFontBind(@zngBitmap[0],8,16,32,126)<>1 : ProcedureReturn 0 : EndIf
 NeonFontDefaults()
 zngClear[0]=GraphicsF32ByteBits(6) : zngClear[1]=GraphicsF32ByteBits(9)
 zngClear[2]=GraphicsF32ByteBits(14) : zngClear[3]=GraphicsF32ByteBits(255)
 If AnvilTrueTypeSlotLoad(#ANVIL_TTS_BOOT_SLOT,?anvilBootTtf,#ANVIL_BOOT_TTF_BYTES)<>1 : ProcedureReturn 0 : EndIf
 If AnvilTrueTypeSlotSelect(#ANVIL_TTS_BOOT_SLOT)<>1 : ProcedureReturn 0 : EndIf
 If NeonVkPortFontBind(@zngFont,#ANVIL_TTS_BOOT_SLOT,#NEON_FONT_UI,16)<>0 : ProcedureReturn 0 : EndIf
 If NeonVkChromeLogoSource(?anvilPix,#ANVIL_PIC_W,#ANVIL_PIC_H)<>0 : ProcedureReturn 0 : EndIf
 If ZentajiNeonSurfaceStartCapacities(#NEON_VK_CHROME_MAX_QUADS,#CON_CELLS+1)<>1 : ProcedureReturn 0 : EndIf
 zngLineHeight=NeonVkPortFontLineHeight(@zngFont)
 If zngLineHeight<1 : ProcedureReturn 0 : EndIf
 cols=(znsWidth-16)/4 : rows=(znsHeight-#ZNG_CONSOLE_TOP-8)/zngLineHeight
 If cols<1 Or rows<1 : ProcedureReturn 0 : EndIf
 If cols>#CON_MAXCOLS : cols=#CON_MAXCOLS : EndIf
 If rows>#CON_MAXROWS : rows=#CON_MAXROWS : EndIf
 ConGridInit(cols,rows) : ConGridProportionalSet(znsWidth-16,1)
 ConSetRenderer(@zngPaint) : UartMirrorSetDrain(@ConMirrorDrain) : UartMirror(1)
 zngUp=1 : ProcedureReturn 1
EndProcedure
Procedure.i ZentajiNeonConsolePump()
 Protected resized.i,cols.i,rows.i
 If zngUp=0 Or zngSuspended<>0 : ProcedureReturn 1 : EndIf
 If zngPainting<>0 : ProcedureReturn 1 : EndIf
 resized=ZentajiNeonSurfaceResize()
 If resized=0 : zngFault=11 : ProcedureReturn 0 : EndIf
 If resized=2
  cols=(znsWidth-16)/4 : rows=(znsHeight-#ZNG_CONSOLE_TOP-8)/zngLineHeight
  ConGridResize(cols,rows) : gConPixelWidth=znsWidth-16
  zngPresented=0 : zngCursorRow=-1 : zngClockDirty=1
  ConGridMarkAll()
 EndIf
 If zngClockPoll()<>1 : zngFault=10 : ProcedureReturn 0 : EndIf
 ScreenPump()
 ProcedureReturn Bool(zngFault=0 And znsState=2)
EndProcedure

; Retain CPU-side Vulkan objects in protected monitor RAM while giving the
; native queue/display and the retired channel back to a supervisor payload.
Procedure.i zngDmaDown()
 Protected n.i
 If avkZenDma\state<>1 Or ZentajiDmaOwned(@avkZenDma)<>1 : ProcedureReturn 0 : EndIf
 For n=0 To $20 Step 8 : PokeQ(#ZEN_DMA_CHANNEL+n,0) : Next
 avkZenDma\state=0 : zenDmaTransferOwner=0
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiNeonConsoleSuspend()
 If zngUp=0 : ProcedureReturn 1 : EndIf
 If zngSuspended<>0 Or nvcInFrame<>0 Or NeonVkChromePresentPending()<>0 : ProcedureReturn 0 : EndIf
 ; Service applications borrow this resident owner. Ordinary supervisor
 ; payloads receive released hardware, as before; they may own another driver.
 If GraphicsServiceState()=1
  If ZentajiGraphicsDisplayOwned()<>1 Or ZentajiDmaOwned(@avkZenDma)<>1 : ProcedureReturn 0 : EndIf
  zngPresented=0 : ConNoRenderer() : zngSuspended=2 : ProcedureReturn 1
 EndIf
 If vkDeviceWaitIdle(znsDev)<>0 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayRelease()<>1 : ProcedureReturn 0 : EndIf
 If zngDmaDown()<>1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsRelease(@avkZenQueue)<>1 : ProcedureReturn 0 : EndIf
 zngPresented=0 : ConNoRenderer() : zngSuspended=1 : ProcedureReturn 1
EndProcedure
Procedure.i ZentajiNeonConsoleResume()
 If zngUp=0 : ProcedureReturn 1 : EndIf
 If zngSuspended=2
  ; Shared PmfEnter also calls Leave, idempotently, after HwPayloadRun. Retire
  ; it here before the console can submit work or reuse a payload font cache.
  If GraphicsServiceLeave()<>0 : ProcedureReturn 0 : EndIf
  If ZentajiGraphicsDisplayOwned()<>1 Or znsState<>2 : ProcedureReturn 0 : EndIf
  zngSuspended=0 : ConSetRenderer(@zngPaint) : ConGridMarkAll()
  ProcedureReturn ZentajiNeonConsolePump()
 EndIf
 If zngSuspended<>1 Or PeekQ(#ZEN_GFX_DISPLAY+$50)<>znsWidth Or PeekQ(#ZEN_GFX_DISPLAY+$58)<>znsHeight : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsBind(@avkZenQueue,15,zenMemoryGraphicsBase,4096,zenMemoryGraphicsBase,2048,zenMemoryGraphicsBase+2048)<>1 : ProcedureReturn 0 : EndIf
 If ZentajiDmaBind(@avkZenDma,zenMemoryGraphicsBase,2048)<>1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsDisplayManagedStart(zgdBase)<>1 : ProcedureReturn 0 : EndIf
 zngSuspended=0 : ConSetRenderer(@zngPaint) : ConGridMarkAll()
 ProcedureReturn ZentajiNeonConsolePump()
EndProcedure
Procedure.i ZentajiNeonConsoleService(operation.i)
 If operation=#APS_SCREEN
  If ZentajiNeonConsolePump()<>1 : ZentajiPayloadRecoveryFailed($5C01,"Console graphics failed (0x5C01): display ownership or presentation was lost.") : EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiNeonConsoleBind()
 If zngUp<>1 Or AnvilPromptServicesPresent()<>0 : ProcedureReturn 0 : EndIf
 If AnvilPromptServicesBind(@ZentajiNeonConsoleService)<>1 : ProcedureReturn 0 : EndIf
 If GraphicsServiceBind(@VulkanNeonServiceDispatch,@VulkanNeonServiceReset)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn ZentajiPayloadGraphicsBind(@ZentajiNeonConsoleSuspend,@ZentajiNeonConsoleResume)
EndProcedure

; Hardware hooks for the existing shared resident Neon application service.
; The shared particle path prepares Q8 corners on the CPU and draws a sampled
; palette through Vulkan. It does not require the optional compute provider.
Procedure.i AvsSurfaceFlags()
 ProcedureReturn #NEON_SERVICE_VULKAN | #NEON_SERVICE_FONT_REFS | #NEON_SERVICE_SPRITES | #NEON_SERVICE_FONT_BYTES | #NEON_SERVICE_PARTICLES | #NEON_SERVICE_MAPPING | #NEON_SERVICE_FONT_SPACING | #NEON_SERVICE_FONT_SNAP | #NEON_SERVICE_FONT_CONTROLS | #NEON_SERVICE_FONT_DERIVE | #NEON_SERVICE_TARGETS | #NEON_SERVICE_TARGET_CONTINUATION | #NEON_SERVICE_TARGET_LOAD | #NEON_SERVICE_TARGET_RETRO | #NEON_SERVICE_FONT_CARETS | #NEON_SERVICE_ROLE_CARETS
EndProcedure
Procedure.i AvsSurfacePresentError() : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndProcedure
Procedure.i AvsSurfaceRetireReady()
 If ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsOwned(@avkZenQueue)<>1 Or avkZenQueue\state<>1 : ProcedureReturn 0 : EndIf
 If ZentajiDmaOwned(@avkZenDma)<>1 Or avkZenDma\state<>1 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i AvsSurfaceStart()
 If zngUp<>1 Or zngSuspended<>2 Or znsState<>2 Or ZentajiGraphicsDisplayOwned()<>1 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
 avsLogicalW=znsWidth : avsLogicalH=znsHeight
 ProcedureReturn 0
EndProcedure
Procedure.i AvsSurfaceStop()
 zngPresented=0
 ProcedureReturn ZentajiNeonSurfaceChromeReset()
EndProcedure
Procedure.i AvsSurfacePresent()
 Protected started.i
 started=Ticks()
 If ZentajiNeonSurfacePresent()<>1 : ProcedureReturn #NEON_SERVICE_ERR_PROVIDER : EndIf
 avsCopyDmaTicks=0 : avsCopyCleanTicks=0 : avsCopyPublishTicks=Ticks()-started
 ProcedureReturn 0
EndProcedure
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_resident_service.pbi"
Procedure.i ZentajiNeonConsoleStop()
 If zngUp=0 : ProcedureReturn 1 : EndIf
 If zngSuspended<>0 : ProcedureReturn 0 : EndIf
 If ZentajiNeonSurfaceStop()<>1 : ProcedureReturn 0 : EndIf
 If zngDmaDown()<>1 Or ZentajiGraphicsRelease(@avkZenQueue)<>1 : ProcedureReturn 0 : EndIf
 ConNoRenderer() : UartMirrorSetDrain(0) : UartMirror(0)
 AnvilPromptServicesBind(0) : ZentajiPayloadGraphicsBind(0,0)
 ConGridStop() : zngUp=0 : ProcedureReturn 1
EndProcedure
