# Pi 4 transfer-scoped barrier proof

A returning RAM payload on Raspberry Pi 4 monitor build 223 executed public
`vkCmdFillBuffer`, `vkCmdUpdateBuffer`, a transfer-scoped global and buffer
`vkCmdPipelineBarrier`, then `vkCmdCopyBuffer` in one command buffer. Its
388-byte report passed the independent checker: three guarded DMA operations,
three backend jobs, exact source and destination bytes, 256 intact guard
words, unchanged TFU and fault counts, and zero MMU/OOM/native faults.

A separate command buffer recorded a valid fill followed by an out-of-range
buffer barrier. `vkEndCommandBuffer` returned `-20004`; submission was
refused without another DMA operation, backend job, TFU job, or destination
change. The payload measured 697,197 microseconds and returned under a
confirmed 15-second deadman. No monitor image or storage was changed.

Recheck the committed report with:

```text
python tools/vulkan_transfer_barrier_check.py --self-test
python tools/vulkan_transfer_barrier_check.py docs/evidence/vulkan-transfer-barrier-pi4-20261001/report.bin
```

`manifest.json` pins the signed payload and report digests. This evidence is
for the bounded coherent transfer path on Pi 4. Shader and graphics memory
barriers, render-pass global or buffer barriers, and other boards remain
outside this proof.
