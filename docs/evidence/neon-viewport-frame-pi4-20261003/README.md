# Pi 4 Neon Vulkan viewport placement

Chrome now has an opt-in `NeonVkChromeViewportSet` for an empty active frame.
It records a bounded dynamic Vulkan viewport and maps its existing scissor
endpoints through the same rectangle. Each new Begin restores the full target,
so callers that do not select placement keep the previous behavior.

The returning scene proof rendered an 800×450 Neon canvas into an 800×800
linear BGRA target, centered between 175-pixel black bars. It drew a blue
full-canvas box, a red box clipped by the canvas scissor, and a cropped green
sprite. On Pi 4 resident Anvil build 244, PMFBOOT SHA-256
`2D421E275A2F021552B5CDF8BB7E187B52A40D4AA9F6CA7248091CB25D673C1C`
uploaded with matching board digest at `0x00800000`, ran under a confirmed
15-second deadman and returned report pointer `x0 = 0x025EDD78` in 4.4 s.
The checker passed both bars, content boundaries, clipped/outside pixels,
sprite color, inverse pointer/bar mapping, three draws/18 vertices, one
present intent, zero Vulkan faults and clean teardown.

The non-opt-in frame proof was rebuilt against the same Chrome source.
PMFBOOT SHA-256
`708A4F2EF108250201C47329DBF437FDDC23C00DA4CEF434A787BAD075A8DF85`
also returned under the deadman. Its existing checker passed rectangle, text,
cropped sprite, exact sampled colors, 22 white text pixels and clean teardown.
These are offscreen RAM payloads; the resident console, scanout and storage
were unchanged.

The first placement payload requested a 1280×800 Vulkan image and returned
before drawing because the test configured a 1024-pixel image-dimension cap.
The corrected GPU proof uses 800×800. A separate
[viewport math proof](../neon-viewport-pi4-20261003/README.md) covers the
1280×720-on-1280×800 rectangle, but that size has not passed this GPU frame
path. Scaled Neon text also remains unsupported when canvas and target sizes
differ; this placed scene does not claim full UI or resident app integration.

Saved reports: [placed](placed-report.bin) SHA-256
`D0027FB562C9B70482F05932AFDA9E0A02984B44CCEF0FDF6DCC685D413A8E6A`;
[default](default-report.bin) SHA-256
`5276E8EA0A10A85C1CFEA5007653F2C99C8805AA1862AD17663C94F0282157CE`.
From the repository root, run
`python RaspberryPi4/Examples/Diagnostics/vulkanNeonViewportFrameProofCheck.py docs/evidence/neon-viewport-frame-pi4-20261003/placed-report.bin`
and
`python RaspberryPi4/Examples/Diagnostics/vulkanNeonPortFrameProofCheck.py docs/evidence/neon-viewport-frame-pi4-20261003/default-report.bin`.
