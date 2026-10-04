# Anvil on Raspberry Pi 5

The current Pi 5 monitor is the shared Anvil composition in
`RaspberryPi4/Board/board.pi4`, selected by `#PMF_CHIP = 2712`. Its Pi 5
firmware stub is `RaspberryPi5/Board/armstub8-2712.asm`. The image is linked at
`$80000`, where the Pi 5 firmware loads it; the card configuration must not
set `kernel_address`. `tools/pi5_card_build.py` prepares `ANVIL5.IMG` and the
stub from an exact commit and validates the card layout before writing it.

On 2026-09-27, the image from Anvil commit `f385c7b` booted on Pi 5 silicon
at EL3 and reached the `pmf>` prompt. The serial capture recorded an HDMI
console, caches on, a 2.4 GHz CPU, 8 GB RAM, firmware mailbox and thermal
readings, and fan control. That boot refused PCIe because the RP1 inbound
window was not adopted; USB, card storage and Ethernet could not start. The
card did not yet contain the later PCIe, storage-order and idle changes saved
for the next hardware session. A later returning PCIe/RP1 payload adopted the
firmware's base-zero inbound window, set the root port's missing bus numbers,
adopted RP1's BAR, and completed two xHCI No-Op DMA requests on silicon. The
shared monitor source now includes that adoption path. Its modeled PCIe,
xHCI, keyboard, USB-storage and GEM gates pass, and the Pi 4 image is
byte-identical before and after the BCM2712-only change. The updated monitor
has **not** been booted on Pi 5; the first prompt remains the last full-monitor
silicon result, and USB, card storage and Ethernet remain separate acceptance
work.

The board-specific `RaspberryPi5/Board/board.pi4` is an earlier framebuffer,
logo and serial composition. `RaspberryPi5/Boot/board.pi4` is an even earlier
FDT/exception-level entry probe. Neither is the current full monitor entry.
The active board source and device drivers are shared with the Pi 4 through
explicit BCM2712 branches; Pi 5 changes must preserve the Pi 4 path.

V3D 7.1 power/clock, TFU and CSD/QPU work has dedicated desk-gated probes.
The production Pi 5 monitor does not yet have a Vulkan hardware backend or a
GPU-rendered console proof. Its display currently uses the firmware surface;
the DMA/blitter path was still failing at the pause point. Pi 5 HDMI EDID,
DSI video and further GPU bring-up remain open.

The next board session should build a checked card from main and verify the
PCIe adoption in the full monitor, then check SD, USB and Ethernet from
`pmf>`. Storage boot order and idle-sleep work remains parked. Returning RAM
payloads with the deadman armed are the test path for V3D 7.1 before changing
the resident monitor. Do not infer device or Vulkan support from a compile
gate alone.

The boot and memory-map contract is checked by `tools/a64/pi5_boot_to_prompt_check.py`
and `tools/a64/pi5_memmap_check.py`. The earlier DTB probe and its source-tree
preflight remain under `RaspberryPi5/Boot/` for diagnostics; they do not replace
the current monitor.
