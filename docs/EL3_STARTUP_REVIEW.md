# Pi 4 EL3 startup and payload review

Desk review, 2026-09-11. No board access or monitor image build.

## Contract

The custom `RaspberryPi4/Board/armstub8.asm` enters the monitor and released
secondary cores at EL3. The stock firmware stub remains an EL2 entry route.
Returning native payloads run at the monitor's current exception level:
`cache.pi4` uses BLR, not an exception return. This is not a lower-EL isolation
boundary, and no SMC service ABI is promised by this milestone.

## Reviewed paths

| Path | Finding |
| --- | --- |
| Custom stub | Clears CPTR_EL3 traps, initializes SCR_EL3 and SCTLR_EL3, executes ISB, explicitly masks DAIF, and branches without ERET. Firmware DTB and entry fields remain 32-bit loads. |
| Primary startup | Main captures x0 before its own scratch use and relocates SP. The source comments still describe the stock EL2 route, but the capture sequence is level-independent. Compiler preamble assumptions require emitted-image acceptance, not comments alone. |
| Cache-state ABI | HwMmuState reads MmuSctlr(), selecting the live level rather than assuming SCTLR_EL2. |
| Returning payload | CallAddr preserves the native same-level call contract. After BLR it saves the payload return value, restores the monitor stack and calls ExceptionInstall to reclaim VBAR and the FP/SIMD gate before returning to recovery code. Cache/DMA recovery still needs silicon proof; this is trusted same-level payload recovery, not arbitrary architectural-state repair. |
| Linux boot | HwBootToEl1 deliberately refuses EL3 before EthDown and CacheDisable. This is correct: its actual transition writes ELR_EL2/SPSR_EL2. Removing the guard would not implement EL3 boot. |
| Secondary startup | core_worker and mmu_secondary explicitly require the pinned EL3 stub contract. Their EL3 register names are intentional, not a missed generic bank selection. They reject incompatible entry rather than pretending to support stock EL2 worker startup. |
| Display identity | The banner now renders the actual exception level rather than hardcoding EL2. The banner emitted gate covers the corrected identity; monitor display behavior still needs silicon verification. |

## Acceptance boundaries

Existing `tools/a64/a64_el3_check.py` covers the assembled stub layout,
firmware offsets, primary entry and secondary releases. Existing
`tools/a64/el3_runtime_emitted_check.py` covers live-bank selection;
`tools/a64/a64_core_worker_check.py` covers the secondary ownership contract.
This review did not rerun those gates or turn their earlier results into new
hardware evidence. The supervisor records this session's gate runs separately.

Fault/vector and cached-MMU integration are separate desk-test lanes. A
complete boot-image acceptance must also inspect the generated compiler
preamble and prove that initialization preceding Main preserves x0, enables
FP/SIMD under the stub's EL3 configuration and does not change exception level.

## Exception support added during desk continuation

`Anvil/Kernel/exceptions.pbi` supplies primary-core-only EL2/EL3 vectors.
Installation opens only the selected level's FP/SIMD trap gate, publishes
metadata, then installs VBAR with barriers; it never unmasks an interrupt.
The 16 slots capture general registers, syndrome, handler-entry SP and FP/SIMD
state on an aligned frame. A 16 KiB private stack hosts callbacks. Only the
current-EL SPx IRQ slot can return, and only when its no-argument callback
returns exactly 1. Everything else reports and parks, with no instruction skip.

The vector bootstrap reserves TPIDR at its own level. After the minimum x10
save, the busy guard is set before bulk capture. Nested exceptions thereafter
park without changing the first frame, including an injected fault midway
through capture. A fault on the guard/bootstrap memory itself cannot promise
a complete record. Those memory mappings are installation prerequisites.
Callbacks must not change exception level, translation, stack ownership or
DAIF masks. Returning through an arbitrarily corrupted architectural state
is not supported. IRQ return restores x0-x30, q0-q31, FPCR, FPSR, SP, ELR and
SPSR; TPIDR remains reserved vector scratch rather than application TLS.

`tools/a64/exceptions_check.py --compiler COMPILER --self-test` passed:
both bank installs, reinstall after foreign VBAR/TFP changes, preservation of
unrelated CPTR bits and the other bank, six secondary refusals, all 32 slots,
both full IRQ restores, declined IRQ refusal, nested first-record preservation
and three emitted-byte negative controls (SIMD restore, ERET, nested guard).
The callback clobber and nested-exception injection are explicit host fixtures;
vector capture, dispatch and restore execute the real emitted image. These
tests do not prove physical interrupt delivery, translation or cache coherency.

`tools/a64/exception_report_check.py --compiler COMPILER` also passed. It
compiles the actual raw reporter source with explicitly stubbed normal-console
mirrors, verifies the exact EL/slot/ESR/PC/FAR text including full 64-bit values,
exercises ready and delayed PL011 FIFO states, proves a stuck byte returns
after 4096 status reads without writing the FIFO, and checks the 192-byte
unterminated-text bound. This is MMIO modeling, not a physical UART test.

## Direct architectural cross-check

The following primary Arm documents were opened and checked after implementation;
they are verification references, not a claim that the initial code was transcribed
from them. No reference text or code was copied into the implementation.

- [Arm AArch64 Exception Model, 102412_0103_02](https://documentation-service.arm.com/static/67ac57fb091bfc3e0a9479cc), pages 31-35: vector entries are spaced by 0x80; current-EL SPx IRQ is offset 0x280 (slot 5). ERET restores processor state from the current level's SPSR and the PC from its ELR. This matches the sole resumable slot and selected-bank return.
- [Cortex-A72 TRM, 100095_0003_06](https://documentation-service.arm.com/static/60368ce38f952d2e4134dc2e), sections 4.3.35 and 4.3.40, pages 4-137/4-145: CPTR_EL2 and CPTR_EL3 place TFP at bit 10. Clearing that bit, rather than overwriting the entire register, preserves unrelated controls. The register summary also lists both 64-bit TPIDR banks.
- [Arm Architecture Registers, DDI 0595 ID092421](https://documentation-service.arm.com/static/6166bf63e4f35d248467c9c0), PDF pages 310-317, 1973-1976 and 2019-2022: CPTR TFP controls cover SIMD/FP registers including FPCR/FPSR. VBAR_EL2/3 bits 10:0 are reserved zero, consistent with 2048-byte alignment. TPIDR_EL2/3 are software-managed storage; the PE does not interpret their contents, and the selected-level accesses used here are permitted. Reserving them for vector scratch is therefore an explicit Anvil software ownership contract, not an architectural requirement to use them this way.

No new source defect was identified by these checks. Generic architecture
features absent from Cortex-A72, such as SVE or VHE register formats, were not
treated as Pi 4 implementation requirements. Browser-extracted PDF text was used;
the optional Defuddle CLI was unavailable and is not a PDF extractor.

## Remaining hardware and later-phase work

- EL3 to non-secure EL1/EL2 Linux handoff and a lower-EL/SMC payload ABI.
- Hardware validation of firmware acceptance, caches, interrupt delivery,
  DMA coherency, returning payload recovery and secondary execution.
- Any firmware configuration change or boot-medium write while the board is
  assigned to another task.

For a future board slot, use the separately prepared boot/recovery checklist;
do not infer permission to flash from completion of these desk checks.
