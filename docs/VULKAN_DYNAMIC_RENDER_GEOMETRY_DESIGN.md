# Vulkan dynamic render geometry — bottom-up design

Status: design only. No image-format maximum is advertised from this document.

## Why this is a prerequisite

The V3D 4.2 layer already derives tile and supertile geometry from a width,
height and render-target format in `V3dRenderBegin()`. The fixed assumption is
one layer higher: `NeonInit()` calls that procedure once, carves tile allocation
and tile-state buffers for that one geometry, and builds coordinate tables of
that one size. `NeonRetarget()` then changes only the target address.

Consequently the Vulkan backend can render only an image whose width, height
and pitch equal the display geometry used by `NeonInit()`. A
`VkImageFormatProperties.maxExtent` cannot express “exactly this one extent”,
so `vkGetPhysicalDeviceImageFormatProperties` must remain withheld until the
engine can rebind geometry safely. Inventing a maximum now would promise legal
images which the submit path refuses.

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

The existing address-only `NeonRetarget()` remains as the cheap same-geometry
operation and can delegate to the new primitive with the current dimensions.

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
capacity and proves refusal before any V3D submission. No public Vulkan maximum
is added until both the desk mutants and these board boundaries pass.
