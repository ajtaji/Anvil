# Pi 4 EL3 boot and acceptance

Status: **EL3 cold-boot hardware accepted on Raspberry Pi 4 with final build
99**. Builds 98 and 99 both passed witnessed physical power cycles.

## Accepted artifacts

| Artifact | Identity |
|---|---|
| Monitor | build 99, 2,815,748 bytes, CRC32 `9EF87F35` |
| Monitor SHA-256 | `2dec5dba7441ddf3b0cdbfc1115f2cbeac05414383f8db22e4a4210e487e8179` |
| Symbol sidecar SHA-256 | `85c816dd81dba137866052852d710c0a51f413984b6818384c81e794f9b5cd20` |
| EL3 stub | 512 bytes, SHA-256 `9f96324d137ebb4c1452ab00477ffe8c5bf77c53a3bb80ae7fb34234d693f2a2` |
| Unified compiler SHA-256 | `0c0bac62627184109f3a7f7692919b9523e80e413f50b67b82dfc1867f89d51e` |

The firmware configuration selects the checked custom `armstub8.bin`; build 99
reported EL3 and its live CRC matched the host artifact after deployment.

## Defect found and fixed

The retained EL3 boot state used `SCR_EL3 = 0x5B1`. That left IRQ routing to
EL3 disabled. The secure physical timer became pending and the GIC reported
`HPPIR = 29`, but the exception was never delivered. This was not a timer or
GIC polling defect.

The boot layer now masks DAIF before changing the retained state and uses
`SCR_EL3 = 0x5B3`, routing IRQ to EL3. A binary gate checks the emitted stub so
this setting and ordering cannot silently regress.

## Silicon acceptance completed

- `el3test` delivered exactly one secure physical timer interrupt through
  INTID29 and completed the controlled EL3 BRK test at slot 4 with
  `ESR_EL3 = 0xF2000531`.
- Handler, timer, VBAR, DAIF, GIC and watchdog ownership state were restored.
- Build 98 passed the EL3 test three times across warm resets and once after a
  witnessed physical power cycle. That cold run also passed USB/storage and
  DMA/V3D display checks with the prompt present at EL3 and CRC `B8FA3959`.
- Build 98 completed two runs of 16 nonce-tagged rounds on each of cores 1, 2
  and 3. Cache and payload changes were refused while the cores were owned;
  permanent stop acknowledged, and reset cleared the retained leases.
- After the final cleanup, build 99 passed `el3test`, one 16-round run on all
  three secondary cores, all stop acknowledgements, USB/storage and DMA/V3D.
  It was reset afterward to clear the parked workers.
- Build 99 then passed a witnessed physical power cycle: prompt, exact build
  and CRC `9EF87F35`, EL3, cold/zero leases, `el3test`, USB xHCI hub/storage,
  DMA/V3D DSI display, touch identity, Wi-Fi DHCP and network console.
- Quick non-regression checks passed for screen DMA/V3D, touch, USB xHCI and
  storage, Wi-Fi and the network console.

## Accepted boundary

The exact build 99 image and stub are accepted through physical cold start.
The cold result includes the initial prompt/display path, build/EL and live CRC,
`el3test`, USB/storage, touch and Wi-Fi. It does not claim a general SMP
scheduler, lower-EL handover or a general SMC service ABI.

Keep a known-good boot-medium copy and the checked build 98 and 99 images/stub available
for recovery. If the board fails before Anvil starts, restore those files from a
host; a monitor watchdog cannot repair a bad firmware-stage stub.
