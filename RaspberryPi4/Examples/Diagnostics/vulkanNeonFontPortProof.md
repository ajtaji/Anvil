# Pi 4 Neon Vulkan font-handle payload

This returning payload passed on Pi 4 build 244. Its predecessor returned a
safe status-26 failure during font warm.
It binds Anvil's embedded DejaVu Sans Bold bytes to the reserved TrueType boot
slot 4, warms `Wi` before beginning an offscreen Vulkan frame, measures its
width and line height, then draws the run at a fixed origin, right aligned,
and centred. The 64×64 BGRA8 image stays offscreen. A full-pixel oracle checks
that the second and third 20-row bands equal translated copies of the first,
with nonzero ink and a black lower guard. The report also records three draws,
36 vertices, Vulkan faults, and teardown state.

The compiled vulkanNeonFontPortProof.img.pmf artifact is kept outside the
repository. Match its digest below before any board run.
The 2,124,020-byte PMF container has SHA-256
`232739368D4C42ACE8171D3E90404E79E318C74B9D06B768DB15E60E0E689177`.
Its 2,123,892-byte inner image has SHA-256
`BA29D1FAD6D33487FA5C8D52857B025CE01586C8DE2C73DD3A82800F429E5AF7`.
The source SHA-256 is
`E2E009B91E80747D792B6698C685223839F73C261EAAF68DDFD8DCA49B8360EB`.
The included Pi 4 backend source SHA-256 is
`F7217918FC460267DF8DC915F9D95181C7B42BB10E737F4B7B4631DE79326318`.

The compiler used `--entry-returns --load-addr 0x800000 --bss-addr
0x2000000 --stack-addr 0x4000000 -t pi4 -s`. The image occupies
`0x00800000..0x00A06873`. BSS occupies
`0x02000000..0x02B6499F`; the stack starts at `0x04000000` and grows
downward. The Neon surface is `0x06000000..0x063E7FFF`, the Vulkan
window is `0x063E8000..0x06FE7FFF`, and the arena is
`0x0A000000..0x0AFFFFFF`. These are the same disjoint low-memory regions as
the previously measured port-frame proof; they avoid the resident monitor,
display framebuffer, driver arena, screenshot space, and resident Vulkan heap.

`global_npfreport` is at `0x025EDD20`; the expected x0 return is that address.
Read 128 bytes there and pass them to
`RaspberryPi4/Examples/Diagnostics/vulkanNeonFontPortProofCheck.py`. A later
board run should use the monitor's normal verified PMF upload and a 15-second
deadman. No card file or monitor image needs to change. The proof is offscreen,
so a physical-screen screenshot is not an oracle for this payload.

Every returning path checks `vkDeviceWaitIdle` before tearing down Chrome,
Neon, or the Vulkan device. Report word 28 must be zero. If a submitted frame
or atlas upload cannot be proven idle, or Chrome's own teardown idle check
fails, the payload parks in WFE without petting the watchdog. The armed
15-second deadman must then reset the board; it must not return to the monitor
while GPU work may still be in flight. A host timeout in that path is not a
passing report. Early setup failures that pass the same idle check can return
a failure report safely.

The first board run returned status 26 at font warm. Its fault text identified
a guarded DMA partial-atlas tile scatter, even though this returning payload
had not called `DmaInit`. Its initial full-atlas upload had succeeded through
TFU. The backend now advertises DMA transfer capabilities only when
`DmaReady()` is true and the channel is not quarantined; without DMA, font
warm selects another full-atlas TFU
upload. Report word 29 captures `DmaError()` and should be zero. Word 30
counts successful full-atlas uploads and should be two (initial atlas plus
warmed `Wi`). The revised artifact returned under a 15-second deadman; its
report passed exact translated-pixel, draw-count, upload-count and teardown
checks at `docs/evidence/neon-vk-font-port-pi4-20261003/report.bin`.

The payload does not implement arbitrary desktop `GLFont` names, dynamic
fixed-advance settings, font files, or other boards. Its boot-face source is
the same embedded face selected by Anvil's first screen frame.
