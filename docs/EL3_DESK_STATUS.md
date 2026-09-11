# Pi 4 EL3 desk verification

Status: **desk-tested; not hardware accepted**. No board, boot-medium or
firmware configuration changes were made for these checks. The monitor keeps
production interrupts masked; the new interrupt API does not mean production
device drivers have become interrupt-driven.

## Reproduce

From the repository root, set `COMPILER` to the installed unified compiler
application and run these commands with that path substituted. The application
is invoked headlessly with `--compile` by the gates; no separate compiler is
used. These gates compile small diagnostic fixtures, not a monitor image.

```text
python tools/a64/exceptions_check.py --compiler COMPILER --self-test
python tools/a64/exception_report_check.py --compiler COMPILER
python tools/a64/interrupts_emitted_check.py --compiler COMPILER
python tools/a64/el3_cached_emitted_check.py --compiler COMPILER
python tools/a64/el3_startup_emitted_check.py --compiler COMPILER
python tools/a64/banner_el_emitted_check.py --compiler COMPILER
```

Verified compiler SHA-256:
`890f1ba477f1d68f46a61a668a3daa9eec194b593782d9447cf64aeb193146a3`.

## Evidence

| Gate | Desk result |
|---|---|
| Exception vectors | EL2/EL3 installation, six secondary-core refusals, all 32 vector slots, full IRQ context and nested first-record preservation passed; three emitted-byte negative controls rejected. Independently rerun after final source changes. |
| Fatal report | Exact 64-bit EL/slot/ESR/PC/FAR text, ready/delayed PL011 FIFO, a stuck-byte limit of 4096 polls and a 192-byte text bound passed. Normal console mirrors are explicit stubs; raw byte/text/hex/report routines execute. Independently rerun. |
| GIC | 18 claim/dispatch/reserved-ID/restoration cases, 13 bad-context/identity refusals with zero MMIO writes, and 14 rollback/foreign-ownership cases passed. Independently rerun after final source changes. |
| Cached MMU | 12 cold/warm EL2/EL3 cases and 16 rejected emitted mutations; selected register banks, maintenance ordering, set/way operands and memory-free cache-off flush interval checked. |
| Normal startup | Both EL2/EL3 paths preserve firmware DTB x0, clear poisoned BSS, establish an aligned stack, mask asynchronous exceptions and retain the incoming EL; FP result checked; four mutations rejected. |
| Banner | Actual generated subtitle reports synthetic EL0 through EL3; hardcoded-EL2 mutation rejected for the other three values. |

## Full-monitor return-path acceptance

The final desk candidate (2,701,300 bytes) passed the return-path gate:
30 machine-code routes, six rejected mutations, 11 artifact-admission refusals,
seven memory guards and 292,415 returned-route instructions. Real EL2/EL3
`ExceptionInstall` execution restores deliberately poisoned VBAR and FP trap
state; it is not replaced with a test callback. The immediate post-payload
DAIF-mask instruction is checked, but asynchronous masking is not simulated.

Image SHA-256:
`7b761837facba4e765e8bf71934fbf7a9bea09bc9552b01a2c391cd1cd02f9a2`.
Symbol-sidecar SHA-256:
`c816de70cd800094b12b07bb78289350725e161d63055f3e0f40c2b258809780`.

```text
python tools/payload_return_emitted_check.py --image _work/el3-desk-20260911-c/anvil-el3-desk.img --image-sha256 7b761837facba4e765e8bf71934fbf7a9bea09bc9552b01a2c391cd1cd02f9a2 --symbols-sha256 c816de70cd800094b12b07bb78289350725e161d63055f3e0f40c2b258809780
```

This executes selected procedures from the full image with modeled
hardware/printing/network seams. It does not execute a complete monitor boot.
The separate normal-startup fixture therefore remains a small entry-contract
test, not a claim that the entire candidate has booted or run on silicon.

## Boundaries

- Exception injection and callbacks are modeled, not physical exception or
  interrupt delivery. Current vectors are primary-core only; other cores are
  explicitly refused installation.
- GIC readback, write-one semantics and failure injection are a register model,
  not proof of silicon routing or device service behavior.
- The interpreter does not enforce FP trap permissions or simulate cache/TLB
  effects and barrier ordering across cores. The cached gate supplies a local
  scalar CLZ adapter with six boundary checks because that opcode is absent
  from its interpreter; production code is not replaced.
- Synthetic banner EL0/EL1 inputs do not claim a privileged monitor can run at
  those levels. Normal startup checks stop after a small fixture, not a whole
  boot sequence.
- Same-EL trusted-payload return is not isolation from a malicious payload or
  arbitrary page-table/GIC/system-register corruption. Lower-EL payload/SMC
  service support is not delivered by this work.

## Hardware acceptance still required

Use the separately reviewed recovery procedure and a scheduled board slot.
Prove firmware acceptance of the EL3 stub, early visible boot, actual exception
capture and IRQ return, cache/DMA coherency, secondary-core behavior, display,
networking and returning payloads. Do not deploy the interpreter fixtures:
their witness addresses are not valid hardware page-table configurations.
