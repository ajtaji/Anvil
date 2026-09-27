# Pi 4 prompt idle wait and CPU usage — 2026-09-27

The running Pi 4 monitor was build 210 at `192.168.1.111`. Its prompt
cooperatively serviced input, screen, network and fan work, but the Pi 4 had
not qualified the counter-event WFE idle wait. The usage meter counts time
spent in that wait; without it, the banner had no meaningful idle percentage
and the main core kept polling. Before this change the board reported 51 °C,
a 1.5 GHz measured CPU clock, and a hardware-controlled fan at 40.4%.

A deadman-guarded RAM diagnostic independently configured the 54 MHz
`CNTKCTL_EL1` event stream, performed 32 WFE wake waits, and restored the
original register. Capture 110 measured the first event interval at
10,484–16,391 counter ticks (300 µs mean). Build 221 enabled that interval:
the CPU field appeared, but a quiet prompt still showed about 24.56% core-0
busy time. Capture 113 measured the longest available four-bit event interval:
59,789–65,558 ticks (1.210 ms mean), with all 32 wakes below the 2 ms guard.
Both diagnostics returned `x0=0` under a 15-second deadman. Capture 108 was
an earlier pass/fail-only check; it did not measure sleep duration.

The resident prompt now enables this wait only on the measured Pi 4
configuration: EL3, a 54 MHz counter, and successful counter-event control
readback. It uses the measured 1.21 ms interval. Other configurations keep
cooperative polling or their existing shorter interval. Input and service
checks still run before each short sleep, and software-PWM fan mode still
prevents sleep. The CPU usage meter remains a core-0 busy estimate over
completed one-second windows, not an all-core operating-system metric.

Normal Pi 4 build 221 compiled at 4,368,844 bytes, image SHA-256
`65feea85f6205781a8d10b78a811616253488b53d018ce174903329b63d0fd8e`.
Before replacing the USB boot stick's `KERNEL8.IMG`, its 4,161,468 bytes
were read back with CRC-checked chunks and backed up (SHA-256
`9c5518a3112bd20f0a5dfeea415f0885c5d92a1a3e6431f6485166f4115d3381`).
The new file was uploaded to RAM with an exact SHA-256 match, saved to the
FAT32 boot partition, loaded back from that partition at a separate address,
and hashed again on the board to the same digest. One reset then booted
build 221; `version full` measured the running image at 4,368,844 bytes,
CRC32 `6988EFCE`, and the network console, display, fan and core-status
commands returned normally. The CPU field appeared in the banner. The
first screenshot showed 98.69% after interactive commands; a later quiet
capture showed 24.56%.

Normal build 222 also compiled at 4,368,844 bytes; its image SHA-256 is
`e5eab20873ffcf3bb7de0d314243b9253c404c701d5a7c53d3ce3b497cdc0489`.
The boot stick's build-221 image was checked against its archived hash before
replacement. Build 222 was uploaded, saved, loaded back and hashed to the
same digest before one reset. `version full` then reported live build 222,
image size 4,368,844 bytes and CRC32 `C77DC16C`; network console, display,
fan and core-status commands answered. A quiet build-222 CPU and temperature
comparison found a second, larger idle cost. With the boot-default Vulkan
console active, the banner showed 92.78% core-0 busy and 52 °C. Switching
the same build to the DMA console yielded 23.27% and 50 °C; switching back
to Vulkan yielded 92.45%.

The Vulkan renderer called `ConOverlayDamage()` after `ConGridClearDirty()`
on every completed frame. `ScreenPump()` immediately paints the overlay in
that same pass, so the damage call scheduled another full GPU frame on the
next service tick. Removing it ends the self-sustaining repaint loop; real
grid or keyboard changes still mark damage through their own paths.

Normal build 223 compiled at 4,368,844 bytes, image SHA-256
`9db6861b6cd644e0f1f6b9b1d8237da663950bbf4180e4b9181fb04e6be7f344`.
The build-222 boot file was checked against its archived digest, then build
223 was uploaded, saved, loaded back and hashed before one reset. The running
monitor reported build 223 and CRC32 `5BC668D0`; network console, screen,
fan and core-status commands answered. After several quiet minutes with the
boot-default Vulkan console still active, capture 117 showed 8.36% core-0
busy and 49 °C. That is a measured one-window utilization and sensor sample,
not a long-term thermal plateau. Captures 115 (DMA on build 222), 116
(Vulkan on build 222) and 117 (Vulkan on build 223) retain the tier and
before/after banner evidence.

The backup, all three update images, diagnostic PMFBOOT files, return metadata,
32-byte traces, compressed transcripts and banner captures are in
`docs/evidence/pi4-prompt-idle-20260927/`. Run
`py docs/evidence/pi4-prompt-idle-20260927/verify_probe.py` to recheck the
hashes and WFE trace.
