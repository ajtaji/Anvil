# Isolated typed-IR to V3D 4.2 lowering contract

`vk_ir_v3d42.pbi` is the typed downstream lowerer used by the Pi 4 Vulkan
shader emitter. Its earlier isolated contract remains the basis for exact
publication; public support is bounded by pipeline validation and physical
evidence, not by this document alone.

The lowerer consumes an `AvkIrModule` only after `AnvilVkIrVerify` succeeds.
It supports the existing one-block binary32 operations: input or descriptor
`Load`, one-member `AccessChain`, `CompositeExtract`, `CompositeConstruct`,
combined `ImageSampleImplicitLod`, output `Store`, and final `Return`.
The reviewed arithmetic extension lowers exact float32 scalar and equal-width
vec2/vec3/vec4 `FAdd`, `FSub` and `FMul` nodes owned by the passive IR. It emits one
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
construct/extract fixture. Arithmetic coverage pins both operations at scalar,
vec2, vec3, and vec4 widths with two VPM operands, plus scalar and vec4 cases
whose two operands are exact constants. The independent decoder checks the
raw FADD and FMUL opcodes, muxes, non-magic destinations, ordered LDVPM input
slots, ALU lanes, ordered STVPM output slots, and the final VPM wait. Constant
cases additionally check each LDUNIFRF destination and every uniform word in
stream order. V3D 4.2 embeds pack/unpack choice in these selected arithmetic
opcode forms rather than exposing a separate pack/unpack field; checking the
complete raw opcode/mux/magic tuple pins the admitted no-conversion form.

V3D encodings and scheduling follow the locally pinned Mesa sources cited in
`RaspberryPi4/Lib/v3dqpu.pi4`: `qpu_pack.c`, `qpu_instr.c`,
`qpu_validate.c`, and `nir_to_vir.c`. The independent Python gate decodes every
published 64-bit word with `tools/v3d42_qpu_decode.py`; it does not trust the
emitter's own field packer.


The paired coordinate/vertex path now admits at most sixteen scalar multiply
or add nodes in a position graph. Large input layouts reuse dead input-index
registers above all coordinate output indices. Scratch allocation respects the
current four-way RF0..31 budget and still refuses insufficient register/code
space before publication. The shared VPM record covers the larger of input
and output row requirements. The physical sixteen-node compact proof, a
seventeen-node public refusal, raw code/register checks and all four-rotation
pixels are recorded in `docs/evidence/vertex-shared-vpm-pi4-20261026/README.md`.
Fragment high-register execution modes are not covered by that proof.

The fragment result now publishes `registerCount`, the physical RF high-water
mark including fixed TMU registers. It is cleared on refusal and published
with code/uniform metadata only after the transaction succeeds. Pi 4 pipeline
records select four-way threading through RF31 and two-way threading through
RF63. The emitter still refuses allocations beyond RF63. Short shaders retain
their existing scheduling mode; paired vertex programs retain their separate
RF0..31 allocation contract.

This corrects an unconditional four-way flag that corrupted 350 of 24,511
parent pixels in a longer fragment arithmetic proof. The same returning
candidate with register-derived scheduling passed every parent pixel, the
target/filter/UI checks and the complete scanout comparison on installed
Anvil 388 (capture 37). The installed monitor itself was not changed.
`build_vulkan_fragment_register_proof.py` and
`vulkan_fragment_register_check.py` separately cover 28, 32, 36 and 64
register metadata, and transactional refusal of a 68-register request on
the physical CPU. These boundary programs are not themselves GPU workloads.

Register availability was checked against Mesa's primary
`src/broadcom/compiler/vir_register_allocate.c`, revision
`c4cb1b20e4dca03d0683b03bc99360884daf5235`, in its thread-index selection.
No Mesa runtime code was imported. This result does not complete the original
CRT shader.

Subtraction qualification on Anvil 388 uses two returning proofs. Capture 39
executes the production parser, retained-record adapter, typed verifier and
lowerer on the physical CPU for scalar, vec2, vec3 and vec4 subtraction. Each
result feeds the output colour. The input module is overwritten before record
reads and adaptation, so successful reads prove retained ownership. The host
decoder checks each FSUB opcode, ordered register operands, destination and
uniform value. Self-use, mixed operand types, an out-of-bound result and
instructions after Return refuse; typed operand-count and dominance checks
also refuse. All 142 corrupted records, operands, opcodes and uniforms fail
the independent checker. These are emitted-byte checks, not GPU execution of
every width. The host fixture's initial flat-colour decoder contract and
after-Return expected error were corrected from source evidence without
repeating the board run; original expectations remain in the archive.

Capture 40 executes scalar subtraction in both coordinate expressions and
vec4 subtraction in fragment colour on the GPU. Identity expressions
`(x+x)-x`, `(y+y)-y` and `(colour+colour)-colour` preserve the independent
geometry, retained-parent and linear-filter pixel oracles. All 45 filter,
142 idle-scope, 164 target-pool and 297 scripted UI checks pass, including
24,511 parent pixels and the 4,096,000-byte scanout comparison. This closes
the FSub prerequisite, not the remaining extended instructions, computed
texture coordinates or control flow required by the complete CRT effect.
The shared parser/IR changes apply to all consumers; GPU execution is
qualified on V3D 4.2 only. Installed monitor 388 predates these candidates.

### Computed sampling coordinates — 28 October 2026

The typed SPIR-V path accepts ordered binary32 vec2 coordinate values, including
arithmetic, reconstruction and constants. Legacy direct-input summaries remain
available only for direct loads; computed graphs retain typed dependencies.
Scalar, vec3, undefined and self-dependent coordinates refuse. The V3D texture
configuration is emitted immediately before the sample request, after any UBO
load used to compute its coordinates. Emitting that configuration in the shader
prologue let an earlier memory request consume it; the first GPU draw failed.

Physical Anvil388 capture44 validates uniform offsets +0.5, -0.5 and zero against
six independently expected red/blue texels, plus 25 API checks and the existing
filter/idle/target/UI and scanout oracles. The initial captures41/43 failed safely
and are retained. CPU captures42 and45 separately proves four coordinate forms through
retained records, typed verification and decoded instructions. These are candidate
payloads; installed388 is unchanged. Full CRT and general Vulkan remain incomplete.


### Fragment dot product — 28 October 2026

OpDot retains two ordered, identically typed binary32 vec2/vec3/vec4 operands
and a scalar result of their component type. The typed verifier rejects shape,
result-type and dominance errors. V3D fragment emission multiplies each lane,
then adds products in lane order without fused contraction. The bounded vertex
position planner does not yet support dot products.

Physical CPU capture47 validates all three widths, a negative case, source
retention after caller-memory destruction, invalid modules and typed mutations.
The decoder checks multiplication operands/destinations, exact FADD encoding and
accumulation order. All105 damaged report/instruction/uniform controls reject.
The first candidate refused vec4 because five registers were requested through
a four-component allocator; products and accumulator now allocate separately.

GPU capture49 validates dot((x,0.5),(0.5,0.25)) for x=+0.5/-0.5, and zero input,
producing coordinate shifts +0.375/-0.125/0.0. Fifteen texel probes distinguish
missing terms and wrong scale from the correct result. Existing filter, target,
idle-scope and scripted UI oracles remain passing. CPU capture47 covers emitted
instructions for all widths; numerical GPU coverage here is vec2. Both are
returning candidates on unchanged Anvil388. Full CRT remains incomplete.

Semantics: https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpDot


### Fragment vector scaling — 28 October 2026

OpVectorTimesScalar is retained as a distinct typed operation: its binary32
vec2/vec3/vec4 result matches its vector operand, and the multiplier is the
same scalar component type. The V3D fragment lowerer multiplies each selected
vector register by the one scalar register. Existing componentwise arithmetic
keeps its own lane selection. The bounded vertex-position planner remains
unchanged and does not claim this new operation.

Physical CPU capture50 validates all widths with alternating vector components,
a negative-value case, retained ownership after destroying caller words,
malformed modules and typed operand/dominance mutations. An independent decoder
checks each multiplication's operands, destination, scalar broadcast and uniform
words;131 damaged report/instruction/uniform controls reject.

Physical GPU capture51 composes scaling with dot product and texture sampling:
dot(2*(x,0.5),(0.5,0.25)) produces +0.75/-0.25 for x=+0.5/-0.5;
zero input produces zero. Fifteen expected texels detect omitted scaling and
incorrect lane use. Existing filter, idle, target, UI and full scanout comparisons
pass. CPU/emitted instruction coverage includes all widths; numerical GPU coverage
is vec2. Installed Anvil388 is unchanged. Full CRT remains incomplete.


### Composed CRT curvature — 28 October 2026

The original radial coordinate equation is composed from the shared typed
arithmetic path, including the original 0.015 strength. A zero coefficient and
negative coefficient provide controls; the production Chrome source is unchanged.
The generated fragment uses centered UV, dot(uv,uv), two vector scalings, the
radial addition, and conversion back to texture coordinates before sampling.

Physical Pi4 capture52 returned zero in14.0s on unchanged Anvil388. A64-column
striped texture rendered to256x256 gives18 independently predicted texels at
six positions for +0.015,-0.015,0. The sameX at differentY distinguishes both
squared terms of the radial expression. All25APIchecks and existing filter,
idle,target,UI,parentpixel and fullscanout oracles pass. All71changed API/pixel
records refuse. This proves coordinate curvature, not scanlines, vignette,
outside-bounds black output or the completeCRT effect.

The original vignette uses reversed smoothstep edges(0.8,0.3), which the GLSL
extended-instruction specification leaves undefined/poison. Its intended
center-bright, edge-dark transition will be expressed with ordered edges as
1-smoothstep(0.3,0.8,distance), preserving the cubic interpolation and thresholds.
That path is not yet implemented or qualified.
See https://registry.khronos.org/SPIR-V/specs/unified1/GLSL.std.450.html .


### GLSL Sin candidate: CPU qualification only

The retained path recognizes the exact GLSL.std.450 import and unary Sin
instruction 13. Typed SIN nodes carry one binary32 scalar/vector argument of
the result type. The fragment candidate scales radians by reciprocal pi,
rounds and subtracts periods, evaluates the reduced SIN, then restores odd
period sign. Physical CPU capture 54 on Anvil 388 validates scalar and all
three vector widths, retained ownership, eight invalid shader cases and the
independently decoded instruction sequence. It returned zero in 2.3 seconds;
189 report/register/uniform corruption controls reject.

This does not establish GPU numerical accuracy or a complete CRT shader.
Those qualifications remain pending, along with vertex-position support for
this operation. Forum issue 1513 remains open. The first CPU capture 53
exposed the adapter's old blanket import refusal; the recognized import
identity is now retained and validated across that handoff.


### Sine numerical GPU qualification (28 October 2026)

Physical Pi 4 capture 55 on Anvil 388 returned zero in 14.1 seconds. The typed
fragment path evaluates a mixed vec4 of radians, with independently predicted
RGB output on a mid-gray texture. Eighteen channel samples include zero,
positive/negative extrema, pi boundaries, multiple periods, +/-800 radians,
and nearby extrema. The maximum error against the reference was 0.418 of an
8-bit channel step (allowed one step). This is sampled UNORM output evidence,
not exhaustive binary32 accuracy. All 40 API calls, 45 filter, 142 idle-scope,
164 target, scripted UI, 24511 parent pixels and full scanout comparisons pass.
All 67 damaged GPU report controls reject. The existing rendering is preserved
when the sine input is zero. CPU capture 54 covers all scalar/vector widths.

The original time-dependent scanline expression is not yet composed and the
complete CRT port remains unfinished. Forum 1513 remains open for that work;
installed Anvil 388 is unchanged. Publication still requires architecture-gate
corrections. No vertex-position Sin support is claimed.


### Original scanline composition qualified

Capture 56 on physical Pi 4, Anvil 388, returned zero in 14.1 seconds.
The shader evaluates `sin(uv.y*800-time*10)*.04` and subtracts that scalar
from RGB only. Six normalized image rows at times 0, 0.125 and 12.5 seconds
produce all eighteen expected pixels; alpha remains 255. Maximum channel
error is 0.376 of an 8-bit step. All 25 API calls and baseline filtering,
target, idle, UI and scanout comparisons pass. All 100 damaged report controls
reject. The source image uses its own normalized coordinates rather than an
atlas rectangle. Baseline rendering sets the effect enable to zero.

This closes the missing fragment sine prerequisite (forum 1513). Curvature
and scanlines are qualified separately; the combined CRT pipeline, vignette
and outside-black conditional still require implementation and verification.
Installed monitor unchanged. Source publication remains blocked by the
architecture gate; vertex-position Sin is not claimed.


### Curvature and scanlines composed

Pi 4 capture 57 on Anvil 388 returned zero in 14.2 seconds. The original .015
radial warp feeds both texture coordinates and the vertical coordinate of
`sin(uv.y*800-time*10)*.04`. Alternating gray source columns distinguish warped
sampling from unchanged sampling; six points at three times distinguish the
warped scanline phase. All eighteen pixels match within one UNORM step
(maximum error 0.547), with alpha preserved. All 25 API calls and baseline
filter/target/idle/UI/scanout checks pass; 100 corrupted report controls reject.
The graph fits the existing register/code bounds without bypasses or ID-based
special cases. The production Chrome shader is unchanged. Vignette and
outside-black behavior remain absent; this is not the complete CRT port.


### Fragment Distance qualified on Pi 4

GLSL.std.450 Distance (67) retains two matching binary32 scalar or vector
operands and a scalar component result. Import identity, type, arity and
dominance checks precede lowering. The fragment backend subtracts components,
squares and sums them, then computes reciprocal of reciprocal square root,
with explicit SFU dependency spacing. The vertex planner is unchanged.

CPU capture 58 on Anvil 388 covers scalar through vec4, eight malformed calls,
retained semantics and emitted register/uniform operands. GPU capture 59
returned zero in 14.0 seconds: six vectors include zero distance, signs and
changes confined to the last two components. Eighteen RGB channel observations
match independent Euclidean-distance predictions within one UNORM step;
maximum error is 0.380 step and alpha stays 255. All 40 API results and existing
filter, target, idle, UI, parent-pixel and scanout comparisons pass. There are
149 rejected CPU and 67 rejected GPU report corruption controls.

This is sampled display-output evidence, not exhaustive binary32 accuracy.
Cores, fonts and Vulkan returned healthy, timeouts zero and watchdog off.
Installed Anvil 388 is unchanged. SmoothStep, the complete vignette and
outside-black behavior remain; the overall Neon work is still open. Source
publication remains subject to the architecture gate.


### Fragment SmoothStep qualified on Pi 4

GLSL.std.450 SmoothStep (49) now retains edge0, edge1 and x, verifies matching
binary32 scalar/vector types, and lowers the clamped cubic interpolation per
component. The vertex planner is unchanged. Ordered edges are required for
defined results; the intended Neon fade will use one minus SmoothStep(.3,.8,x).

CPU capture 61 on Anvil 388 covers scalar through vec4, eight malformed calls,
typed arity/dominance refusals and decoded instructions. The first fixture
(capture 60) did not consume results for widths below four; dead-code removal
correctly skipped those operations. The corrected fixture consumes each result.
Its initial host check also assumed sequential constant-register placement and
separate FMin/FMax decode names; the recorded bytes passed after these checking
assumptions were corrected, without changing or rerunning the payload.
All 235 corrupted CPU report/register/uniform controls reject.

GPU capture 62 returned zero in 14.2 seconds. Six mixed input vectors exercise
both endpoints, outside values and interior interpolation. All eighteen RGB
channels agree with independent predictions within one UNORM step (maximum
error 0.440); alpha remains 255. All 40 API results and existing filtering,
target, idle, UI, parent-pixel and full scanout checks pass. All 67 damaged GPU
report controls reject. This is sampled numeric output, not exhaustive binary32
verification. Cores/fonts/Vulkan returned healthy, timeouts zero and watchdog
off. Installed Anvil 388 is unchanged. The complete vignette composition and
outside-black behavior remain; source publication awaits architecture checks.


### Fragment register reuse candidate — rendering regression remains

The full curvature/scanline/vignette graph exhausted the monotonic allocator
at Distance result 76 (Pi capture 63, range error -23405 at allocation stage4).
A general free-register allocator now reclaims dead values and scratch at SSA
operation boundaries, protects future operands and aliases, keeps constants
and deferred output, and reserves fixed resource registers. CPU capture65
passes25 focused alias/lifetime/exhaustion checks;53 damaged controls reject.
The graph passes pipeline creation with the candidate, but capture64 fails
cross-target image checks55/57: expected red/green both read opaque black.
This candidate is NOT qualified; the composed vignette and forum1516 remain
open. No hardware bound increase, source-ID exception or monitor installation.
All runs returned healthy on Anvil388, timeouts0 and watchdog off.


### Fragment reuse and composed vignette qualified

Capture66 traced the black output to Dot writing first+lanes rather than its
allocated accumulator, overwriting cached constant1.0 in RF21. Dot now uses
the returned register. Reclamation also retains cached input maps for later
loads, avoiding another varying FIFO read. CPU69 passes36 lifetime, alias,
input-cache, noncontiguous-accumulator and refusal checks;78 damaged controls
reject. GPU70 returns zero13.2s with all18 composed curvature/scanline/vignette
pixels matching within1UNORMstep (maxerror0.486),25API calls and the existing
filter/target/idle/UI/parent-pixel/scanout checks passing.125 damaged GPU
controls reject. Captured code944bytes,24uniformwords,39registers; Dot uses
RF24 while cachedRF21 survives. The trace check rejects the broken capture66.
No hardware limit change or shader-ID exception. Earlier candidate warnings
above are superseded by this qualification. Installed388 unchanged and healthy;
timeouts0, watchdog off. Outside-black behavior and full engine integration
remain; source publication still awaits architecture checks.


### Boolean GPU emission and outside border qualified — 29 October 2026

The fragment lowerer emits ordered less/greater comparisons, logical OR and
integer-move selection. GPU capture 74 passes 18 RGB checks including signed
zero, both infinities and positive/negative quiet and signaling NaNs. Capture
76 passes 18 more channels at exact 0/1 bounds and adjacent values. Each report
checker rejects 29 damaged controls. This is sampled fragment verification;
vertex logical operations and arbitrary structured control flow remain outside
this qualification.

The composed curvature, scanline, vignette and opaque outside-border shader
passes GPU capture 75: all 12 outside samples are black and six interior samples
match within one UNORM step across three times. All 77 damaged controls reject.
The 1160-byte program uses 24 uniform words and 39 registers. Code slots expand
from 1 KiB to 2 KiB, coordinated with scratch arrays and shader-record offsets
inside the same 8 KiB pipeline allocation; hardware register limits are unchanged.
All three runs return normally with cores, fonts and Vulkan healthy, zero
display timeouts and watchdog off. Installed Anvil 388 remains unchanged.

The original outside-border regression now passes in the generated shader
fixture. Production Chrome and full Neon engine integration remain incomplete;
this does not close the overall application topic. Source publication remains
blocked by architecture findings.
