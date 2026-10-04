# Pi 5 firmware PCIe adoption: current-source desk gates

The BCM2712 branch of the shared PCIe driver now accepts the inbound DMA
window the Pi 5 firmware actually left at PCIe base zero. It verifies the
window's ARM-zero remap and size, sets root-port bus numbers only when all
three are unset, and checks RP1's existing memory BAR before using its
register window. On a Linux-style 64 GiB window at PCIe `$10_0000_0000`, it
continues to use that base. No Pi 4 PCIe path was changed.

The motivating Pi 5 silicon captures were made with resident build 215 from
Anvil `f385c7b`: RC_BAR2 described a 64 GiB window at PCIe zero, UBUS_BAR2
remapped ARM zero with access enabled, root-port bus numbers were all zero,
and RP1's BAR decoded at PCIe zero. A returning diagnostic with the adopted
layout completed two xHCI No-Op DMA commands. That diagnostic is evidence for
the hardware layout and this narrow transaction; **the full monitor with
this source has not booted on Pi 5 silicon**.

On the current tree, using the tracked PureMetalForge build, the following
desk checks passed after applying the BCM2712 change:

| Gate | Result |
|---|---|
| `a64_pcie_pi5_inbound_check.py` | Six layouts, eight of eight fault mutants rejected |
| `a64_xhci_pi5_check.py` | Nine scenarios, 24 of 24 fault mutants rejected |
| `a64_usb_kbd_pi5_check.py` | Five scenarios, five of five fault mutants rejected |
| `a64_gem_pi5_check.py --sources <Pi-5-vault-folder> --no-mutants` | 194 checks; hardware constants re-derived from three pinned DTBs |
| `a64_usb_msc_pi5_check.py --no-breaks` | FAT32, exFAT and no-stick scenarios |
| `a64_nvme_pi5_check.py --no-mutants` | 41 checks; the unmodified-tree baseline had already rejected 11 of 11 mutants |
| `pi5_sd_save_check.py` | Modeled ANVIL5.IMG replacement, independent readback and lost-word negative control |

A Pi 4 image compiled before and after this change was byte-identical:
5,255,504 bytes, SHA-256
`656B42255217E68D4A80CB79DCBF9938EE77E347A9194A9099D9C9448D87A7BB`.
The images were compiled from `RaspberryPi4/Board/board.pi4` with `-t pi4`
and the same compiler executable. This verifies the Pi 4 source branch
remained unchanged in that build; it is not a Pi 4 board run.

The full `pi5_boot_to_prompt_check.py` model takes its DTB and config from an
explicit `--boot-staging` directory (or `PI5_BOOT_STAGING`), rather than a
machine-specific path. An exact-tree `absent` run built both Pi 5 images but
the first image exhausted the model's 80-million-step limit in
`anvil_tt_TableChecksum`, before the board bring-up or PCIe path. Its UART
streams matched, with no forbidden access or code write, but it did not reach
`pmf>`. The second image was stopped rather than spending another full model
budget in the same font checksum. This is **not** a boot pass or evidence of a
Pi 5 hardware hang. A model fast path for the checksum would need independent
equivalence checks before this gate could efficiently cover the current boot.
The Pi 5 card rebuild and physical monitor boot acceptance remain open.
