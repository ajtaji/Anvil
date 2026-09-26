# Bounded Vulkan indexed drawing

On 2026-09-17 Anvil gained a deliberately bounded public
`vkCmdBindIndexBuffer` / `vkCmdDrawIndexed` path for the existing Pi 4 V3D
graphics backend. This is an implementation note and desk-proof record, not a
claim of Vulkan conformance or of a completed board run.

## Accepted slice

- The index buffer is a live, same-device, bound `VkBuffer` created with
  `VK_BUFFER_USAGE_INDEX_BUFFER_BIT`.
- `VK_INDEX_TYPE_UINT16` and `VK_INDEX_TYPE_UINT32` are accepted. The bind
  offset and selected index range must be aligned to the selected element
  width and remain inside the buffer.
- The active pipeline remains the existing one-instance
  `VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST` slice. `instanceCount` must be one,
  `firstInstance` and `vertexOffset` must be zero, and a zero `indexCount` is a
  no-op.
- Each nonempty call records an immutable generation-tagged snapshot. Submit
  re-resolves the index buffer and memory, scans the selected coherent index
  elements, and derives the maximum referenced vertex. Every vertex binding is
  then bounded through that maximum rather than through `indexCount`.

The scan is intentionally repeated at submit. A stale handle, destroyed or
rebound resource, changed generation, out-of-range selected span, or index
that would overrun any vertex binding is rejected before the backend submit
counter, job counters, command-buffer state, or in-flight ledger moves. A
successful submission retains the index buffer and its memory until completion
and makes destroy/free refuse during that interval.

## V3D 4.2 closure

The lowering is pinned to Mesa's `v3d_packet.xml` packet definitions. The
locally audited XML has SHA-256
`D757D2C81F7C7AA7B7A6F848E275827AFFCB5CC7935C4D96DC0995BED6F4F695`:

- `INDEX_BUFFER_SETUP` is opcode 44 followed by a 32-bit base address and a
  32-bit byte size.
- `INDEXED_PRIM_LIST` is opcode 32. The hardware index-type field is bits 6..7
  of byte one: value 1 for 16-bit indices and value 2 for 32-bit indices. Its
  final word is a byte offset into the installed index buffer.

The backend installs the bound base and the complete remaining bound byte span
once. It places `firstIndex * indexElementBytes` in the indexed packet once;
`firstIndex` is not also folded into the setup base. The selected exact index
range is included in the physical cache-clean union before submission. The
emitted-packet fixture independently checks the complete 19-byte setup-plus-draw
sequence for both element widths, plus the no-write refusals for an unsupported
type and a wrapped setup range.

This interpretation also matches Mesa's audited `v3dvx_cmd_buffer.c`, SHA-256
`4D3E5A0BB2F67D4650C0381FC93FB08B1D9E5A8B49AA884C3C132D4B8868D4A2`.

## Desk gates

Run from the repository root:

```text
py -3 tools/vulkan_indexed_draw_check.py --mutate
py -3 tools/vulkan_draw_pool_check.py
py -3 tools/vulkan_v3d_backend_list_check.py
py -3 tools/vulkan_dispatch_check.py --registry C:\path\to\v1.4.350\registry\vk.xml
py -3 tools/vulkan_v3d_backend_check.py
```

The focused indexed checker covers 32 public-path cells, 12 packet-encoder
results, and 46 exact packet/refusal bytes. Its six hostile mutations must all
be caught: disabled maximum-index scanning, missing index lifetime retention,
record-time range acceptance, wrong packet type bits, inclusive-end setup size,
and word rather than byte packet offsets.

`RaspberryPi4/Examples/Diagnostics/vulkanIndexedTriangleProof.pi4` is the board
diagnostic. It binds a UINT16 buffer at byte offset four, selects indices
`2, 0, 1` with `firstIndex = 1`, and requires the exact adjacent
`INDEX_BUFFER_SETUP` and `INDEXED_PRIM_LIST` packets in the captured binning
control list before accepting the same two-pass pixel oracle as the established
triangle proof.

## Pi 4 silicon acceptance, 2026-09-26

The current `main` source at `c66e4b9` compiled with the tracked PureMetal
Forge executable from compiler commit `8480695c`. Build 210 of the Raspberry
Pi 4 monitor reported staging at `$00600000`, so the diagnostic was built at
that address. The returning PMFBOOT v2 container was 875,544 bytes, SHA-256
`9BBC183F6D9D18858CDC43E1552845E85CCEEBBD33E6670A8A9DE03A1C1DF291`.

The RAM-only run over Wi-Fi `192.168.1.111` used the DMA console tier, a
confirmed 15-second deadman, and a fresh capture. The board verified the
container digest before entry, returned expected `x0=$00AD44C0`, and reached
the real `pmf>` prompt. The complete 256-byte report has both magic words,
both pass verdicts zero, all three red and green inside pixels correct, all
six outside pixels at the clear colour, and unchanged guard sums. Bin and
render jobs each advanced from zero to two; submit/wait, MMU, native backend
and Vulkan validation fault slots were zero. The present verdict was one and
the diagnostic reached step ten. A zero second-pass verdict also means its
exact adjacent index setup/draw packet and odd-viewport packet oracles passed.

Capture sequence advanced from zero to one. The fresh 1280 x 800 PNG shows
the green triangle on the blue-grey ground, with pixel SHA-256
`D79CBB44CEAB1A2E2632B5BD5F60BED114F638D2B1E776178C3F8BF5329FA8AB`.
Afterward, `last run` confirmed return, `deadman off` confirmed disarm, and
`coretest status` showed secondary, GIC and watchdog leases all zero. No
flash, reset or boot-medium write occurred. The manifest, report bytes and
picture are in `docs/evidence/vulkan-indexed-20260926/`; the full local run is
`runs/vulkan-indexed-20260926-r1/`.

This proves the bounded UINT16 indexed case on Pi 4 silicon. UINT32 and wider
indexed workloads retain their desk evidence and need separate silicon proof.
