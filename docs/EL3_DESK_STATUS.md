# Pi 4 EL3 verification status

Status: **desk gates pass; builds 98 and 99 are cold-boot accepted**. Build 99
is the final accepted artifact.

## Reproducible desk gates

Use the installed unified IDE/compiler; no separate compiler is part of this
workflow.

```text
python tools/a64/exceptions_check.py --compiler COMPILER --self-test
python tools/a64/exception_report_check.py --compiler COMPILER
python tools/a64/interrupts_emitted_check.py --compiler COMPILER
python tools/a64/el3_cached_emitted_check.py --compiler COMPILER
python tools/a64/el3_startup_emitted_check.py --compiler COMPILER
python tools/a64/banner_el_emitted_check.py --compiler COMPILER
python tools/a64/a64_el3_check.py --compiler COMPILER
python tools/el3_acceptance_check.py --compiler COMPILER
python tools/a64/core_accept_check.py --compiler COMPILER
python tools/a64/a64_core_worker_check.py --compiler COMPILER
python tools/multicore_reservation_check.py --compiler COMPILER
```

Verified compiler SHA-256:
`0c0bac62627184109f3a7f7692919b9523e80e413f50b67b82dfc1867f89d51e`.

These gates cover EL3 entry and retained state, exception vectors and fatal
reporting, GIC ownership/restoration, cached MMU transitions, startup register
contracts, the displayed exception level, secure-timer and BRK acceptance, raw
secondary entry, resident multicore jobs and board-memory reservations. They
also contain negative mutations for the boot-layer IRQ-route defect.

## Accepted full monitor

| Item | Value |
|---|---|
| Build | 99 |
| Bytes | 2,815,748 |
| CRC32 | `9EF87F35` |
| Image SHA-256 | `2dec5dba7441ddf3b0cdbfc1115f2cbeac05414383f8db22e4a4210e487e8179` |
| Symbols SHA-256 | `85c816dd81dba137866052852d710c0a51f413984b6818384c81e794f9b5cd20` |
| Stub | 512 bytes, SHA-256 `9f96324d137ebb4c1452ab00477ffe8c5bf77c53a3bb80ae7fb34234d693f2a2` |

Build 98 proved the secure timer and controlled fault path three times across
warm resets, two 16-round multicore runs on cores 1-3, ownership refusals,
permanent stop and lease clearing. It then passed a witnessed physical power
cycle: prompt, EL3, CRC `B8FA3959`, `el3test`, USB/storage and DMA/V3D display.

The final cleanup build 99 passed `el3test`, one 16-round run on cores 1-3,
all stop acknowledgements, USB/storage and DMA/V3D after deployment. A reset
then cleared the parked workers. Its subsequent witnessed physical power cycle
returned the prompt at EL3 with CRC `9EF87F35` and cold/zero leases; `el3test`,
USB xHCI hub/storage, DMA/V3D DSI display, touch identity, Wi-Fi DHCP and the
network console all passed.

The discovered silicon failure was `SCR_EL3 = 0x5B1`: INTID29 was pending and
visible as HPPIR29 but IRQ was not routed to EL3. The boot layer now masks DAIF
first and retains `SCR_EL3 = 0x5B3`; the emitted-stub gate pins both facts.

## Boundary

Builds 98 and 99 prove the checked EL3 boot path across physical cold start;
build 99 is the final accepted artifact. Lower-EL kernel handover, a general
SMC ABI and isolation from a malicious same-EL payload are outside this
acceptance.
