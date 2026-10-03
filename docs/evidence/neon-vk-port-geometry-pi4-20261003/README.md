# Pi 4 Neon Vulkan polygon, line, and batch frame

Anvil build 244 on Raspberry Pi 4 ran `vulkanNeonPortGeometryProof.pi4` as a returning offscreen RAM payload. The board verified the 1,366,556-byte PMF container (SHA-256 `E60832C67BEE54D68A3CF64773A432E00CF16D360E6B5154EAD53D94C944A817`) at `0x00800000`, armed a 15-second deadman, and received `x0=0x02229CD0` after 4.3 seconds. Anvil returned to `pmf>` with the deadman stopped. The boot image was not changed.

The [128-byte report](report.bin) has SHA-256 `FF4383698BD68212C70DA6A94155C02CE58CC48C9A2E57D25755B6D91631B78D`. Check it from the repository root with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonPortGeometryProofCheck.py docs/evidence/neon-vk-port-geometry-pi4-20261003/report.bin
```

The checker passed a red filled diamond, a green outline with 32 matching pixels, a yellow static line with 20 matching pixels, and an ordered blue/magenta sprite overlap. The frame recorded five Vulkan draws and 54 vertices, with no reported backend faults and clean teardown. The output was a 64×64 offscreen image, so the physical monitor picture did not change.

The first host attempt stopped at an unanswered `shot status` before upload or boot; `last run` remained 5. The retry verified the same frozen container, ran once, and advanced `last run` to 6. The transcript is in `runs/neon-vk-port-geometry-board-r2-pi4-20261003/` in this checkout.

The load image occupied `[0x00800000, 0x0094D99C)`, BSS `[0x02000000, 0x02B649D0)`, Neon surface `[0x06000000, 0x063E8000)`, Vulkan window `[0x063E8000, 0x06FE8000)`, and arena `[0x0A000000, 0x0B000000)`. These ranges were checked against the resident build-244 monitor and reserved regions before entry.

This proves one small frame using the Anvil-only Neon port adapter on Pi 4 V3D Vulkan. It does not prove the full Neon application, asset loader, UI framework, 10,000-particle throughput, or acceleration on other boards.
