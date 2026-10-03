# Pi 4 Vulkan banner status after deferred startup

Build 242 rendered the Vulkan banner without CPU, temperature, or fan status.
The live 1280×800 capture is [before-build242.png](before-build242.png) (SHA-256
`3EC55C4B88B88FB88D1C6B84D5B6468F9A6EC47F0212AC7C1F905665FB90BFBB`,
wire CRC32 `16751BE5`). Deferred startup skipped the CPU `DrawBanner()` call,
which had been the only caller that initialized `BannerClockLayout()`.
`BannerClockTick()` consequently returned on its zero-width guard.

Build 244 initializes the caption geometry and initial text in the common
screen setup, including geometry rebuilds. It measures the fixed banner row
at scale 1 regardless of console magnification. The signed compiler produced
a 5,251,408-byte image with SHA-256
`75A4711484CAB669F91C8389FC7E4D6CB0D326434BFBD9B5DA71AA768050006E`.
The Pi 4 received that image over Wi-Fi at `192.168.1.14`; its in-memory
digest, saved candidate digest, and final `KERNEL8.IMG` reload digest matched
before one reset. The old image remains on the boot medium as `OLD242.IMG`.

After reboot, the board reported build 244 at `pmf>`. The live capture
[screen.png](screen.png) (SHA-256
`760B0826D6DEE76A6D664525DC2686E86BF799B400585BEEBBFD92C8330DC4CD`,
wire CRC32 `3DD77A1D`) shows the clock, `CPU0 36.92%`, `118 F`, and `fan 13%`
in the Vulkan banner. Those values are one sampled instant, not a CPU-load or
thermal-performance claim. The deadman was off and the board lease was
released after the capture.
The `screen keyboard` status command independently reported the resident
Vulkan/Neon tier composing the band on the GPU and presenting by DMA.
