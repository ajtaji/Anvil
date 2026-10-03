# Pi 4 two-workgroup compact-particle expansion

Anvil build 244 on Raspberry Pi 4 ran `vulkanNeonParticleCsdTwoGroupProof.pi4` as a returning RAM payload at `0x00800000`. The 79,040-byte PMF container (SHA-256 `7729ACA4FBFEB19C235E32EC2E3B5270F06645DBF0946C1E93825453FFA3B969`) was verified on the board. A 15-second deadman was armed before entry. The payload returned `x0=0x00880978`, and the board remained at `pmf>` with the deadman stopped. No boot file was changed.

The 256-byte [report](report.bin) has SHA-256 `3427DFD3FFC06D43DD633B2F6DA96C54EFDF5017C2E9D79D8DE106B650158B47`. Check it from the repository root with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdTwoGroupProofCheck.py docs/evidence/neon-particle-csd-two-group-pi4-20261003/report.bin
```

The checker passed: two 16-lane groups expanded 32 distinct compact records into 192 ordered, six-component Vulkan-format vertices. All 1,152 vertex words matched, and output/input guards and record canaries were intact. The QPU program was 1,216 bytes; CSD completion advanced 0→1 in 210 microseconds with no reported V3D or MMU fault.

The first upload-listener attempt was unconfirmed and sent no image. A subsequent Wi-Fi console query answered, and the same frozen container ran successfully. The host run transcript is under `runs/neon-particle-csd-two-group-r2-pi4-20261003/` in this checkout.

This is a diagnostic compute output buffer. It is not yet a Vulkan vertex resource or a production particle path, and its 32-record timing does not predict a 10,000-particle frame time. No other board was tested.
