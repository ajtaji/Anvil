# Cooperative Wi-Fi Recovery

The automatic reconnect path in `RaspberryPi4/Lib/wifi.pi4` is an explicit
phase machine. `WifiLinkTick()` advances at most one scan, join, entropy,
PBKDF2, handshake, key-install, persistence, or DHCP-start operation per
prompt service turn. The common DHCP service owns all lease retransmission,
renewal, rebind, and expiry after `NetDhcpStart()` succeeds. Ethernet service
therefore has an opportunity to run between radio phases.

PBKDF2 cache misses use the resumable engine in
`RaspberryPi4/Lib/pbkdf2.pi4`, with 16 complete PRFs per recovery turn. That
is a compute-work bound, not a wall-time promise. Recovery owns a bounded copy
of the selected passphrase and wipes it, the partial SNonce, and resumable
PBKDF state on cancellation or completion. Manual join/leave and settings or
policy changes invalidate the active generation before taking ownership.

A cache fingerprint selects a possible PMK; it is not proof that the PMK is
correct. If and only if a cache-sourced PMK fails the four-way handshake, the
recovery machine removes that RAM cache row and performs one fresh derivation
from its owned credential copy. A failure after that fresh derivation cannot
loop back into PBKDF2. A fresh PMK is added to the masked `.secret` setting
and saved only after pairwise and group keys install successfully.

Each join snapshots the cumulative CYW43 event-drop count immediately before
`Cyw43JoinStart()`. A historical nonzero count is accepted, but a new delta
through join, verification, keying, persistence, or DHCP wait rejects the
candidate. Candidate failure is intentionally stronger than neutral user
cancellation: it revokes the pending DHCP address and keyed-session
eligibility before scheduling the existing bounded backoff.

If the foreground boot join cannot find or authenticate a saved network after
the radio firmware is already running, boot arms that same cooperative machine
on its normal slow retry cadence. It does not repeat the foreground join loop.
A failure before `gWifiUp` is a distinct limitation: the monitor reports that
automatic association retry is unavailable and keeps Ethernet usable rather
than synchronously reloading firmware on prompt turns. Incremental radio
initialization still needs its own begin/poll service contract. If an active
association generation later observes `gWifiUp=0`, it cancels and remains
unarmed for the same reason instead of retrying an unready radio forever.

Prepared WPA2 M2/M4 bytes are not treated as transmitted: a negative
`wifi_SendSup()` result cannot advance M1 or key installation. Because a
transport refusal did not test the PMK, it retries the association without
evicting a cached PMK or starting fresh PBKDF2. Only a supplicant rejection or
timeout owns the cached-key fallback described above. The older foreground
join follows the same checked M2/M4 send rule and reports the exact failed
stage and transport result before returning failure to its candidate owner.
That foreground candidate owns one PMK across both of its bounded association
attempts; the handshake only borrows it and cannot erase the second attempt's
input. The candidate wipes its PMK, encoded cache row, and synchronous PBKDF2
scratch on every exit. A cache row is validated in full before decode, and a
freshly derived row is offered to `SettingsSet()` only after both keys install.
Settings refusal leaves the encrypted link usable but does not mark the row
dirty or claim persistence.

Live rekey service is also fail-closed. A PTK message 1 must obtain exactly 32
fresh nonce bytes before the session supplicant sees it; short, refused, or
health-failed entropy wipes the partial nonce. M2/M4/G2 response sends and PTK
or GTK installation are checked individually. Session arm and success counters
advance only after their complete send/install sequence succeeds.

The receive callback records the first pending failure stage/result and clears
the scalar keyed/address eligibility immediately, but does not re-associate,
run DHCP, or call back into radio receive. `WifiLinkTick()` consumes that latch
after the radio pump returns. It wipes and records the broken identity even
when link/heal policy is off; those switches may suppress a new association,
but cannot make a partially changed session usable. Manual cancellation and a
new recovery generation discard stale pending work without erasing the last
diagnostic.

Recovery declares DHCP success only when the common Wi-Fi client is `BOUND`,
the interface address provenance is `LEASE`, and the common client, interface
row, and compatibility state contain the same nonzero IP.

The scan/join loops and PBKDF spin are cooperative, but individual CYW43
control requests still use the driver's existing atomic timeout. A single
control phase can therefore occupy up to that timeout. Removing this last
stall requires a separately reviewed begin/poll control transaction contract;
this recovery change does not claim to have solved it.

## Desk gates

Set `PMF_COMPILER` to the product compiler and `PMF_A64_INTERP` to the external A64
interpreter, or pass the equivalent `--compiler` and `--interp` options:

```text
python tools/wifi_recovery_emitted_check.py
python tools/wifi_link_policy_emitted_check.py
python tools/entropy_tryword_emitted_check.py
python tools/pbkdf2_step_emitted_check.py
python tools/a64/pbkdf2_progress_emitted_check.py
```

The gates compile extracted production procedures and execute their emitted
A64. They cover phase ordering and service opportunities; cancellation and
credential ownership; real CYW43 event-ring ownership at the join boundary;
event-drop generations; LEAVE, DISASSOC, cached-PMK-preserving handshake sends,
the actual two-attempt foreground candidate with cache decode/derive/publish
ownership and sensitive-buffer wiping;
foreground and live M2/M4/G2 send failures; partial key installation; nonce
entropy failures; callback/outer-service ownership; policy-off invalidation;
DHCP-start failures; exact DHCP lease ownership; bounded first-connection retry; the
cached-PMK fallback; one-word entropy boundaries; the published RFC 6070
PBKDF2 vector; and the IEEE 802.11 Annex H.4 4096-iteration WPA2 vector.
They are desk evidence, not proof of radio reconnection on physical hardware.

## 2026-09-10 reviewed desk checkpoint

Compiler SHA-256:
`8350107c47c1532b66485d57dda482edbbbc772bfe7adfb295d52d576c2a3b49`.

Gate results:

- recovery, foreground candidate, handshake, rekey, nonce and failure phases:
  106 assertions, 818,911 emitted instructions, with candidate-owner,
  partial-cache and unchecked-send mutations rejected;
- event ownership/pump ordering: 28 assertions, 16,092 instructions, with
  pump-first and callback-reentry mutations rejected;
- one-word entropy: 10 assertions, 1,932 instructions;
- resumable RFC/IEEE PBKDF2: 14 assertions, 710,698,425 instructions;
- unchanged synchronous PBKDF2/callback behavior: exact 2/257 cadence,
  40,842,273 instructions.

Reviewed closure SHA-256 values:

```text
6dd835eea9030928793d426066c9d24d4726884a014f6352b811032a995e5ec6  Anvil/Core/wifi_cmd.pbi
1fef5b309f9157638ffcf70ebc8b6155ee36ecfd0b929628a9e8f4e90a552017  RaspberryPi4/Lib/entropy.pi4
7333a7c5e19d278942ec0f61e422a24e67fc2b50f9f0be5407bbfaa5d817cfda  RaspberryPi4/Lib/pbkdf2.pi4
1a5353fef36406f9481b859b57b282e47da938792a908de74b7077cf4932265b  RaspberryPi4/Lib/wifi.pi4
8540bdbeab8449700c2227d58ac7c5ef8a70ac599c20bb8db0d8c60990fbc1ed  RaspberryPi4/Tests/pbkdf2_step_emitted_gate.pi4
0d01e52722ce13ab1d2f337d2445835e79c7b71212691aaeeb81ac56c9585164  tools/entropy_tryword_emitted_check.py
697206e22c2ecfc944cef81b2a2d661bc9daaf0e98f32838803154661e8e84fb  tools/pbkdf2_step_emitted_check.py
6e3a189fa830575bd6fdbd20d63bc25ce5a9f3396ff60dfa059458f5ebac10fe  tools/wifi_link_policy_emitted_check.py
e88aa06cacc2969c08557cea7c007c2f31c3c9bee40b04f15a328717431efbe5  tools/wifi_recovery_emitted_check.py
```

The narrower cooperative-recovery and cached-PMK transport-owner cut received
an independent read-only review. The expanded foreground/rekey failure surface
above has emitted desk evidence and awaits separate integration and physical
AP/rekey review. An indefinitely unanswered but normally running DHCP client
also still requires later board observation.
