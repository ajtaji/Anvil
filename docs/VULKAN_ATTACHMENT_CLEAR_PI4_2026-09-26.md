# Pi 4 whole-attachment Vulkan clear

`vkCmdClearAttachments` now accepts one colour attachment and one complete
one-layer framebuffer rectangle before the first draw in an active render pass.
The command captures four binary32 clear components at recording time, packs
them as BGRA8, and replaces the render pass's load clear. The existing V3D
tile clear executes that colour before the ordered draw list. The public
entry point has the Vulkan 1.0 five-parameter signature and is available
through the device dispatch table.

The current V3D transaction cannot execute a partial in-pass clear or a clear
after a draw without losing ordering. Arrays, partial rectangles, other
aspects, and post-draw clears invalidate the command buffer; `vkEndCommandBuffer`
reports the refusal. A render pass with no draw now submits its load/attachment
clear through the same V3D tile-clear job used by `vkCmdClearColorImage`. Its
framebuffer, render pass and image view remain retained until the job completes;
the attachment image and allocation use the command buffer's image-reference
ledger. Other limits remain explicit until ordered in-pass clear primitives exist.

The accepted semantics and ABI follow the Vulkan specification for
[`vkCmdClearAttachments`](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdClearAttachments.html),
[`VkClearAttachment`](https://docs.vulkan.org/refpages/latest/refpages/source/VkClearAttachment.html),
and [`VkClearRect`](https://docs.vulkan.org/refpages/latest/refpages/source/VkClearRect.html).
The emitted pipeline gate checks the 24-byte records, recording-time capture,
the backend's exact clear word, clear-only submission and retained lifetime,
and refusal of partial and post-draw clears.
The emitted gate also proved that typed writes to the public clear-value array
arrive intact. The implementation reads the union's four ABI words by offset,
matching the existing render-pass clear path; direct typed pointer-array reads
had yielded zero in the emitted check.
It does not execute V3D hardware. Earlier Pi 4 triangle and clear diagnostics
established the backend's tile clear on silicon, but this new public entry
point has not yet been run there.
