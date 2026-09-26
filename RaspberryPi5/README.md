# Raspberry Pi 5 source bring-up

The prepared Pi 5 card has a first-entry **diagnostic** `ANVIL5.IMG`, not a
network-capable Anvil monitor. The Pi 5 is not connected, so firmware handoff,
serial output and Wi-Fi remain unproved on hardware. Do not put the Pi 4
`kernel8.img` in its place.

`Boot/board.pi4` produces the diagnostic with the IDE compiler:

```powershell
PureMetalForge.exe --compile RaspberryPi5/Boot/board.pi4 -t pi4 -o runs/pi5-entry.img
```

The present compiler has only the Pi 4 AArch64 target. This source uses that
instruction emitter without its BCM2711 hardware intrinsics or libraries. It
is linked at the documented 64-bit firmware default `$200000`, with separate
BSS at `$400000` and stack at `$800000`. The emitter's `_start` sets the stack,
masks exceptions and clears BSS using x9/x10/x16; it does not modify x0 before
the source saves the expected live FDT pointer. These are source and compiler
checks, not Pi 5 firmware measurements. The image writes `ANVIL PI5` and
`FDT 0` (missing pointer), `FDT 1` (magic only) or `FDT 2` (bad magic) at
115200 baud on the dedicated 3.3 V Pi 5 debug UART. It then stays in a loop.
It cannot read the card, display a prompt, or join Wi-Fi.

`PeekL` is signed, so the magic word must be masked to 32 bits before it is
compared with `$EDFE0DD0`. The first card image compared the sign-extended
value against a zero-extended constant and would have printed `FDT 2` for every
valid tree (disassembly audit, 2026-09-26). The corrected image is 1,108 bytes,
SHA-256 `1D5EA770653E7A26F3C6A72B12307A9A9CB967389DA52AF7BDBCC909172FB01D`.
The card's `config.txt` adds `os_check=0` (not a Linux kernel) and
`uart_2ndstage=1` (bootloader progress on the debug UART).

The source DTB's UART10 child address `$7D001000` translates through `/soc`
`ranges` to CPU physical `$107D001000`. The WLAN is a function on BCM2712
SDIO2 at physical `$1001100000`, 4-bit, non-removable, with a WL_ON regulator.
`dtb_contract.py` now validates both translations and the wireless bus
contract across all three staged tree variants. A previous untested diagnostic
used `$107C001000`; it was replaced on the card before any Pi 5 boot.
Wi-Fi requires a Pi 5 SDIO2 transport, power/clock/pin setup, firmware upload,
and the existing CYW43 protocol and network stack, followed by board proof.

`Boot/dtb_contract.py` is a **host-side source-tree preflight**. It validates
the FDT envelope, node structure, Pi 5/BCM2712 identity, memory node, enabled
BCM2712 PCIe host, RP1 bridge, and address-translation properties. It reports
the paths a first board image must discover from the *bootloader-provided*
DTB. It also resolves the source tree's `chosen/stdout-path` through aliases
and refuses a missing, disabled or non-PL011 early UART. It does not prove the
firmware-selected DTB, RAM extent, PCIe windows, EL3 handoff, or a single
peripheral at runtime.

Run it against the three explicit pinned files in the vault:

```powershell
$env:PI5_DTB_DIR = "$env:USERPROFILE\Desktop\CompilerEmbedded\Raspberry Pi 5\Boot staging"
py -3 RaspberryPi5/Boot/dtb_contract.py "$env:PI5_DTB_DIR\bcm2712-rpi-5-b.dtb" "$env:PI5_DTB_DIR\bcm2712-d-rpi-5-b.dtb" "$env:PI5_DTB_DIR\bcm2712d0-rpi-5-b.dtb"
py -3 -m unittest discover -s RaspberryPi5/Boot -p test_dtb_contract.py -v
```

The preflight reports `Raspberry Pi 5`, `brcm,bcm2712`, a memory node,
`/axi/pcie@1000120000/rp1`, and the enabled PL011 early UART at
`/soc@107c000000/serial@7d001000` for each pinned variant. Four tests pass,
including malformed-tree, wrong-board and broken-UART refusals. The source
trees select `serial10:115200n8`; their RP1 `serial0` and `serial1` nodes are
disabled. Set `PI5_DTB_DIR` to
the explicit directory containing the three named DTBs on another host.

Next source milestones, in dependency order:

1. Establish the Pi 5 firmware-to-Anvil entry contract, including verified
   AArch64 EL3 entry, x0 live DTB handoff, stack, exception vector and cache
   state. The Pi 4 `armstub8.bin` configures BCM2711 registers and is not a
   Pi 5 stub. Refuse entry if the required level is unavailable; do not infer
   it from the pinned source DTB.
2. Validate the live DTB bounds, parse memory and reserved ranges, selected
   aliases, PCIe/RP1 ranges and interrupt topology. Never use the source DTB's
   unmodified memory placeholder as installed RAM size.
3. Bring up an early serial diagnostic that returns, then timer/interrupts,
   SD through the existing shared filesystem interface, and PCIe/RP1. Attach
   display, network, USB, wireless and GPU only after their dependencies pass.

Hardware evidence is required before any source milestone is called booted or
working. The Pi 5 reference files, pinned revisions, and boot checklist live
in the vault's `Raspberry Pi 5/SOURCES.md` and `HARDWARE-BRINGUP.md`.
