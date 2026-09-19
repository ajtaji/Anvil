; vulkanTriangleProof.pi4 - one triangle, from SPIR-V, drawn by V3D.
;
; DIAGNOSTIC. IT DOES NOT SHIP. It is an instrument, not a how-to.
;
;   PureMetalForge.exe --compile \
;       RaspberryPi4/Examples/Diagnostics/vulkanTriangleProof.pi4 -t pi4 \
;       --load-addr 0x500000 --stack-addr 0x4F00000 --entry-returns \
;       -o vulkanTriangleProof.img
;
; ======================================================================
;  WHAT IT PROVES, ON THE SILICON
; ======================================================================
;  vulkanClearProof.pi4 proved that V3D executes a Vulkan colour clear.
;  It proved no shader and no draw, and said so. This proves both.
;
;  Through Anvil's PUBLIC vk* entry points, and nothing private:
;
;    vkCreateInstance, vkEnumeratePhysicalDevices, vkCreateDevice,
;    vkGetDeviceQueue, vkCreateImage, vkGetImageMemoryRequirements,
;    vkAllocateMemory, vkBindImageMemory, vkCreateImageView,
;    vkCreateRenderPass, vkCreateFramebuffer, vkCreateBuffer,
;    vkGetBufferMemoryRequirements, vkBindBufferMemory,
;    vkCreateShaderModule, vkCreatePipelineLayout,
;    vkCreateGraphicsPipelines, vkCreateCommandPool,
;    vkAllocateCommandBuffers, vkBeginCommandBuffer,
;    vkCmdBeginRenderPass, vkCmdBindPipeline, vkCmdBindVertexBuffers,
;    vkCmdPushConstants, vkCmdDraw, vkCmdEndRenderPass,
;    vkEndCommandBuffer, vkCreateFence, vkQueueSubmit, vkWaitForFences,
;    vkDeviceWaitIdle and the ordered teardown.
;  The live physical device's exact linear and optimal format-feature words
;  are checked before image creation, and both allocations are populated through
;  vkMapMemory/vkUnmapMemory. Correct GPU pixels after those unflushed host
;  writes are the silicon proof behind this backend's HOST_COHERENT claim.
;
;  FOUR SPIR-V MODULES ARE ASSEMBLED WORD BY WORD, from the Khronos
;  specification's own opcode numbers, in
;  Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi. Nothing generates them and
;  no tool is needed to read them. They live in their own file so that
;  tools/vulkan_pipeline_check.py can walk THE SAME FOUR at a desk and
;  compare every word against modules its own assembler builds: the bench
;  is a bad place to discover that one of those words was wrong.
;
;  TWO PASSES, TWO VERDICTS, because they are two different questions:
;
;    slot 1  - THE UNIFORM-COLOUR TRIANGLE. A position-only vertex shader
;              and a fragment shader that writes the push-constant colour.
;              Its fragment program is the shape this tree's engine
;              already runs on every rectangle it draws; the new things
;              in it are the viewport transform in the coordinate shader
;              and the fact that a SPIR-V module chose the shape.
;    slot 4  - THE PER-VERTEX-COLOUR TRIANGLE. The same geometry with a
;              four-component colour attribute carried through the VPM as
;              a varying and read back with LDVARY. ALL THREE VERTICES
;              CARRY THE SAME COLOUR, on purpose: that makes the expected
;              pixel exact whatever the interpolator's precision is, so
;              this verdict is about the varying PATH and not about
;              interpolation. A gradient is a later run and is owed.
;
;  SIX PIXELS PER PASS. Three points inside the triangle must hold the
;  triangle's colour and three outside it must still hold the render
;  pass's clear colour. A pass that cleared and drew nothing fails the
;  first three; a pass that painted the whole screen fails the last three.
;
;  THE GUARD. The engine is bound to a surface at #VTP_SURFACE and the
;  Vulkan window is the memory ABOVE it. The surface half is filled with
;  its own pattern and must be BYTE-FOR-BYTE UNCHANGED afterwards.
;
;  THE EXPECTED BYTES. VK_FORMAT_B8G8R8A8_UNORM stores B, G, R, A in
;  ascending byte order, so a 32-bit word read on this little-endian part
;  is (A<<24)|(R<<16)|(G<<8)|B.
;      clear     R 0.2 G 0.5 B 0.7 A 1.0   ->  $FF3380B2
;      uniform   R 1.0 G 0.0 B 0.0 A 1.0   ->  $FFFF0000
;      varying   R 0.0 G 1.0 B 0.0 A 1.0   ->  $FF00FF00
;  EVERY COMPONENT IS EXACTLY ZERO OR ONE in the two triangle colours.
;  That is deliberate: the fragment shader packs two binary32 lanes into
;  one 2 x f16 result and the tile buffer converts to 8-bit UNORM, and a
;  component of 0.5 would put the answer on a rounding boundary and turn
;  a colour-path proof into an argument about rounding.
;
;  THERE IS NO PROCESSOR-SIDE FALLBACK ANYWHERE UNDER THIS. If V3D does
;  not rasterise the triangle, the readback fails.
;
; ======================================================================
;  WHAT THE OPERATOR SHOULD SEE
; ======================================================================
;  A solid GREEN triangle, apex up, on a blue-grey ground, held for six
;  seconds. The Vulkan target and its deliberately odd 799 x 1279 viewport
;  put the apex at
;  (399.5, 319.75) and the base from (199.75, 959.25) to
;  (599.25, 959.25). Its half-pixel centres are also verified directly in
;  the submitted BCL; a correct-looking picture alone is not that proof.
;
;  The green is PASS TWO. Pass one's red triangle is drawn into the same
;  image and then overwritten by pass two's clear, so it is never on the
;  glass and lives only in report slots 17 to 22. An operator who sees
;  red has watched a run where pass two did not happen, and slot 4 says
;  which step stopped it.
;
; ======================================================================
;  BEFORE RUNNING IT
; ======================================================================
;  * TAKE THE ACCELERATED CONSOLE OFF V3D FIRST: `screen dma`. This
;    payload initialises the graphics engine itself and uses the SAME
;    16 MiB arena at $0A000000 that the V3D console vets and owns; two
;    owners of one V3D page table is not a thing that can be made to
;    work.
;  * THE BUFFERS ARE IN THE PAYLOAD WINDOW at $06000000: one screen of
;    guard and one screen plus 128 KiB of Vulkan window, 8,323,072 bytes
;    ending at $067EF000, which is the same band vulkanClearProof.pi4
;    already used.
;  * IT DOES NOT RE-INITIALISE THE DISPLAY and asks the firmware for
;    nothing. It adopts the scanout buffer for the length of one copy.
;  * IT CALLS NeonShutdown() BEFORE RETURNING, which hands the V3D MMU
;    back.
;  * RECOVERY: the console repaints over the presented picture by itself;
;    `screen on` forces it and `screen v3d` brings the accelerated
;    console back. Neither needs a reset. Nothing here writes a core spin
;    slot, releases a core, or touches the monitor, its variables, the
;    DSI control registers, the GENET ring or the driver-module region.
;
; ======================================================================
;  THE REPORT, AND HOW TO READ IT
; ======================================================================
;  x0 comes back as the address of SIXTY-FOUR 32-BIT WORDS - 256 bytes.
;  ONE SLOT IS ONE WORD, so the slot number below is the word number in
;  the dump. Read it with
;
;      md.l <x0> 100
;
;  and NOT with a bare `md`: the dump's count is in BYTES whichever width
;  is chosen, so 100 hex is 256 bytes is 64 words, and a bare `md` groups
;  by one byte. $100 is written in hex because every argument of that
;  command is.
;
;  Slot 0 is $564B5452 ("VKTR") and slot 63 is $52544B56, the same four
;  letters backwards. A dump that does not show BOTH did not show the
;  whole report, and the verdicts near the end of it were not read.
;
;    0  magic $564B5452          32 layout after pass one
;    1  UNIFORM-COLOUR VERDICT   33 bin OOM count
;    2  failure detail, or BCL start on success
;    3  failure detail 2, or BCL bytes on success
;                                34 bin error status
;                                35 render error status
;    4  PER-VERTEX VERDICT       36 MMU fault count
;    5  surface (guard) base     37 MMU violation address
;    6  Vulkan window base       38 guard sum before
;    7  Vulkan window bytes      39 guard sum after
;    8  image address            40 submit result, pass one
;    9  image size               41 wait result, pass one
;   10  image row pitch          42 submit result, pass two
;   11  vertex buffer address    43 wait result, pass two
;   12  pipeline A code base     44 backend native error
;   13  pipeline B code base     45 validation fault count
;   14  expected clear word      46 validation fault text
;   15  expected red word        47 PRESENT VERDICT
;   16  expected green word      48 DisplayLastError()
;   17  pass 1, inside  (400,500)   49 engine arena needed
;   18  pass 1, inside  (400,700)   50 backend can draw
;   19  pass 1, inside  (400,900)   51 backend name
;   20  pass 1, outside (100,100)   52 image layout after
;   21  pass 1, outside (700,1200)  53 microseconds, submit 1
;   22  pass 1, outside (400,200)   54 microseconds, submit 2
;   23  pass 2, inside  (400,500)   55 draws the backend ran
;   24  pass 2, inside  (400,700)   56 last shader record address
;   25  pass 2, inside  (400,900)   57 command buffer failure text
;   26  pass 2, outside (100,100)   58 shutdown reached
;   27  pass 2, outside (700,1200)  59 emitter step, if it refused
;   28  pass 2, outside (400,200)   60 encoder code, if it refused
;   29  bin jobs before             61 HIGHEST STEP REACHED (1..10)
;   30  bin jobs after              62 report length in bytes (256)
;   31  render jobs before          63 tail magic $52544B56
;
;  SLOT 61 IS THE ONE TO READ FIRST when anything is wrong. It is the
;  number of the step that was running, 1 to 10, and 10 means the whole
;  payload ran including the present. It exists because the first board
;  run of this diagnostic left a reader asking whether step eight had
;  been reached, and nothing in the report could answer.

XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/timer.pi4"
XIncludeFile "RaspberryPi4/Lib/safety.pi4"
XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"
CompilerIf #VTP_LIST_PROOF
  #DSP_DMA_LINKED = 1
  XIncludeFile "RaspberryPi4/Lib/dma.pi4"
CompilerElse
  #DSP_DMA_LINKED = 0
CompilerEndIf
XIncludeFile "RaspberryPi4/Lib/display.pi4"
XIncludeFile "RaspberryPi4/Lib/v3dqpu.pi4"
XIncludeFile "RaspberryPi4/Lib/v3d.pi4"
XIncludeFile "RaspberryPi4/Lib/neon.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_shader.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"

CompilerIf #VTP_LIST_PROOF
  #VTP_MAGIC = $564B444C               ; "VKDL", slot 0
  #VTP_TAIL_MAGIC = $4C444B56          ; "VKDL" reversed, slot 63
CompilerElse
  #VTP_MAGIC = $564B5452               ; "VKTR", slot 0
  #VTP_TAIL_MAGIC = $52544B56          ; "VKTR" reversed, slot 63
CompilerEndIf

#VTP_ARENA = $0A000000
#VTP_ARENA_BYTES = $01000000

#VTP_SURFACE = $06000000
#VTP_PANEL_W = 800
#VTP_PANEL_H = 1280
#VTP_VIEW_W = 799
#VTP_VIEW_H = 1279
#VTP_PANEL_PITCH = 3200
#VTP_SCREEN_BYTES = 4096000
#VTP_WIN_BASE = $063E8000              ; $06000000 + 4,096,000
#VTP_WIN_BYTES = 4227072               ; one screen plus 128 KiB
#VTP_MAP_SPAN = 8323072
#VTP_DSI_SCAN = $08A00000

#VTP_GUARD = $5A3C0FF0

; The clear and the two triangle colours, as binary32 bit patterns in
; R, G, B, A order, and the packed words they must become.
#VTP_F_ZERO = $00000000
#VTP_F_ONE = $3F800000
CompilerIf #VTP_LIST_PROOF
  #VTP_CLEAR_R = $3E4CCCCD
  #VTP_CLEAR_G = $3F000000
  #VTP_CLEAR_B = $3F333333
  #VTP_CLEAR_A = $3F800000
  #VTP_CLEAR_WORD = $FF3380B2
  #VTP_RED_WORD = $FFFF0000
  #VTP_GREEN_WORD = $FF00FF00
  #VTP_SOURCE_ALPHA = $3F000000
CompilerElseIf #VTP_BLEND_PROOF
  ; Source-over acceptance scene: half-alpha red/green over opaque blue.
  ; V3D quantizes the source factor to 128/255 and its exact complement to
  ; 127/255. The source channel is therefore 128 while surviving blue is 127.
  #VTP_CLEAR_R = $00000000
  #VTP_CLEAR_G = $00000000
  #VTP_CLEAR_B = $3F800000
  #VTP_CLEAR_A = $3F800000
  #VTP_CLEAR_WORD = $FF0000FF
  #VTP_RED_WORD = $BF80007F
  #VTP_GREEN_WORD = $BF00807F
  #VTP_SOURCE_ALPHA = $3F000000
CompilerElse
  #VTP_CLEAR_R = $3E4CCCCD               ; 0.2 -> 51
  #VTP_CLEAR_G = $3F000000               ; 0.5 -> 128
  #VTP_CLEAR_B = $3F333333               ; 0.7 -> 178
  #VTP_CLEAR_A = $3F800000               ; 1.0 -> 255
  #VTP_CLEAR_WORD = $FF3380B2
  #VTP_RED_WORD = $FFFF0000
  #VTP_GREEN_WORD = $FF00FF00
  #VTP_SOURCE_ALPHA = $3F800000
CompilerEndIf

CompilerIf #VTP_LIST_PROOF
  #VTP_LIST_DRAWS = 6
  #VTP_LIST_VERTICES = 36
  ; V3D's UNORM blend factors are the quantized source alpha byte and its
  ; exact complement: 128/255 and 127/255. Therefore half-blue over opaque
  ; green is B=128/G=127, not two independently rounded 128s. Repeating with
  ; half-red gives R=128/G=63/B=64. These are the attachment words observed
  ; before presentation; the display copy makes its destination alpha opaque.
  #VTP_LIST_BLUE_OVER_GREEN = $BF007F80
  #VTP_LIST_RED_OVER_BLUE_GREEN = $9F803F40
  #VTP_LIST_MAGENTA = $FFFF00FF
  #VTP_LIST_WHITE = $FFFFFFFF
  #VTP_LIST_P_OUT = (50 << 16) | 50
  #VTP_LIST_P_RED = (150 << 16) | 1000
  #VTP_LIST_P_GREEN = (650 << 16) | 1000
  #VTP_LIST_P_ORDER = (350 << 16) | 1050
  #VTP_LIST_P_BLEND1 = (550 << 16) | 800
  #VTP_LIST_P_BLEND2 = (320 << 16) | 700
  #VTP_LIST_P_VARY = (400 << 16) | 250
  #VTP_LIST_P_TOP = (400 << 16) | 640
CompilerEndIf

; The triangle, in clip space. +Y is DOWN, which is Vulkan's framebuffer
; orientation and the V3D rasteriser's.
#VTP_X0 = $00000000                    ;  0.0
#VTP_Y0 = $BF000000                    ; -0.5
#VTP_X1 = $BF000000                    ; -0.5
#VTP_Y1 = $3F000000                    ;  0.5
#VTP_X2 = $3F000000                    ;  0.5
#VTP_Y2 = $3F000000                    ;  0.5
#VTP_STRIDE = 24                       ; vec2 position + vec4 colour

; The six sample points. The odd viewport makes the triangle's apex
; (399.5, 319.75) and its base run from (199.75, 959.25) to
; (599.25, 959.25); every point below remains comfortably clear of an edge.
#VTP_IN0X = 400
#VTP_IN0Y = 500
#VTP_IN1X = 400
#VTP_IN1Y = 700
#VTP_IN2X = 400
#VTP_IN2Y = 900
#VTP_OUT0X = 100
#VTP_OUT0Y = 100
#VTP_OUT1X = 700
#VTP_OUT1Y = 1200
#VTP_OUT2X = 400
#VTP_OUT2Y = 200

#VTP_SHOW_MS = 6000

; ----------------------------------------------------------------------
;  THE VERDICTS. Slot 1 is the uniform-colour pass and slot 4 the
;  per-vertex-colour pass; both use these codes.
; ----------------------------------------------------------------------
#VTP_OK = 0
#VTP_NOT_TRIED = 1
#VTP_ERR_NEON = 6
#VTP_ERR_WINDOW = 7
#VTP_ERR_INSTANCE = 8
#VTP_ERR_DEVICE = 9
#VTP_ERR_IMAGE = 10
#VTP_ERR_MEMORY = 11
#VTP_ERR_BIND = 12
#VTP_ERR_VIEW = 13
#VTP_ERR_RENDERPASS = 14
#VTP_ERR_FRAMEBUFFER = 15
#VTP_ERR_BUFFER = 16
#VTP_ERR_SHADER = 17
#VTP_ERR_LAYOUT = 18
#VTP_ERR_PIPELINE = 19
#VTP_ERR_RECORD = 20
#VTP_ERR_SUBMIT = 21
#VTP_ERR_FENCE = 22
#VTP_ERR_PIXELS_IN = 23
#VTP_ERR_PIXELS_OUT = 24
#VTP_ERR_GUARD_CHANGED = 25
#VTP_ERR_NO_JOBS = 26
#VTP_ERR_V3D_FAULT = 27
#VTP_ERR_FORMAT = 28
#VTP_ERR_MAP = 29
#VTP_ERR_VIEWPORT_PACKET = 30
#VTP_ERR_PRESENT = 31

; ERR_STAT bit 12 is V3D_ERR_VCDI. The BCM2711 V3D 4.2 documentation names
; the VCD-idle condition in this register, and every healthy silicon graphics
; run records $1000 throughout. It is state evidence, not a job failure. Any
; other ERR_STAT bit remains fatal.
#VTP_ERRSTAT_BENIGN_VCDI = $00001000

; Independent V3D 4.2 packet oracle for the consecutive draw-local override.
; Packet 110 is CLIPPER_XY_SCALING and packet 108 is VIEWPORT_OFFSET.
; CLIPPER_XY_SCALING consumes binary32 values in 1/256-pixel units. The
; origin-zero half extents and the unsigned u14.8 VIEWPORT_OFFSET fields are
; therefore both width/height multiplied by 128; only their bit encodings
; differ.
#VTP_PKT_CLIPPER_XY_SCALING = 110
#VTP_PKT_VIEWPORT_OFFSET = 108
#VTP_SCALE_X_BITS = $47C7C000
#VTP_SCALE_Y_BITS = $481FE000
#VTP_FINE_X = $00018F80
#VTP_FINE_Y = $00027F80

#VTP_P_NOT_TRIED = 0
#VTP_P_OK = 1
#VTP_P_ADOPT_REFUSED = 2

; Report slots.
#VTP_S_MAGIC = 0
#VTP_S_STATUS = 1
#VTP_S_DETAIL = 2
#VTP_S_DETAIL2 = 3
#VTP_S_STATUS2 = 4
#VTP_S_SURFACE = 5
#VTP_S_WIN_BASE = 6
#VTP_S_WIN_BYTES = 7
#VTP_S_IMG_ADDR = 8
#VTP_S_IMG_SIZE = 9
#VTP_S_IMG_PITCH = 10
#VTP_S_VERTEX_ADDR = 11
#VTP_S_PIPE_A = 12
#VTP_S_PIPE_B = 13
#VTP_S_CLEAR_WORD = 14
#VTP_S_RED_WORD = 15
#VTP_S_GREEN_WORD = 16
#VTP_S_P1_IN0 = 17
#VTP_S_P1_IN1 = 18
#VTP_S_P1_IN2 = 19
#VTP_S_P1_OUT0 = 20
#VTP_S_P1_OUT1 = 21
#VTP_S_P1_OUT2 = 22
#VTP_S_P2_IN0 = 23
#VTP_S_P2_IN1 = 24
#VTP_S_P2_IN2 = 25
#VTP_S_P2_OUT0 = 26
#VTP_S_P2_OUT1 = 27
#VTP_S_P2_OUT2 = 28
#VTP_S_BIN_BEFORE = 29
#VTP_S_BIN_AFTER = 30
#VTP_S_RENDER_BEFORE = 31
#VTP_S_RENDER_AFTER = 32
#VTP_S_BIN_OOM = 33
#VTP_S_BIN_ERRSTAT = 34
#VTP_S_RENDER_ERRSTAT = 35
#VTP_S_MMU_FAULTS = 36
#VTP_S_MMU_VIOADDR = 37
#VTP_S_GUARD_BEFORE = 38
#VTP_S_GUARD_AFTER = 39
#VTP_S_SUBMIT1 = 40
#VTP_S_WAIT1 = 41
#VTP_S_SUBMIT2 = 42
#VTP_S_WAIT2 = 43
#VTP_S_NATIVE = 44
#VTP_S_FAULT_COUNT = 45
#VTP_S_FAULT_TEXT = 46
#VTP_S_PRESENT = 47
#VTP_S_DISPLAY_ERR = 48
#VTP_S_ARENA_NEED = 49
#VTP_S_BACKEND_DRAW = 50
#VTP_S_BACKEND_NAME = 51
#VTP_S_LAYOUT_AFTER = 52
#VTP_S_US1 = 53
#VTP_S_US2 = 54
#VTP_S_DRAWS = 55
#VTP_S_SHREC = 56
#VTP_S_CB_TEXT = 57
#VTP_S_SHUTDOWN = 58
#VTP_S_EMIT_STAGE = 59
#VTP_S_QPU_ERR = 60
; HOW FAR THE PAYLOAD GOT. Bumped at the head of every numbered step, so
; a report always says which step was running - no reader ever has to
; infer it from which slots look written. It is the answer to "was step
; eight reached", and it costs one store per step.
#VTP_S_STEP = 61
; The block's own length in bytes, and a tail magic. A dump that stops
; short does not reach the tail, so "I read the whole report" stops being
; something a reader has to take on trust.
#VTP_S_BYTES = 62
#VTP_S_TAIL = 63

; ======================================================================
;  THE REPORT IS 32 BITS WIDE AND THAT IS NOT A DETAIL
; ======================================================================
;  The monitor's dump has three widths - md.b, md.w and md.l - AND NO
;  64-BIT ONE, and its count is in BYTES whichever is chosen
;  (Anvil/Core/memcmd.pbi, the width table). A report of 64-bit slots can
;  therefore only ever be read as 128 32-bit words, and slot N appears at
;  word 2N with a zero word beside it. That is exactly how the first
;  board run of this diagnostic was misread: twelve words that decoded
;  perfectly as slots 9 to 14 were read as slots 17 to 28, so the
;  addresses and sizes in the middle of the block were taken for the
;  pixel readbacks, and the two verdicts - which live at words 2 and 8 -
;  were never read at all.
;
;  So the block is 32-BIT WORDS. One slot is one word, `md.l` shows them
;  one per column, and the slot number in this file is the word number in
;  the dump. Every value it carries fits: the addresses are payload and
;  window addresses below 4 GiB, the pixels are 32-bit words by
;  definition, and the guard sum is masked to 32 bits below.
; ======================================================================
Global Dim vtpReport.l[64]
Global Dim vtpClear.l[4]
Global Dim vtpPush.l[4]
CompilerIf #VTP_LIST_PROOF
  ; dma.pi4 needs a 512-byte block aligned to 256. Keeping the storage in the
  ; returning payload makes the DMA presentation independent of monitor state.
  Global Dim vtpDmaScratch.a[768]
CompilerEndIf

; The four SPIR-V modules are assembled by
; Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi, which the desk gate walks
; too - so the exact words this payload hands the front end are the words
; a gate has already checked against an independent assembler.

Procedure vtpPut(slot.i, value.i)
  If slot < 0 Or slot > 63
    ProcedureReturn
  EndIf
  vtpReport[slot] = value & $FFFFFFFF
EndProcedure

; Read a slot back WITHOUT the sign of a 32-bit load leaking into a
; 64-bit comparison. A pixel of $FFFF0000 read from a .l is -65536, and
; comparing that against the constant $FFFF0000 would fail on every
; correct run - which is the one way a width change like this turns a
; green board into a red one.
Procedure.i vtpGet(slot.i)
  If slot < 0 Or slot > 63
    ProcedureReturn 0
  EndIf
  ProcedureReturn vtpReport[slot] & $FFFFFFFF
EndProcedure

; Mark the numbered step that is now running. The report carries the
; highest one reached, so a run that stopped says where.
Procedure vtpStep(n.i)
  vtpPut(#VTP_S_STEP, n)
EndProcedure

Procedure.i vtpStop(status.i)
  vtpPut(#VTP_S_STATUS, status)
  vtpPut(#VTP_S_FAULT_TEXT, AnvilVkFaultText())
  vtpPut(#VTP_S_FAULT_COUNT, AnvilVkFaultCount())
  ProcedureReturn @vtpReport[0]
EndProcedure

Procedure.i vtpSum(base.i, bytes.i)
  Define i.i
  Define s.i
  s = 0
  i = 0
  While i < bytes
    s = (s + (PeekL(base + i) & $FFFFFFFF) + i) & $FFFFFFFF
    i = i + 4
  Wend
  ProcedureReturn s
EndProcedure

Procedure vtpFill(base.i, bytes.i, word.i)
  Define i.i
  i = 0
  While i < bytes
    PokeL(base + i, word)
    i = i + 4
  Wend
EndProcedure

Procedure.i vtpPixel(imgBase.i, pitch.i, x.i, y.i)
  ProcedureReturn PeekL(imgBase + (y * pitch) + (x * 4)) & $FFFFFFFF
EndProcedure

CompilerIf #VTP_LIST_PROOF
Procedure vtpListVertex(base.i, index.i, xbits.i, ybits.i, rbits.i, gbits.i, bbits.i, abits.i)
  Define p.i = base + (index * #VTP_STRIDE)
  PokeL(p + 0, xbits) : PokeL(p + 4, ybits)
  PokeL(p + 8, rbits) : PokeL(p + 12, gbits)
  PokeL(p + 16, bbits) : PokeL(p + 20, abits)
EndProcedure

Procedure vtpListRect(base.i, first.i, x0.i, y0.i, x1.i, y1.i, r.i, g.i, b.i, a.i)
  vtpListVertex(base, first + 0, x0, y0, r, g, b, a)
  vtpListVertex(base, first + 1, x0, y1, r, g, b, a)
  vtpListVertex(base, first + 2, x1, y1, r, g, b, a)
  vtpListVertex(base, first + 3, x0, y0, r, g, b, a)
  vtpListVertex(base, first + 4, x1, y1, r, g, b, a)
  vtpListVertex(base, first + 5, x1, y0, r, g, b, a)
EndProcedure
CompilerEndIf

; Control-list words are byte-aligned, not naturally aligned. Read them the
; same byte-wise way the V3D packet encoder writes them.
Procedure.i vtpLe32(addr.i)
  ProcedureReturn (PeekA(addr) & $FF) | ((PeekA(addr + 1) & $FF) << 8) | ((PeekA(addr + 2) & $FF) << 16) | ((PeekA(addr + 3) & $FF) << 24)
EndProcedure

; Return the byte offset of the exact consecutive scaling/offset pair. A
; single opcode byte is not evidence because arbitrary packet payload can
; contain the same value.
Procedure.i vtpFindOddViewportPackets(base.i, bytes.i)
  Define i.i
  If base = 0 Or bytes < 18 : ProcedureReturn -1 : EndIf
  i = 0
  While i <= bytes - 18
    If (PeekA(base + i) & $FF) = #VTP_PKT_CLIPPER_XY_SCALING
      If vtpLe32(base + i + 1) = #VTP_SCALE_X_BITS And vtpLe32(base + i + 5) = #VTP_SCALE_Y_BITS
        If (PeekA(base + i + 9) & $FF) = #VTP_PKT_VIEWPORT_OFFSET
          If vtpLe32(base + i + 10) = #VTP_FINE_X And vtpLe32(base + i + 14) = #VTP_FINE_Y
            ProcedureReturn i
          EndIf
        EndIf
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

; The indexed proof deliberately makes setup and draw adjacent. Compare every
; field, not merely the opcodes: opcode-like payload bytes are common in a BCL.
Procedure.i vtpFindIndexedPackets(base.i, bytes.i, indexBase.i, indexBytes.i)
  Define i.i
  If base = 0 Or bytes < 19 : ProcedureReturn -1 : EndIf
  i = 0
  While i <= bytes - 19
    If (PeekA(base + i) & $FF) = 44 And vtpLe32(base + i + 1) = indexBase And vtpLe32(base + i + 5) = indexBytes
      If (PeekA(base + i + 9) & $FF) = 32 And (PeekA(base + i + 10) & $FF) = $44
        If vtpLe32(base + i + 11) = 3 And vtpLe32(base + i + 15) = 2
          ProcedureReturn i
        EndIf
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i Main()
  Define rc.i
  Define inst.i
  Define phys.i
  Define dev.i
  Define queue.i
  Define pool.i
  Define cmd.i
  Define img.i
  Define mem.i
  Define view.i
  Define rp.i
  Define fb.i
  Define buf.i
  Define bmem.i
  Define ibuf.i
  Define imem.i
  Define fence.i
  Define count.i
  Define imgBase.i
  Define vaddr.i
  Define iaddr.i
  Define mapped.i
  Define pitch.i
  Define imagePitch.i
  Define vsA.i
  Define fsA.i
  Define vsB.i
  Define fsB.i
  Define layA.i
  Define layB.i
  Define pipeA.i
  Define pipeB.i
  Define pipeC.i
  Define bytesA.i
  Define bytesB.i
  Define bytesC.i
  Define bytesD.i
  Define t0.i
  Define hz.i
  Define badIn.i
  Define badOut.i
  Define viewportPacket.i
  Define indexPacket.i
  Define drawsBefore.i
  Define dmaScratch.i
  Define dmaBefore.i

  Define ici.VkInstanceCreateInfo
  Define fp.VkFormatProperties
  Define dci.VkDeviceCreateInfo
  Define qci.VkDeviceQueueCreateInfo
  Define prio.l
  Define pci.VkCommandPoolCreateInfo
  Define cbai.VkCommandBufferAllocateInfo
  Define bi.VkCommandBufferBeginInfo
  Define imgci.VkImageCreateInfo
  Define req.VkMemoryRequirements
  Define mai.VkMemoryAllocateInfo
  Define fci.VkFenceCreateInfo
  Define si.VkSubmitInfo
  Define ivci.VkImageViewCreateInfo
  Define att.VkAttachmentDescription
  Define aref.VkAttachmentReference
  Define sub.VkSubpassDescription
  Define rpci.VkRenderPassCreateInfo
  Define fbci.VkFramebufferCreateInfo
  Define bufci.VkBufferCreateInfo
  Define smci.VkShaderModuleCreateInfo
  Define plci.VkPipelineLayoutCreateInfo
  Define pcr.VkPushConstantRange
  Define Dim stages.VkPipelineShaderStageCreateInfo[2]
  Define bind.VkVertexInputBindingDescription
  Define Dim attrs.VkVertexInputAttributeDescription[2]
  Define vi.VkPipelineVertexInputStateCreateInfo
  Define ia.VkPipelineInputAssemblyStateCreateInfo
  Define vpstate.VkPipelineViewportStateCreateInfo
  Define vp.VkViewport
  Define sc.VkRect2D
  Define rs.VkPipelineRasterizationStateCreateInfo
  Define ms.VkPipelineMultisampleStateCreateInfo
  Define cba.VkPipelineColorBlendAttachmentState
  Define cb.VkPipelineColorBlendStateCreateInfo
  Define gp.VkGraphicsPipelineCreateInfo
  Define rpbi.VkRenderPassBeginInfo
  Define cbHandle.i
  Define fenceArray.i
  Define bufHandle.i
  Define bufOffset.q

  vtpPut(#VTP_S_MAGIC, #VTP_MAGIC)
  vtpPut(#VTP_S_TAIL, #VTP_TAIL_MAGIC)
  vtpPut(#VTP_S_BYTES, 256)
  vtpStep(0)
  vtpPut(#VTP_S_STATUS, #VTP_ERR_NEON)
  vtpPut(#VTP_S_STATUS2, #VTP_NOT_TRIED)
  vtpPut(#VTP_S_PRESENT, #VTP_P_NOT_TRIED)
  vtpPut(#VTP_S_SURFACE, #VTP_SURFACE)
  vtpPut(#VTP_S_WIN_BASE, #VTP_WIN_BASE)
  vtpPut(#VTP_S_WIN_BYTES, #VTP_WIN_BYTES)
  vtpPut(#VTP_S_CLEAR_WORD, #VTP_CLEAR_WORD)
  vtpPut(#VTP_S_RED_WORD, #VTP_RED_WORD)
  vtpPut(#VTP_S_GREEN_WORD, #VTP_GREEN_WORD)
  TimerInit()
  hz = TickHz() / 1000000
  If hz < 1
    hz = 1
  EndIf
  pitch = #VTP_PANEL_PITCH

  ; The guard half, filled before anything else touches the engine.
  vtpFill(#VTP_SURFACE, #VTP_SCREEN_BYTES, #VTP_GUARD)

  ; ------------------------------------------------------------------
  ;  1. The graphics engine, over memory this payload owns.
  ; ------------------------------------------------------------------
  vtpStep(1)
  If NeonArena(#VTP_ARENA, #VTP_ARENA_BYTES) <> #NEON_OK
    vtpPut(#VTP_S_DETAIL, Neon_Error())
    ProcedureReturn vtpStop(#VTP_ERR_NEON)
  EndIf
  If NeonSurface(#VTP_SURFACE, #VTP_PANEL_W, #VTP_PANEL_H, pitch) <> #NEON_OK
    vtpPut(#VTP_S_DETAIL, Neon_Error())
    ProcedureReturn vtpStop(#VTP_ERR_NEON)
  EndIf
  NeonSurfaceMapSpan(#VTP_MAP_SPAN)
  If NeonInit() <> #NEON_OK
    vtpPut(#VTP_S_DETAIL, Neon_Error())
    vtpPut(#VTP_S_DETAIL2, Neon_ArenaNeed())
    ProcedureReturn vtpStop(#VTP_ERR_NEON)
  EndIf
  vtpPut(#VTP_S_ARENA_NEED, Neon_ArenaNeed())

  ; ------------------------------------------------------------------
  ;  2. The Vulkan device, over the memory above the surface.
  ; ------------------------------------------------------------------
  vtpStep(2)
  rc = AnvilVkV3dWindow(#VTP_WIN_BASE, #VTP_WIN_BYTES)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_WINDOW)
  EndIf
  vtpPut(#VTP_S_BACKEND_DRAW, AnvilVkBackendCanDraw())
  vtpPut(#VTP_S_BACKEND_NAME, AnvilVkBackendName())

  ici\sType = #VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
  If vkCreateInstance(@ici, 0, @inst) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_INSTANCE)
  EndIf
  count = 1
  If vkEnumeratePhysicalDevices(inst, @count, @phys) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_INSTANCE)
  EndIf
  vkGetPhysicalDeviceFormatProperties(phys, #VK_FORMAT_B8G8R8A8_UNORM, @fp)
  If fp\linearTilingFeatures <> (#VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT | #VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT) Or fp\optimalTilingFeatures <> #VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT Or fp\bufferFeatures <> 0
    vtpPut(#VTP_S_DETAIL, fp\linearTilingFeatures)
    vtpPut(#VTP_S_DETAIL2, fp\optimalTilingFeatures | fp\bufferFeatures)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FORMAT)
  EndIf
  prio = 0
  qci\sType = #VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO
  qci\queueCount = 1
  qci\pQueuePriorities = @prio
  dci\sType = #VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO
  dci\queueCreateInfoCount = 1
  dci\pQueueCreateInfos = @qci
  rc = vkCreateDevice(phys, @dci, 0, @dev)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_DEVICE)
  EndIf
  vkGetDeviceQueue(dev, 0, 0, @queue)
  pci\sType = #VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO
  pci\flags = #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT
  If vkCreateCommandPool(dev, @pci, 0, @pool) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_DEVICE)
  EndIf
  cbai\sType = #VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO
  cbai\commandPool = pool
  cbai\level = #VK_COMMAND_BUFFER_LEVEL_PRIMARY
  cbai\commandBufferCount = 1
  If vkAllocateCommandBuffers(dev, @cbai, @cmd) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_DEVICE)
  EndIf

  ; ------------------------------------------------------------------
  ;  3. The colour attachment at the panel's native extent.
  ; ------------------------------------------------------------------
  vtpStep(3)
  imgci\sType = #VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO
  imgci\imageType = #VK_IMAGE_TYPE_2D
  imgci\format = #VK_FORMAT_B8G8R8A8_UNORM
  imgci\extent\width = #VTP_VIEW_W
  imgci\extent\height = #VTP_VIEW_H
  imgci\extent\depth = 1
  imgci\mipLevels = 1
  imgci\arrayLayers = 1
  imgci\samples = #VK_SAMPLE_COUNT_1_BIT
  imgci\tiling = #VK_IMAGE_TILING_LINEAR
  imgci\usage = #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | #VK_IMAGE_USAGE_TRANSFER_SRC_BIT
  imgci\sharingMode = #VK_SHARING_MODE_EXCLUSIVE
  imgci\initialLayout = #VK_IMAGE_LAYOUT_UNDEFINED
  rc = vkCreateImage(dev, @imgci, 0, @img)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_IMAGE)
  EndIf
  vkGetImageMemoryRequirements(dev, img, @req)
  mai\sType = #VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO
  mai\allocationSize = req\size
  mai\memoryTypeIndex = 0
  rc = vkAllocateMemory(dev, @mai, 0, @mem)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_MEMORY)
  EndIf
  rc = vkBindImageMemory(dev, img, mem, 0)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_BIND)
  EndIf
  imgBase = AnvilVkImageAddress(img)
  vtpPut(#VTP_S_IMG_ADDR, imgBase)
  vtpPut(#VTP_S_IMG_SIZE, req\size)
  imagePitch = AnvilVkImageRowPitch(img)
  vtpPut(#VTP_S_IMG_PITCH, imagePitch)
  ; POISON IT through the public mapping API. An image that already held an
  ; answer would prove nothing, and the map must name the bound image bytes.
  mapped = 0
  If vkMapMemory(dev, mem, 0, #VK_WHOLE_SIZE, 0, @mapped) <> #VK_SUCCESS Or mapped <> imgBase
    vtpPut(#VTP_S_DETAIL, mapped)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_MAP)
  EndIf
  vtpFill(mapped, req\size, ~#VTP_CLEAR_WORD)
  vkUnmapMemory(dev, mem)

  ivci\sType = #VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO
  ivci\image = img
  ivci\viewType = #VK_IMAGE_VIEW_TYPE_2D
  ivci\format = #VK_FORMAT_B8G8R8A8_UNORM
  ivci\subresourceRange\aspectMask = #VK_IMAGE_ASPECT_COLOR_BIT
  ivci\subresourceRange\levelCount = 1
  ivci\subresourceRange\layerCount = 1
  If vkCreateImageView(dev, @ivci, 0, @view) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_VIEW)
  EndIf

  att\format = #VK_FORMAT_B8G8R8A8_UNORM
  att\samples = #VK_SAMPLE_COUNT_1_BIT
  att\loadOp = #VK_ATTACHMENT_LOAD_OP_CLEAR
  att\storeOp = #VK_ATTACHMENT_STORE_OP_STORE
  att\stencilLoadOp = #VK_ATTACHMENT_LOAD_OP_DONT_CARE
  att\stencilStoreOp = #VK_ATTACHMENT_STORE_OP_DONT_CARE
  att\initialLayout = #VK_IMAGE_LAYOUT_UNDEFINED
  att\finalLayout = #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
  aref\attachment = 0
  aref\layout = #VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
  sub\pipelineBindPoint = #VK_PIPELINE_BIND_POINT_GRAPHICS
  sub\colorAttachmentCount = 1
  sub\pColorAttachments = @aref
  rpci\sType = #VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO
  rpci\attachmentCount = 1
  rpci\pAttachments = @att
  rpci\subpassCount = 1
  rpci\pSubpasses = @sub
  rc = vkCreateRenderPass(dev, @rpci, 0, @rp)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_RENDERPASS)
  EndIf

  fbci\sType = #VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO
  fbci\renderPass = rp
  fbci\attachmentCount = 1
  fbci\pAttachments = @view
  fbci\width = #VTP_VIEW_W
  fbci\height = #VTP_VIEW_H
  fbci\layers = 1
  If vkCreateFramebuffer(dev, @fbci, 0, @fb) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FRAMEBUFFER)
  EndIf

  ; ------------------------------------------------------------------
  ;  4. The vertex buffer. Three vertices, position and colour, and the
  ;     same array serves both pipelines: the uniform-colour one
  ;     declares one attribute over the same stride and simply never
  ;     fetches the colour.
  ; ------------------------------------------------------------------
  vtpStep(4)
  bufci\sType = #VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO
CompilerIf #VTP_LIST_PROOF
  bufci\size = #VTP_LIST_VERTICES * #VTP_STRIDE
CompilerElse
  bufci\size = 3 * #VTP_STRIDE
CompilerEndIf
  bufci\usage = #VK_BUFFER_USAGE_VERTEX_BUFFER_BIT
  bufci\sharingMode = #VK_SHARING_MODE_EXCLUSIVE
  If vkCreateBuffer(dev, @bufci, 0, @buf) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_BUFFER)
  EndIf
  vkGetBufferMemoryRequirements(dev, buf, @req)
  mai\allocationSize = req\size
  If vkAllocateMemory(dev, @mai, 0, @bmem) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_BUFFER)
  EndIf
  If vkBindBufferMemory(dev, buf, bmem, 0) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_BUFFER)
  EndIf
  vaddr = AnvilVkBufferAddress(buf)
  vtpPut(#VTP_S_VERTEX_ADDR, vaddr)
  mapped = 0
  If vkMapMemory(dev, bmem, 0, #VK_WHOLE_SIZE, 0, @mapped) <> #VK_SUCCESS Or mapped <> vaddr
    vtpPut(#VTP_S_DETAIL, mapped)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_MAP)
  EndIf
CompilerIf #VTP_LIST_PROOF
  ; Six rectangles, each two triangles. The first four are push-colour
  ; geometry; draw four consumes the magenta vertex colour as a varying; the
  ; final rectangle is a small opaque top layer.
  vtpListRect(mapped, 0,  $BF400000, $BF400000, $3E800000, $3F400000, #VTP_F_ONE,  #VTP_F_ZERO, #VTP_F_ZERO, #VTP_F_ONE)
  vtpListRect(mapped, 6,  $BE800000, $BF400000, $3F400000, $3F400000, #VTP_F_ZERO, #VTP_F_ONE,  #VTP_F_ZERO, #VTP_F_ONE)
  vtpListRect(mapped, 12, $BF000000, $BF000000, $3F000000, $3F000000, #VTP_F_ZERO, #VTP_F_ZERO, #VTP_F_ONE,  #VTP_SOURCE_ALPHA)
  vtpListRect(mapped, 18, $BE800000, $BE800000, $3E800000, $3E800000, #VTP_F_ONE,  #VTP_F_ZERO, #VTP_F_ZERO, #VTP_SOURCE_ALPHA)
  vtpListRect(mapped, 24, $BE000000, $BF400000, $3E000000, $BEC00000, #VTP_F_ONE,  #VTP_F_ZERO, #VTP_F_ONE,  #VTP_F_ONE)
  vtpListRect(mapped, 30, $BE000000, $BE000000, $3E000000, $3E000000, #VTP_F_ONE,  #VTP_F_ONE,  #VTP_F_ONE,  #VTP_F_ONE)
CompilerElse
  PokeL(mapped + 0, #VTP_X0)
  PokeL(mapped + 4, #VTP_Y0)
  PokeL(mapped + 8, #VTP_F_ZERO)
  PokeL(mapped + 12, #VTP_F_ONE)
  PokeL(mapped + 16, #VTP_F_ZERO)
  PokeL(mapped + 20, #VTP_SOURCE_ALPHA)
  PokeL(mapped + 24, #VTP_X1)
  PokeL(mapped + 28, #VTP_Y1)
  PokeL(mapped + 32, #VTP_F_ZERO)
  PokeL(mapped + 36, #VTP_F_ONE)
  PokeL(mapped + 40, #VTP_F_ZERO)
  PokeL(mapped + 44, #VTP_SOURCE_ALPHA)
  PokeL(mapped + 48, #VTP_X2)
  PokeL(mapped + 52, #VTP_Y2)
  PokeL(mapped + 56, #VTP_F_ZERO)
  PokeL(mapped + 60, #VTP_F_ONE)
  PokeL(mapped + 64, #VTP_F_ZERO)
  PokeL(mapped + 68, #VTP_SOURCE_ALPHA)
CompilerEndIf
  vkUnmapMemory(dev, bmem)

CompilerIf #VTP_INDEXED_PROOF
  ; Bind at byte four and draw from firstIndex one. The dummy element at the
  ; bind base is not selected; the GPU must fetch 2,0,1 from byte offset two.
  bufci\size = 16 : bufci\usage = #VK_BUFFER_USAGE_INDEX_BUFFER_BIT
  If vkCreateBuffer(dev, @bufci, 0, @ibuf) <> #VK_SUCCESS
    NeonShutdown() : ProcedureReturn vtpStop(#VTP_ERR_BUFFER)
  EndIf
  vkGetBufferMemoryRequirements(dev, ibuf, @req) : mai\allocationSize = req\size
  If vkAllocateMemory(dev, @mai, 0, @imem) <> #VK_SUCCESS Or vkBindBufferMemory(dev, ibuf, imem, 0) <> #VK_SUCCESS
    NeonShutdown() : ProcedureReturn vtpStop(#VTP_ERR_BUFFER)
  EndIf
  iaddr = AnvilVkBufferAddress(ibuf) : mapped = 0
  If vkMapMemory(dev, imem, 0, #VK_WHOLE_SIZE, 0, @mapped) <> #VK_SUCCESS Or mapped <> iaddr
    NeonShutdown() : ProcedureReturn vtpStop(#VTP_ERR_MAP)
  EndIf
  PokeW(mapped + 4, 99) : PokeW(mapped + 6, 2)
  PokeW(mapped + 8, 0) : PokeW(mapped + 10, 1)
  vkUnmapMemory(dev, imem)
CompilerEndIf

  ; ------------------------------------------------------------------
  ;  5. Four shader modules, two layouts, two pipelines.
  ; ------------------------------------------------------------------
  vtpStep(5)
  bytesA = vtpBuildVsA()
  bytesB = vtpBuildFsA()
  bytesC = vtpBuildVsB()
  bytesD = vtpBuildFsB()
  smci\sType = #VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
  smci\pCode = @vtpVsA[0]
  smci\codeSize = bytesA
  rc = vkCreateShaderModule(dev, @smci, 0, @vsA)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_DETAIL2, AnvilVkSpirvLastOpcode())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SHADER)
  EndIf
  smci\pCode = @vtpFsA[0]
  smci\codeSize = bytesB
  rc = vkCreateShaderModule(dev, @smci, 0, @fsA)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_DETAIL2, AnvilVkSpirvLastOpcode())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SHADER)
  EndIf
  smci\pCode = @vtpVsB[0]
  smci\codeSize = bytesC
  rc = vkCreateShaderModule(dev, @smci, 0, @vsB)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_DETAIL2, AnvilVkSpirvLastOpcode())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SHADER)
  EndIf
  smci\pCode = @vtpFsB[0]
  smci\codeSize = bytesD
  rc = vkCreateShaderModule(dev, @smci, 0, @fsB)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_DETAIL2, AnvilVkSpirvLastOpcode())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SHADER)
  EndIf

  pcr\stageFlags = #VK_SHADER_STAGE_FRAGMENT_BIT
  pcr\offset = 0
  pcr\size = 16
  plci\sType = #VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
  plci\pushConstantRangeCount = 1
  plci\pPushConstantRanges = @pcr
  If vkCreatePipelineLayout(dev, @plci, 0, @layA) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_LAYOUT)
  EndIf
  plci\pushConstantRangeCount = 0
  plci\pPushConstantRanges = 0
  If vkCreatePipelineLayout(dev, @plci, 0, @layB) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_LAYOUT)
  EndIf

  ia\sType = #VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
  ia\topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
  ia\primitiveRestartEnable = #VK_FALSE
  PokeL(@vp\x, #VTP_F_ZERO)
  PokeL(@vp\y, #VTP_F_ZERO)
  PokeL(@vp\width, $4447C000)            ; 799.0, deliberately odd
  PokeL(@vp\height, $449FE000)           ; 1279.0, deliberately odd
  PokeL(@vp\minDepth, #VTP_F_ZERO)
  PokeL(@vp\maxDepth, #VTP_F_ONE)
  sc\offset\x = 0
  sc\offset\y = 0
  sc\extent\width = #VTP_VIEW_W
  sc\extent\height = #VTP_VIEW_H
  vpstate\sType = #VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO
  vpstate\viewportCount = 1
  vpstate\pViewports = @vp
  vpstate\scissorCount = 1
  vpstate\pScissors = @sc
  rs\sType = #VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO
  rs\polygonMode = #VK_POLYGON_MODE_FILL
  rs\cullMode = #VK_CULL_MODE_NONE
  rs\frontFace = #VK_FRONT_FACE_COUNTER_CLOCKWISE
  PokeL(@rs\lineWidth, #VTP_F_ONE)
  ms\sType = #VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO
  ms\rasterizationSamples = #VK_SAMPLE_COUNT_1_BIT
CompilerIf #VTP_BLEND_PROOF
  cba\blendEnable = #VK_TRUE
  cba\srcColorBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstColorBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\colorBlendOp = #VK_BLEND_OP_ADD
  cba\srcAlphaBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstAlphaBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\alphaBlendOp = #VK_BLEND_OP_ADD
CompilerElse
  cba\blendEnable = #VK_FALSE
CompilerEndIf
  cba\colorWriteMask = #VK_COLOR_COMPONENT_R_BIT | #VK_COLOR_COMPONENT_G_BIT | #VK_COLOR_COMPONENT_B_BIT | #VK_COLOR_COMPONENT_A_BIT
  cb\sType = #VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO
  cb\attachmentCount = 1
  cb\pAttachments = @cba

  bind\binding = 0
  bind\stride = #VTP_STRIDE
  bind\inputRate = #VK_VERTEX_INPUT_RATE_VERTEX
  attrs[0]\location = 0
  attrs[0]\binding = 0
  attrs[0]\format = #VK_FORMAT_R32G32_SFLOAT
  attrs[0]\offset = 0
  attrs[1]\location = 1
  attrs[1]\binding = 0
  attrs[1]\format = #VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[1]\offset = 8
  vi\sType = #VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
  vi\vertexBindingDescriptionCount = 1
  vi\pVertexBindingDescriptions = @bind
  vi\vertexAttributeDescriptionCount = 1
  vi\pVertexAttributeDescriptions = @attrs[0]

  stages[0]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[0]\stage = #VK_SHADER_STAGE_VERTEX_BIT
  stages[0]\module = vsA
  stages[1]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[1]\stage = #VK_SHADER_STAGE_FRAGMENT_BIT
  stages[1]\module = fsA

  gp\sType = #VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO
  gp\stageCount = 2
  gp\pStages = @stages[0]
  gp\pVertexInputState = @vi
  gp\pInputAssemblyState = @ia
  gp\pViewportState = @vpstate
  gp\pRasterizationState = @rs
  gp\pMultisampleState = @ms
  gp\pColorBlendState = @cb
  gp\layout = layA
  gp\renderPass = rp
  gp\subpass = 0
  gp\basePipelineIndex = -1
  rc = vkCreateGraphicsPipelines(dev, 0, 1, @gp, 0, @pipeA)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_EMIT_STAGE, AnvilVkV3dShaderStage())
    vtpPut(#VTP_S_QPU_ERR, AnvilVkV3dShaderError())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_PIPELINE)
  EndIf
  vtpPut(#VTP_S_PIPE_A, AnvilVkPipelineCodeBase(pipeA))

CompilerIf #VTP_LIST_PROOF
  ; Same push-colour shaders, exact source-over fixed-function state.
  cba\blendEnable = #VK_TRUE
  cba\srcColorBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstColorBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\colorBlendOp = #VK_BLEND_OP_ADD
  cba\srcAlphaBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstAlphaBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\alphaBlendOp = #VK_BLEND_OP_ADD
  rc = vkCreateGraphicsPipelines(dev, 0, 1, @gp, 0, @pipeC)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_PIPELINE)
  EndIf
  ; The varying pipeline is opaque; its state change is intentionally visible
  ; to the list transition oracle.
  cba\blendEnable = #VK_FALSE
CompilerEndIf

  stages[0]\module = vsB
  stages[1]\module = fsB
  vi\vertexAttributeDescriptionCount = 2
  gp\layout = layB
  rc = vkCreateGraphicsPipelines(dev, 0, 1, @gp, 0, @pipeB)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_EMIT_STAGE, AnvilVkV3dShaderStage())
    vtpPut(#VTP_S_QPU_ERR, AnvilVkV3dShaderError())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_PIPELINE)
  EndIf
  vtpPut(#VTP_S_PIPE_B, AnvilVkPipelineCodeBase(pipeB))

  ; ------------------------------------------------------------------
  ;  6. PASS ONE: the uniform-colour triangle.
  ; ------------------------------------------------------------------
  vtpStep(6)
CompilerIf #VTP_LIST_PROOF
  PokeL(@vtpClear[0] + 0, #VTP_CLEAR_R)
  PokeL(@vtpClear[0] + 4, #VTP_CLEAR_G)
  PokeL(@vtpClear[0] + 8, #VTP_CLEAR_B)
  PokeL(@vtpClear[0] + 12, #VTP_CLEAR_A)
  rpbi\sType = #VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO
  rpbi\renderPass = rp
  rpbi\framebuffer = fb
  rpbi\renderArea\extent\width = #VTP_VIEW_W
  rpbi\renderArea\extent\height = #VTP_VIEW_H
  rpbi\clearValueCount = 1
  rpbi\pClearValues = @vtpClear[0]
  bi\sType = #VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  bi\flags = #VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
  If vkBeginCommandBuffer(cmd, @bi) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_RECORD)
  EndIf
  bufHandle = buf : bufOffset = 0
  vkCmdBeginRenderPass(cmd, @rpbi, #VK_SUBPASS_CONTENTS_INLINE)
  vkCmdBindVertexBuffers(cmd, 0, 1, @bufHandle, @bufOffset)

  ; 0: opaque red base.
  vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeA)
  PokeL(@vtpPush[0] + 0, #VTP_F_ONE) : PokeL(@vtpPush[0] + 4, #VTP_F_ZERO)
  PokeL(@vtpPush[0] + 8, #VTP_F_ZERO) : PokeL(@vtpPush[0] + 12, #VTP_F_ONE)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
  vkCmdDraw(cmd, 6, 1, 0, 0)
  ; 1: opaque green overlap. The order-only probe must read green.
  PokeL(@vtpPush[0] + 0, #VTP_F_ZERO) : PokeL(@vtpPush[0] + 4, #VTP_F_ONE)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
  vkCmdDraw(cmd, 6, 1, 6, 0)
  ; 2: half-alpha blue source-over green.
  vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeC)
  PokeL(@vtpPush[0] + 4, #VTP_F_ZERO) : PokeL(@vtpPush[0] + 8, #VTP_F_ONE)
  PokeL(@vtpPush[0] + 12, #VTP_SOURCE_ALPHA)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
  vkCmdDraw(cmd, 6, 1, 12, 0)
  ; 3: a distinct half-alpha red push over the preceding result.
  PokeL(@vtpPush[0] + 0, #VTP_F_ONE) : PokeL(@vtpPush[0] + 8, #VTP_F_ZERO)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
  vkCmdDraw(cmd, 6, 1, 18, 0)
  ; 4: magenta comes from the vertex varying, not a push block.
  vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeB)
  vkCmdDraw(cmd, 6, 1, 24, 0)
  ; 5: final opaque white top layer, after the varying transition.
  vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeA)
  PokeL(@vtpPush[0] + 0, #VTP_F_ONE) : PokeL(@vtpPush[0] + 4, #VTP_F_ONE)
  PokeL(@vtpPush[0] + 8, #VTP_F_ONE) : PokeL(@vtpPush[0] + 12, #VTP_F_ONE)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
  vkCmdDraw(cmd, 6, 1, 30, 0)
  vkCmdEndRenderPass(cmd)
  rc = vkEndCommandBuffer(cmd)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_CB_TEXT, AnvilVkCommandBufferFailureText(cmd))
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_RECORD)
  EndIf

  fci\sType = #VK_STRUCTURE_TYPE_FENCE_CREATE_INFO
  If vkCreateFence(dev, @fci, 0, @fence) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf
  vtpPut(#VTP_S_BIN_BEFORE, V3dBinJobs())
  vtpPut(#VTP_S_RENDER_BEFORE, V3dRenderJobs())
  vtpPut(#VTP_S_GUARD_BEFORE, vtpSum(#VTP_SURFACE, #VTP_SCREEN_BYTES))
  drawsBefore = avkBackendDraws()
  vtpPut(#VTP_S_VERTEX_ADDR, drawsBefore)
  cbHandle = cmd
  si\sType = #VK_STRUCTURE_TYPE_SUBMIT_INFO
  si\commandBufferCount = 1
  si\pCommandBuffers = @cbHandle
  t0 = Ticks()
  rc = vkQueueSubmit(queue, 1, @si, fence)
  vtpPut(#VTP_S_SUBMIT1, rc)
  vtpPut(#VTP_S_US1, (Ticks() - t0) / hz)
  vtpPut(#VTP_S_NATIVE, AnvilVkBackendNativeError())
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SUBMIT)
  EndIf
  fenceArray = fence
  rc = vkWaitForFences(dev, 1, @fenceArray, 1, 2000000000)
  vtpPut(#VTP_S_WAIT1, rc)
  If rc <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf
  vtpPut(#VTP_S_LAYOUT_AFTER, AnvilVkImageLayout(img))
  vtpPut(#VTP_S_SHREC, AnvilVkV3dLastShaderRecord())
  vtpPut(#VTP_S_PIPE_A, avkBackendDraws())
  vtpPut(#VTP_S_PIPE_B, AnvilVkV3dLastVaryingTransitionCount())
  vtpPut(#VTP_S_P1_IN0, vtpPixel(imgBase, imagePitch, 50, 50))
  vtpPut(#VTP_S_P1_IN1, vtpPixel(imgBase, imagePitch, 150, 1000))
  vtpPut(#VTP_S_P1_IN2, vtpPixel(imgBase, imagePitch, 650, 1000))
  vtpPut(#VTP_S_P1_OUT0, vtpPixel(imgBase, imagePitch, 350, 1050))
  vtpPut(#VTP_S_P1_OUT1, vtpPixel(imgBase, imagePitch, 550, 800))
  vtpPut(#VTP_S_P1_OUT2, vtpPixel(imgBase, imagePitch, 320, 700))
  vtpPut(#VTP_S_P2_IN0, vtpPixel(imgBase, imagePitch, 400, 250))
  vtpPut(#VTP_S_P2_IN1, vtpPixel(imgBase, imagePitch, 400, 640))
  vtpPut(#VTP_S_P2_IN2, AnvilVkV3dLastCacheInputRangeCount())
  vtpPut(#VTP_S_P2_OUT0, AnvilVkV3dLastCacheMergedRangeCount())
  vtpPut(#VTP_S_P2_OUT1, AnvilVkV3dLastResourceCacheRangeCount())
  vtpPut(#VTP_S_P2_OUT2, AnvilVkV3dLastListCount())
  vtpPut(#VTP_S_SUBMIT2, AnvilVkV3dLastListCount())
  vtpPut(#VTP_S_WAIT2, AnvilVkV3dLastListPrimitives())
  vtpPut(#VTP_S_US2, AnvilVkV3dLastViewportTransitionCount())
  vtpPut(#VTP_S_EMIT_STAGE, AnvilVkV3dLastBlendTransitionCount())
  vtpPut(#VTP_S_QPU_ERR, AnvilVkV3dLastVaryingTransitionCount())

  badIn = 0
  If vtpGet(#VTP_S_P1_IN0) <> #VTP_CLEAR_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_IN1) <> #VTP_RED_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_IN2) <> #VTP_GREEN_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT0) <> #VTP_GREEN_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT1) <> #VTP_LIST_BLUE_OVER_GREEN : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT2) <> #VTP_LIST_RED_OVER_BLUE_GREEN : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P2_IN0) <> #VTP_LIST_MAGENTA : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P2_IN1) <> #VTP_LIST_WHITE : badIn = badIn + 1 : EndIf
  If badIn <> 0
    vtpPut(#VTP_S_STATUS2, #VTP_ERR_PIXELS_IN)
  ElseIf AnvilVkV3dLastListCount() <> #VTP_LIST_DRAWS Or AnvilVkV3dLastListPrimitives() <> #VTP_LIST_DRAWS
    vtpPut(#VTP_S_STATUS2, #VTP_ERR_NO_JOBS)
  ElseIf AnvilVkV3dLastViewportTransitionCount() <> 1 Or AnvilVkV3dLastBlendTransitionCount() <> 3 Or AnvilVkV3dLastVaryingTransitionCount() <> 3
    vtpPut(#VTP_S_STATUS2, #VTP_ERR_VIEWPORT_PACKET)
  ElseIf AnvilVkV3dLastCacheInputRangeCount() <> 18 Or AnvilVkV3dLastCacheMergedRangeCount() <> 13 Or AnvilVkV3dLastResourceCacheRangeCount() <> 0
    vtpPut(#VTP_S_STATUS2, #VTP_ERR_V3D_FAULT)
  Else
    vtpPut(#VTP_S_STATUS2, #VTP_OK)
  EndIf
CompilerElse
  PokeL(@vtpClear[0] + 0, #VTP_CLEAR_R)
  PokeL(@vtpClear[0] + 4, #VTP_CLEAR_G)
  PokeL(@vtpClear[0] + 8, #VTP_CLEAR_B)
  PokeL(@vtpClear[0] + 12, #VTP_CLEAR_A)
  PokeL(@vtpPush[0] + 0, #VTP_F_ONE)     ; red
  PokeL(@vtpPush[0] + 4, #VTP_F_ZERO)
  PokeL(@vtpPush[0] + 8, #VTP_F_ZERO)
  PokeL(@vtpPush[0] + 12, #VTP_SOURCE_ALPHA)

  rpbi\sType = #VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO
  rpbi\renderPass = rp
  rpbi\framebuffer = fb
  rpbi\renderArea\extent\width = #VTP_VIEW_W
  rpbi\renderArea\extent\height = #VTP_VIEW_H
  rpbi\clearValueCount = 1
  rpbi\pClearValues = @vtpClear[0]

  bi\sType = #VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO
  bi\flags = #VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT
  If vkBeginCommandBuffer(cmd, @bi) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_RECORD)
  EndIf
  bufHandle = buf
  bufOffset = 0
  vkCmdBeginRenderPass(cmd, @rpbi, #VK_SUBPASS_CONTENTS_INLINE)
  vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeA)
  vkCmdBindVertexBuffers(cmd, 0, 1, @bufHandle, @bufOffset)
  vkCmdPushConstants(cmd, layA, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @vtpPush[0])
CompilerIf #VTP_INDEXED_PROOF
  vkCmdBindIndexBuffer(cmd, ibuf, 4, #VK_INDEX_TYPE_UINT16)
  vkCmdDrawIndexed(cmd, 3, 1, 1, 0, 0)
CompilerElse
  vkCmdDraw(cmd, 3, 1, 0, 0)
CompilerEndIf
  vkCmdEndRenderPass(cmd)
  rc = vkEndCommandBuffer(cmd)
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_CB_TEXT, AnvilVkCommandBufferFailureText(cmd))
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_RECORD)
  EndIf

  fci\sType = #VK_STRUCTURE_TYPE_FENCE_CREATE_INFO
  If vkCreateFence(dev, @fci, 0, @fence) <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf

  vtpPut(#VTP_S_BIN_BEFORE, V3dBinJobs())
  vtpPut(#VTP_S_RENDER_BEFORE, V3dRenderJobs())
  vtpPut(#VTP_S_GUARD_BEFORE, vtpSum(#VTP_SURFACE, #VTP_SCREEN_BYTES))

  cbHandle = cmd
  si\sType = #VK_STRUCTURE_TYPE_SUBMIT_INFO
  si\commandBufferCount = 1
  si\pCommandBuffers = @cbHandle
  t0 = Ticks()
  rc = vkQueueSubmit(queue, 1, @si, fence)
  vtpPut(#VTP_S_SUBMIT1, rc)
  vtpPut(#VTP_S_US1, (Ticks() - t0) / hz)
  vtpPut(#VTP_S_NATIVE, AnvilVkBackendNativeError())
  If rc <> #VK_SUCCESS
    vtpPut(#VTP_S_DETAIL, rc)
    vtpPut(#VTP_S_DETAIL2, AnvilVkBackendNativeError())
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_SUBMIT)
  EndIf
  fenceArray = fence
  rc = vkWaitForFences(dev, 1, @fenceArray, 1, 2000000000)
  vtpPut(#VTP_S_WAIT1, rc)
  If rc <> #VK_SUCCESS
    NeonShutdown()
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf
  vtpPut(#VTP_S_LAYOUT_AFTER, AnvilVkImageLayout(img))
  vtpPut(#VTP_S_SHREC, AnvilVkV3dLastShaderRecord())

  vtpPut(#VTP_S_P1_IN0, vtpPixel(imgBase, imagePitch, #VTP_IN0X, #VTP_IN0Y))
  vtpPut(#VTP_S_P1_IN1, vtpPixel(imgBase, imagePitch, #VTP_IN1X, #VTP_IN1Y))
  vtpPut(#VTP_S_P1_IN2, vtpPixel(imgBase, imagePitch, #VTP_IN2X, #VTP_IN2Y))
  vtpPut(#VTP_S_P1_OUT0, vtpPixel(imgBase, imagePitch, #VTP_OUT0X, #VTP_OUT0Y))
  vtpPut(#VTP_S_P1_OUT1, vtpPixel(imgBase, imagePitch, #VTP_OUT1X, #VTP_OUT1Y))
  vtpPut(#VTP_S_P1_OUT2, vtpPixel(imgBase, imagePitch, #VTP_OUT2X, #VTP_OUT2Y))

  ; ------------------------------------------------------------------
  ;  7. PASS TWO: the per-vertex-colour triangle, over the same image.
  ; ------------------------------------------------------------------
  vtpStep(7)
  vkResetFences(dev, 1, @fenceArray)
  vkResetCommandBuffer(cmd, 0)
  If vkBeginCommandBuffer(cmd, @bi) = #VK_SUCCESS
    vkCmdBeginRenderPass(cmd, @rpbi, #VK_SUBPASS_CONTENTS_INLINE)
    vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, pipeB)
    vkCmdBindVertexBuffers(cmd, 0, 1, @bufHandle, @bufOffset)
CompilerIf #VTP_INDEXED_PROOF
    vkCmdBindIndexBuffer(cmd, ibuf, 4, #VK_INDEX_TYPE_UINT16)
    vkCmdDrawIndexed(cmd, 3, 1, 1, 0, 0)
CompilerElse
    vkCmdDraw(cmd, 3, 1, 0, 0)
CompilerEndIf
    vkCmdEndRenderPass(cmd)
    rc = vkEndCommandBuffer(cmd)
    If rc <> #VK_SUCCESS
      vtpPut(#VTP_S_STATUS2, #VTP_ERR_RECORD)
    Else
      t0 = Ticks()
      rc = vkQueueSubmit(queue, 1, @si, fence)
      vtpPut(#VTP_S_SUBMIT2, rc)
      vtpPut(#VTP_S_US2, (Ticks() - t0) / hz)
      If rc <> #VK_SUCCESS
        vtpPut(#VTP_S_STATUS2, #VTP_ERR_SUBMIT)
      Else
        rc = vkWaitForFences(dev, 1, @fenceArray, 1, 2000000000)
        vtpPut(#VTP_S_WAIT2, rc)
        If rc <> #VK_SUCCESS
          vtpPut(#VTP_S_STATUS2, #VTP_ERR_FENCE)
        Else
          vtpPut(#VTP_S_DETAIL, V3dBclStartAddr())
          vtpPut(#VTP_S_DETAIL2, V3dBclBytes())
          viewportPacket = vtpFindOddViewportPackets(V3dBclStartAddr(), V3dBclBytes())
CompilerIf #VTP_INDEXED_PROOF
          indexPacket = vtpFindIndexedPackets(V3dBclStartAddr(), V3dBclBytes(), iaddr + 4, 12)
CompilerEndIf
          vtpPut(#VTP_S_P2_IN0, vtpPixel(imgBase, imagePitch, #VTP_IN0X, #VTP_IN0Y))
          vtpPut(#VTP_S_P2_IN1, vtpPixel(imgBase, imagePitch, #VTP_IN1X, #VTP_IN1Y))
          vtpPut(#VTP_S_P2_IN2, vtpPixel(imgBase, imagePitch, #VTP_IN2X, #VTP_IN2Y))
          vtpPut(#VTP_S_P2_OUT0, vtpPixel(imgBase, imagePitch, #VTP_OUT0X, #VTP_OUT0Y))
          vtpPut(#VTP_S_P2_OUT1, vtpPixel(imgBase, imagePitch, #VTP_OUT1X, #VTP_OUT1Y))
          vtpPut(#VTP_S_P2_OUT2, vtpPixel(imgBase, imagePitch, #VTP_OUT2X, #VTP_OUT2Y))
          badIn = 0
          badOut = 0
          If vtpGet(#VTP_S_P2_IN0) <> #VTP_GREEN_WORD : badIn = badIn + 1 : EndIf
          If vtpGet(#VTP_S_P2_IN1) <> #VTP_GREEN_WORD : badIn = badIn + 1 : EndIf
          If vtpGet(#VTP_S_P2_IN2) <> #VTP_GREEN_WORD : badIn = badIn + 1 : EndIf
          If vtpGet(#VTP_S_P2_OUT0) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
          If vtpGet(#VTP_S_P2_OUT1) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
          If vtpGet(#VTP_S_P2_OUT2) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
          If viewportPacket < 0 Or (#VTP_INDEXED_PROOF <> 0 And indexPacket < 0)
            vtpPut(#VTP_S_STATUS2, #VTP_ERR_VIEWPORT_PACKET)
          ElseIf badIn <> 0
            vtpPut(#VTP_S_STATUS2, #VTP_ERR_PIXELS_IN)
          ElseIf badOut <> 0
            vtpPut(#VTP_S_STATUS2, #VTP_ERR_PIXELS_OUT)
          Else
            vtpPut(#VTP_S_STATUS2, #VTP_OK)
          EndIf
        EndIf
      EndIf
    EndIf
  Else
    vtpPut(#VTP_S_STATUS2, #VTP_ERR_RECORD)
  EndIf
CompilerEndIf

  vtpPut(#VTP_S_BIN_AFTER, V3dBinJobs())
  vtpPut(#VTP_S_RENDER_AFTER, V3dRenderJobs())
  vtpPut(#VTP_S_BIN_OOM, V3dBinOomCount())
  vtpPut(#VTP_S_BIN_ERRSTAT, V3dBinErrStat())
  vtpPut(#VTP_S_RENDER_ERRSTAT, V3dRenderErrStat())
  vtpPut(#VTP_S_MMU_FAULTS, V3dMmuFaultsNow())
  vtpPut(#VTP_S_MMU_VIOADDR, V3dMmuVioAddrNow())
  vtpPut(#VTP_S_GUARD_AFTER, vtpSum(#VTP_SURFACE, #VTP_SCREEN_BYTES))
  vtpPut(#VTP_S_DRAWS, avkBackendDraws())

  ; ------------------------------------------------------------------
  ;  8. Present what is on the image now - the second triangle.
  ; ------------------------------------------------------------------
  vtpStep(8)
  rc = DisplayAdopt(#VTP_DSI_SCAN, #VTP_PANEL_PITCH, #VTP_PANEL_W, #VTP_PANEL_H, 32)
  vtpPut(#VTP_S_DISPLAY_ERR, DisplayLastError())
  If rc = #DSP_OK
CompilerIf #VTP_LIST_PROOF
    ; The scene is already complete in the V3D attachment. Present it as one
    ; DMA copy; a CPU DisplayBlit fallback remains correct but is a failed
    ; acceleration proof and is recorded in slot 57.
    dmaScratch = @vtpDmaScratch[0] + 255
    dmaScratch = dmaScratch - (dmaScratch % 256)
    If DmaSetScratch(dmaScratch, 512) <> 0
      If DisplayDmaBind() <> 0
        If DmaInit() <> 0
          DisplayDmaReadback(1)
          DisplayUseDma(1)
        EndIf
      EndIf
    EndIf
    dmaBefore = DisplayDmaOps()
CompilerEndIf
    DisplayBlit(imgBase, imagePitch, 0, 0, #VTP_VIEW_W, #VTP_VIEW_H)
CompilerIf #VTP_LIST_PROOF
    vtpPut(#VTP_S_CB_TEXT, DisplayDmaOps() - dmaBefore)
    DisplayUseDma(0)
CompilerEndIf
    DisplayFlush()
    vtpPut(#VTP_S_PRESENT, #VTP_P_OK)
    delay(#VTP_SHOW_MS)
  Else
    vtpPut(#VTP_S_PRESENT, #VTP_P_ADOPT_REFUSED)
  EndIf

  ; ------------------------------------------------------------------
  ;  9. Ordered teardown, then hand the V3D MMU back.
  ; ------------------------------------------------------------------
  vtpStep(9)
  vkDeviceWaitIdle(dev)
  vkDestroyFence(dev, fence, 0)
  vkDestroyPipeline(dev, pipeA, 0)
  vkDestroyPipeline(dev, pipeB, 0)
CompilerIf #VTP_LIST_PROOF
  vkDestroyPipeline(dev, pipeC, 0)
CompilerEndIf
  vkDestroyPipelineLayout(dev, layA, 0)
  vkDestroyPipelineLayout(dev, layB, 0)
  vkDestroyShaderModule(dev, vsA, 0)
  vkDestroyShaderModule(dev, fsA, 0)
  vkDestroyShaderModule(dev, vsB, 0)
  vkDestroyShaderModule(dev, fsB, 0)
  vkDestroyFramebuffer(dev, fb, 0)
  vkDestroyRenderPass(dev, rp, 0)
  vkDestroyImageView(dev, view, 0)
CompilerIf #VTP_INDEXED_PROOF
  vkDestroyBuffer(dev, ibuf, 0)
  vkFreeMemory(dev, imem, 0)
CompilerEndIf
  vkDestroyBuffer(dev, buf, 0)
  vkFreeMemory(dev, bmem, 0)
  vkDestroyImage(dev, img, 0)
  vkFreeMemory(dev, mem, 0)
  vkDestroyCommandPool(dev, pool, 0)
  vkDestroyDevice(dev, 0)
  vkDestroyInstance(inst, 0)
  NeonShutdown()
  vtpPut(#VTP_S_SHUTDOWN, 1)

  ; ------------------------------------------------------------------
  ;  10. The uniform-colour verdict. Every one of these is a separate
  ;      way to be wrong, and they are checked in the order that makes
  ;      the earliest real cause the one reported.
  ; ------------------------------------------------------------------
  vtpStep(10)
CompilerIf #VTP_LIST_PROOF
  If vtpGet(#VTP_S_BIN_AFTER) <> (vtpGet(#VTP_S_BIN_BEFORE) + 1) Or vtpGet(#VTP_S_RENDER_AFTER) <> (vtpGet(#VTP_S_RENDER_BEFORE) + 1)
    ProcedureReturn vtpStop(#VTP_ERR_NO_JOBS)
  EndIf
  If vtpGet(#VTP_S_STATUS2) <> #VTP_OK
    ProcedureReturn vtpStop(vtpGet(#VTP_S_STATUS2))
  EndIf
  If vtpGet(#VTP_S_BIN_OOM) <> 0 Or (vtpGet(#VTP_S_BIN_ERRSTAT) & $FFFFEFFF) <> 0 Or (vtpGet(#VTP_S_RENDER_ERRSTAT) & $FFFFEFFF) <> 0 Or vtpGet(#VTP_S_MMU_FAULTS) <> 0 Or vtpGet(#VTP_S_NATIVE) <> 0 Or vtpGet(#VTP_S_FAULT_COUNT) <> 0
    ProcedureReturn vtpStop(#VTP_ERR_V3D_FAULT)
  EndIf
  If vtpGet(#VTP_S_GUARD_AFTER) <> vtpGet(#VTP_S_GUARD_BEFORE)
    ProcedureReturn vtpStop(#VTP_ERR_GUARD_CHANGED)
  EndIf
  If vtpGet(#VTP_S_PIPE_A) <> (drawsBefore + #VTP_LIST_DRAWS)
    ProcedureReturn vtpStop(#VTP_ERR_NO_JOBS)
  EndIf
  If vtpGet(#VTP_S_LAYOUT_AFTER) <> #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL Or vtpGet(#VTP_S_SHUTDOWN) <> 1
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf
  ; DisplayLastError carries the display API's return code; #DSP_OK is the
  ; positive value 1, not the Vulkan convention of zero success.
  If vtpGet(#VTP_S_PRESENT) <> #VTP_P_OK Or vtpGet(#VTP_S_DISPLAY_ERR) <> #DSP_OK Or vtpGet(#VTP_S_CB_TEXT) <> 1
    ProcedureReturn vtpStop(#VTP_ERR_PRESENT)
  EndIf
  ProcedureReturn vtpStop(#VTP_OK)
CompilerElse
  If vtpGet(#VTP_S_BIN_AFTER) <= vtpGet(#VTP_S_BIN_BEFORE) Or vtpGet(#VTP_S_RENDER_AFTER) <= vtpGet(#VTP_S_RENDER_BEFORE)
    ProcedureReturn vtpStop(#VTP_ERR_NO_JOBS)
  EndIf
  If vtpGet(#VTP_S_BIN_OOM) <> 0 Or vtpGet(#VTP_S_MMU_FAULTS) <> 0
    ProcedureReturn vtpStop(#VTP_ERR_V3D_FAULT)
  EndIf
  If vtpGet(#VTP_S_GUARD_AFTER) <> vtpGet(#VTP_S_GUARD_BEFORE)
    ProcedureReturn vtpStop(#VTP_ERR_GUARD_CHANGED)
  EndIf
  badIn = 0
  badOut = 0
  If vtpGet(#VTP_S_P1_IN0) <> #VTP_RED_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_IN1) <> #VTP_RED_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_IN2) <> #VTP_RED_WORD : badIn = badIn + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT0) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT1) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
  If vtpGet(#VTP_S_P1_OUT2) <> #VTP_CLEAR_WORD : badOut = badOut + 1 : EndIf
  If badIn <> 0
    ProcedureReturn vtpStop(#VTP_ERR_PIXELS_IN)
  EndIf
  If badOut <> 0
    ProcedureReturn vtpStop(#VTP_ERR_PIXELS_OUT)
  EndIf
  If vtpGet(#VTP_S_LAYOUT_AFTER) <> #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
    ProcedureReturn vtpStop(#VTP_ERR_FENCE)
  EndIf
  ProcedureReturn vtpStop(#VTP_OK)
CompilerEndIf
EndProcedure
