# Neon canvas port to Vulkan

Include `neon_vk_port.pi4` after `neon.pi4`, and include
`neon_vk_sprite_port.pi4` after the Vulkan chrome renderer. Enable floating
point and select the existing Vulkan lifecycle before drawing. These adapters
convert float canvas coordinates and RGBA colors to Anvil's integer Neon and
Vulkan chrome primitives. They do not select a board backend or present a frame.

| Restored Neon interface | Anvil Vulkan route | This adapter |
| --- | --- | --- |
| `DrawGLBox` and `Neon_Box` | `Neon_Box` → `NeonVkChromeBox` | `NeonVkPortBox` converts float coordinates, color, `Scaled`, and `IgnoreCamera`. |
| `DrawGLPolygon` | `NeonFanBegin/Point/End` or `NeonLinesBegin/Line/End` → Vulkan chrome geometry | `NeonVkPortPolygon` keeps center/radii, side count, fill/outline, color, canvas and camera order. |
| `CreateGLStaticLines` and `DrawGLStaticLines` | `NeonLinesBegin/Line/End` → Vulkan chrome line list | `NeonVkPortStaticLines` draws an interleaved float x/y buffer in virtual-canvas coordinates. |
| `Neon_ScissorSet/Clear` | `Neon_ScissorSet/Clear` → Vulkan scissor | `NeonVkPortScissorSet/Clear` converts virtual-canvas bounds. |
| Frame clear and buffer flip | `NeonFrameBegin/End` → configured Vulkan lifecycle; completed frame goes to the existing present record | `NeonVkPortFrameBegin/End` converts clear color and preserves return codes. |
| `GetGLTextWidth`, `Neon_Text`, `Neon_TextRight/Centre` | `Neon_TextWidth`, `Neon_Text`, and the Vulkan font callbacks | `NeonVkPortTextWidth/Text/TextRight/TextCentre` keep float position and RGBA arguments. |
| `DrawGLSprite` | `NeonVkChromeImageSpriteDrawTransformId` and image registration | `NeonVkPortSpriteUpload/Sprite/Clear` keep crop, tint, angle, scale, and camera order through an explicit image reference. |
| `BeginBatch/AddBatchedSprite/EndBatch` | `NeonVkChromeSpriteBatchBegin/Add/End` | `NeonVkPortSpriteBatchBegin/Add/End` retain one uploaded image reference and ordered full-image sprite calls. |
| `InitParticleEngine/ClearParticles/AddParticle/RenderParticles` | `NeonVkChromeParticlesPrepare/DrawPrepared` | `NeonVkPortParticleInit/Clear/Add/ParticlesPrepare/ParticlesDrawPrepared` retain the ordered list and issue one Vulkan draw after explicit pre-frame preparation. |

Call `NeonVkPortCanvas(canvasWidth, canvasHeight, targetWidth, targetHeight)`
after the Vulkan render target is created. Target dimensions are its logical
framebuffer extent; the adapter maps the full virtual canvas to that extent.
`NeonVkPortCamera(x, y, zoom)` uses the desktop box transform: subtract camera
position, zoom around the center of the selected coordinate space, then map
to target pixels. Pass `Scaled=1, IgnoreCamera=1` for application chrome.
Rectangles round both edges to pixels so adjacent edges stay aligned.

Text uses a NUL-terminated UTF-8 pointer and one of Anvil's four Neon font
slots; a desktop `GLFont` pointer cannot cross this interface. The text
wrappers use the installed Vulkan measurement callback so width and draw share
the same font metrics. They refuse virtual-canvas stretch or camera zoom other
than 1.0 because the current font draw callback cannot scale glyph geometry
by an arbitrary ratio. Text translation and alignment remain supported.

A desktop `GLSprite` texture handle cannot cross this interface. Upload a
tightly packed RGBA or BGRA buffer into one of the Vulkan chrome image slots
before drawing. A successful upload publishes a `NeonVkPortSpriteRef` with its
image generation; a stale reference is refused. The sprite wrapper interprets
`SrcX=-1` as the full image, requires integral crop edges, and rejects a crop
outside the uploaded image. It converts radians and camera zoom to Q16 for
the existing Vulkan transform, whose CORDIC rotation approximates the desktop
float trigonometry around the cropped rectangle's
center. Rotated sprites require uniform canvas scaling across both axes;
unrotated sprites may use different horizontal and vertical scale factors.
Coordinates and dimensions are rounded to
whole target pixels; subpixel geometry and fractional source crops are not
represented by this renderer. Uploaded rows are top-down: the crop's top V
coordinate samples its top row, matching Neon's Linux sprite UV branch. A
Windows OpenGL texture import whose rows are bottom-up needs a vertical row
flip before upload.

`NeonVkPortPolygon` rounds each generated vertex to a target pixel. Solid
polygons use a center fan with the first perimeter point repeated; outlines
connect each perimeter point to the next with one-pixel Vulkan line quads.
It accepts 3–2048 sides. Larger shapes return
`#NEON_VK_PORT_ERR_GEOMETRY_CAPACITY` before starting a path. A side count
below three is a no-op, as in `DrawGLPolygon`.

`NeonVkPortStaticLines` takes a caller-owned pointer to interleaved float
`x,y` values plus a vertex count. The pointer is read during the call; this
does not create a persistent GPU mesh or accept a desktop `GLStaticMesh`
handle. Coordinates use the virtual canvas and ignore the camera, matching
`CreateGLStaticLines`. A positive `LimitVertices` truncates the list; an
unmatched final vertex is ignored as with `GL_LINES`. More than 4096 effective
vertices are refused before reading the buffer. Lines are one-pixel Vulkan
quads, so edge coverage can differ from OpenGL rasterization.

`NeonVkPortSpriteBatchBegin` binds one uploaded image reference. Add uses
target/window-space position and size, full-image UVs, tint, radians and the
same center-based camera/rotation order as the desktop batch call. End appends
the ordered group to the frame. The underlying retained group supports 128
sprites; an excess returns a capacity error. It emits one Vulkan draw record
per sprite rather than the desktop batcher's single draw call. Image
replacement and clear are refused while a port batch is active; the Vulkan
renderer also disallows image replacement during an open frame. A failed End
keeps the group active for retry. Begin can discard that group and start a
fresh one, matching the desktop batch count reset. The port's FrameEnd refuses
an unfinished group so it cannot disappear without an explicit End.

Include `neon_vk_sprite_asset.pi4` after the sprite adapter and the selected
board's `HwFile*` implementation to load pixels. `NeonVkPortSpriteLoadRGBA`
accepts a caller-owned, length-delimited, tightly packed, top-down RGBA
buffer. It applies a PureBasic-layout `RGB()` color key (`$00BBGGRR`, or `-1`
to disable) and can fill a one-byte-per-pixel alpha mask. Matching key pixels
become transparent black; other pixels retain their straight alpha. The source
and output can be the same buffer or disjoint buffers; a supplied mask must be disjoint from
both, and from encoded input. `NeonVkPortSpriteLoadMemory` accepts an
encoded buffer with an explicit byte length; `NeonVkPortSpriteLoadFile` reads
it through the board-neutral `HwFileOpen/Size/ReadAt/Close` seam. The caller
must mount storage first and provide both encoded and RGBA buffers. The file
reader handles partial reads and closes before decoding. Neon's intermediate
PureBasic alpha-blend draw can change RGB values on translucent source pixels,
so exact color-key parity for those pixels is not established.

The included decoder accepts only uncompressed Windows BMP with a 40-byte
header and 24-bit BGR or 32-bit BGRA pixels, up to 1024 by 1024 and
4,194,432 encoded bytes. It handles top-down and bottom-up rows and 24-bit
padding. For 32-bit `BI_RGB` it interprets the fourth byte as alpha; assets
that use this byte as padding should be converted to explicit RGBA first.
PNG, JPEG, palette, RLE, and bitfield BMP return an unsupported-format error.
The restored desktop library delegates these formats to PureBasic's selected
image decoders; its repository has no asset files or loading call sites from
which to infer a production format. This subset has a desktop compiler and
emitted-code gate. The Pi 4 [BMP asset proof](../../../docs/evidence/neon-vk-bmp-asset-pi4-20261003/README.md)
passed decoding, color key, alpha mask and an ordered Vulkan draw from a
2×2 in-memory BMP. File loading and larger assets remain unproved on board.

Include `neon_vk_particle_port.pi4` after the canvas port and Vulkan chrome.
Call `NeonVkPortParticleInit(1)` to accept the quantized coordinate path,
then `NeonVkPortParticleAdd` for each desktop
center position, size, radian angle and RGBA color. `NeonVkPortParticleClear`
resets the list. Call `NeonVkPortParticlesPrepare` after the final Add and
camera update, before `NeonVkPortFrameBegin`; call
`NeonVkPortParticlesDrawPrepared` at the former `RenderParticles` position
inside the frame. DrawPrepared reuses the list on later frames. A changed
camera, added particle, or clear requires another Prepare; otherwise a
nonempty draw refuses stale data. Empty draws are no-ops. Prepare validates
and uploads at most 10,000 ordered particles and snapshots the current
`NeonVkPortCamera` values. Particle positions and camera offsets are in
target/window pixels, matching the desktop particle shader's `screenSize`;
virtual-canvas scaling is not applied. The target must match Chrome's logical
extent. Float edges, colors and angles are rounded to integral pixels,
8-bit channels and Q16 radians, so subpixel positions differ from desktop GL.

The adapter owns a fixed CPU list and no Vulkan objects. Chrome creates and
releases its palette and staging resources, and draws the prepared list in
one ordered draw record. The current production Chrome route expands six
vertices per particle on the CPU during DrawPrepared; a future direct GPU
particle path can retain this Prepare/DrawPrepared seam. This is call and
ordering portability, not GPU instancing or throughput parity. The restored
desktop shader uses a square with local corners at ±0.5 while its fragment
mask starts outside radius 0.8, so that source currently gives its square
interior full alpha rather than a feathered circle. The Vulkan route keeps
the square footprint and supports the same source-alpha blending, but raster
edges and rotations remain quantized. The caller must reserve enough Chrome
vertex capacity for six vertices per particle and one draw slot.

The port uses explicit `NeonVkPort*` names. PureMetalForge does not compile
the desktop procedures' optional parameter syntax or by-value `Text.s` copy
in this target, so a same-name include would hide required resource and call
changes. Font slots, uploaded sprite references, and static-line buffers
must be bound through the Anvil interfaces above.

The Pi 4 hardware frame reports are
`docs/evidence/neon-vk-port-frame-pi4-20261003/README.md` (box, one glyph,
cropped sprite) and `docs/evidence/neon-vk-port-geometry-pi4-20261003/README.md`
(polygon fill/outline, static line, two-sprite batch). These are offscreen
application-level proofs. The resident Pi 4 console includes Vulkan chrome,
but does not include this port adapter or a complete Neon-authored application.
Broader image decoding, desktop font handles, UI layout/events, viewport
presentation, and particle throughput parity remain to be ported.

Letterboxed or cropped viewports require their own viewport mapping; these
adapters assume the full logical target. The default native Neon path and
compile-time Vulkan backend selection are unchanged.

The Pi 4 board proof in `docs/evidence/neon-vk-port-frame-pi4-20261003/`
exercised this adapter through the real V3D Vulkan backend. It checked a
rectangle, text and a cropped sprite in one offscreen frame. The report and
its checker are saved there; this is a Pi 4 proof, not an assertion of other
board acceleration.
