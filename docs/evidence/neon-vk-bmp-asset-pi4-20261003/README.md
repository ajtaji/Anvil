# Pi 4 Neon Vulkan BMP asset proof

Anvil build 244 on Raspberry Pi 4 ran `vulkanNeonPortBmpProof.pi4` as a returning 64×64 offscreen RAM payload. The board verified the 1,359,548-byte PMF container (SHA-256 `8ECD6F18A9E6BD647AB7D37B63D71ECCCE4B04E3D533E6E16ABDA9B0938AF094`) at `0x00800000`, armed a 15-second deadman, and received `x0=0x02756158` after 4.2 seconds. The monitor returned to `pmf>`; no boot image or storage was changed.

The [128-byte report](report.bin) has SHA-256 `FEC826B99F0D97DA560E6C17E63A611205A034F1E3DFBDCC54B619976FC3B311`. Check it from the repository root with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonPortBmpProofCheck.py docs/evidence/neon-vk-bmp-asset-pi4-20261003/report.bin
```

The checker passed a decoded 2×2 uncompressed BMP, green color key, explicit alpha mask, and the expected ordered pixels after sprite drawing over a red box. Half-alpha white produced `0xBFFF8080`, matching the source-alpha factors used for both color and alpha. The frame recorded two Vulkan draws and 12 vertices with no backend faults and clean teardown.

This verifies the Anvil-only BMP asset bridge on the Pi 4 offscreen path. It does not cover PNG, JPEG, compressed or palette BMP, mounted-file loading, the complete Neon application, resident monitor integration, or other boards.
