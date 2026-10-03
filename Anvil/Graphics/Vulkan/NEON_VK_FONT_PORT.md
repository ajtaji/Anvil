# Bounded Neon font handles for Anvil Vulkan

`neon_vk_font_port.pi4` is an opt-in bridge for Neon-authored text placement.
Include it after `neon_vk_port.pi4` and `neon_vk_chrome.pi4`. It does not load a
font, select a renderer, or own glyph memory. Bind a caller-owned
`NeonVkPortFontRef` to an already loaded Anvil TrueType slot, one of Neon's four
font channels, and a pixel height. File slots 0–3 and the embedded boot slot 4
are valid only while their bytes remain loaded. The reference records the slot
generation and refuses use after replacement or unload.

The font channel is a size selection for the currently selected face, not a
separate font face. Anvil can hold four file faces and its boot face, but only
one parser face is selected at a time. `NeonVkPortFontWarm` selects the bound
slot and uploads the UTF-8 run **before** `NeonVkPortFrameBegin`. During an open
frame, the text methods refuse another slot or a dirty atlas. A frame using
several pixel heights of one face may warm each run before Begin and draw them
in order. If a needed run was not warmed, the underlying Vulkan text method
refuses the missing glyph rather than rasterizing or uploading inside a frame.

`NeonVkPortFontTextWidth` and `NeonVkPortFontLineHeight` use the same Anvil
TrueType layout metrics as the Vulkan draw path. `NeonVkPortFontTextRight` and
`NeonVkPortFontTextCentre` measure before placing the run. The strings are
NUL-terminated UTF-8 pointers; positions and RGBA colors remain floating-point
arguments to the existing canvas adapter. Unsupported canvas text stretch and
camera zoom are refused by that adapter.

This is not a drop-in `GLFont` implementation. The desktop API creates an
arbitrary named face and point size, maintains one atlas per handle, supports
fixed advances, control-character modes, column-to-x helpers, and page budgets.
None of those controls or arbitrary face creation are represented by this
bounded bridge. A port must load its desired TTF bytes into an Anvil slot and
bind that slot explicitly. Widths may differ from the desktop font because
the face, kerning and raster metrics can differ.

`py -3 tools/neon_vk_font_port_check.py` compiles the production adapter and
executes its emitted A64 under a desk interpreter. The gate checks loaded file
and boot slots, two pixel heights, measured width and line height, right and
centre placement, and refusal of mid-frame prewarm, face switch, dirty atlas,
stale generation and unsupported canvas stretch. The Pi 4
[offscreen board proof](../../../docs/evidence/neon-vk-font-port-pi4-20261003/README.md)
passed boot-slot TrueType width, right/centre placement and exact translated
pixels through three Vulkan draws. This adapter is not included in the
resident Pi 4 monitor.
