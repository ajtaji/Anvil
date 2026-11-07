# Existing AArch64 payload entry contract

This records the CPU-specific part of Anvil's current service ABI. The common
service vocabulary and table remain in `Anvil/Hal/abi.pbi`. These details apply
to the existing AArch64 backends; another CPU must supply and verify its own
entry, service-call and recovery convention.

Anvil's AArch64 monitor and ordinary same-context payloads require EL3. Stock
firmware entering a lower level is an open bring-up gap, not another supported
execution mode. In particular, the experimental UNO Q UEFI route has not yet
met the EL3 entry requirement. There is no approved privilege downshift here.

At payload entry:

- `x0` holds the service-table address when the validated container requested
  services, and zero otherwise. `x1` through `x7` are zero. Other volatile
  registers have no initial-value guarantee.
- The compiled payload startup selects the validated payload stack, including
  for a payload built with `--entry-returns`. The AArch64 placement contract
  requires 16-byte alignment and the backend's declared initial stack extent.
- Interrupts are masked at the architectural boundary. The monitor's fault
  handling remains installed. The backend owns exception vectors and interrupt
  state; shared policy does not access DAIF or an exception-level register.
- Image placement, digest verification and BSS initialization happen before
  entry. MMU and cache state must be queried through `SvcMmuState`; a particular
  board's current cache-off handoff is not a portable service ABI guarantee.
- Only the owning core enters the payload. Secondary execution requires the
  board's explicit parallel service and its context checks.

Service calls use Forge's existing AArch64 convention: arguments in `x0` through
`x7`, result in `x0`, and preserved registers/frames as required by that backend.
The service must not use the caller's stack below SP. A returning payload must
preserve its link and the callee-saved context required by its compiled entry.

The backend stages the entry value in private `gGoX0` and saves the monitor stack
in private `gSp`, declared by `Anvil/Kernel/AArch64/payload_state.pbi`. The common
core owns the selected entry address and full-width returned result. Board
compositions select these ARM slots; a new architecture must not inherit them
by including common state.

On payload return, the architecture code restores the trusted monitor stack
before calling the board's recovery hook with interrupts masked. A failed
recovery parks without re-enabling interrupts. Pi 4 still uses its own
`CallAddr` implementation; Pi 3 and UNO Q select the common AArch64
`PayloadCall` implementation. Unifying those implementations remains open.
`SvcReturn` still refuses nonlocal unwinding; return from the payload's own
entry is the supported route back to the monitor.

This documentation and ownership refactor changes no table slot, signature,
container architecture identifier, trampoline source instruction, or ABI
version. It does not establish a Zentaji payload backend or physical boot proof.
