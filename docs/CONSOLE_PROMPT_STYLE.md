# Anvil prompt style

The interactive `pmf> ` prompt is bright green where a target has an on-screen
console. Its protocol remains exactly five ASCII bytes followed by no newline.
No ANSI escape is inserted: upload, board-run and network-console tools continue
to match the same raw stream.

On Raspberry Pi 4, `UartScreenStyle()` attaches a one-byte style only to the
primary screen-mirror entry. The independent PL011 and auxiliary/network paths
receive only the original character. The terminal grid stores style beside each
cell, and both the DMA and V3D renderers paint contiguous prompt runs as
RGB(80,255,120); ordinary text remains RGB(226,232,240). Clear, scroll, wrap,
tab and backspace update character and style state together.

On Arduino UNO Q, the firmware text console is the display seam. Main saves the
current UEFI text attribute, selects light green on black, emits and flushes the
prompt, then restores the exact saved attribute before `ReadLine()` echoes input.
The transcript contains no colour metadata.

The current Pi 3 cold-entry image parks after its hardware diagnostic and does
not yet expose an interactive prompt. When its full command loop lands, it must
use the display backend's style seam rather than adding bytes to PL011.

Desk gates:

- `tools/screen_capture_console_emitted_check.py` executes the Pi 4 mirror and
  grid operations in emitted A64 and checks both renderers' source contract.
- `tools/unoq_prompt_style_check.py --compiler <PureMetalForge.exe>` compiles
  the UNO Q UEFI attribute fixture and rejects ordering/protocol mutations.
