# Bounded combined-image-sampler state

The first combined-image-sampler object path is implemented as Vulkan state,
not as a sampled-pixel claim. It deliberately stops at the closed record the
future shader backend will consume.

## Accepted shape

- one `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER` at binding zero;
- fragment stage only, descriptor count one, no immutable sampler;
- a pool whose single advertised type is also combined image sampler;
- a live sampler using the existing nearest/linear, clamp-to-edge, LOD-zero
  subset;
- a full 2D view of one live, bound, linear
  `VK_FORMAT_B8G8R8A8_UNORM` image created with
  `VK_IMAGE_USAGE_SAMPLED_BIT`;
- `VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL` in the descriptor and on the
  image when the record is consumed.

The resolved record contains image base, byte extent, width, height, row
pitch, format, current layout and the two filters. Resolution repeats the
handle, owner, binding, usage and layout checks. Destroying the view or
sampler, invalidating the image, or transitioning it away from the promised
layout closes the record instead of exposing an old address.

## Refused rather than guessed

Mixed descriptor layouts, descriptor arrays, separate sampled-image and
sampler descriptors, storage images, immutable samplers, non-fragment use,
pool/type mismatch, wrong write arm, stale/cross-device objects, missing
sampled usage and any other image layout are all refused at the owner of that
state.

## Proof boundary

The emitted pipeline gate exercises both accepted and hostile paths through
the public entry points, submits the required image-layout transition, and
compares every field of the resolved record. Its focused mutation batch must
turn red when any of twelve independent validation or record rules is broken.
The resource, foundation and SPIR-V gates remain separate controls.

This tranche does **not** accept sampled-image SPIR-V types or instructions,
does not emit a V3D texture request, and does not prove a sampled pixel. Those
parts must land and be proved together in the next texture-lowering tranche.
