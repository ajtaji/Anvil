# Resident Pi 4 secondary-core acceptance

Status: **passed on Pi 4 silicon in Anvil builds 98 and 99**. This command is a bounded
acceptance instrument, not a general SMP scheduler.

## Commands

| Command | Action |
|---|---|
| `coretest` or `coretest status` | Report ownership, run count, nonces and per-core state |
| `coretest run` | Start cores 1-3 if needed and run 16 verified rounds on each |
| `coretest stop` | Publish stop requests and wait for permanent-park acknowledgement |

Extra arguments and unknown subcommands are refused. There is no automatic
start and no payload form.

## Execution and ownership contract

Start requires core 0, measured EL3, M/C/I together, SMPEN, masked DAIF and a
plausible architectural-counter frequency. It acquires the GIC and watchdog
acceptance leases as an all-or-nothing pair before preparing any core. Once a
secondary is released, those leases remain owned after success, failure or
stop, because secondary code and translation state stay resident until reset.

Each secondary uses its own board-reserved 4 KiB stack. The cold entry verifies
EL3, SMPEN and cold M/C/I before touching DRAM, joins the primary translation
regime, and invalidates only its private L1. Firmware spin slots are written
once and never reclaimed.

Every run submits 16 rounds to all three cores. Each request carries a fresh
64-bit nonce and inputs; each result reports its nonce, core and status. Release
and acquire ordering publishes requests and results without per-job cache
maintenance, so the silicon run exercises coherent sharing. Independent
primary arithmetic verifies every result. Waits have both a two-second counter
deadline and a one-million-iteration ceiling.

Stop waits for all prior acknowledgements, publishes zero-work requests and
requires all three park acknowledgements. It does not make monitor replacement
safe. Cache/MMU policy changes and arbitrary payload execution remain refused
from start until full reset.

## Silicon evidence

- Build 98 passed two complete runs: 16 nonce rounds on each of cores 1, 2 and 3.
- Build 99 passed one complete 16-round run on all three cores and every stop
  acknowledgement, then was reset to clear the parked workers.
- Exact sums, core identities, status and fresh acknowledgements matched.
- Cache-mode change and payload execution were refused while ownership was
  active.
- All three stop acknowledgements passed and permanent ownership was retained.
- Reset cleared the leases and returned the command to its cold state.
- Screen DMA/V3D, touch, USB xHCI/storage, Wi-Fi and network console remained
  operational in quick non-regression checks.

Current accepted image: build 99, 2,815,748 bytes, CRC32 `9EF87F35`, SHA-256
`2dec5dba7441ddf3b0cdbfc1115f2cbeac05414383f8db22e4a4210e487e8179`.
Symbols SHA-256:
`85c816dd81dba137866052852d710c0a51f413984b6818384c81e794f9b5cd20`.

## Desk gates

```text
python tools/a64/a64_core_worker_check.py --compiler <PureMetalForge.exe>
python tools/a64/core_accept_check.py --compiler <PureMetalForge.exe>
python tools/multicore_reservation_check.py --compiler <PureMetalForge.exe>
```

Current results are 416 worker checks, 71 resident-acceptance checks, and 1,135
reservation checks plus 18 negative mutants using compiler SHA-256
`0c0bac62627184109f3a7f7692919b9523e80e413f50b67b82dfc1867f89d51e`.

## Remaining boundary

General scheduling, arbitrary application parallelism and monitor reclamation
are not claimed. Builds 98 and 99 both passed witnessed physical cold-power
cycles. Final build 99 returned at EL3 with exact CRC and cold/zero leases;
timer, USB/storage, DMA/V3D, touch and Wi-Fi checks passed.
