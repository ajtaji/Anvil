# Pi 4 Neon Vulkan TrueType font-handle proof

Anvil build 244 on Raspberry Pi 4 ran `vulkanNeonFontPortProof.pi4` as a returning offscreen RAM payload. The board verified the 2,124,020-byte PMF container (SHA-256 `232739368D4C42ACE8171D3E90404E79E318C74B9D06B768DB15E60E0E689177`) at `0x00800000`, armed a 15-second deadman, and received `x0=0x025EDD20` after 9.4 seconds. The monitor returned to `pmf>`. The boot image and storage were not changed.

The [128-byte report](report.bin) has SHA-256 `6A9EBF092401C2FEF07C6E7E16C2D7B1B55F8303905B0C0D04ABEC2F5D1FE74E`. Check it from the repository root with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonFontPortProofCheck.py docs/evidence/neon-vk-font-port-pi4-20261003/report.bin
```

The checker passed embedded TrueType boot slot 4, generation 1, measured `Wi` width 24 and line height 18, 193 reference ink pixels, and exact translated pixels for right-aligned and centered draws. The frame recorded three GPU draws and 36 vertices. Two full atlas uploads succeeded through TFU with DMA uninitialized; backend faults, DMA error, pixel mismatches, and teardown residues were zero. This verifies the Anvil-only font-handle bridge on the Pi 4 offscreen path.

An earlier payload returned status 26 during TrueType warm-up: the backend had advertised DMA tile-transfer capabilities because the driver was linked, though `DmaInit()` had not run. The capability gate now requires DMA readiness and no quarantine, allowing this payload to use the full-atlas TFU path. This proof does not cover arbitrary desktop font names, font files, the complete Neon application, other boards, or resident monitor integration.
