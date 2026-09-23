# Vulkan dynamic render geometry — bottom-up design

Status: implemented and proved on the Pi 4 on 2026-09-13. The geometry and
capacity prerequisite is green. The subsequent image-format-properties query
shares the same limit, pitch and usage owner and has its own desk and silicon
acceptance record below.

## Why this is a prerequisite

Before this tranche, the V3D 4.2 layer derived tile and supertile geometry from
a width, height and render-target format in `V3dRenderBegin()`, but Neon carved
tile allocation/state buffers and coordinate tables for only its initial
geometry. `NeonRetarget()` changed only the target address.

That was why the public maximum had to remain withheld until the engine could
rebind geometry safely: a `VkImageFormatProperties.maxExtent` cannot express
“exactly this one extent”. The implemented planner and transactional rebind now
remove that mismatch rather than inventing a capability.

## Ownership

- `RaspberryPi4/Lib/v3d.pi4` owns format-to-tile rules, tile and supertile
  derivation, minimum pool sizes, render-target validation and packet emission.
- `RaspberryPi4/Lib/neon.pi4` owns arena capacity, mapped framebuffer span,
  active surface geometry, coordinate tables and the frame boundary.
- `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` owns translating one validated
  Vulkan image/framebuffer/viewport into an engine rebind and restoring the
  display-owned geometry afterward.
- Portable Vulkan files continue to own image metadata, memory and Vulkan
  lifetime rules. They must not learn V3D tile sizes or Neon arena addresses.

## Required low-level contract

Add a pure V3D geometry planner. Given width, height, output format, render
target count, MSAA and double-buffer state, it returns a closed record with:

- internal type, bpp and clamp;
- tile width/height and tile counts;
- supertile width/height and frame supertile counts;
- minimum tile-allocation and tile-state bytes;
- whether every packet field can encode the result.

`V3dRenderBegin()` should consume that same planner result. There must not be a
second copy of the arithmetic in Neon or the Vulkan backend.

The planner has no MMIO and changes no global. That is what lets capacity be
checked before any live engine state is mutated.

## Capacity before initialization

Neon needs a declared render-capacity geometry before `NeonInit()`. The default
is the initial display surface, preserving every existing caller. A caller may
raise the capacity to a larger width and height before initialization.

`NeonInit()` uses the planner for that capacity to carve the maximum required
tile allocation, tile state, X-coordinate and Y-coordinate storage. It still
activates the initial display geometry. It must not resize or move later arena
objects during a rebind: doing so would invalidate the V3D page table, shader
addresses and every pointer handed to the engine.

The mapped framebuffer span remains an independent capacity. A geometry may fit
the tile pools yet be refused because its target bytes are outside that span.

## Transactional rebind

Add one Neon operation that takes target base, width, height, pitch, byte extent,
output format and orientation. It may run only outside a frame and only after
initialization. In order, it must:

1. reject zero/overflowing dimensions, an undersized pitch or byte extent, an
   address range outside the already mapped framebuffer span, and geometry
   beyond the declared capacity;
2. plan the complete new V3D geometry without changing live state;
3. prove the existing tile allocation/state buffers and coordinate-table
   storage are large enough;
4. snapshot the complete old Neon surface and V3D geometry/target/pool state;
5. install `V3dRenderBegin`, `V3dRenderTarget`, `V3dRenderPool` and the existing
   overflow pool for the new plan;
6. rebuild the active X/Y coordinate tables and viewport centre for the new
   geometry;
7. publish the new Neon surface fields only after every step succeeds.

Any failure restores the complete old state. A caller must be able to begin and
finish a frame at the old geometry immediately after a refused rebind. Partial
publication is a correctness defect, not an error-reporting detail.

The existing address-only `NeonRetarget()` remains the cheap same-geometry
operation and delegates to the new primitive with the current dimensions.

## Vulkan use

The backend saves the full display-owned surface descriptor, not only its base
and byte count. For a clear or draw it rebinds to the Vulkan image geometry,
executes the frame, waits for completion and performs the existing cache
maintenance, then restores the full display descriptor transactionally.

The pipeline viewport and framebuffer extent must equal the active Vulkan
render geometry for this first tranche. Dynamic viewport, sub-rect render areas
and scaling remain unsupported and unadvertised.

Row pitch becomes a rule of the image format and backend alignment, not a copy
of the display pitch. The same rule must be used by image creation, memory
requirements, render-target binding and any later image-format query.

Only after these paths share one limit owner may
`vkGetPhysicalDeviceImageFormatProperties` report maxima. The reported extent,
resource size and sample count must agree with image creation, memory
requirements, pool capacity and submission for every accepted boundary case.

## Desk gates

The desk gate must execute the real planner and packet builders without MMIO.
It needs at least:

- initial geometry, a smaller geometry, a larger in-capacity geometry and a
  geometry with partial right/bottom tiles;
- exact tile, supertile, tile-allocation and tile-state results;
- matching binning/rendering packet fields and render-target stride;
- target range at the first and last mapped byte;
- refusal of zero, field overflow, short pitch/extent, range overflow,
  over-capacity, in-frame and undersized-pool requests;
- a failed rebind followed by a successful frame using the unchanged old state;
- rebind to Vulkan geometry followed by exact restoration of the display
  geometry, orientation, pitch, centre and coordinate tables.

Mutation teeth must independently remove or stale: geometry planning, pool
revalidation, mapped-span validation, the in-frame guard, viewport centre,
coordinate-table rebuild, delayed publication, and full old-state restoration.

## Silicon gate

Use a known-good monitor and one RAM payload. Render guarded offscreen images at
the native geometry, a small non-square geometry, and a partial-tile geometry
such as 257x193. For every geometry require:

- exact job-counter movement and successful fence completion;
- no MMU fault, OOM or control-list error;
- all expected pixels and untouched bytes before/after the target;
- an exact screenshot or copied presentation result where applicable;
- successful restoration and a subsequent normal console frame.

The negative run asks for one dimension or one row beyond each accepted
capacity and proves refusal before any V3D submission. The public Vulkan
maximum was added only after both the desk mutants and these board boundaries
passed.

## Acceptance record — 2026-09-13

`RaspberryPi4/Examples/Diagnostics/vulkanDynamicGeometryProof.pi4`'s silicon-run
artifact was rebuilt byte-for-byte with the final unified IDE/compiler SHA-256
`04D5EE6EF643BE3330D4FC0A0AE8E4B27E6388FAD17643068173C7776B5DD3AF`.
The PMFBOOT container was 382,124 bytes, SHA-256
`275fdb26db7fe3065b4e7f61f4eb303441dec4d1d71e96f414c44c00a6b74767`;
its 381,996-byte image SHA-256 was
`2c72e249478c6f6a773decb7e0851bbc166026ca76e073fff522c02604d18cee`.
It ran as a returning RAM payload under the known build-101 monitor and did not
replace or flash it.

The fixed report at `$05900000` returned status zero in 6.4 seconds.  All three
geometries — 800x1280, 640x360 and partial-tile 257x193 — reported tight pitch
and exact size, one bin and one render job, fence `VK_NOT_READY` before submit
and `VK_SUCCESS` after wait, zero mismatches, and exact first/last word
`$FF3380B2`.  The memory allocator reused the same mapped address only after
each prior image and allocation were destroyed.  The 1281x64 negative was
refused with the implementation's invalid-extent code -20001 while both job
counters remained unchanged.  The restored 800x1280 ordinary Neon frame then
advanced each job counter once, contained `$FF2060A0` in every word, presented,
and shut the V3D MMU down with result zero.

Evidence is under `_work/vulkan-dynamic-20260913/run1/`.  The captured raster is
1280x800 after the monitor's 90-degree presentation and has pixel SHA-256
`bd7076afc74b29dc6c55ac1006dc9935efb02bad4569a2ce07a36811b169f68e`.
The build-101 monitor rewrote the capture header's payload return from the old
`$595F98` to zero and streamed the new uniform `$FF2060A0` frame, but failed to
raise its capture sequence from one.  Therefore `board_run.py` correctly marks
the separate capture-freshness invariant red even though the payload report,
header change and new pixels prove this geometry run.  That monitor defect is
not folded into the Vulkan tranche.

## Image-format query acceptance — 2026-09-13

The same diagnostic was extended to call the public
`vkGetPhysicalDeviceImageFormatProperties` entry point before creating its
images. Its desk gate now checks the exact registry ABI and 179 emitted
properties, and thirteen independent query mutants go RED if the query invents
geometry, pitch, mips, layers, samples, image type, tiling, usage, flags,
transfer-only graphics support, output lifetime, handle lifetime, or diverges
from image creation's combination owner.

The extended payload was rebuilt byte-for-byte by the final unified
IDE/compiler SHA-256
`BF5FDE44797D3F561AA8CC442493FD2A938D01F046F2C02CD1001167C993E01E`.
Its 385,572-byte PMFBOOT container SHA-256 is
`96FC0742033BC1E4352543331078CEF31043980786D1103D8570F979AD08AD44`;
the 385,444-byte image SHA-256 is
`7371A6168C23B649F2F367C6B745CFE957D5BA645FFBA193293745D47F95C572`.

It ran as a returning RAM payload on build 101 without changing flash. The
report returned status zero in 6.6 seconds. The query returned `VK_SUCCESS`,
maximum extent 1280x1280x1, one mip level, one array layer, sample count one,
and 6,553,600 maximum bytes — exactly 1280 rows of the backend's 5,120-byte
pitch. The subsequent native, smaller, partial-tile, refusal, fence, cache and
restoration checks all remained green. The monitor capture sequence advanced
from one to two and the raster retained pixel SHA-256
`bd7076afc74b29dc6c55ac1006dc9935efb02bad4569a2ce07a36811b169f68e`.
Evidence is under `_work/vulkan-image-format-20260913/run1/`.

The focused desk gate executes 84 properties over 108,668 emitted A64
instructions without one MMIO access, compiles all three board diagnostics,
and rejects all sixteen independently injected errors.  The silicon record
above supplies the one rule that cannot be reached with the engine down.
