# Isolated typed-IR to V3D 4.2 lowering contract

`vk_ir_v3d42.pi4` is a desk-proven downstream unit. It is not included by the
SPIR-V parser, Vulkan pipeline, current shader emitter, or backend, and it adds
no advertised shader support.

The lowerer consumes an `AvkIrModule` only after `AnvilVkIrVerify` succeeds.
It supports the existing one-block binary32 operations: input or descriptor
`Load`, one-member `AccessChain`, `CompositeExtract`, `CompositeConstruct`,
combined `ImageSampleImplicitLod`, output `Store`, and final `Return`.
The reviewed arithmetic extension lowers exact float32 scalar and equal-width
vec2/vec3/vec4 `FAdd` and `FMul` nodes now owned by the passive IR. It emits one
QPU operation per lane, retains the IR result/type identity, and still refuses
RelaxedPrecision, NoContraction, FPFastMathMode, non-binary32 values, and all
unrepresented arithmetic. It never invents sidecar opcodes or a parallel
request language.

Binding policy is explicit target input. IO records map a unique source
variable/member to bounded, non-overlapping VPM or varying slots with exact
component agreement. Push words, uniform-buffer bus address, texture-state
and sampler-state bus pointers, and the TLB configuration are supplied by the
target. The generated instruction schedule determines their uniform-stream
word positions and returns those positions as metadata. Extra IO maps and
unused push/descriptor resource values are refused rather than discarded.

Caller code and uniform spans must be aligned, large enough for the exact
result, overflow-safe, and disjoint. Resource bus pointers must fit 32 bits
and meet their alignment contract. The encoder always targets private scratch
buffers first. A refusal—including an encoder refusal—therefore leaves both
caller spans untouched; publication occurs only after a complete program has
passed the V3D encoder's hazard checks.

The vertex role is a generic single-segment VPM consumer/producer and is not a
complete coordinate/viewport pipeline. The fragment role implements the
current varying, push-constant, uniform-buffer general-TMU, and combined-image
sample schedules and one RGBA output through TLBU/TLB. Pipeline integration
must separately own shaded-vertex layout, uniform allocation, state-record
flags, cache maintenance, and GPU submission.

Scalar constants used by a represented composite can be materialized from the
uniform stream. The focused proof does not claim a separate constant-colour
fragment family; its independently decoded families are vertex VPM, fragment
varying, push constant, uniform buffer, sampled image, and the vertex
construct/extract fixture, plus both arithmetic operations at scalar, vec2,
vec3, and vec4 widths.

V3D encodings and scheduling follow the locally pinned Mesa sources cited in
`RaspberryPi4/Lib/v3dqpu.pi4`: `qpu_pack.c`, `qpu_instr.c`,
`qpu_validate.c`, and `nir_to_vir.c`. The independent Python gate decodes every
published 64-bit word with `tools/v3d42_qpu_decode.py`; it does not trust the
emitter's own field packer.
