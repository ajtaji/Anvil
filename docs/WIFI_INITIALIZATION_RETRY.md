# Cooperative Wi-Fi radio initialization and control requests

## Scope and present gap

This note records the first coarse radio-initialization retry slice for forum
topic 727 and the design boundary for later fine-grained work. The first slice
is source-accepted after independent review and emitted tests, but not deployed
or physically accepted. The orchestrator yields between existing top-level primitives. It does not
claim that an individual storage, mailbox, SDIO or firmware-control request is
nonblocking.

`BootNetUp()` brings Ethernet up first and then calls `WifiJoinKnown()`.
`WifiJoinKnown()` calls the synchronous `WifiRadioUp()` before scan and
association. If scan or association fails after `gWifiUp` becomes one,
`WifiRecoveryInitialJoinFailed()` arms the existing cooperative association
machine. If an earlier radio stage fails, the same hook now arms a separate
radio-initialization generation when saved credentials exist and link/heal
policy permits it. That generation waits for the normal recovery deadline,
then advances one existing top-level primitive per `WifiLinkTick()`. A transient
missing blob, mailbox refusal, SDIO enumeration failure, firmware-upload
   failure, function-2 timeout, CLM refusal or WLC_UP refusal can therefore be
retried without rerunning the entire synchronous chain in one prompt turn.

`WifiRadioUp()` is also called by the foreground `wifi scan` and `wifi join`
paths. Those commands continue to own the call synchronously. The automatic
initializer is a separate owner: starting a foreground operation, changing
saved networks, turning link/heal policy off, or requesting a radio power cycle
must cancel or replace its generation before the foreground owner acts. A late
phase from an older generation must never publish `gWifiUp` or continue into an
association.

## Current call order and ownership

The synchronous order is:

```
WifiRadioUp
  wifi_RadioGenerationPreflight
  WifiLoadBlobs
  MailboxInit -> WifiClockHz -> SdioSetBaseClockKhz
  SdioAssertWlOn
  SdioInit -> SdioEnableFunction(1)
  Cyw43SetIo -> Cyw43SetBlockIo -> Cyw43Attach
  Cyw43SetBlockMode -> Cyw43PrepareDownload
  Cyw43UploadFirmware -> Cyw43UploadNvram
  Cyw43Start -> Cyw43HtClock -> Cyw43AnnounceHost
  SdioEnableFunction(2)
  Cyw43WifiUp(CLM, event mask, 2000)
  Cyw43SetRoamOff(1, 2000) -> Cyw43SetPowerMode(PM_OFF, 2000)
  gWifiUp = 1
```

The state is not interchangeable between layers:

| Owner | State or buffer | Required lifetime and cancellation rule |
| --- | --- | --- |
| `wifi.pi4` blob owner | `gWifiLoaded`; firmware at `0x01000000`, NVRAM at `0x01200000`, CLM at `0x01300000`; NVRAM work at `0x01210000`; verify scratch at `0x01220000` | The three input blobs may survive failed radio generations after their exact lengths and CRC policy pass. A partial load is not published. An initializer borrows these fixed regions only while it owns its generation. |
| radio-init owner | phase, generation, phase result, retry deadline, clock result, firmware-call count and announcement policy | Exactly one automatic generation. A service step compares its captured generation after every called operation and before publishing a later phase. Cancellation is effective at the next operation boundary; it cannot interrupt an SDIO command already in flight. Fine-grained upload offsets remain future work. |
| `sdio.pi4` bus owner | controller-ready state, RCA/OCR/function count, command response/error fields, base clock, bus width, WL_ON once-per-run latch | One SDIO command/data transaction at a time. `SdioInit()` is destructive to the controller generation. `SdioAssertWlOn()` may power-cycle a warm radio and must run at most once unless an explicit reset owner first calls `SdioForgetWlOn()`. |
| forum-737 readiness owner | exact card IENx and host INT_ENABLE snapshots, callback, core address and pending/restore state | Before `SdioInit`, callback replacement, attach, RAM geometry replacement, download reset/start, upload, or transport reset, `Cyw43RxIrqTelemetry(0)` must return verified success through the old transport. Failure enters a restore-pending phase and forbids all destructive new-generation work. The snapshot and callback remain owned for retry. |
| `cyw43.pi4` chip/download owner | attached/core table, backplane-window cache, RAM geometry, reset vector, firmware/NVRAM publication, verify record | These fields belong to one powered-radio generation. `cyw43_fwLoaded` is published only after the configured verify completes; `cyw43_nvLoaded` only after cook, write, full verify and token readback. A failed or cancelled partial upload must not be reused by a new generation. |
| `cyw43.pi4` framed transport owner | SDPCM sequence/credit, BCDC request ID, TX/RX/argument/CLM/word buffers, reply offset/length, retained RX/event rings | Only one firmware control request may be outstanding with the present globals. `cyw43_replyOff` refers into the shared RX buffer and is valid only until another receive operation. Transport reset is a generation boundary and must remain ordered before CLM/event-mask/WLC_UP. |
| association/DHCP owner | persisted network rows and PMK cache versus live PMK/PTK/GTK, keyed state and the common per-interface DHCP lease | Saved credentials and a validated cached PMK are configuration and survive neutral radio-init cancellation. Live session keys and a Wi-Fi lease do not prove a new radio generation. Any failed/destructive initialization keeps `HwLinkReady(WIFI)` false and calls the common Wi-Fi link-down/lease invalidation boundary once; it must not erase saved configuration or advertise an old lease. |

No callback into Ethernet, TCP, the console, display, DHCP, or settings is safe
while a mailbox message, SDIO CMD52/CMD53, backplane-window transfer, firmware
control request, or shared CYW43 buffer operation is in progress. A wired
service opportunity exists only after such an operation returns and the radio
state machine has stored its next phase.

## Real bounds in the current synchronous primitives

The following are implementation bounds, not latency promises:

| Current operation | Existing bound and atomicity | Cooperative boundary |
| --- | --- | --- |
| one property-mailbox transaction | `MailboxSend()` has a 1000 ms transport budget plus a spin guard | Inherently atomic with the single mailbox buffer. Return before servicing wired work. `WifiClockHz()` can attempt eight such calls and adds a 25 ms gap after each zero result, so its enclosing call is not a 200 ms operation. |
| WL_ON | several one-second mailbox transactions, an optional 20 ms low interval and a mandatory 150 ms high interval | The property transactions are atomic. The low/high settle intervals can become deadline phases, but a cancelled attempt that has driven the rail low must still finish the high write/readback or explicitly report the radio left off. |
| controller reset/clock | reset and clock-stable waits are 100 ms each | A reset request and its completion proof are one phase. Do not service the same SDIO controller between them. |
| one CMD52/CMD53 command | command/data inhibit up to 500 ms, command response up to 200 ms; R1b or final data completion up to 500 ms | One issued command plus its response/data completion and error-line recovery is atomic. It cannot be abandoned with controller inhibit or FIFO ownership unresolved. |
| CMD53 data body | each PIO block receives its own 500 ms ready budget, and final transfer completion receives 500 ms | The current API may carry up to 511 blocks, so 500 ms is not a whole-call ceiling. A later resumable bulk API must issue fewer complete CMD53 commands per step; it must never yield in the middle of a command or FIFO block. |
| SDIO I/O-operating condition | overall 1000 ms CMD5-ready budget with 10 ms between complete CMD5 calls | Safely split into SEND/POLL deadline phases. Wired work may run after each complete CMD5 reply, not while a command is active. |
| function enable | overall 1000 ms IORx-ready budget around complete CMD52 reads | Safely split into IOEx read/write then one IORx read per service step. The outer deadline can overrun by one atomic CMD52 today. |
| CYW43 ALP and HT availability | each has a 1000 ms availability budget around complete CMD52 reads; ALP adds 65 us settle | Safely split into request/echo/poll/finalize phases, one complete register access per step. Core/window ownership remains exclusive. |
| core disable/reset | 20 us reset settle and a 300 us observation loop; reset release has at most 51 attempts with 60 us gaps | Keep each ordered register write plus posted-write read together. The short observation gaps do not justify callbacks inside the core transition. |
| firmware image upload | 609,312 padded bytes; backplane windows are 32 KiB; one CMD53 is at most 511 blocks; head and tail verification are 16 KiB each in the monitor's mode 2 | Safely resumable at completed backplane-transfer chunks. Store the offset only after a complete write/read-and-compare succeeds. Never yield between programming the 32 KiB window and its associated CMD53. Publication remains false until both verify regions pass. |
| NVRAM | 2074 input bytes, cooked into the caller-owned 4096-byte work area, then write, full readback and independent token readback | Small enough for separate COOK, WRITE, VERIFY and TOKEN phases. The cooked work buffer must remain owned until all phases finish. |
| one `Cyw43Ioctl(..., 2000)` | the 2000 ms value bounds only `cyw43_Poll`'s reply loop after send. A preliminary 100 ms credit poll and synchronous F2 send precede it; each receive/send CMD53 has its own bounds. The call can therefore exceed 2000 ms. | Not safely cooperative through the present API. It builds into shared TX storage, allocates a request ID, sends once, and waits while retaining unrelated data/events. A begin/poll owner is required before yielding. |
| `Cyw43WifiUp` at the present CLM size | transport reset, three CLM chunk ioctls, one CLM-status ioctl, event-mask ioctl, WLC_UP ioctl, then 100 ms settle; callers pass 2000 ms to each ioctl | This is several independently reply-bounded requests, not one two-second request. It is safely split only if transport reset stays first and the CLM BEGIN/END flags, offset and status-query requirement remain generation-owned. |
| roam-off/power-mode policy | one 2000 ms ioctl each; currently nonfatal | Keep their nonfatal policy meaning, but report their exact result. They may be separate final phases and cannot publish a false claim that the requested policy took effect. |

`WifiLoadBlobs()` also contains storage open/read operations and bytewise CRC
work whose full wall bounds are not expressed by the Wi-Fi layer. Merely moving
that call behind a timer would not make it cooperative. The first slice below
keeps one blob-load call as an honest remaining atomic stage and retries it only
on an explicit new attempt, never on every prompt spin. A later storage slice
would need a storage-owned incremental read contract rather than Wi-Fi reaching
into FAT internals.

## Target radio-initialization machine

The implemented public shape is `WifiRadioInitArm(announce)`,
`WifiRadioInitTick()`, `WifiRadioInitCancel()` and read-only phase, attempt,
firmware-call and last-failure accessors. `WifiLinkTick()` is the single
prompt-service caller. Boot failure with saved credentials, link/heal
policy enabled and `gWifiUp=0` arms it once; it does not call `WifiRadioUp()`
again. A manual command cancels the automatic generation before retaining its
existing synchronous behavior.

A complete target phase order is:

```
IDLE / WAIT_POLICY / BACKOFF
RESTORE_737
BLOBS
MAILBOX / CLOCK
WLON_READ / WLON_LOW_SETTLE / WLON_HIGH_SETTLE / WLON_VERIFY
SDIO_RESET / SDIO_IDENT / SDIO_OPCOND / SDIO_SELECT / SDIO_WIDTH
F1_ENABLE
IO_BIND / ATTACH / PREPARE_DOWNLOAD
FW_BEGIN / FW_WRITE / FW_VERIFY_HEAD / FW_VERIFY_TAIL
NVRAM_COOK / NVRAM_WRITE / NVRAM_VERIFY / NVRAM_TOKEN
FW_START / HT_REQUEST / HT_POLL / HOST_ANNOUNCE / F2_ENABLE
TRANSPORT_RESET
CLM_BEGIN / CLM_CHUNK / CLM_STATUS
EVENT_MASK / WLC_UP / WLC_UP_SETTLE
ROAM_POLICY / POWER_POLICY
READY
```

Each tick performs at most one existing top-level operation in the first
implementation slice, or one complete bus/control operation after that layer
has a resumable API. It stores the next phase and returns. The board's ordinary
outer service loop can then service Ethernet, TCP timers, console ownership,
display and watchdog before the next radio phase. The radio phase itself never
calls those services.

The machine owns a monotonically changing 32-bit generation. Arm, cancel,
manual join/scan/leave, credential or network changes, policy-off, and explicit
power-cycle all advance it. Every completion compares the captured generation
before mutating publication state. Tick arithmetic uses unsigned subtraction so
deadlines survive 32-bit wrap.

Failure records exact phase, transport result, SDIO/CYW43 error and whether
737 restoration remains pending. A retry is armed only when saved credentials
exist, link and heal policy remain enabled, the previous call has returned, and
the retry deadline is due. Backoff prevents repeated blob/firmware work; it is
only an attempt scheduler, not the mechanism that makes initialization
cooperative. Missing media/blob is reported and remains at a slow retry state;
policy or settings change may explicitly re-arm immediately. There is never a
synchronous firmware reload on every prompt turn.

## First minimal implementation slice

The implemented first cut changes only the orchestration, not SDIO or CYW43
transaction internals:

1. It adds generation-owned radio-init state to `wifi.pi4` and advances one
   current public call per tick in the exact existing `WifiRadioUp()` order.
   `Cyw43UploadFirmware()` runs once as its own phase; it is never restarted
   merely because the prompt serviced another subsystem. If it fails, the
   partial radio image is not published and the next *new* generation repeats
   the complete coarse predecessor chain (readiness restoration, blobs,
   mailbox/clock/WL_ON and `SdioInit`), not a saved middle offset.
2. Before the first destructive phase, it consults `Cyw43RxIrqActive()` and
   `Cyw43RxIrqRestorePending()`, then call `Cyw43RxIrqTelemetry(0)` when the
   737 observer owns or may owe restoration. Refusal enters `RESTORE_737` and
   performs zero `SdioInit`, callback replacement, attach, upload or transport
   reset operations until verified disable succeeds.
3. On successful radio publication, it arms the existing cooperative association
   recovery generation. Do not duplicate scan, PBKDF2, handshake or DHCP
   state. On failure, invalidate only live Wi-Fi usability/lease state, retain
   saved settings and PMK cache, record the exact phase, and use the existing
   slow recovery cadence as the next-attempt schedule.
4. Foreground `wifi scan`/`wifi join` retain their compatibility behavior and
   cancel the automatic generation first. The common recovery cancellation
   seam also cancels radio-generation ownership.
5. `SdioInit`, blob load, firmware upload, and each CYW43 ioctl remain atomic in
   this cut and say so in status/docs. This cut gives wired-service
   opportunities between major stages and fixes eventual retry after a
   transient `gWifiUp=0` failure; it does not eliminate every multi-second
   phase.

This cut is intentionally smaller than adding resumable firmware, staged SDIO,
and asynchronous control at once. Those follow only after the orchestration and
cancellation ownership pass independently.

The focused emitted candidate gate currently passes 42 scenario assertions,
17 mandatory phase-failure rows and 23 cancellation boundaries over 94,189
executed A64 instructions. It rejects 15 emitted product mutations and 10
structural command-branch mutations. A second emitted fixture executes the
extracted real `CmdWifi` control flow for 16 success/refusal/foreground-policy
assertions over 13,437 A64 instructions and rejects a hook moved before setter
success. This is desk evidence for ownership and order,
not physical radio acceptance. The gate includes the supported
`Cyw43SetBlockMode(1) = 0` byte-mode fallback, the shared synchronous/automatic
forum-737 preflight, and cancellation after GTK publication but before DHCP:
the live keyed session remains valid and reconciliation explicitly hands the
unaddressed interface to the common DHCP client.

## Generic configuration revision

The follow-on source-accepted slice adds one settings-owned, wrapping Wi-Fi
selection revision. Its positive allow-list is exactly `wifi.network`,
`wifi.password.plaintext`, and the SSID/passphrase pair for numbered slots 1
through 4. Cached `wifi.N.pmk.secret` rows and unrelated settings are excluded:
they are session bookkeeping, not network selection. A successful direct set
advances only when the stored value actually changes; a refused set, identical
set, missing removal or settings discard does not. A successful removal does.

`SettingsParse` owns a batch around reset and every accepted input line, so a
full or partial replacement publishes at most one revision. Null and negative-
length parses still close the batch after their documented reset. The no-file
`SettingsLoad` reset has its own batch; open/size/read failures before table
replacement preserve the old table and revision. `SettingsDiscardLoad` changes
only whether a partial image may later be saved, so it publishes no selection
event.

Wi-Fi samples the revision only after the settings/shared-buffer operation has
returned, at the top of `WifiLinkTick`. It acknowledges the newest value before
cancelling once and calling `WifiRecoveryReconcile(0)`, so any number of setters
between ticks coalesce. Wi-Fi-specific commands acknowledge their synchronous
event in `WifiConfigChanged`, avoiding a duplicate cancellation on the next
tick. There is no callback from the settings store, no secret output, and no
unconditional radio auto-arm. Policy-off/no-credential truth remains idle;
keyed live sessions remain live, with the existing keyed/unaddressed path
explicitly returning address ownership to the common DHCP client.

The emitted settings gate executes the real reset, set, remove, parse, load and
discard bodies for 20 assertions over 713,193 A64 instructions and rejects six
assertion-failing mutations. The link-policy composition executes the real
outer observer, including one-shot/coalesced consumption, policy-off and active
recovery preservation when PMK bookkeeping leaves the revision unchanged.

## Follow-on split: firmware/SDIO and atomic control

The next bulk cut may add begin/step/finalize APIs for firmware and NVRAM.
One step owns a bounded number of complete backplane transfers, records its
offset after success, and returns with no controller command, FIFO or window
change in progress. Cancel clears offset/reset-vector/publication and requires
the next generation to put the core passive and begin at byte zero. Verification
must still cover the configured head/tail regions before `cyw43_fwLoaded=1`.

SDIO's long readiness waits may similarly become request/poll phases, but a
CMD52/CMD53 and its completion/error recovery remain atomic. WL_ON cancellation
needs a terminal cleanup state: after LOW was issued, HIGH plus readback is
mandatory even if the logical owner was cancelled.

Atomic control removal is a separate transport cut. It needs one outstanding
request object containing request ID, command, interface, SET/GET kind,
deadline, copied payload or stable caller-owned storage, result status and an
owned reply buffer. `Begin` builds and transmits exactly once. `Poll` performs a
bounded receive budget, preserves wire order, queues unrelated data, classifies
events, updates credits, and accepts only a matching BCDC reply. `Cancel` marks
the ID stale and retains enough metadata to discard a late matching reply; it
does not resend with a new ID. Request-ID wrap must skip every outstanding or
stale-quarantine ID. Since the present reply pointer aliases shared RX storage,
the matching response bytes must be copied into request-owned storage before
`Poll` yields. Only one control request may exist until the global TX/argument,
sequence/credit and reply ownership is redesigned.

The synchronous `Cyw43Ioctl` wrapper can later be expressed as Begin followed
by Poll for existing foreground callers, preserving behavior. The cooperative
radio initializer uses Begin/Poll directly. No network callback or recursive
`NetInput` is allowed inside control polling, and queue exhaustion is an
explicit bounded resource failure rather than a request resend.

## Deterministic acceptance gates

The first orchestration slice needs emitted-code tests with injected operation
results and ticks:

- fail each phase once and prove no later phase or `gWifiUp` publication;
- transient boot failure with `gWifiUp=0`, saved credentials and policy on:
  one backoff, one new generation, exact ordered calls, then handoff to the
  existing association machine;
- permanent failure: no call before the deadline, one attempt at the deadline,
  no per-spin blob/upload loop, wrap-safe deadline arithmetic;
- active and failed-restore 737 ownership: repeated ticks perform only disable
  retries and zero destructive bus/chip operations; verified disable permits
  exactly one new generation and leaves no stale callback/latch;
- one service-opportunity counter between every returned phase, and a reentry
  trap proving the radio primitive itself never calls wired/network service;
- cancellation at every phase, including after WL_ON LOW: old generations
  cannot advance or publish; rail cleanup completes; manual owner then proceeds;
- settings/policy change during a phase: the old result cannot publish and the
  replacement generation uses current settings without printing secrets;
- firmware phase called once per generation; failed upload cannot proceed to
  NVRAM/start; a later generation re-runs passive/reset and begins from zero;
- cached PMK and saved credentials survive neutral initialization failure,
  while live Wi-Fi readiness, session eligibility and common DHCP lease are
  unusable until a new keyed association and exact common-client lease bind;
- failure diagnostics retain the first exact phase/error without a later
  cleanup error silently replacing it, while still reporting cleanup failure.

The later bulk and control gates must add:

- every firmware window boundary, final odd-length padding, write failure,
  head/tail mismatch and cancel/restart; no duplicated or skipped offset;
- SDIO CMD5/IORx/ALP/HT not-ready, late-ready and timeout rows with wired service
  only between complete commands;
- control data/event/glom before the matching reply, credit refresh before send,
  malformed/wrong command/interface/ID replies, timeout, cancellation, late
  reply, 16-bit ID wrap, queue exhaustion and a real subsequent request;
- mutations that resend after a yield, leave reply bytes aliased to shared RX,
  cross a 737-owned generation, or publish `gWifiUp` before all mandatory
  phases must fail.

Desk gates prove ordering and ownership only. Physical acceptance still needs a
normal successful boot, injected recoverable bring-up failures on a developer
build, verified Ethernet console/service throughout retry, and a subsequent
Wi-Fi join/DHCP/transfer without stale lease or key publication.

## Primary sources and provenance

- The SD Association's [simplified specification index](https://www.sdcard.org/downloads/pls/)
  supplies the SDIO card and host-controller rules for CMD5, IOEx/IORx,
  CMD52/CMD53 and completion ownership. Specification behavior is referenced,
  not copied.
- Linux v6.12 [`mmc/core/sdio_ops.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/mmc/core/sdio_ops.c)
  and [`mmc/core/sdio_io.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/mmc/core/sdio_io.c)
  are GPL-licensed behavioral cross-checks for operating-condition and function
  enable ordering. No Linux MMC code is copied.
- Linux v6.12 Broadcom [`brcmfmac/sdio.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/net/wireless/broadcom/brcm80211/brcmfmac/sdio.c)
  and [`brcmfmac/bcmsdh.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/net/wireless/broadcom/brcm80211/brcmfmac/bcmsdh.c)
  are the ISC-licensed primary implementation references for firmware download,
  core activation, CLM/control sequencing, SDPCM request ownership and SDIO
  receive behavior. Any later adapted CYW43 code must retain the Broadcom
  copyright/ISC notice already indexed by `docs/THIRD_PARTY_NOTICES.md`.
