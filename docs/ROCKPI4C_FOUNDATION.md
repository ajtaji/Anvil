# Original ROCK Pi 4C v1.2 foundation

Status: build 39 reached MiniDP first light on hardware on September 13, 2026.
The physical monitor displayed the framebuffer. Build 44 subsequently read
1920x1080 at 148.5 MHz and reached transmitter-valid status, but the physical
picture rolled and corrupted. That is a failed preferred-mode test, not proof
of a correct display. Its fixed RGB1280 line-buffer mode was incompatible with
1920-pixel scanout. The correction selects RGB1920X5 through width 1920 and
RGB2560X4 above it, matching the reference driver's RGB selection rule.
Raw EDID and final programmed clock/timing registers are now logged to make
the next board run independently checkable. Visual proof remains pending.

## Identity and ownership

This target is the original ROCK Pi 4C PCB v1.2 with RK3399. It is not a
Raspberry Pi 4 and not the RK3399-T 4C+. The `rockpi4c` compiler profile uses
the existing ARMv8-A A64 IR/emitter/assembler and its own RK3399 intrinsic
file. It does not import BCM2711 mailbox, V3D, GENET, interrupt-controller or
MMIO definitions.

U-Boot and TF-A retain DRAM discovery, PSCI and secure-firmware ownership.
Anvil enters at Non-secure EL2. After validating that handoff, it explicitly
owns only the display graph's documented clocks, resets, pin control and power
domains; no display block is touched before those prerequisites pass.

## Exact U-Boot handoff

The wrapper is a 64-byte little-endian arm64 `Image` header followed by the
flat compiler payload linked at `0x02000040`. Header instruction zero branches
to byte 64. `text_offset` is zero, `image_size` is the exact file length,
flags bit 3 asks U-Boot to respect the load placement, and magic is `ARM\x64`.

Load the exact board DTB at `0x12000000` and the Image at `0x02000000`, then:

```text
booti 0x02000000 - 0x12000000
```

No initrd is permitted in the first contract. At entry x0 is the FDT and
x1-x3 are zero. The runtime requires EL2, the boot CPU, the exact FDT address,
a bounded valid FDT header/structure/reserve map, and identity strings for
`radxa,rockpi4c`, `rockchip,rk3399`, `serial2:1500000n8`, and `arm,gic-v3`.
It parks on every disagreement.

## Memory contract

| Range | Owner |
|---|---|
| `0x02000000..0x0200003f` | arm64 Image header |
| `0x02000040..0x027fffff` | linked code window |
| `0x02800000..0x03ffffff` | compiler BSS window, including bounded scanout |
| `0x04f00000..0x04ffffff` | primary cold-entry stack, 1 MiB |
| `0x05000000..0x050fffff` | held for later exception/multicore ownership |
| `0x12000000..0x121fffff` | exact external FDT handoff window |

The compiler refuses placement outside the conservative
`0x02000000..0x11ffffff` bootstrap envelope. The runtime rejects an FDT or
firmware reserve-map entry that intersects `0x02000000..0x050fffff`.
Installed 4 GiB is not treated as permission to allocate it; widening memory
ownership requires parsing the live memory and reserved-memory nodes.
The framebuffer reserves 2560x1600x32 bits (16,384,000 bytes) plus alignment
slack inside that BSS window. This is the pinned little-VOP maximum output,
not an assumption about the attached monitor. Selected pitch and height must
fit that allocation. The compiler gate proves its complete allocation before
an image is accepted.

## Earliest witness, vectors, timer and GIC

U-Boot configures RK3399 UART2 at `0xff1a0000` for 1,500,000 8N1. Anvil adopts
that state and emits its board-specific witness before FDT parsing. Display
clock, reset and power programming occurs later and is owned explicitly.

The architectural counter supplies every deadline; frequency and monotonicity
are validated first. All polling also has a finite iteration ceiling.

Anvil installs a 2 KiB-aligned EL2 vector table while every DAIF mask remains
set. Every vector captures ESR/FAR/ELR/SPSR once and parks. There is no IRQ
return until dispatch has hardware proof.

The GICv3 foundation uses GICD `0xfee00000` and six 128 KiB GICR frames from
`0xfef00000`. It finds the current frame by comparing GICR_TYPER affinity with
MPIDR, wakes only that redistributor, and owns only hypervisor physical timer
INTID 26. The board root deliberately leaves IRQ masked and never arms CNTHP
in this milestone.

All RK3399 peripheral registers in the board libraries are accessed at their
architectural width. In particular, UART, GIC, CRU, PMU, TCPHY, Cadence and VOP
32-bit registers use 32-bit loads/stores; the desk gate refuses `PeekN` or
`PokeN` anywhere in `RockPi4C/Lib`.

## MiniDP first-light contract

The September 13 FTDI run entered Anvil and reached the clock check, then
refused with `DPE1`, error 47. The inherited CPLL was in slow mode and GPLL
was locked at 800 MHz. The former check assumed a loader had prepared CPLL
at 384 MHz and GPLL at 594 MHz. Display clock setup must use the live parent
rate; this failure is not evidence of a broken serial loader or PLL.

The clock correction uses the decoded live GPLL for the non-pixel display
clocks and the dedicated VPLL for the exact 65 MHz pixel clock. Rockchip's
fractional-divider precision requirement is a denominator at least twenty
times the numerator for a non-integer division; both the former 65/594
fraction and a proposed 13/160 fraction fall short. The reference RK3399
65 MHz VPLL-specific tuple is reference divider 1, feedback divider 113,
post dividers 7 and 6, and fractional feedback 0xC00000 with DSM enabled.
That yields a 2.73 GHz VCO divided by 42. The DisplayPort firmware clock register receives the actual
core frequency in whole MHz.

The established deployment chain is stock U-Boot, a serial-capable U-Boot
loaded into RAM from the removable SD, then Anvil's Image and DTB transferred
over FTDI/XMODEM. The Anvil image and DTB passed board CRC checks twice before
entry. Build 39 subsequently passed PHY readiness, EDID, training and video
valid, and the physical monitor displayed the 1024x768 color bars and title.

Build 36 passed clocks, power, and Cadence firmware startup on the board,
then stopped inside PHY initialization. The source audit found a swapped
reset mapping: TCPHY's register interface is reset 332, UPHY is 149, and
PIPE is 148. The required release order is 332 before register access,
149 after configuration, then 148 after common-ready acknowledgement.
Holding 332 until the end left the register interface in reset during
configuration. Named reset identities and serial operation witnesses make
this order explicit. Fatal EL2 faults also report their saved syndrome,
address, and instruction address instead of parking silently.

The exact original 4C device tree selects VOPL -> Cadence DP and describes the
virtual Type-C state as DP with SuperSpeed enabled and no flip. That means two
DP lanes on TCPHY0 physical lanes 2/3 while USB3 retains lanes 0/1. The
connector's `dp_pwr` pinctrl entry is `<1 24 RK_FUNC_GPIO &pcfg_pull_up>`:
GPIO1_D0 is left as an input with its pull-up; Anvil does not invent an output
polarity. GPIO4_D1 is the active-low cable-detect net, while the Cadence HPD
mailbox state remains the authoritative post-firmware gate.

Cold bring-up is ordered and fail-closed:

1. derive display divisors from validated live PLL state, enable transition
   clocks, and configure GPIO1_D0 pin control;
2. power VIO, then its HDCP and VO/VOPL children, plus independent TCPD0, with
   bounded PMU power and bus-idle acknowledgement polls;
3. hold all relevant TCPHY0, Cadence and VOPL resets, initialize TCPHY0 split
   mode and AUX, then release blocks only when their dependencies are live;
4. load the exact Cadence DPTX IRAM/DRAM firmware, require its keep-alive,
   enable the host/event contract, and require HPD;
5. read DPCD and validate the EDID base block, then select its first detailed
   timing within the VOP, pixel-clock and two-lane bandwidth limits;
6. require the firmware link-training EQ-complete event and valid one- or
   two-lane link status; program transfer-unit and stream timing while idle;
7. apply the selected dedicated VPLL clock, render eight ARGB color bars plus
   `ANVIL ROCK PI 4C` with the selected stride, program matching VOP timing and
   polarity, then mark video valid. A rejected preferred timing falls back to
   1024x768@60 only if the same valid EDID advertises it. Serial output gives
   the selected dimensions, pixel frequency, source and rejection reason.

This supports the base EDID preferred progressive separate-sync timing plus
an explicitly advertised established fallback, not all extension-block modes.
Link training uses the Cadence firmware's fixed PHY settings, matching
the reference driver's documented fallback. A silicon failure at training may
justify adding software training with per-request TCPHY swing/pre-emphasis;
desk evidence is not permission to add it speculatively.

The UART trace identifies the last completed stage: `DP00` begins the cold
path, `DP01` through `DP07` identify clocks/power, PHY, firmware, HPD,
DPCD/EDID, framebuffer, and trained link, and `DP08 VISIBLE <width>X<height>` is issued
only after video is marked valid. `DPE1` through `DPEE` are terminal stage
refusals.

## Desk gates and first board run

### FTDI recovery

After the validated entry/display path, UART2 is polled without unmasking
interrupts. Exact lowercase `help` and `reboot` lines are accepted. Unknown,
overlong or UART-error-contaminated lines do not cause a reboot. The reset
path waits a bounded time for UART LSR TEMT, issues PSCI SYSTEM_RESET through
SMC to retained EL3 firmware, and reports/fail-stops if firmware unexpectedly
returns. It never guesses a direct-CRU fallback. A physical cycle is still
needed after an early fatal failure that cannot service the recovery loop.
Network-triggered reboot is not implemented on this target.

This new command path requires its own silicon acceptance: `help` must reply,
invalid lines must not reset, and `reboot` must return the board to the stock
boot chain without a physical power cycle.

```text
python tools/rockpi4c_foundation_check.py --compiler <candidate>
python tools/rockpi4c_display_check.py --compiler <candidate>
python tools/build.py rockpi4c --compiler <candidate>
```

Before a board run, verify the generated `Image.json` hash, attach the MiniDP
display before power-on, and retain the proven stock-U-Boot recovery media.
Preferred-mode acceptance is:

1. the early UART witness appears at 1,500,000 baud;
2. no refusal appears;
3. clock/PHY/EDID stages precede link training (`DP07`), then framebuffer
   arming (`DP06`) and valid video (`DP08`);
4. eight color bars and `ANVIL ROCK PI 4C` are stable at the reported preferred
   resolution; if fallback is required its reason and preferred dimensions
   are explicit, and full preferred-mode proof remains unmet;
5. `FOUNDATION READY; IRQ STILL MASKED` appears;
6. U-Boot recovery still works after a power cycle.

That run proves only this connector/display/mode/link combination. It does not
prove timer interrupts, secondary cores, storage, other modes or displays,
networking or Mali.

## Primary references and clean implementation

- Arm, *A-profile Architecture Reference Manual*, architectural exception,
  timer and GIC system-register definitions.
- Arm, *Generic Interrupt Controller Architecture Specification*, GICv3.
- Linux kernel documentation, `Documentation/arch/arm64/booting.rst`, arm64
  Image header and register handoff.
- Devicetree bindings and DTS for `rk3399-rock-pi-4c`, `arm,gic-v3`,
  `arm,armv8-timer` and `snps,dw-apb-uart`.
- Mainline U-Boot `booti` implementation and ROCK Pi 4C defconfig/DTS.
- Radxa release-4.4-rockpi4 revision
  `86a614bc15b3b1aeb3a9a9e395aedd088c70e35e`, RK3399 power/clock/TCPHY,
  Cadence DP and VOP register facts and ordering.
- linux-firmware revision `d371ae3b6888b260e4c37b327a020401cfaaaefd`,
  unmodified Rockchip DPTX firmware version 3.1.

Those references establish interfaces and facts. This MIT repository contains
an original implementation; no GPL implementation code was copied.

## Bundled Rockchip DPTX firmware terms

The `dptx.bin` bytes embedded in `RockPi4C/Lib/cdn_dp.pbi` are not covered by
the Anvil MIT license. The following notice and terms accompany those
unmodified binary firmware bytes:

```text
Copyright (c) 2016, Fuzhou Rockchip Electronics Co.Ltd
All rights reserved.

Redistribution.  Redistribution and use in binary form, without
modification, are permitted provided that the following conditions are
met:

* Redistributions must reproduce the above copyright notice and the
  following disclaimer in the documentation and/or other materials
  provided with the distribution.

* Neither the name of Fuzhou Rockchip Electronics Co.Ltd, its products
  nor the names of its suppliers may be used to endorse or promote products
  derived from this Software without specific prior written permission.

* No reverse engineering, decompilation, or disassembly of this software
  is permitted.

Limited patent license. Fuzhou Rockchip Electronics Co.Ltd grants a world-wide,
royalty-free, non-exclusive license under patents it now or hereafter
owns or controls to make, have made, use, import, offer to sell and
sell ("Utilize") this software, but solely to the extent that any
such patent is necessary to Utilize the software alone, or in
combination with an operating system licensed under an approved Open
Source license as listed by the Open Source Initiative at
http://opensource.org/licenses.  The patent license shall not apply to
any other combinations which include this software.  No hardware per
se is licensed hereunder.

DISCLAIMER.  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING,
BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
DAMAGE.
```
