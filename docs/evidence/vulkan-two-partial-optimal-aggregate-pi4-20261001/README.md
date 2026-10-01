# Pi 4 aggregate partial optimal-image uploads

On 2026-10-01, four Pi 4 RAM runs exercised two ordered public `vkCmdCopyBufferToImage` calls into one 72×64 BGRA8 optimal image. Each call uploaded a disjoint rectangle 64 texels high, starting at the left or right image edge. The widths were 8, 16, 24 and 32 texels, yielding aggregate budgets of 64, 128, 192 and exactly 256 complete 4×4 UIF utiles. The image's padded allocation is 96×64 texels.

Before either partial upload, a full-image TFU upload produced a nontrivial baseline. A separately calculated UIF memory oracle checked all 4,608 logical baseline texels and fixed offsets across UIF blocks. After both uploads and fence completion, the oracle checked every logical texel again. At the 256-tile limit, 4,096 changed texels matched their distinct source patterns and the 512-texel center gap retained the baseline. A checksum of all 1,536 padded UIF texels remained unchanged; 128 image-allocation guard words and 64 source-buffer guard words passed. Source contents and row padding were checked without a pixel-copy fallback.

| Aggregate utiles | Changed / unchanged logical texels | DMA operations | Full payload time | Report SHA-256 |
| ---: | ---: | ---: | ---: | --- |
| 64 | 1,024 / 3,584 | 0→64 | 1.200129 s | `F80C92825E7CE1740FDF447DF9AA704C6B7DF3CEC51C007FB216FA9EE8195E7F` |
| 128 | 2,048 / 2,560 | 0→128 | 1.211311 s | `306CCFE31243BEE9461F7B57170935D355D8AC8AD6D23F5482356B68AF10D25D` |
| 192 | 3,072 / 1,536 | 0→192 | 1.222280 s | `81B1923E18FEFC779D12A3AE5D3A1EF15C3B2AB28F32DFF399FC3E3738B6C911` |
| 256 | 4,096 / 512 | 0→256 | 1.233617 s | `950994B42ABB357C52613C74EC11869C9AE078D41760BC221E4B97C300128A73` |

The corresponding 1,056-byte traces are `report64.bin`, `report128.bin`, `report192.bin` and `report256.bin`. Each reports one TFU baseline job before the partial copies, no subsequent TFU increment, and two backend jobs for the ordered partial calls (jobs 1→3). All status, MMU, OOM, native-error and fault-text checks passed. The 256-tile monitor run took about 1.4 seconds; the RAM runner used a 15-second deadman and no screenshot. No flash or boot-medium write was performed. These measurements establish the Pi 4 backend path only; other boards have no claim from this evidence.

The public source is `RaspberryPi4/Examples/Diagnostics/vulkanTwoPartialOptimalUploads256Proof.pi4` (SHA-256 `8105E91402BA93DC1A59868308E3E602795778A8DC78514D45576B012C2487A3`). The 64/128/192 compile variants differ only in `#AGG_TILES`; their source hashes are respectively `A5D0216EB274F9496ED04867AFCBFEC007B5FCE4BDCB85694CCCEDCB618813F7`, `C84D2FED78D14D73F344BF571FABF85C244E7FC831A392DF7B0401B8BF520AF6` and `5CF4FD9F52759294117C95AB3F5DD1BDC2EDB78FC63CDFF0F4F11415B6599CB2`. Signed compiler SHA-256 was `997A2C05876B806C468368936E49456DB7506C8854D684B214A21381A5AA8B06`. The PMF SHA-256 values for 64/128/192/256 were, respectively:

| Utiles | PMF SHA-256 |
| ---: | --- |
| 64 | `7CB7DD30FA89773606E2C5ED204485CBE93E761CE38695F9AA88104D46D3416F` |
| 128 | `74FD5AC5A0685E245EBA4D68AE5C6CEC2E3116FED4E32CC49C2C39AA73DAB96C` |
| 192 | `9F2C1A8D4C398B79D1655D0EFB333B7C07E793876873369DFC5B01E1EA9C0058` |
| 256 | `4DB8C10F66DE99B67A0C32A325974965003FC40BE872647AFD620C8046319319` |

`tools/vulkan_two_partial_optimal_aggregate_check.py` (SHA-256 `44ABA1806FAB034BA607D5DF97A8017C132B7D5E9FE50BA1F83A93EF8C7AAC5F`) passes all four public reports and 174 self-test checks, including rejection of nonzero fault text. For the maximum case, run `python tools/vulkan_two_partial_optimal_aggregate_check.py --source RaspberryPi4/Examples/Diagnostics/vulkanTwoPartialOptimalUploads256Proof.pi4 --report docs/evidence/vulkan-two-partial-optimal-aggregate-pi4-20261001/report256.bin`.
