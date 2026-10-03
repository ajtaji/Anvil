# Pi 4 CSD output in a live Vulkan vertex buffer

Anvil build 244 on Raspberry Pi 4 ran `vulkanNeonParticleCsdVkBufferProof.pi4` as a returning 64×64 offscreen RAM payload. The board verified the 1,336,468-byte PMF container (SHA-256 `48334F85C91F2F197268C5830F53BCB309C7F58975BDACDD457CEE277E947FF9`) at `0x00800000`, armed a 15-second deadman, and received `x0=0x00B79CC0` after 4.2 seconds. The monitor returned to `pmf>`; no boot image or storage was changed.

The [256-byte report](report.bin) has SHA-256 `8ABB266834588A1C8BF6A7880FF077FA1A166E302C323FD9E16D28F4BD73B2D1`. Check it from the repository root with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdVkBufferProofCheck.py docs/evidence/neon-particle-csd-vkbuffer-pi4-20261003/report.bin
```

Two 16-lane CSD workgroups expanded 32 compact records into 192 ordered vertices directly in a live, bound 8192-byte `VkBuffer` at `0x067F2000`. The checker passed all 1,152 vertex words, output guards, input records and canaries, then checked 64 rendered pixel probes after one non-indexed Vulkan draw. It recorded CSD completion in 219 microseconds and Vulkan submit/wait in 84,014 microseconds, with no reported MMU/backend faults and clean teardown. There was no CPU vertex copy between compute and draw.

This establishes the small shared-allocation handoff on Pi 4. It does not establish 10,000-particle throughput, rotated or camera-transformed records, production particle API integration, or GPU acceleration on other boards. A failed CSD wait or GPU idle check in this diagnostic stays in the payload for the armed deadman reset rather than returning to the monitor while work may be in flight.
