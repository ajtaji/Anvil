# V3D 4.2 optimal-texture transfer contract

`vk_v3d_texture.pi4` is an isolated prerequisite, not a public Vulkan feature.
Nothing includes it yet, so the current backend must continue refusing larger
sampled images and `VK_IMAGE_TILING_OPTIMAL` until resource, command, descriptor
and sampler owners adopt the same layout as one transaction.

## Supported conversion

- One 2D image, mip level 0, array layer 0, one sample.
- Opaque four-byte texels copied exactly; no scaling, filtering, swizzle or
  numeric format conversion.
- Raster source with a byte pitch divisible by four.
- V3D `UIF_NO_XOR` destination: 4x4/64-byte utiles, 8x8/256-byte UIF blocks,
  four UIF-block columns per padded row group.
- Width and height from 1 through 4096. Padded width is `align(width, 32)`;
  padded height is `align(height, 8)`; allocation size is
  `padded_width * padded_height * 4`.
- Page-aligned destination and mapped-window base; 64-byte-aligned source.
- Non-overlapping source and destination inside one declared 32-bit GPU virtual
  address window.
- A caller-selected wait from 1 through 1,000,000 microseconds. Completion or
  any low-level V3D error is returned unchanged.

The source read span is exact: `pitch * (height - 1) + width * 4`. Padding after
the final source row is not read or cache-maintained. Destination cache ownership
covers its complete padded allocation.

The plan reports both encodings later integration must carry together:

- TFU output format 6 (`UIF_NO_XOR`);
- texture memory format 4 (`UIF_NO_XOR`).

Using one without the other is not supported. The TFU texture type is 29,
`R32_FLOAT`, but only as Mesa's raw four-byte exact-copy selector. This module
does not claim that the bytes are BGRA8; a later VkFormat/sampler owner must
establish that association.

## Required execution order

After all geometry, capacity, mapped-range, alignment, overlap and timeout checks
pass:

1. `V3dTfuBegin(width, height, raw32_type)`
2. `V3dTfuSourceRaster(source, pitch / 4, exact_read_span)`
3. `V3dTfuDest(destination, UIF_NO_XOR, padded_allocation)`
4. `V3dTfuSubmit()`
5. `V3dTfuWait(timeout_us)`

Every failure stops the chain immediately. `V3dTfuSubmit` owns pre-launch cache
maintenance for both spans, and `V3dTfuWait` owns destination invalidation. This
module deliberately has no CPU or DMA tiling fallback.

## Source provenance

The implementation was derived from the locally pinned Mesa 24.3.4 V3D files:

- `mesa-24.3.4_v3dx_tfu.c`, lines 57-77 and 92-156: exact-copy restrictions,
  cpp-to-TFU-type selection, raster stride, V3D 4.2 ICFG/IOA and UIF OPAD.
- `mesa-24.3.4_v3d_tfu.h`, lines 28-49: V3D 3.3/4.2 TFU field values.
- `mesa-24.3.4_v3d_tiling.h`, lines 29-63: UIF block and tiling definitions.
- `mesa-24.3.4_v3d_tiling.c`, lines 35-61 and 149-210: four-byte utile geometry
  and the UIF_NO_XOR byte-address equation.
- `mesa-24.3.4_v3d_resource.c`, lines 575-698: level-zero UIF padding, stride
  and allocation size.
- `mesa-24.3.4_v3dvx_meta_common.c`, lines 932-1031: an independent Mesa Vulkan
  TFU job builder with the same raster-source and UIF-destination contract.

Mesa is a consulted implementation reference, not a runtime dependency and no
Mesa code is copied into Anvil.

## Desk proof and integration boundary

Run:

```text
py -3 tools/vulkan_v3d_texture_check.py --mutate
```

The emitted fixture uses mocked TFU owners to prove packet arguments, ordering,
bounded failure and no calls after hostile inputs. The Python oracle independently
evaluates the saved Mesa UIF byte-address equation at 1x1, utile and block edges,
an odd extent, and every UIF block of the 4096x4096 maximum. Ten source mutations
must all turn the gate red.

This proof does not advertise optimal images or demonstrate silicon output.
Integration still needs one resource owner for optimal allocation/metadata, an
explicit transfer command and synchronization transition, and texture shader
state using the reported UIF memory format. Those existing files are intentionally
untouched by this tranche.
