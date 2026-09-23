# ROCK Pi 4C v1.2 direct-SD EL3 candidate

Build 99 cold-booted from SD into its EL3 UART console on 2026-09-21. Its
`help`, filesystem, trust update, acknowledged 2 MiB download, and software
`reboot` paths passed on hardware. Its single loaded Anvil component contains
a 556-byte entry at `0x00040000`, a 532,448-byte runtime at
`0x00041000`, and the 96,672-byte board DTB at `0x001C0000`; the component is
1,669,536 bytes and the two-copy trust image is 4 MiB. Earlier U-Boot
runs proved MiniDP first light at 1024x768 and a UART console; 1920x1080 rolled
and corrupted. Those results do not validate this direct-SD entry path.

## Identity and ownership

This target is the original ROCK Pi 4C PCB v1.2 with RK3399. It is not a
Raspberry Pi 4 and not the RK3399-T 4C+. The `rockpi4c` compiler profile uses
the existing ARMv8-A A64 IR/emitter/assembler and its own RK3399 intrinsic
file. It does not import BCM2711 mailbox, V3D, GENET, interrupt-controller or
MMIO definitions.

The SD image uses Rockchip DDR/miniloader firmware, which trained both
2 GiB LPDDR4 channels and entered the wrapper at EL3. No U-Boot or TF-A
runtime is present. The candidate cold-entry wrapper is PMF raw A64 at
`0x00040000`; its emitted-code gate checks EL3 and cache state before branching
to the real Anvil composition at `0x00041000`. It also establishes a 24 MHz
counter frequency and the secure timer when not already enabled. Anvil does
not depend on a resident TF-A/PSCI service in this path.

## Direct-SD handoff contract

The cold-entry wrapper requires EL3, an inactive MMU/data cache and trained
DDR. It masks DAIF and disables an inherited instruction cache before compiler
startup. The measured incoming SCTLR_EL3 was 0x00C5383A; only I was set
among M/C/I. Lower-level or MMU/data-cache-enabled entry is refused. The current candidate wrapper enters
at `0x00040000`, then branches to the Anvil runtime at `0x00041000`; the
embedded board DTB is at `0x001C0000`. At Anvil entry x0 is that DTB and x1-x3
are zero; the stack
top is `0x05000000`. UART2 is inherited at 1,500,000 8N1 from the Rockchip
firmware, and the wrapper sets CNTFRQ to 24 MHz and enables the secure timer if
needed. These entry conditions passed the first cold-boot and software-reset runs.

The compiler's emitted `_start` sets SP, masks DAIF, barriers, and clears BSS
before calling `Main`. It does not itself check CurrentEL. The wrapper's cold
entry check is therefore mandatory; `Main` preserves x0 as the FDT pointer,
rechecks CurrentEL==EL3, verifies its stack is aligned and checks that SCTLR_EL3
M/C/I are clear. It then installs a 2 KiB-aligned VBAR_EL3 table before timer
or UART services. The DTB validator requires the exact address, bounded valid
FDT structure/reserve map, and identity strings for `radxa,rockpi4c`,
`rockchip,rk3399`, `serial2:1500000n8`, and `arm,gic-v3`.

## Memory contract

| Range | Owner |
|---|---|
| `0x00040000..0x00040fff` | Anvil EL3 entry prefix |
| `0x00041000..0x001bffff` | linked Anvil runtime window |
| `0x001c0000..0x0023ffff` | embedded board-DTB window |
| `0x00240000..0x027fffff` | unloaded reserved gap before compiler BSS |
| `0x02800000..0x03ffffff` | compiler BSS window, including bounded scanout |
| `0x04f00000..0x04ffffff` | primary cold-entry stack, 1 MiB |
| `0x05000000..0x050fffff` | held for later exception/multicore ownership |

The bundler refuses an entry larger than 4 KiB, a runtime that reaches the
embedded DTB, or a DTB that takes the component beyond `0x00240000`. The
runtime requires the same fixed DTB address and an end no later than
`0x00240000`; it rejects a firmware reserve-map entry that intersects Anvil's
early ownership range `0x00040000..0x050fffff`.
Installed 4 GiB is not treated as permission to allocate it; widening memory
ownership requires parsing the live memory and reserved-memory nodes.
The former display framebuffer reservation remains inside the BSS window, but
display initialization is disabled for this direct-SD entry candidate. The
existing MiniDP path has not been checked against the candidate loader state.

## Early witness, vectors, timer and deferred GIC

The wrapper inherits the Rockchip firmware's UART2 setup at `0xff1a0000` and
Anvil adopts it at 1,500,000 8N1. The wrapper sets the architectural counter
to 24 MHz and ensures the secure timer is enabled. Anvil requires that exact
frequency and validates monotonic reads before using bounded UART polling.

Anvil installs a 2 KiB-aligned EL3 vector table while every DAIF mask remains
set. Every vector captures ESR_EL3/FAR_EL3/ELR_EL3/SPSR_EL3 once and parks.
There is no IRQ return until dispatch has EL3 hardware proof.

The old GICv3 foundation uses GICD `0xfee00000` and six 128 KiB GICR frames
from `0xfef00000`, but owns the EL2 hypervisor timer PPI (INTID 26). It is not
called by the direct-SD path. GIC setup and display are explicit disabled
capabilities; IRQ remains masked and the UART recovery loop polls for commands.

All RK3399 peripheral registers in the board libraries are accessed at their
architectural width. In particular, UART, GIC, CRU, PMU, TCPHY, Cadence and VOP
32-bit registers use 32-bit loads/stores; the desk gate refuses `PeekN` or
`PokeN` anywhere in `RockPi4C/Lib`.

Direct EL3 accesses to PL330 use the secure APB mapping in RK3399 TRM figure
1-1. DMAC0's secure alias is `0xFFFC0000`; `0xFF6D0000` is the normal-world
view published to Linux. The normal view returned all-zero status and
PrimeCell identity at EL3 even after a bounded TF-A-style tie-off/reset
experiment. A UART-only-write probe of `0xFFFC0000` then returned
`PID=0x00241330` and `CID=0xB105F00D` with live configuration registers. The
runtime therefore admits only the secure DMAC0 alias, never DMAC1, and does
not alter PL330 security tie-offs or resets. Its 100 MHz clock plan and
readiness checks remain mandatory, and failure only disables DMA acceleration;
HDMI continues through the CPU framebuffer path. PL330 fill uses the
silicon-proven incrementing-copy instruction sequence from a CPU-seeded
256-byte region and doubles the filled span with nonoverlapping copies. This
larger-span algorithm is awaiting a hardware proof. The fixed-memory-source
program is excluded because it faulted on this board. Hardware passed a
private-buffer incrementing copy/compare and a 256-byte repeating-block
fill/compare using the earlier algorithm on 2026-09-21. The fill proof
returned `0x444D4100`, completed all `0x100` bytes and captured no PL330 fault.

## Historical U-Boot MiniDP path (not the direct-SD candidate)

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

## Direct-SD recovery and desk gates

### FTDI recovery

After the validated EL3 entry and DTB, UART2 is polled without unmasking
interrupts. Exact lowercase `help` and `reboot` lines are accepted. Unknown,
overlong or UART-error-contaminated lines do not cause a reboot. The direct-SD
reset path drains UART and writes the known RK3399 sequence: clear PMUGRF at
`0xff320300`, then write the keyed warm-reset value `0xeca8` to CRU at
`0xff760504`. It does not call PSCI. The direct-SD `reboot` command returned through DDR/miniloader startup to
Anvil at EL3, where `help` answered again on 2026-09-21. Network-triggered reboot is not implemented.

Build 47's UART and PSCI recovery tests belong to the old U-Boot path. The
current desk gate builds the real Anvil composition as a flat payload; the
separate SD wrapper gate covers nine emitted entry, refusal and handoff cases.
Build 96 with the 556-byte wrapper passed cold boot and software reboot.
Its recovery console also passed a 2 MiB exFAT put/get integrity run using the
negotiated 16 KiB serial window and bounded multi-block SD path. The returned
file matched the source SHA-256 exactly.

Build 97 corrected the early-ownership base but retained an obsolete rule that
required the DTB to be external to Anvil. It reached EL3, reported its SCTLR,
then refused the handoff before recovery. Build 98 bounds the DTB inside the
single Anvil component and preserves the corrected firmware-reservation check.
Build 99 adds acknowledged 16 KiB windows to file downloads. It installed from
build 98, verified both trust copies, returned through a software reset to EL3,
and downloaded 2 MiB with an exact host SHA-256 match.

```text
python tools/rockpi4c_foundation_check.py --compiler <PureMetalForge> --output build/rockpi4c/anvil-single-99/anvil-runtime.bin
```

For later builds, verify the SD wrapper/payload/DTB hashes. The initial EL3
handoff, UART adoption, DTB validation and direct reset now have hardware
evidence; this does not prove the deferred drivers. Display/GIC remain
disabled and have no acceptance steps in this candidate. Historical MiniDP
acceptance was limited to the old U-Boot state:

1. the early UART witness appears at 1,500,000 baud;
2. no refusal appears;
3. clock/PHY/EDID stages precede link training (`DP07`), then framebuffer
   arming (`DP06`) and valid video (`DP08`);
4. eight color bars and `ANVIL ROCK PI 4C` are stable at the reported preferred
   resolution; if fallback is required its reason and preferred dimensions
   are explicit, and full preferred-mode proof remains unmet;
5. the old display path printed `FOUNDATION READY; IRQ STILL MASKED`;
6. the old U-Boot recovery path returned after a power cycle.

That run proves only this connector/display/mode/link combination. It does not
prove timer interrupts, secondary cores, storage, other modes or displays,
networking or Mali command submission.

The compiled board contains an observation-only Mali-T860 probe contract. It
checks RK3399 PMU/CRU power, idle, clock and reset state before permitting any
GPU-aperture read, then exposes bounded feature, job-manager and MMU snapshots.
The first returning deadman payload observed all admission fields ready. A
second returned `GPU_ID=08602000`, `MMU_FEATURES=00002830`,
`AS_PRESENT=000000FF`, `JS_PRESENT=00000007`, and zero GPU, job-manager and MMU
status, then returned `X0=47512000` cleanly to recovery; passive serial remained
silent. `gpuinfo` repeats only this proven read set behind the hardware deadman
and exact lowercase command grammar. The GPU layer contains no power, clock,
reset, MMU or job write and is not called
at boot. Command submission and rendering remain outside the proven boundary.

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
