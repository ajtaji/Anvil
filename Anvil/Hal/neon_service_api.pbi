; SPDX-License-Identifier: MIT
; Pure payload/monitor contract. No device, driver or renderer implementation.
; Candidate query uses console slot38 at service ABI1.8; old tables refuse.
; This header does not imply that a resident provider has been installed.
#NEON_SERVICE_SLOT = 38
#NEON_SERVICE_ABI_MAJOR = 1
#NEON_SERVICE_ABI_MINOR = 8
#NEON_SERVICE_MAGIC = $315350414E4F454E
#NEON_SERVICE_MAJOR = 1
#NEON_SERVICE_MINOR = 0
#NEON_SERVICE_VULKAN = 1
#NEON_SERVICE_FONT_REFS = 2
#NEON_SERVICE_SPRITES = 4
#NEON_SERVICE_FONT_BYTES = 8
#NEON_SERVICE_PARTICLES = 16
#NEON_SERVICE_MAPPING = 32
#NEON_SERVICE_MAPPING_MINOR = 4
#NEON_SERVICE_FONT_SPACING = 64
#NEON_SERVICE_FONT_SPACING_MINOR = 5
#NEON_SERVICE_FONT_SNAP = 128
#NEON_SERVICE_FONT_SNAP_MINOR = 6
#NEON_SERVICE_FONT_CONTROLS=256
#NEON_SERVICE_FONT_CONTROLS_MINOR=7
#NEON_SERVICE_FONT_DERIVE=512
#NEON_SERVICE_FONT_DERIVE_MINOR=8
#NEON_SERVICE_FONT_DERIVE_CREATE=37
Structure NeonServiceFontDeriveRequest Align #PB_Structure_AlignC
  font.i : role.i : pixels.i
EndStructure
#NEON_SERVICE_FONT_CONTROLS_SET=36
Structure NeonServiceFontControlsRequest Align #PB_Structure_AlignC
  font.i : mode.i
EndStructure
#NEON_SERVICE_FONT_SNAP_SET = 35
Structure NeonServiceFontSnapRequest Align #PB_Structure_AlignC
  font.i : enabled.i
EndStructure
#NEON_SERVICE_FONT_ADVANCE = 34
Structure NeonServiceFontAdvanceRequest Align #PB_Structure_AlignC
  font.i : advanceQ16.i
EndStructure
#NEON_SERVICE_MAX_STATIC_LINE_VERTICES = 262144
#NEON_SERVICE_PARTICLE_MINOR = 3
#NEON_SERVICE_MAX_PARTICLES = 10000
#NEON_SERVICE_PARTICLE_RECORD_BYTES = 32
#NEON_SERVICE_FONT_BYTES_MINOR = 2
#NEON_SERVICE_MAX_FONT_ASSETS = 4
#NEON_SERVICE_MAX_FONT_BYTES = 1048576
; Additive protocol feature. Basic vector/font clients still accept minor0.
#NEON_SERVICE_SPRITE_MINOR = 1
#NEON_SERVICE_MAX_SPRITES = 16
#NEON_SERVICE_MAX_SPRITE_DIM = 2048
#NEON_SERVICE_MAX_SPRITE_BYTES = 16777216
#NEON_SERVICE_MAX_SPRITE_BATCH = 128
#NEON_SERVICE_ERR_ARGS = -21500
#NEON_SERVICE_ERR_ABI = -21501
#NEON_SERVICE_ERR_UNBOUND = -21502
#NEON_SERVICE_ERR_STATE = -21503
#NEON_SERVICE_ERR_PROVIDER = -21504
#NEON_SERVICE_ERR_BUSY = -21505
#NEON_SERVICE_ERR_STALE = -21506
#NEON_SERVICE_ERR_CAPACITY = -21507
#NEON_SERVICE_ERR_FORMAT = -21508
#NEON_SERVICE_QUERY = 0
#NEON_SERVICE_OPEN = 1
#NEON_SERVICE_CLOSE = 2
#NEON_SERVICE_BEGIN = 3
#NEON_SERVICE_END = 4
#NEON_SERVICE_ABORT = 5
#NEON_SERVICE_BOX = 6
#NEON_SERVICE_TEXT = 7
#NEON_SERVICE_WIDTH = 8
#NEON_SERVICE_HEIGHT = 9
#NEON_SERVICE_POLYGON = 10
#NEON_SERVICE_PREPARE = 11
#NEON_SERVICE_FONT_REGISTER = 12
#NEON_SERVICE_ERROR = 13
#NEON_SERVICE_SPRITE_LIMITS = 14
#NEON_SERVICE_SPRITE_UPLOAD = 15
#NEON_SERVICE_SPRITE_CLEAR = 16
#NEON_SERVICE_SPRITE_DRAW = 17
#NEON_SERVICE_CAMERA = 18
#NEON_SERVICE_SPRITE_BATCH_BEGIN = 19
#NEON_SERVICE_SPRITE_BATCH_ADD = 20
#NEON_SERVICE_SPRITE_BATCH_END = 21
#NEON_SERVICE_FONT_LOAD = 22
#NEON_SERVICE_FONT_UNLOAD = 23
#NEON_SERVICE_PARTICLE_LIMITS = 24
#NEON_SERVICE_PARTICLE_PREPARE = 25
#NEON_SERVICE_PARTICLE_DRAW = 26

; Additive virtual canvas, clipping and mapped vector/text operations.
#NEON_SERVICE_CANVAS = 27
#NEON_SERVICE_SCISSOR_SET = 28
#NEON_SERVICE_SCISSOR_CLEAR = 29
#NEON_SERVICE_BOX_MAPPED = 30
#NEON_SERVICE_POLYGON_MAPPED = 31
#NEON_SERVICE_TEXT_MAPPED = 32
#NEON_SERVICE_STATIC_LINES = 33
Structure NeonServiceCanvasRequest Align #PB_Structure_AlignC
  width.i : height.i
EndStructure
Structure NeonServiceScissorRequest Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f
EndStructure
Structure NeonServiceMappedBoxRequest Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f
  r.f : g.f : b.f : a.f
  scaled.i : ignoreCamera.i
EndStructure
Structure NeonServiceMappedPolygonRequest Align #PB_Structure_AlignC
  x.f : y.f : rx.f : ry.f
  sides.i
  r.f : g.f : b.f : a.f
  solid.i : scaled.i : ignoreCamera.i
EndStructure
Structure NeonServiceMappedTextRequest Align #PB_Structure_AlignC
  font.i
  x.f : y.f
  text.i
  r.f : g.f : b.f : a.f
  scaled.i : ignoreCamera.i
EndStructure
; XY float32 pairs are borrowed for this immediate draw only. No mesh owner.
Structure NeonServiceStaticLinesRequest Align #PB_Structure_AlignC
  data.i : sourceBytes.i : vertexCount.i
  r.f : g.f : b.f : a.f
  limitVertices.i
EndStructure

Structure NeonServiceParticleLimits Align #PB_Structure_AlignC
  maxCount.i : recordBytes.i : coordinateFractionBits.i
EndStructure
Structure NeonServiceParticlePrepareRequest Align #PB_Structure_AlignC
  data.i : sourceBytes.i : count.i
EndStructure

; Source bytes are borrowed during Load only; Core copies into an empty slot.
Structure NeonServiceFontLoadRequest Align #PB_Structure_AlignC
  data.i : bytes.i : role.i : pixels.i
EndStructure
Structure NeonServiceFontUnloadRequest Align #PB_Structure_AlignC
  font.i
EndStructure

Structure NeonServiceSurface Align #PB_Structure_AlignC
  bytes.i
  logicalW.i
  logicalH.i
  flags.i
  maxFonts.i
EndStructure

; Sprite uploads borrow tightly packed pixel bytes only for the call. A
; successful upload returns a new positive opaque handle; replacement/clear
; invalidates the old handle. Failed replacement retains its previous owner.
Structure NeonServiceSpriteLimits Align #PB_Structure_AlignC
  slots.i : maxDimension.i : maxUploadBytes.i : maxBatch.i
EndStructure
Structure NeonServiceSpriteUploadRequest Align #PB_Structure_AlignC
  slot.i : pixels.i : sourceBytes.i : width.i : height.i : bgra.i
EndStructure
Structure NeonServiceSpriteHandleRequest Align #PB_Structure_AlignC
  handle.i
EndStructure
Structure NeonServiceSpriteDrawRequest Align #PB_Structure_AlignC
  handle.i
  x.f : y.f : angle.f : scale.f
  r.f : g.f : b.f : a.f
  scaled.i
  srcX.f : srcY.f : srcW.f : srcH.f
  ignoreCamera.i
EndStructure
Structure NeonServiceCameraRequest Align #PB_Structure_AlignC
  x.f : y.f : zoom.f : reserved.l
EndStructure
Structure NeonServiceSpriteBatchRequest Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f : angle.f
  r.f : g.f : b.f : a.f : reserved.l
  ignoreCamera.i
EndStructure

; Query copies exactly this versioned prefix into a caller-owned48-byte record.
; Dispatch signature: .i(op.i,context.i,request.i,bytes.i); QUERY uses context0.
; Record types below define exact request sizes. The function remains valid in the
; current resident monitor. Open returns a positive opaque context or an error.
; Failed End/Abort/Close retains ownership until successful Abort or Close.
; End includes physical presentation; it cannot consume a frame before success.
; Width/height return nonnegative signed Q16 metrics or a negative status;
; every operation has an integer ABI result. Draw coordinates remain float32.
; FontRegister binds an already loaded face; no driver or font bytes are lent.
Structure NeonServiceApi Align #PB_Structure_AlignC
  magic.q
  major.l
  minor.l
  bytes.i
  flags.i
  maxFonts.i
  dispatch.i
EndStructure
Structure NeonServiceColour Align #PB_Structure_AlignC
  r.f : g.f : b.f : a.f
EndStructure
Structure NeonServiceBoxRequest Align #PB_Structure_AlignC
  x.f : y.f : w.f : h.f
  r.f : g.f : b.f : a.f
EndStructure
Structure NeonServiceTextRequest Align #PB_Structure_AlignC
  font.i
  x.f : y.f
  text.i
  r.f : g.f : b.f : a.f
EndStructure
Structure NeonServiceMeasureRequest Align #PB_Structure_AlignC
  font.i : text.i
EndStructure
Structure NeonServicePolygonRequest Align #PB_Structure_AlignC
  x.f : y.f : rx.f : ry.f
  sides.i
  r.f : g.f : b.f : a.f
  solid.i
EndStructure
Structure NeonServiceFontRequest Align #PB_Structure_AlignC
  slot.i : role.i : pixels.i
EndStructure

; Additive offscreen ownership. Tokens are context-checked values, never GPU
; handles or kernel addresses. Binding changes coordinate space while idle;
; ordinary Begin/End then record/complete offscreen frames without display.
#NEON_SERVICE_TARGETS = 1024
#NEON_SERVICE_TARGET_MINOR = 9
; Optional mid-frame binding suspends and later resumes the window frame.
#NEON_SERVICE_TARGET_CONTINUATION = 2048
#NEON_SERVICE_TARGET_CONTINUATION_MINOR = 10
; Preserve a completed offscreen image while recording another section.
#NEON_SERVICE_TARGET_LOAD = 4096
#NEON_SERVICE_TARGET_LOAD_MINOR = 11
#NEON_SERVICE_TARGET_BEGIN_LOAD = 45
#NEON_SERVICE_MAX_TARGETS = 16
#NEON_SERVICE_TARGET_DIMENSION = 2048
#NEON_SERVICE_TARGET_CREATE = 38
#NEON_SERVICE_TARGET_RESIZE = 39
#NEON_SERVICE_TARGET_FREE = 40
#NEON_SERVICE_TARGET_BIND = 41
#NEON_SERVICE_TARGET_UNBIND = 42
#NEON_SERVICE_TARGET_DRAW = 43
#NEON_SERVICE_TARGET_LIMITS = 44
Structure NeonServiceTargetCreateRequest Align #PB_Structure_AlignC
  width.i : height.i : linear.i
EndStructure
Structure NeonServiceTargetResizeRequest Align #PB_Structure_AlignC
  handle.i : width.i : height.i
EndStructure
Structure NeonServiceTargetBindRequest Align #PB_Structure_AlignC
  handle.i : width.i : height.i
EndStructure
Structure NeonServiceTargetLimits Align #PB_Structure_AlignC
  slots.i : maxDimension.i
EndStructure

; Optional full-target CRT composition. Prepare while idle after target End;
; draw during an open window frame. The target's aspect-fit viewport is used.
#NEON_SERVICE_TARGET_RETRO = 8192
#NEON_SERVICE_TARGET_RETRO_MINOR = 12
#NEON_SERVICE_TARGET_RETRO_PREPARE = 46
#NEON_SERVICE_TARGET_RETRO_DRAW = 47
Structure NeonServiceTargetRetroRequest Align #PB_Structure_AlignC
  handle.i : time.f : reserved.l
EndStructure

; Optional caret queries. Text includes its terminal NUL in textBytes (1..4096).
; Caller owns the whole record; result fields change only after success.
; Columns count Unicode scalars. Positions are Q16 source pixels, before mapping.
#NEON_SERVICE_FONT_CARETS = 16384
#NEON_SERVICE_FONT_CARETS_MINOR = 13
#NEON_SERVICE_FONT_CARET_POINT = 48
#NEON_SERVICE_FONT_CARET_HIT = 49
#NEON_SERVICE_FONT_TEXT_X = 50
#NEON_SERVICE_FONT_TEXT_COLUMN = 51
Structure NeonServiceFontCaretRequest Align #PB_Structure_AlignC
  font.i : text.i : textBytes.i : column.i : line.i : xQ16.i
  resultX.i : resultY.i : resultByte.i : resultColumn.i
EndStructure

; Role-font caret queries resolve the current selected face and role size,
; exactly as role text drawing. No persistent font reference is allocated.
#NEON_SERVICE_ROLE_CARETS = 32768
#NEON_SERVICE_ROLE_CARETS_MINOR = 14
