# A64 local structure helper-write reduced control

`compiler_local_struct_helper_control.pi4` isolates the storage shape that failed
inside `AnvilVkIrV3d42Lower`: a procedure-local structure is cleared and filled
through helper procedures, inspected by another helper, and then published.

This small extraction is a passing control, not a reproducer. The current A64
compiler emitted it successfully, and the interpreter returned the exact eight
words `{$4C535452, 112, 5, 2, 3, 4, 5, 8}` after 384 instructions. Therefore the
failure depends on additional context in the full lowerer; the repository does
not claim a compiler root cause that this reduction cannot prove.

The full V3D42 gate gave an exact differential result. With a local pending
record, all valid lowerings returned success but published `codeBytes = 0` and
zero metadata; intended refusals still behaved correctly. Moving only that
unpublished record into the lowerer's existing private module scratch made the
same 61-case image pass, with 661 independently decoded QPU words and
22,372,297 interpreted A64 instructions.

This control is a compiler diagnostic, not an Anvil workaround contract. It makes
no claim about the compiler's internal cause or about non-A64 targets. Its
expected eight report words are documented in the source so the compiler team
can compile and inspect it independently. Anvil's lowerer was already
serialized by module-level instruction, uniform, liveness, and SSA scratch, so
the unpublished result now deliberately lives in that same private domain and
is copied to the caller only after the transaction succeeds.
