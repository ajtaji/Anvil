# Neon Vulkan viewport frame proof

This returning Pi 4 RAM diagnostic renders an 800×450 canvas into the centered
800×450 region of an 800×800 linear BGRA image. The 175-pixel top and bottom
bars are cleared black. The scene draws a blue canvas box, a red box through a
canvas scissor, and a green cropped sprite. The report checks bar/content
pixels, draw and vertex counts, present intent, inverse pointer mapping, Vulkan
faults, and clean teardown. `vulkanNeonViewportFrameProofCheck.py` checks its
160-byte report at the `global_npfreport` symbol from the linked `.sym` file.

The separate `vulkanNeonViewportGate.pi4` still covers the 1280×720 canvas on
a 1280×800 screen as pure viewport math. That larger image is not a valid
target for this standalone GPU composition: its native Neon surface is
800×1280, and `NeonRenderCapacity(1024, 1024)` caps the backend's supported 2D
image extent at 1024 per axis. A prior 1280×800 image creation failed before
any drawing with `vkCreateImage was given an extent outside this backend's
supported 2D range`. Enlarging the GPU target requires a separately reviewed
native capacity and memory-map change. The 800×800 proof does not establish
that larger target.

The viewport placement call is opt-in and occurs immediately after frame begin.
The port keeps its logical target at 800×800; Chrome's dynamic Vulkan viewport
places normalized drawing coordinates in y=175..624. Scaled text is not part of
this proof because the current port rejects text when canvas and target sizes
differ. A board run requires the existing returning-payload loader, a verified
live map, and an armed 15-second deadman; uncertain GPU completion waits for
reset rather than returning to the monitor.

The 800×800 returning payload passed on Pi 4 build 244, including the bar,
content, clipped box, sprite, pointer, fault and teardown checks. The
non-opt-in frame regression passed against the same Chrome code. Exact
artifacts and checker commands are saved in
`docs/evidence/neon-viewport-frame-pi4-20261003/README.md`.
