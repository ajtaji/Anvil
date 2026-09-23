# ROCK Pi 4C v1.2

Status: **Build 124 boots from SD into Anvil at EL3, owns the card filesystem, and runs bounded returning test payloads under a hardware watchdog.** On the original ROCK Pi 4C v1.2 it mounts the GPT Microsoft Basic Data partition as exFAT, lists directories, creates and verifies files after flush/remount, transfers files over UART2, and rewrites both fixed trust copies with readback verification. Rockchip firmware trains both 2 GiB LPDDR4 channels before entering Anvil. Interrupts and networking remain unavailable.

The PMF wrapper is Anvil's cold entry at `0x00040000`. It refuses non-EL3 entry or an enabled MMU/data cache, disables an inherited instruction cache, and branches to the complete Anvil runtime at `0x00041000`. The device tree is embedded in the same Anvil component at `0x001C0000`; the loader loads that one component and performs no hardware bring-up beyond the required DDR/entry contract. The packer and serial updater run nine emitted-entry interpreter cases before accepting an image, so an entry that branches to a stale RAM address is rejected.

The real `Board/board.rockpi4c` composition preserves incoming x0 as the FDT, then rechecks CurrentEL at Main, stack alignment and EL3 SCTLR M/C/I before installing VBAR_EL3. Its contract requires x0=DTB `0x001C0000`, x1-x3 zero, SP=`0x05000000`, masked DAIF, MMU/caches off, UART2 at 1,500,000 baud, and an enabled 24 MHz architectural counter.

HDMI is a proven diagnostic path through VOPB and the DesignWare transmitter. A 1920x1080@60 EDID-preferred mode reached stable RGB888 scanout and displayed the test bars on physical hardware on 2026-09-21. The last blocker was RK3399 BootROM security state in PMUSGRF DDR region 16: releasing the documented DDR/SRAM security fields before DMA changed the VOP result from a repeatable AXI bus error to nine clean frame edges. Anvil now performs and verifies that release during early EL3 startup, before storage or display DMA. Automatic display initialization remains off; `hdmi` performs one bounded attempt per boot and reports its stage over serial. MiniDP remains deferred.

The PL330 display accelerator uses the RK3399 TRM's secure DMAC0 APB alias at
`0xFFFC0000`. The Linux device-tree aperture at `0xFF6D0000` is the normal
DMAC0 view and returned zeros to direct EL3 secure accesses. A read-only
watchdog-guarded payload proved the secure alias on this board with
`PID=0x00241330`, `CID=0xB105F00D`, `CR0=0x001F3071`, and
`CRD=0x07FF7F73`. The driver keeps exact identity, clock and reset-state
admission and does not rewrite SGRF tie-offs or pulse a DMA reset. DMA remains
optional for HDMI; a refusal leaves screen composition on its bounded CPU
fill/copy path. Silicon accepted incrementing memory copies but faulted a
fixed-memory-source fill. The current fill candidate seeds 256 bytes with the
CPU and doubles the filled region through nonoverlapping memory copies, with
at most 19 bounded submissions for a full-HD frame. On 2026-09-21 the original
4C passed both a private-buffer copy/compare and a 256-byte fill/compare
through the earlier repeating-copy path; the latter returned
`X0=0x444D4100`, DMA error zero, 256 completed bytes and no frozen fault state.

GIC/timer interrupt setup remains disabled. Reboot uses the known RK3399 PMUGRF/CRU warm-reset sequence; it does not call PSCI. There is no Rock Pi network command service.

The recovery console accepts `storage`, `sdmeta`, `ls`, `get`, `put`, `writeproof`, `trustupdate`, `payload`, `hdmi`, and `reboot`. The host utility is `tools/rockpi4c_update.py` (COM7, 1,500,000 baud by default). Uploads are staged in a bounded 4 MiB Anvil buffer and checked by CRC32 before use. A returning payload is entered only after the watchdog is armed and verified; Anvil restores its EL3 monitor stack and exception vectors when the payload returns. Writes are flushed, remounted, and read back. Trust updates validate the fixed one-component image and write/read back the backup copy before the primary copy; reboot is an explicit recovery command after verification.

Build 112 added the guarded arbitrary-payload path. A return-only silicon proof returned `X0=0x1122334455667788`. The HDMI diagnostic then reproduced the VOP AXI bus error without reflashing, and a second payload applied the two exact PMUSGRF masked writes used by mainline RK3399 U-Boot before running the unchanged HDMI path. It reported DDR security `0x0000C001 -> 0x0000C000`, zero VOP scanout faults, stable 60 Hz frame cadence, physical test bars, and a clean return to Anvil.

Build 96 is the hardware-accepted buffered-storage candidate. It advertises 16 KiB acknowledged serial windows, drains UART2 directly into the staging area, and preserved build 94's paced 1 KiB protocol for the upgrade. Contiguous filesystem ranges reach the SD card as bounded 128 KiB CMD18/CMD25 operations with explicit CMD12 termination, instead of one command and readiness wait per 512-byte sector. On 2026-09-21, build 94 installed build 96 through `trustupdate`; both trust copies passed readback and the recovery `reboot` command returned through DDR training to Anvil at EL3. A 2 MiB file passed put, flush, remount, board readback, host get, CRC32, and matching SHA-256. A separate upload reported the expected `00004000` (16 KiB) window. The host reader now reserves a multi-megabyte receive queue and waits through bounded filesystem preparation and UART gaps before declaring a timeout.

Build 97 corrected the firmware-reservation ownership base from the obsolete U-Boot address to `0x00040000`, but its validator still rejected the DTB because the older contract expected an external tree. It reached EL3 and then stopped before recovery. Build 98 fixed that contradiction: the DTB is explicitly bounded inside the one Anvil component while firmware reservations are checked against the complete early-ownership range. It booted and passed reset and storage checks. Its unacknowledged `get` sender could still strand the polled recovery loop after the `DATA` header.

Build 99 makes file downloads use the same explicit flow-control principle as uploads. The board advertises a 16 KiB window in the `DATA` header, waits for the host before the first window, and requires an acknowledgement after every window. It installed through build 98's recovery console, verified both trust copies, reset through DDR training back to EL3, and returned a 2 MiB file in 53.2 seconds with matching source/readback SHA-256. The current package is `Boards/RockPi4C/direct-sd/`.

Earlier U-Boot hardware runs confirmed a UART recovery console and MiniDP output at 1024x768. The 1920x1080 picture rolled and corrupted, so preferred mode remains unaccepted. Those runs do not validate direct SD, EL3, or this candidate. This is the original 4C, not the 4C+ with RK3399-T.

Hardware basis: RK3399, two Cortex-A72 plus four Cortex-A53 cores, Mali-T860. Do not copy Pi firmware mailbox calls, V3D commands, interrupt-controller setup or MMIO addresses here. Display setup is RK3399-specific and refuses at the first failed prerequisite.

The resident Mali layer is observation-only. `RockPi4C/Lib/gpu_probe.pbi`
records the RK3399 GPU power-domain, bus-idle, clock-gate and reset state
before it can read the Mali aperture, then identifies the T860 and snapshots
Panfrost's feature, job-manager and MMU state. Two watchdog-guarded returning
payloads proved this boundary on the original 4C: the infrastructure refusal
mask was zero, then `GPU_ID=08602000`, `MMU_FEATURES=00002830`,
`AS_PRESENT=000000FF`, `JS_PRESENT=00000007`, and global, job-manager and MMU
status were all zero. It returned `X0=47512000` and produced no later passive
serial output. The exact `gpuinfo` recovery command repeats only that
minimal read set after the same fail-closed PMU/CRU admission. It performs no
GPU, power, clock, reset, MMU or job write. A separate returning payload,
`RockPi4C/Tests/mali_write_value_payload.rockpi4c`, has since passed behind
the resident deadman on build 121. It completed the Panfrost reset and
L2/shader/tiler power sequence, configured address space 0, then submitted a
Mesa v5 WRITE_VALUE job through JS1. The job returned done interrupt bit 1,
zero fault status, a zeroed private target, and intact surrounding guard words.
This is a job-submission proof, not a rendered glyph or framebuffer blit.

Build 124 uses PL330 to publish staged console rows and to scroll the display;
glyph rasterization on screen is still CPU work. The Rock Pi font atlas
adapter uses Anvil's shared TrueType parser and rasterizer to pack Courier
Prime coverage into a 256x96 ARGB8888 texture source. The Mali textured render
job and on-screen TrueType presentation remain to be completed. The
`fontatlas` diagnostic prepares that source from the SD filesystem and reports
its checksum; it does not draw it. On the original board it loaded the 71,188
byte Courier Prime file, rasterized 95 glyphs, and reported CRC32 `2D4DF9FF`.

Build the flat candidate and run the desk contract with:

```text
python tools/rockpi4c_foundation_check.py --compiler <PureMetalForge> --output build/rockpi4c/direct-sd/anvil-flat.img
```

This counts a successful monitor build. Do not treat the payload as a complete boot artifact. See the [foundation contract](../docs/ROCKPI4C_FOUNDATION.md) before any board run. The shared Anvil Vulkan API is reusable; its V3D hardware backend is not a Mali driver.

References:

- [Radxa model comparison](https://wiki.radxa.com/Rockpi4/hardware/models)
- [Radxa hardware specification](https://wiki.radxa.com/Rockpi4/hardware/rockpi4)
- [Original 4C v1.2 schematic](https://dl.radxa.com/rockpi/docs/hw/rockpi4/rockpi4c_v12_sch_20200620.pdf)

The embedded Rockchip `dptx.bin` remains byte-for-byte identical to linux-firmware revision `d371ae3b6888b260e4c37b327a020401cfaaaefd` and is covered by the Rockchip binary firmware terms reproduced in the foundation contract. Its SHA-256 is `203c5f061fb5075e4ca5398f8becc74e7cc450b494af857da5400788a7eae20b`.
