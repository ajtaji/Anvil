# Raspberry Pi 3 Model B v1.2: early hardware foundation

Desk implementation, not a booted Anvil release. The capability manifest stays
disabled until a real board entry and silicon gates exist. No board was accessed.

## Implemented

`RaspberryPi3/Lib/timer.pbi` reads BCM2837's 1 MHz system timer at
`0x3F003000` using high/low/high sampling. Delays have both elapsed-time and
iteration limits, and report failure instead of waiting forever.

`RaspberryPi3/Lib/uart.pbi` provides PL011 initialization, byte transmit and
nonblocking receive at `0x3F201000`. GPIO14/15 ALT0 uses the BCM2837 GPPUD
sequence, not Pi4 pull registers. Clock rate is supplied explicitly; do not
assume 48 MHz. Receive distinguishes no byte (-1) from errors (-2). Transmit
and initialization return success/failure. This is 3.3 V TTL, not RS232.

`RaspberryPi3/Lib/mailbox.pbi` implements a serialized early property channel
at `0x3F00B880`, using separate outbound-full and inbound-empty status registers.
`Pi3ClockRate(2)` obtains the UART clock. A submitted request which times out
leaves its buffer firmware-owned: later calls refuse, including before changing
the internal clock-request buffer. Reboot is required; no blind retry is made.

## Boot contract and limits

- Use 64-bit firmware entry with the stock AArch64 stub (normally EL2). No EL3
  transition or cache-state guess is introduced by these libraries.
- The mailbox explicitly checks current EL2/EL3 and refuses if SCTLR.M or C is
  set. The caller must enter with genuinely uncached resident ARM RAM, not merely
  switch a live cached mapping off. Timer/UART also require suitable MMIO mapping.
- BCM2837 has one cluster; Aff0 zero selects its primary core. This is not a
  generic multicore/cluster test. The property channel requires exclusive ownership.
- Every buffer must be a valid reserved ARM RAM span, aligned to 16 bytes. The
  address ceiling below peripherals is only an encoding/range guard, NOT proof
  that the firmware assigned that RAM to ARM. Validate firmware/DTB memory and
  reserve the actual image, stack, DTB and mailbox buffers before wider allocation.
- The explicit compiler target is `-t pi3` / `.pi3`, distinct BCM2837 metadata.
  Its conservative envelope ends at `0x08000000`; do not infer the GPU memory
  split. Firmware entry is normally `0x80000`; preserve firmware's first 4 KiB.
- Route PL011 away from Bluetooth with `dtoverlay=disable-bt`, and use
  `enable_uart=1`. Confirm firmware and UART pin routing before board testing.
- Libraries deliberately have no nested includes. Include timer, UART and
  mailbox explicitly in that order. No Pi4 hardware library is reused.

## Desk gate

Run `python tools/pi3_early_hardware_check.py --compiler <unified-IDE> --target pi3`.
It compiles `RaspberryPi3/Tests/early_hardware.pi3`, then executes its actual A64
instructions against fake timer/UART/mailbox registers. The fixture writes to a
synthetic result address and is **not a boot image**.

Nine cases cover successful EL2/EL3 operation, full TX, empty/error RX,
mailbox full/empty timeout, cache-on and EL1 mailbox refusal, UART baud divisors
and GPIO preservation. A second clock request checks that timed-out submitted
buffers are not reused. Compiler candidate SHA256:
`8aae9d73c1837a6d18036dcdc6ca462135aad3b7fabd0084bc02c9046ac108d3`.

This is instruction/control-flow evidence, not physical UART timing, firmware
DMA/coherency, frozen-hardware deadline calibration, or boot proof. Earlier
`--target pi4` runs were CPU-only diagnostic gates, not Pi3 target support.

Still required: silicon proof of the cold entry/framebuffer described below,
accelerated display, interrupt and scheduler context, storage, networking,
firmware staging/recovery and silicon tests. Do not enable advertised capabilities
or overwrite a working card based on this desk result.

## Counted cold-entry candidate

`RaspberryPi3/Board/board.pi3` is now a real, minimal cold entry, deliberately
absent from the default build target registry. It captures firmware x0 as its
first Main statement, brings up UART using the measured firmware UART clock,
prints progress, queries the actual ARM memory extent, checks the DTB's outer
header/span and rejects overlap with the image/stack reservation. It then parks
with exceptions masked. No allocation occurs, so all other firmware reservations
remain untouched. This is not a complete FDT parser or monitor.

The staging contract must already guarantee resident ARM RAM for the image and
stack: runtime checks cannot protect writes that startup made before Main.
Reserve `[0x80000,0x200000)` exclusively, compile for load `0x80000`, stack
`0x200000`, and prove image plus BSS ends below `0x1F0000`. The final 64 KiB is
stack. The DTB must be outside that reserved span and remain resident. No
128 MiB allocation assumption is used by this cold entry.

Two actual candidate builds were recorded through `tools/build_count.py` in
the separate Pi3 counter (now 2); Pi4's counter was untouched. The final image
SHA256 is `55f353f86846478655c1a575d17b061aea938abbc6c45881016b53bd15ea293b`.
`tools/pi3_cold_entry_check.py <image>` runs the existing candidate without
rebuilding: 4 fake-MMIO cases pass, 112,332 instructions, including actual
normal startup, preserved firmware x0, small-RAM refusal, DTB collision and
bad magic. BSS ends at `0x100070`, below the reserved stack floor.

No card was changed. A stock Pi3 handoff is EL2; the current Anvil scheduler's
EL3-only proof does not apply here. No EL2-to-EL3 transition is assumed. A
future EL3 stub needs its own Pi3 proof and a recoverable hardware test.

## First framebuffer

`RaspberryPi3/Lib/framebuffer.pbi` requests a firmware framebuffer after the
minimum memory/DTB checks. A bounded early PL011 attempt now precedes the
request only to make pre-display failures observable; UART failure never stops
the display path. Its one 176-byte transaction sets 640x480 physical/virtual
geometry, 32-bit depth and zero virtual offset, allocates the buffer, then gets
pitch, pixel order, alpha mode and VC memory extent. It requires compatible
response tags and prefix lengths, fixed returned geometry, bounded
pitch/allocation, allocation inside firmware-reported VC memory, and no
image/stack/DTB collision before its first pixel write. All four VideoCore bus
aliases normalize to the same ARM address. Both firmware pixel orders and all
three documented alpha modes are accepted and packed correctly.

It then clears by CPU and renders an early ASCII console using the original
shared `Anvil/Graphics/text_glyph.pbi` font: 42 columns, 20 rows, integer scaling,
line wrapping and upward CPU scrolling. Actual boot progress and the compiled
build number appear there. This is a minimal VC4-era framebuffer path,
**not DMA, V3D, accelerated VC4 or the full interactive Anvil console**.
Failure preserves UART diagnostics and makes no pixel writes.
Malformed allocation responses are not blindly freed or retried; the cold
entry parks. Mailbox timeout retains the existing outstanding-buffer rule.
Initialization is once-only: a second call refuses before changing the known
allocation. A failed first allocation attempt is not repeated before reboot.

The third counted Pi3 image is `3c629429a283e9added7f82a7ee358c9efbbdad53b64d5bd9fb8fe1e35978356`.
Its BSS ends at `0x100140`; the earlier UART-only evidence above is historical.
The current cold-entry gate includes depth, pitch and allocation-size rejection
and checks that rejected responses make zero framebuffer writes. This remains
desk evidence only; no monitor or television was used.

The fourth counted image adds full ASCII, boot progress/build text, scrolling
and once-only initialization: SHA256
`280a5f0a4cee5668342af1d0cc1e40ac1d3c800034ea0d2e45fe00f8b4d9da61`.
`tools/pi3_console_host_check.py --purebasic <host-PureBasic>` executes the
production scroll/glyph procedures against host RAM. It passes whole-frame
row-copy checks, unchanged stride padding/end guard, known glyph/scaling and
line wrapping. This does not replace the separate emitted cold-start gate.
The fourth image passes all seven full cold-start cases (11,607,295 executed
instructions). Its once-only repeat-init refusal separately passes 61 emitted
instructions with no writes outside its stack and the old framebuffer preserved.
The shared existing build-count mechanism increments source after successful
compilation: this fourth image contains build constant 3; source marker is 4.
Use the image hash/ledger together, not an inferred next build constant.

## Reproducible boot-card candidate (2026-09-12)

`RaspberryPi3/Boot/config.txt` and `README.txt` define the isolated experimental
card layout. `firmware.json` pins official firmware commit
`ae2a7dc5330b7ea2c7107e5c4cb6b2691355bb9c` and all six firmware/license file
SHA256 values. `tools/pi3_boot_stage.py` validates supplied files read-only by
default; an explicit new output directory stages verified copies. It neither
chooses nor formats a disk, overwrites an existing directory, nor invokes a compiler.

Latest candidate contains build 4, from source HEAD `3669c2c`: 23,012 bytes,
SHA256 `d236518bf333f7aae2a9e51b8fe484ff0c40242c613bc771b92c3fb9fe631769`.
Supervisor reports seven emitted cold-start cases / 11,608,809 instructions plus
61 instructions for repeat-init refusal passed. Config SHA256 on the staged card:
`709af22d957543038255bac7621364e028e924e45380fad00e48cb9dadddb7c5`.
The earlier build-3 image above remains historical. Card-file verification is
not hardware boot acceptance. The broader monitor/services remain unfinished.

## First-silicon visible diagnosis

The first physical boot of build 4 produced a powered HDMI signal but a black
screen. That image had no ACT diagnostic and parked silently before its first
pixel on every mailbox, UART, memory or DTB failure. It also incorrectly
required the returned pixel order to be RGB.

The corrected diagnostic uses the Pi 3B board's real firmware-controlled
STATUS_LED (firmware GPIO 130, expander line 2), not BCM GPIO47. One short flash
means ARM entered with a valid cache-off mailbox context. A repeated two-flash
code means the ARM-memory/DTB check failed; three means framebuffer negotiation
failed; four means PL011 initialization failed; five means PL011 transmit
failed. Codes repeat five times and then enter the bounded WFE park. LED
failure is optional and never prevents the display path. The firmware rainbow
splash is temporarily left enabled so firmware display progress is visible.

The framebuffer remains the primary console even though PL011 is attempted
first as a diagnostic witness. A successful screen therefore remains useful
if serial routing is wrong, while a working FTDI link now names the exact
framebuffer refusal instead of leaving a silent black display.
These diagnostics do not advertise scheduler, storage, USB or network support.
Firmware GPIO protocol facts are derived from the pinned Pi 3B DTS,
`gpio-raspberrypi-exp.c`, and Raspberry Pi firmware tag definitions; no Linux
implementation code is copied.

The desk-accepted diagnostic image contains build 5 and is 25,316 bytes,
SHA256 `3635112fb97ef00d71f09708871ad7281874d34531be494b53524e28c930f57e`.
Its BSS ends at `0x100180`. Nine emitted cold-entry cases execute 35,347,845
instructions: RGB and BGR success, optional LED refusal, three ARM/DTB
failures, and three malformed framebuffer replies. Repeat initialization still
refuses in 61 emitted instructions without changing the existing allocation.
The source marker is now 6 after the counted build. The staged diagnostic
config SHA256 is
`3fb2b1b488bf008cbabefaae3d1945a7794bf9d22de29e3e702b9ef46184eb70`.
This is ready for a card test, not yet silicon acceptance.

Build 5's first physical run reached firmware video handoff but remained black
and emitted no FTDI bytes. The exact source defect was the VC-memory range
check: it required the entire firmware-owned VC reservation to end below
`0x3F000000`. On a 1 GiB Pi 3 the ordinary 76 MiB split can extend to
`0x40000000`; only the returned framebuffer itself must end below the BCM2837
peripheral window. The corrected code follows the pinned Linux driver's address
normalization, accepts a VC reservation through the 1 GiB boundary, checks the
translated framebuffer independently, and uses Linux's three-second bounded
property-transaction deadline instead of the former 100 ms deadline.

The corrected counted image contains build 6 and is 27,724 bytes, SHA256
`83360e81a5eb3b06a0ad549e4368997bc93c3447797487bf7671569fa48d1fe5`.
The source marker is now 7 after the successful counted build. Its exact emitted
image passes nine cold-entry cases / 35,541,181 interpreted instructions;
repeat initialization refuses in 86 instructions while changing only the
reported ownership error. A separate 71-assertion framebuffer contract gate
runs 9,338,787 emitted A64 instructions and challenges the exact message shape,
all bus aliases, all alpha modes and every refusal class before any candidate
framebuffer write. The host glyph/scroll test and the nine-case early-hardware
gate also pass. Compiler SHA256 is
`0c0bac62627184109f3a7f7692919b9523e80e413f50b67b82dfc1867f89d51e`.
The verified boot folder is
`C:\Users\rajta\AppData\Local\Temp\anvil-pi3-diagnostic-build6-final`.
It is ready to replace the files on the dedicated card; silicon framebuffer
and FTDI acceptance remain open until that card is booted.

## Primary references (links)

- [Raspberry Pi Linux driver-reference baseline (`7d182693`)](https://github.com/raspberrypi/linux/tree/7d1826930811232688a50c99c540fbb137aed081)
- [Raspberry Pi processor documentation](https://www.raspberrypi.com/documentation/computers/processors.html)
- [Firmware property protocol](https://github.com/raspberrypi/firmware/wiki/Mailbox-property-interface)
- [Official firmware AArch64 stub](https://github.com/raspberrypi/tools/blob/master/armstubs/armstub8.S)
- [Official UART configuration](https://www.raspberrypi.com/documentation/computers/configuration.html)
- [BCM peripheral register description](https://datasheets.raspberrypi.com/bcm2835/bcm2835-peripherals.pdf)

Register facts and the pinned Linux drivers were consulted; no Linux/NodeBB
implementation code was copied into Anvil.
