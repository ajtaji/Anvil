# Pi 4 optimal-to-optimal edge-tail copy evidence

`report.bin` is the 1,056-byte returning diagnostic trace. SHA-256: `C025612740C1DFF5D00A86A5598FDBA84387C4ACED31E9F7FCF678007E44DF61`.

The 13×13 optimal BGRA8 test copied a 5×5 rectangle at `(8,8)` between distinct images. It changed 25 destination texels and preserved 144; all 169 source texels remained unchanged. The checks covered 338 exact staging words, 78 staging-padding words, 91 padding words in each full readback, and 160 guards. The partial path held TFU at 2, advanced DMA from 0 to 4, and advanced backend jobs from 2 to 3. The two oracle readbacks advanced DMA from 4 to 20 and then 36. A non-edge 5×5 request at `(4,4)` was refused with `-20005` at command-buffer end before further DMA. Status slots were zero; MMU, OOM and native faults were zero; one validation fault was intentional.

The measured PMF SHA-256 was `8594C760D6E3206CFDC5DEAE41DBAAF6C0A770EDDA5FB5A369EBC3AA40ED027F`. The proof covered this bounded Pi 4 DMA shape only. Right-only 5×4 and bottom-only 4×5 cases have desk validation but no separate silicon proof. Other backends do not advertise `TILED_EDGE_TAIL_COPY`.
