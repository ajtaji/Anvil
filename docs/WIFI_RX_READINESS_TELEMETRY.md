# CYW43 SDIO receive-readiness telemetry

## Scope

This is an evidence-collection slice for the idle function-2 polling problem
tracked as forum topic 737. It is not the eventual scheduling fix.

The existing receive path is deliberately unchanged:

```
TcpTick -> TcpPoll(0) -> LinkPumpAllNet -> HwLinkRecv
        -> Cyw43Receive -> cyw43_RxFrame -> F2 FIRSTREAD
```

When the optional telemetry is disabled, no readiness callback is made. When
it is enabled, `cyw43_RxFrame` observes readiness immediately before the same
legacy 64-byte F2 first read. A quiet indication does not suppress that read,
and a pending indication does not add another read. Queued data, control
replies, events, transmit credit, gloms and receive-abort recovery retain their
existing owners.

One mostly-idle measurement of the legacy path recorded 1,915,833 empty F2
first reads and 122,621,384 requested bytes in 147 seconds, about 13,033 reads
and 0.834 MB of requested bus traffic per second. Those counters identify a
cost; they do not prove which readiness signal can safely replace polling.

## Optional ABI and registration

The SDIO side exports one operation callback:

- `SdioRxIrqOp(ARM)` snapshots state and arms persistent status capture.
- `PENDING` samples the raw host `CARD_INT` status level.
- `QUIESCE` masks host `CARD_INT` status generation during capture.
- `REARM` restores host status generation and immediately resamples it.
- `DISABLE` restores the exact card and host snapshots.

The CYW43 side exports `Cyw43SetRxIrqIo()` and
`Cyw43RxIrqTelemetry()`. Installing a callback is inert. A main program must
explicitly register `SdioRxIrqOp` and enable telemetry only after SDIO
functions 1 and 2 and the CYW43 SDIO device core are operational. The normal
board program does not yet register it.

The CYW43 layer conservatively gives the callback snapshot ownership before it
calls ARM. If ARM refuses, it immediately requests DISABLE; callback replacement
and another ARM remain blocked unless that cleanup is verified. Disable can be
retried after a failed restoration.

That ownership is also a transport-generation boundary. `SdioInit` refuses
before clearing any transport, diagnostic or snapshot field and before issuing
hardware I/O while an armed or retryable SDIO snapshot exists. CYW43 refuses
base/block I/O replacement, attach or direct core enumeration, RAM-geometry
replacement, firmware/NVRAM upload, core download reset/start, and SDPCM
transport reset while capture is active or restoration is pending. The old
callback, core address, sequence/queue state, image-publication state and
retryable snapshot remain owned. A caller must run
`Cyw43RxIrqTelemetry(0)` through the still-working old transport and receive
verified success before starting the new generation. Failed disable is not
cancellation and cannot be bypassed by calling initialization again.

## Card and host transaction

ARM verifies both F1 and F2 in CCCR `IOEx` and `IORx`, then snapshots the exact
CCCR `IENx` byte and SDHCI Interrupt Status Enable word. It quiesces host
`CARD_INT`, enables CCCR master/F1/F2 interrupt bits, verifies the write, and
then enables host `CARD_INT` status capture. Unrelated card and host mask bits
are preserved.

SDHCI Signal Enable is not changed. This slice captures a persistent status
level for cooperative polling; it does not install a CPU exception handler.

The initial host quiesce is read back before the card IENx value is changed;
a failed mask therefore issues no card-arm write. Every partial ARM failure
attempts exact rollback. DISABLE also performs an
exact rollback. If either the card or host snapshot cannot be read back, the
operation reports failure and keeps the snapshot retryable. It makes and
verifies a best-effort host quiesce; a failed quiesce has a distinct counter,
so the code never describes an unresolved host state as restored or contained.

`CARD_INT` is excluded from every broad SDHCI Interrupt Status W1C write.
Command and data completion/error bits retain their previous W1C handling.
The level-sensitive card indication is retired by servicing function-specific
causes, not by writing the host `CARD_INT` bit back.

## Device-core capture and races

The sole capture owner is `cyw43_RxFrame`. If raw `CARD_INT` is present, it:

1. quiesces host status capture;
2. reads and acknowledges the CYW43 SDIO-core host interrupt causes;
3. rereads flow-control state after `FC_CHANGE`, so a change crossing the
   acknowledgement is retained conservatively;
4. reads To-Host mailbox data and writes the documented mailbox ACK;
5. converts `NAKHANDLED` into software frame-pending state;
6. rearms host capture and immediately samples for a cause that arrived in the
   quiesced interval.

The observer has a no-reentry guard. A nested call neither touches interrupt
state nor steals queued data. Its faults use a separate telemetry fault code
and preserve the preexisting CYW43 transport error. The unchanged F2 operation
still runs afterward; if that real operation fails, its transport error
correctly replaces the older diagnostic.

Software frame-pending state remains set across a burst and is cleared only by
the existing all-zero SDPCM header. A retained queue entry is already software
owned and therefore performs neither a readiness probe nor an F2 read.
Receive-abort recovery remains ahead of readiness capture and keeps sole
ownership of resynchronization.

## What must be measured before enforcement

A later scheduling change must first establish on silicon that:

- raw `CARD_INT`, CYW43 `FRAME_IND` and nonempty F2 first reads correlate under
  idle, control, event, TCP receive and glom loads;
- rearm-immediate detections close the quiesce race without losing work;
- mailbox and flow-control causes remain serviced when no data frame follows;
- queue and abort paths never need a second hardware reader;
- fault-disable and exact restoration leave ordinary polling intact.

Only then can the shared `cyw43_RxFrame` boundary use readiness to suppress an
empty read. Enforcement needs a per-call stable-quiet/frame/recheck/fault
result; cumulative counters cannot authorize suppression. Rearm-pending,
zero-core-cause, nested observation and exhausted recapture require an immediate
recheck or conservative legacy-read fallback, not a sleep or periodic F2 timer.
An observed nonempty read without readiness blocks enforcement until explained.

Transport reset or reinitialization must also disable and verify restoration
before discarding the old callback/latch generation. The current optional
The monitor keeps the prototype off at boot. `wifi rxready arm` is the only
arming action; it requires a stable operational radio generation, registers the
SDIO callback, enables telemetry, and records counter baselines. `wifi rxready
capture` (or bare `wifi rxready`) prints read-only deltas without clearing
cumulative counters. `wifi rxready disable` restores the exact saved masks and
removes the callback only after restoration verifies. Failed restore retains
the callback, generation and retryable ownership.

Capture places CARD_INT/frame indications beside legacy first/empty F2 reads
and CMD53 calls. It does not change `cyw43_RxFrame`; every case still performs
the legacy read. This is observation, not a scheduler or performance fix.

Quiet-nonempty first reads are further bucketed by parsed SDPCM channel (or
malformed header), preceding accepted wire-frame NEXTLEN, and receive-sequence
continuity. The report distinguishes a FRAME_IND latch inherited from an
earlier pass from one newly captured by the current observation. After a
quiet-nonempty result it takes one additional raw host PENDING sample only; it
does not quiesce, acknowledge, or issue another F2 read. A post-read assertion
is consistent with a timing race but is not proof: the asserted host cause may
be unrelated to the frame just read. These fields are correlations only.

Physical acceptance sequence: arm; capture an idle interval; capture around
ping, control/event, TCP and glom-producing traffic; then disable. `wifi bus`
remains the cumulative transport view. Any nonempty F2 read without readiness
blocks later enforcement until explained.

## Executable gates

The gates compile the production PureMetal sources and execute the
emitted AArch64 image in an external register/FIFO model:

```
python tools/sdio_rx_readiness_emitted_check.py --pmfc PMFC --interp PMF_A64_INTERP
python tools/cyw43_rx_readiness_emitted_check.py --pmfc PMFC --interp PMF_A64_INTERP
python tools/cyw43_f2_fifo_emitted_check.py --pmfc PMFC --interp PMF_A64_INTERP
python tools/cyw43_rx_glom_transport_emitted_check.py --pmfc PMFC --interp PMF_A64_INTERP
```

The focused gates cover exact snapshots and rollback, failed rollback and
retry, unresolved host quiesce, IOEx/IORx refusal, `CARD_INT` W1C exclusion,
FC_CHANGE reread, mailbox ACK, rearm races, nested capture, quiet and pending
legacy reads, queued and abort ownership, data preceding a matching control
reply, observer-fault diagnostic isolation, a subsequent real F2 failure,
active/failed-restore initialization refusal before hardware I/O, callback and
generation-state preservation, direct core/RAM/image generation guards, first
host-mask refusal before card arm, and verified disable before a new generation.
The guard and first-mask negative controls deliberately remove those production
checks and require the emitted gates to fail.
The FIFO and deglom regressions prove the existing F2 fixed-address and bounded
aggregate delivery contracts remain intact.

These are source and emitted-code proofs, not physical interrupt or radio
proof.

## Primary sources and provenance

- The SD Association's [SDIO Simplified Specification 3.00 and current
  simplified-specification index](https://www.sdcard.org/downloads/pls/)
  define CCCR IOEx, IORx, IENx and INTx behavior. The Association's
  [archive](https://www.sdcard.org/downloads/pls/archives/) provides SD Host
  Controller Simplified Specification 3.00. Specification text was referenced,
  not copied.
- Linux v6.12 [`brcmfmac/sdio.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/net/wireless/broadcom/brcm80211/brcmfmac/sdio.c)
  and [`brcmfmac/bcmsdh.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/net/wireless/broadcom/brcm80211/brcmfmac/bcmsdh.c)
  are Broadcom ISC-licensed primary implementation references for CYW43/SDPCM
  interrupt bits, flow-change reread, mailbox acknowledgement, NAK recovery and
  frame-pending semantics. The adapted CYW43-specific code retains Broadcom's
  copyright/ISC notice in `cyw43.pi4`; the complete notice is in
  `licenses/Broadcom-brcmfmac-ISC.txt` and indexed by
  `docs/THIRD_PARTY_NOTICES.md`.
- Linux v6.12 generic [`mmc/core/sdio_irq.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/mmc/core/sdio_irq.c),
  generic [`mmc/host/sdhci.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/mmc/host/sdhci.c),
  and Raspberry Pi's [`bcm2835-mmc.c`](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/mmc/host/bcm2835-mmc.c)
  were GPL-licensed behavioral cross-checks for CCCR enable and host
  mask/service/rearm ordering. No MMC/SDHCI source code was copied.
