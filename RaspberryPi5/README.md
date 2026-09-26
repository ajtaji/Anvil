# Raspberry Pi 5 source bring-up

There is no Raspberry Pi 5 Anvil image or hardware boot proof. The Pi 5 is not
connected. The prepared card in the separate vault has FAT32 and exFAT volumes,
Pi 5 DTB variants and overlays, but no `ANVIL5.IMG`. Do not put the Pi 4
`kernel8.img` in its place.

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
