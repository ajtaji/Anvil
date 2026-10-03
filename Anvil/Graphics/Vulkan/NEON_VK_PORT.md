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

The port uses explicit `NeonVkPort*` names. PureMetalForge does not compile
the desktop procedures' optional parameter syntax or by-value `Text.s` copy
in this target, so a same-name include would hide required resource and call
changes. Font slots, uploaded sprite references, and static-line buffers
must be bound through the Anvil interfaces above.

Letterboxed or cropped viewports require their own viewport mapping; these
adapters assume the full logical target. The default native Neon path and
compile-time Vulkan backend selection are unchanged.

The Pi 4 board proof in `docs/evidence/neon-vk-port-frame-pi4-20261003/`
exercised this adapter through the real V3D Vulkan backend. It checked a
rectangle, text and a cropped sprite in one offscreen frame. The report and
its checker are saved there; this is a Pi 4 proof, not an assertion of other
board acceleration.
