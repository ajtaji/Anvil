# Pi 4 direct buffer fill proof

A public `vkCmdFillBuffer` request filled 16 words in a 256-byte transfer-destination buffer; the other 48 words remained unchanged. The buffer binding used the reported 4,096-byte memory alignment. The guarded allocation used a 4,096-byte prefix bound (1,024 guard words) and a 64-word suffix; all guards passed.

The valid fill added one guarded DMA operation and one backend job. TFU, V3D bin/render and display counters did not change. A separate offset-2 request was refused with `-20001`, produced one intentional validation fault, and added no DMA work. The payload completed without MMU, OOM or native faults.

`report.bin` is 256 bytes; SHA-256 `4E3F001899E7B32390484B1D73DD925E1198B8442ACE8DE00BEA89CD66CA50BD`.
