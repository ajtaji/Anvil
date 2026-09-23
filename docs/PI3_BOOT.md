# Raspberry Pi 3 direct firmware boot

The normal Raspberry Pi 3 card boots the complete Anvil monitor as
`kernel8.img`. A Pi 3-specific `armstub8.bin` runs first at address zero. This
is a direct firmware boot: the firmware does not start an Anvil A/B selector,
and the monitor does not need a slot header, control record, handoff page, or
slot checksum before it can show the console.

## Firmware and stub contract

With `arm_64bit=1`, Raspberry Pi firmware normally uses its built-in AArch64
stub for `kernel8.img`. Selecting `armstub=armstub8.bin` replaces that stub;
on Pi 3 firmware enters the custom stub at EL3. The Pi 3 stub follows the
firmware's fixed armstub layout: it supplies a magic/version block at `0xF0`,
accepts the firmware device-tree pointer at `0xF8` and kernel entry at `0xFC`,
and leaves the secondary-core release slots clear. The stub code must end
before the first firmware-owned slot.

The Anvil stub configures the BCM2837 counter at 19.2 MHz, enables SMP
coherency, configures the EL3 state used by the monitor, masks asynchronous
exceptions, and enters AArch64 EL3h. It parks cores 1-3 in the firmware spin
table. The primary core branches to the firmware-provided kernel entry with
`x0` equal to the firmware DTB address and `x1-x3` cleared. The monitor verifies
EL3 at entry and in `Main`; it refuses a lower-level handoff. It does not
configure the Pi 4 GIC or use the Pi 4 local-control aperture.

The monitor's placement declarations are:

| Region | Address |
| --- | ---: |
| Full `kernel8.img` load and entry | `0x00200000` |
| Firmware DTB | `0x01000000` |
| Monitor BSS | `0x01100000` |
| Monitor stack top | `0x01F00000` |

The emitted PMF sidecar is checked against these values and the compiler target
for BCM2837. The raw kernel image must end before the DTB reservation; BSS must
end before the stack reservation. The firmware-provided RAM extent and DTB
header/span are checked by the monitor after its first instruction has saved
`x0`.

## Monitor startup order

`Main` captures firmware `x0` before calling runtime code. It then establishes
the serial console, asks the firmware for the memory and clock information the
board needs, installs its exception reporting, and builds the MMU mappings
before entering the normal Anvil prompt. SD host initialization is lazy: the
prompt can appear before the first card access. A filesystem mount or hash of
slot metadata is not part of normal cold startup.

Firmware mailbox calls use the registered aligned non-cacheable property
buffer and ownership checks, including after MMU/cache enable. SDHOST receives
its remembered card-clock value during the pre-MMU handoff; the cached SD path
refuses a missing clock handoff or mixed MMU/cache state.

After the first prompt, the board loads the configured TrueType face before
drawing the banner, then advances saved-network startup cooperatively. The
verified Model B v1.2 run connected automatically, received DHCP address
`192.168.1.22`, and completed a CRC-checked 64 KiB wireless transfer. VideoCore
IV has a returning-payload proof for powering the documented firmware domain,
reading IDENT, and clearing a guarded offscreen target. Pi 3 Vulkan, GPU
presentation, USB host, and USB Ethernet are not implemented.

## Build and validate

Build the Pi 3 stub and complete monitor with the single board target:

```text
python tools/build.py pi3 --compiler <PureMetalForge.exe>
```

The targets are also available separately as `pi3-stub` and `pi3-monitor`.
The direct-boot gate checks the actual stub's firmware fields, primary EL3 to
EL2 transfer, counter and Pi 3 register setup, and secondary spin/release
behavior. With a counted monitor artifact present, it also validates the
monitor's PMF load/BSS/stack contract and early direct-entry requirements:

```text
python tools/pi3_direct_boot_check.py
```

The source/config-only check is `python tools/pi3_direct_boot_check.py
--source-only`; the stub can be checked before a full monitor build with
`python tools/pi3_direct_boot_check.py --stub-only`. These desk gates execute
emitted AArch64 instructions or inspect declared source/config contracts. They
do not prove firmware acceptance, physical DRAM reservations, timer accuracy,
or a board boot.

## Current boundary

The monitor supports the direct firmware entry and keeps Anvil's file-backed
payload loader. The normal boot does not use the legacy A/B selector/update
transaction. Hardware drivers and capabilities remain governed by the Pi 3
composition's capability declarations; a built-in peripheral is not evidence
that Anvil has a working backend for it.

For the pinned firmware set, staging and replacement rules, see
[Pi 3 direct update](PI3_SELF_UPDATE.md). The official firmware contract is
documented in [Raspberry Pi's `config.txt` reference](https://www.raspberrypi.com/documentation/computers/config_txt.html);
the EL3 behavior of a custom `armstub8.bin` is summarized by the
[ARM Trusted Firmware Pi 3 platform notes](https://github.com/ARM-software/arm-trusted-firmware/blob/master/docs/plat/rpi3.rst).
