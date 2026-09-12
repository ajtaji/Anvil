# Multicore status — Raspberry Pi 4 (BCM2711, Cortex-A72)

Status: **resident secondary-core acceptance passed on Pi 4 silicon in EL3**
with Anvil builds 98 and 99. This is a bounded diagnostic/worker foundation, not yet a
general SMP scheduler.

## Accepted artifact

- Current build 99, 2,815,748 bytes, CRC32 `9EF87F35`
- Image SHA-256
  `2dec5dba7441ddf3b0cdbfc1115f2cbeac05414383f8db22e4a4210e487e8179`
- Symbol SHA-256
  `85c816dd81dba137866052852d710c0a51f413984b6818384c81e794f9b5cd20`
- Compiler SHA-256
  `0c0bac62627184109f3a7f7692919b9523e80e413f50b67b82dfc1867f89d51e`

## Silicon result

On build 98, `coretest run` completed twice. Each run issued 16 fresh nonce-tagged jobs to
each of cores 1, 2 and 3. Every result matched the independently calculated
sum, reported the expected core, returned success and acknowledged the exact
nonce. The second run advanced the nonces and rejected stale completion as
designed. Build 99 repeated one complete 16-round run across all three cores,
received every stop acknowledgement, and was reset to clear the parked workers.

While the secondary cores were resident, cache-policy changes and payload
execution were refused before mutation. `coretest stop` received all three
permanent-park acknowledgements. Ownership intentionally remained held after
stop because the parked cores still referenced monitor code and translation
state. A full reset cleared the leases and restored the cold state.

The console/display/network remained usable, and quick checks passed for screen
DMA/V3D, touch, USB xHCI/storage, Wi-Fi and the network console.

## Contract

- Only core 0 may start or control the workers.
- Entry requires measured EL3, M/C/I enabled, SMPEN set, all DAIF masks and a
  usable architectural counter.
- Cores 1-3 use distinct board-owned 4 KiB stacks at `0x1FC000`, `0x1FD000`
  and `0x1FE000`.
- Requests are published with release ordering and consumed with acquire
  ordering. Results use the same publication contract.
- Every wait has a counter deadline and a finite loop ceiling; failures do not
  pretend a running core was cancelled.
- GIC and watchdog acceptance leases are acquired as a pair before release and
  retained for the lifetime of resident secondaries.
- Stop is permanent park, not reclamation. Monitor replacement, cache/MMU
  changes and arbitrary payload execution stay refused until full reset.

## Desk regression gates

```text
python tools/a64/a64_core_worker_check.py --compiler <PureMetalForge.exe>
python tools/a64/core_accept_check.py --compiler <PureMetalForge.exe>
python tools/multicore_reservation_check.py --compiler <PureMetalForge.exe>
```

The worker gate passes 416 checks, the resident acceptance gate passes 71, and
the reservation gate passes 1,135 checks plus 18 negative mutants.

## Remaining work

This acceptance does not provide task scheduling, arbitrary application
parallelism or safe monitor replacement beneath parked cores. Builds 98 and 99
both passed witnessed physical cold-power cycles. Final build 99 returned at
EL3 with exact CRC and cold/zero leases; timer, USB/storage, DMA/V3D, touch and
Wi-Fi checks passed.
