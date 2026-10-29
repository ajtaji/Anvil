# Bounded Neon font handles for Anvil Vulkan

`neon_vk_font_port.pbi` is the shared bridge for Neon-authored text placement.
Include it after `neon_vk_port.pbi` and `neon_vk_chrome.pbi`. It does not load a
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

`NeonVkPortFontDerive` creates an independent role/size reference to the same
loaded generation and copies its policies. `NeonVkPortFontSetFixedAdvanceQ16`
and its floating-point counterpart select proportional spacing (zero) or
fixed cells up to 8192 pixels. Fixed cells bypass pair positioning without
scaling glyph ink. `NeonVkPortFontSetSnapToPixel` controls whether glyph origins
are snapped before camera/canvas mapping. Policy changes require an idle frame.

`NeonVkPortFontSetControlMode` selects legacy CR/LF layout (0), hidden C0/DEL
controls (1), or visible control boxes (2). `NeonVkPortFontSetShowControls`
selects hide/show explicitly. Width, prewarm and drawing consume the reference's
control policy; changing one derived reference does not mutate its source.

This remains a bounded bridge rather than a drop-in `GLFont` implementation.
Named operating-system font discovery, point-size selection and per-handle atlas
page budgets are not implemented here.
A port loads TTF bytes into an Anvil slot and binds that slot explicitly.
Widths may differ from the desktop font because the face, pair positioning and
raster metrics can differ. The text-position contract and remaining integration are recorded
in [the caret port audit](../../../docs/NEON_TEXT_CARET_PORT.md).

`NeonVkPortFontTextXForColumn` and `NeonVkPortFontTextColumnForX` provide
single-line queries in source pixels before camera/canvas transformation.
Columns count Unicode scalars. Proportional X queries clamp at the text end;
fixed spacing extends the final pen by additional cells, up to column 2048.
Hidden controls inside the text retain zero advance. Hit tests clamp to the
source length, choose the later boundary at a midpoint, and return column zero
for X at or below zero. Multiline legacy text refuses these single-line calls.

For multiline queries, `NeonVkPortFontCaretPoint` returns Q16 X, baseline Y and
UTF-8 byte offset for an exact scalar boundary. `NeonVkPortFontCaretColumnForX`
accepts an explicit zero-based line and Q16 source X. Each call revalidates the
font generation and applies its spacing/control policies through shared layout.
They do not rasterize or upload glyphs. Integer operations return named errors;
the floating X query returns -1 on refusal. Pointer outputs require distinct,
aligned caller-owned words and are untouched on refusal.

Physical capture 123 passes 78 checks, including stale handles, hidden controls,
supplementary UTF-8, fixed spacing and explicit multiline selection. A rendered
text run and seven caret markers match an independently positioned fixed-cell
reference across 30,720 bytes; frame raster/upload deltas remain zero. This
qualifies that fixed-cell fixture. Capture 124 extends it to 141 checks and
proportional AVATAR with an independent hmtx/GPOS fontTools reference. Both
complete crop pairs match over 61,440 bytes, with 14 markers, zero frame
raster/upload deltas and 328 rejected corruptions. Hostile coordinate, column,
string-length and hidden-scalar capacity cases are included. Resident service
routing and physical pointer interaction remain unqualified. See
`../../../docs/evidence/neon-font-caret-proportional124-20261029`.

`tools/neon_vk_font_port_check.py` is the historical emitted-A64 interpreter
gate; it must not be run when the available-board rule excludes emulation.
Its original scope checks loaded file
and boot slots, two pixel heights, measured width and line height, right and
centre placement, and refusal of mid-frame prewarm, face switch, dirty atlas,
stale generation and unsupported canvas stretch. The Pi 4
[offscreen board proof](../../../docs/evidence/neon-vk-font-port-pi4-20261003/README.md)
passed boot-slot TrueType width, right/centre placement and exact translated
pixels through three Vulkan draws. That October 3 proof does not qualify every
later policy or the missing caret API; later resident/composed evidence is
recorded separately in the Vulkan compatibility status.
