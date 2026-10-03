# Neon canvas port to Vulkan

Include `neon_vk_port.pi4` after `neon.pi4`, and include
`neon_vk_sprite_port.pi4` after the Vulkan chrome renderer. Enable floating
point and select the existing Vulkan lifecycle before drawing. These adapters
convert float canvas coordinates and RGBA colors to Anvil's integer Neon and
Vulkan chrome primitives. They do not select a board backend or present a frame.

| Restored Neon interface | Anvil Vulkan route | This adapter |
| --- | --- | --- |
| `DrawGLBox` and `Neon_Box` | `Neon_Box` → `NeonVkChromeBox` | `NeonVkPortBox` converts float coordinates, color, `Scaled`, and `IgnoreCamera`. |
| `Neon_ScissorSet/Clear` | `Neon_ScissorSet/Clear` → Vulkan scissor | `NeonVkPortScissorSet/Clear` converts virtual-canvas bounds. |
| Frame clear and buffer flip | `NeonFrameBegin/End` → configured Vulkan lifecycle; completed frame goes to the existing present record | `NeonVkPortFrameBegin/End` converts clear color and preserves return codes. |
| `GetGLTextWidth`, `Neon_Text`, `Neon_TextRight/Centre` | `Neon_TextWidth`, `Neon_Text`, and the Vulkan font callbacks | `NeonVkPortTextWidth/Text/TextRight/TextCentre` keep float position and RGBA arguments. |
| `DrawGLSprite` | `NeonVkChromeImageSpriteDrawTransformId` and image registration | `NeonVkPortSpriteUpload/Sprite/Clear` keep crop, tint, angle, scale, and camera order through an explicit image reference. |

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

Letterboxed or cropped viewports require their own viewport mapping; these
adapters assume the full logical target. The default native Neon path and
compile-time Vulkan backend selection are unchanged.
