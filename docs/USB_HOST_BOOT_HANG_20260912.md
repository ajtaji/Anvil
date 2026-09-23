# Pi 4 USB host boot hang: source comparison and silicon result

The intermittent boot stop at `USB host (xHCI)` was narrowed to the first
`USBSTS` read in the new owner's halt/readiness path. Capability-register
reads immediately before it completed, so this was not a missing BAR, a
truncated address, or the automatic-frame/address failures exercised by the
emitted audit. The retained detail word was `0x0812`: "before first readiness
USBSTS read."

## Reference implementations inspected

The implementation was compared with pinned upstream source, not reconstructed
from observed register values:

- U-Boot commit `a44f46af0aa17e48572e0d46c0d082886ee353c3`,
  `drivers/pci/pcie_brcmstb.c`, `drivers/usb/host/xhci-pci.c`,
  `drivers/usb/host/xhci.c`, and `arch/arm/include/asm/io.h`.
- Raspberry Pi Linux commit `7d1826930811232688a50c99c540fbb137aed081`,
  `drivers/pci/controller/pcie-brcmstb.c`,
  `drivers/usb/host/xhci-pci.c`, and `arch/arm64/include/asm/io.h`.

Those sources establish the individual bridge, controller, and MMIO
requirements used by Anvil's ownership design. No single upstream routine
implements the whole firmware-adoption handoff:

1. The xHCI controller must be halted before reset, while BCM2711 ownership
   crosses through the bridge/PERST reset and link-retrain sequence. Anvil
   additionally proves the former firmware owner halted and BME cleared before
   combining those requirements at its ownership boundary.
2. BCM2711 uses `MISC_CTRL` RCB MPS mode; Linux also selects 64-byte RCB mode.
3. A driver that does not implement PCIe power management needs an explicit
   safe CLKREQ policy and must not advertise ASPM states it will not manage.
4. PCIe and xHCI registers are accessed with ordered `readl`/`writel`
   primitives. Raw AArch64 loads and stores are not equivalent.

## Implemented ownership boundary

`PcieInit` now adopts a trained firmware link only long enough to validate its
existing routing and locate the live xHCI registers. `XhciQuiesceAdopted`
waits for CNR to clear, clears Run/Stop, proves HCHalted, then disables and
reads back BME. `PcieEnumerate` then performs the shared reset/train helper,
invalidates every old BAR/DMA cache, retrains the link, enumerates the VL805,
notifies VideoCore, and leaves BME disabled until the xHCI driver reaches the
same enable-before-halt/reset boundary as U-Boot.

PCIe and xHCI MMIO helpers now preserve 32-bit register width and 64-bit
addresses while applying barriers after device reads and before and after
device writes. This is deliberately stronger than U-Boot's minimum DMB
pre-write/post-read implementation. A failed reset attempt is remembered so a
half-owned link cannot be mistaken for firmware-owned hardware on a retry.

## Proof

- Emitted-code execution verified balanced automatic frames, 64-bit BAR
  arithmetic, 32-bit MMIO accesses, post-read barriers, and pre/post-write
  barriers.
- `tools/pcie_takeover_check.py`: 17 emitted ownership/BME cases pass.
- `tools/pcie_reset_policy_check.py`: reset admission, failed-link and unsafe-
  ownership cases pass; six missing-policy/order mutants are rejected.
- `tools/xhci_initial_readiness_check.py`: three readiness cases pass and
  three readiness/cleanup/marker mutants are rejected.
- `tools/vl805_firmware_check.py`: normal, missing-notification and wrong-order
  cases behave as expected.

Silicon comparison on the same Pi 4 and boot medium:

| Image | SHA-256 | Controlled resets | Watchdog recoveries |
| --- | --- | ---: | ---: |
| Reset/policy correction without ordered MMIO | `399061cefbedf147822b432c9184b8fb49af6c836073659435800dd508bf5cd6` | 2 | 2 |
| Reset/policy correction with ordered MMIO | `cb06eac8f02ceae753102bb8fc89f35792351f7ecf99975f5525bf4857ba43cf` | 5 | 0 |
| Main-tree build 92 with the source-backed correction | `6bd3502a246fdab492100344ba6dcd1e5c158e9f1829e11e2494074fb4b15ad7` | 3 | 0 |

The retained boot counter advanced exactly once on each of the five passing
resets (`22` through `27`), and the prior `0x0812` failure word cleared. This
isolates ordered MMIO as the change correlated with eliminating the observed
warm-reset hang. The main image was then verified byte-for-byte after transfer,
saved as `B92MAIN.IMG` and `KERNEL8.IMG`, and its running-image CRC32
`518D4A83` matched the host file. Three further resets advanced the retained
counter exactly once each (`27` through `30`) with failure state `0x0002`.
A physical power-removal cold cycle remains a separate final check; it cannot
be performed remotely without risking an unreachable board.
