# Passive typed shader IR contract

`vk_ir.pbi` is an isolated, target-neutral record schema and verifier. It is
not connected to the SPIR-V parser, pipeline creation, command recording, or
the V3D backend. Passing its verifier therefore makes no public Vulkan or
hardware behavior claim.

The first tranche deliberately represents only the shader shapes already
accepted by `vk_spirv.pbi`: one Vertex or Fragment entry function with a void,
no-parameter function type; one reachable basic block; and `Load`, one-index
`AccessChain`, `CompositeExtract`, `CompositeConstruct`,
`ImageSampleImplicitLod`, `Store`, and final `Return`. Phi, branches,
multi-block control flow, arrays, matrices, separate samplers, and every
unlisted instruction remain unrepresentable and must be refused before an IR
module can be published.

## Preserved semantics

Every type, constant, variable, block, and value-producing node keeps its
original SPIR-V result ID and source opcode. Non-result instructions keep a
zero source ID and their source opcode. Diagnostics always publish a stable
error code plus the offending SPIR-V ID, source opcode, and record index.

The schema retains 32-bit integer signedness, scalar width, vector component
type/count, structure members, pointer storage class/pointee, function return,
the exact accepted 2D sampled-image shape, constant words/components, variable
storage, and decoration target/member/value. The separately retained
decorations are RelaxedPrecision, Block, ColMajor, ArrayStride, MatrixStride,
BuiltIn, Location, DescriptorSet, Binding, and Offset. A retained decoration
is not automatically valid: the verifier enforces its placement, and refuses
ArrayStride/ColMajor/MatrixStride in this tranche because their required array
or matrix types are intentionally absent. Flat, NoPerspective, Component, and
BufferBlock have no IR enum and are refused as unsupported.

## Verifier ownership

The verifier is total over the bounded record arrays. It proves counts and
pointers before traversal; ID bounds and uniqueness across every definition;
all type, constant, variable, decoration, entry, block, operand, and result
references; exact source-opcode-to-IR-kind correspondence; pointer/storage and
operation type rules; structure member bounds; one-block use-before-definition
dominance; one reachable edgeless block; and exactly one final `Return`.

`idBound <= 193` and the record-count constants are the current front-end
implementation limits inherited from the accepted parser slice. They are not
SPIR-V limits and are not architectural limits of this IR.

The independent desk gate constructs valid vertex, sampled-fragment, and
uniform-block shapes, then hostile modules for duplicate/undefined IDs,
forward and self uses, type/storage mismatches, bad decorations, Phi and
multi-block refusal, invalid block ownership, malformed termination, member
bounds, source-opcode mismatch, and the current ID bound. Its mutation mode
recompiles broken verifier variants and requires the emitted cases to fail.

## Provenance

The physical-ID/SSA rules, type and storage-class semantics, decoration
placement, and instruction operands are from the Khronos SPIR-V specification
and registry at <https://registry.khronos.org/SPIR-V/> (sections 2.3, 3.7,
3.20, 3.32, and the instruction reference). The Vulkan shader environment is
described at <https://docs.vulkan.org/spec/latest/appendices/spirvenv.html>.
The source opcode numbers are the same Khronos registry values already pinned
and provenance-recorded in this tree's `vk_spirv.pbi`; this module defines its
own semantic IR enums rather than treating those wire-format numbers as IR.
