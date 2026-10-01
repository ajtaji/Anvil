# Pi 4 ordered Vulkan draw-list scale diagnostic

`vulkanDrawListScaleProof.pi4` is a returning RAM payload. It records 64, 256,
or 1024 actual `vkCmdDraw` calls in one render pass and one `vkQueueSubmit`.
Each call supplies six different vertices and colours a separate 2×2 cell
inside a 128×128 private BGRA8 attachment. The CPU poisons the allocation
before submission but never paints a final pixel. The payload checks every
pixel against an independent cell oracle, including the undrawn background,
and returns a 64-word report pointer in X0.

Build variants and check a captured 256-byte report with
`tools/pi4_vulkan_drawscale.py`:

```text
python tools/pi4_vulkan_drawscale.py --self-test
python tools/pi4_vulkan_drawscale.py --build 64
python tools/pi4_vulkan_drawscale.py --check-report docs/evidence/vulkan-drawlist-scale-pi4-20261001/report-64.bin --draws 64
```

The generated image lives in `tmp/pi4-drawscale/drawscale-64.bin`; substitute
256 or 1024 for the later variants. The checker requires the full-image FNV32
digest, 16,384 exact pixels, unchanged surface and tail guards, a backend draw
delta equal to the variant, the same closed-list and primitive count, exactly
one bin/render job pair, no fault, and a clean fence result. Expected digests:
64 `48DD39C5`, 256 `A1F60DC5`, 1024 `5CA35DC5`.

The current tracked PureMetal Forge IDE compile places the image at
`0x00700000..0x0080E3F8`, BSS at `0x00810000..0x00EFE4DF`, and stack top at
`0x04F00000`. The diagnostic's untouched panel guard is
`0x06000000..0x063E8000`; the Vulkan window is
`0x063E8000..0x06BE8000`, followed by a 256-byte tail guard. The V3D arena
starts at `0x0A000000`, clear of the `0x08A00000` DSI scanout band. The
1024-draw vertex buffer is 147,456 bytes and its private backend slot arena
is 917,504 bytes (896 per draw). These ranges must be checked against the
board's live `map` before any upload.

Run only the 64-draw image first with the board's deadman armed and a host
deadline below 15 seconds. Admit 256 only after the 64 report passes, then
1024 only after 256 passes. Each payload's fence wait is bounded to two
seconds. A refused command, timeout, fault, mismatched pixel, or changed
guard stops the sequence. The source's 4096-record ceiling and backend
preflight do not constitute a generic 4096-draw hardware admission result;
this diagnostic reaches at most 1024.

All three stages passed on Pi 4 monitor build 223 (CRC32 `5BC668D0`) on
2026-10-01. The 64-, 256-, and 1024-draw runs took 3.0, 3.1, and 3.6 seconds
of monitor execution respectively. Each 256-byte report passes the host
checker: exactly the requested number of real draws, all 16,384 pixels,
one bin/render pair, unchanged guards, and zero native/MMU/OOM/fence faults.
Each stage returned under a confirmed 15-second deadman and left the monitor
at a healthy prompt; no monitor or storage image was replaced. The report
files and payload digests are pinned in
`docs/evidence/vulkan-drawlist-scale-pi4-20261001/manifest.json`.
