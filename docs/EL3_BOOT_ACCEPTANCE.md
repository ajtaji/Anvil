# Pi 4 EL3 boot preparation and acceptance

Status: desk preparation only. This checklist does not authorize a transfer,
restart, boot-medium edit or flash. The Pi 4 must have an exclusive test slot
and someone able to recover its USB boot stick before hardware testing.

## Scope and limits

The custom `RaspberryPi4/Board/armstub8.asm` keeps the primary and released
secondary cores at EL3. The normal firmware stub enters Anvil at EL2. Passing
the offline gates proves emitted instruction behavior in the test model, not
firmware acceptance, physical translation, interrupt routing or cache/DMA
coherency. In particular, never boot the interpreter-only register fixtures:
their translation-table values are witnesses, not real page tables.

Running Anvil at EL3 is not a complete secure-world system. Lower-EL kernel
handover currently refuses at EL3, and no general SMC service ABI is promised.
Do not substitute EL3 register names into an EL2 exception return to evade
that refusal. Native monitor payload return is a separate path and needs its
own hardware acceptance.

## Prepare on the host, without touching the board

1. Record the Anvil commit and all relevant dirty files, compiler SHA256,
   source hashes, gate commands/results and the intended monitor build.
   Do not borrow another task's candidate based only on its filename.
2. Obtain a **read-only snapshot** of the actual boot volume when available:
   configuration, all included configuration files, selected monitor image,
   existing custom stub if any, and firmware identity. Record volume identity
   and hashes. Do not assume a drive letter, network address or `kernel8.img`
   selection from an older session.
3. Keep this snapshot unchanged in a host recovery directory. Also retain a
   known-good complete boot-medium backup. Config-only recovery is inadequate
   if the monitor image was changed at the same time.
4. Build the stub explicitly using the existing tool, from the repository root:

   ```text
   python tools/build.py armstub --compiler <PureMetalForge executable>
   python tools/a64/a64_el3_check.py --image build/pi4/armstub8.bin
   python tools/a64/a64_el3_check.py --compiler <PureMetalForge executable>
   ```

   The first gate checks the exact retained artifact. The second additionally
   checks compiler-mode refusals. Archive the artifact and its SHA256 after
   both pass. A later rebuild must be rehashed and rechecked. Building a stub
   is not a monitor build; it does not raise the monitor build number.
5. Run the current EL3 runtime, cached-MMU, exception and secondary-core desk
   gates. Keep their logs with the candidate. Missing integration evidence
   is not a passing gate. Consult the current EL3 desk record for the exact
   gate set rather than treating an old count as proof.
6. If a new monitor is required, use the isolated builder under the shared
   source/build schedule:

   ```text
   python tools/el3_monitor_candidate.py --compiler COMPILER --output _work/el3-candidate-NEW
   ```

   The output directory must not exist. It freezes the include closure and
   target definitions, stages the compiler and records source/artifact hashes.
   It does not overwrite another task's conventional monitor output. Like
   `tools/build.py pi4 --compiler ...`, it records successful monitor builds via
   `tools/build_count.py`; preserve the matching `build/BUILDS.log` record and
   image hash. Do not manually suppress or estimate the count. Do not rebuild
   a monitor merely to prepare this checklist. The snapshot's build marker is
   the compiled identity; the post-build ledger also records the source counter
   advance. Preserve both instead of inferring identity from the latest counter.
   See [build numbering](BUILD_NUMBER.md) and [desk gates](EL3_DESK_STATUS.md).

The commands above only create host artifacts. None installs the stub.

## Configuration review, not a blind rewrite

Create a separate candidate copy of the captured configuration. Preserve the
original bytes, including line endings, encoding, comments and unrelated
settings. The intended scoped change is an effective Pi 4 assignment:

```ini
[pi4]
armstub=armstub8.bin
```

This is an illustration, **not text to append blindly**. Inspect the entire
configuration and every `include`, conditional filter, existing `armstub`,
filename prefix and kernel selection first. An included or later assignment
may override the proposed line; a filter may combine with preceding filters.
Do not invent a universal parser for those cases. If the active Pi 4 context
cannot be established unambiguously, stop preparation of the candidate until
the complete configuration can be reviewed.

Prefer replacing an existing Pi 4-scoped assignment in place. Otherwise use
an explicitly reviewed Pi 4 section without changing the interpretation of
following lines or other boards. The before/after diff must contain only the
necessary `armstub` assignment and, if required, its scope delimiters. Verify
the firmware-resolved stub path actually contains the archived checked bytes.
Do not alter DSI, HDMI, memory, network or EEPROM settings for this experiment.

No config-writing utility is provided here because the current boot snapshot
is not part of the source tree. Guessing its filters is not safe automation.

## Hardware acceptance, only after the board is released

Record a baseline with the known-good EL2 image first. Then install only the
reviewed candidate set, verify its hashes on the medium and cold boot:

| Check | Required evidence |
| --- | --- |
| Identity | Correct build and a register-derived CurrentEL value of 3; a hard-coded banner is insufficient. |
| Early display | Initial banner and progressive boot output on the attached display, with no regression in initial paint. |
| Translation and caches | Real table installation, normal/device attributes, enable/disable transitions and cache maintenance operate without faults or corruption. |
| Interrupts | Actual timer delivery and the intended GIC group/acknowledge/end-of-interrupt path work repeatedly, without a storm or stuck pending interrupt. |
| Fault reporting | Controlled, recoverable test records vector, exception level, syndrome and PC; no uncontrolled fault injection before recovery is available. |
| Secondary cores | Each released core reports EL3, uses its own stack and completes/repeats work with cache coherency intact. |
| DMA/display | Sustained display updates and DMA transfers preserve data with caches enabled. |
| Networking | The available Ethernet/Wi-Fi paths retain normal operation; compare transferred content hashes, not just progress counters. |
| Payload lifecycle | A supported native payload runs, returns and can run again without losing monitor services. Lower-EL kernel handover must still refuse cleanly until separately implemented. |
| Restart | Repeated authorized cold/warm boots return to the same tested behavior. Record the number actually tested. |

Do not mark unconnected interfaces tested. Do not run disruptive negative
tests while the only recovery operator is unavailable. Keep raw logs and the
actual artifact/config hashes beside each result; separate desk proof from
silicon proof in the report.

## Recovery is physical boot-medium access

A bad stub can fail before Anvil, networking, display or its watchdog starts.
A watchdog reset cannot remove a bad `armstub` setting and may only repeat
the same failure. A RAM-run does not prove this firmware boot path.

If boot fails, power down safely, move the USB boot stick to a host and restore
the captured original configuration and any replaced original image/stub
byte-for-byte. Verify the restored hashes, safely eject, reconnect and boot
the known-good set. Restore the original effective configuration, not merely
an assumed `armstub` line: it may already have named another custom stub.
Do not attempt an EEPROM update or unrelated firmware change as recovery.

Until that host-side recovery can be performed, the EL3 candidate remains a
desk artifact and the running board stays unchanged.
