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
timeout owns the cached-key fallback described above. Recovery declares DHCP success only when the common Wi-Fi
client is `BOUND`, the interface address provenance is `LEASE`, and the common
client, interface row, and compatibility state contain the same nonzero IP.

The scan/join loops and PBKDF spin are cooperative, but individual CYW43
control requests still use the driver's existing atomic timeout. A single
control phase can therefore occupy up to that timeout. Removing this last
stall requires a separately reviewed begin/poll control transaction contract;
this recovery change does not claim to have solved it.

## Desk gates

Set `PMFC` to the product compiler and `PMF_A64_INTERP` to the external A64
interpreter, or pass the equivalent `--pmfc` and `--interp` options:

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
event-drop generations; LEAVE, DISASSOC, cached-PMK-preserving handshake-send,
and DHCP-start
failures; exact DHCP lease ownership; bounded first-connection retry; the
cached-PMK fallback; one-word entropy boundaries; the published RFC 6070
PBKDF2 vector; and the IEEE 802.11 Annex H.4 4096-iteration WPA2 vector.
They are desk evidence, not proof of radio reconnection on physical hardware.

## 2026-09-10 reviewed desk checkpoint

Compiler SHA-256:
`8350107c47c1532b66485d57dda482edbbbc772bfe7adfb295d52d576c2a3b49`.

Gate results:

- recovery phases and failures: 67 assertions, 282,771 emitted instructions;
- event ownership/pump ordering: 15 assertions, 8,435 instructions, with the
  old pump-first mutation failing assertion 8;
- one-word entropy: 10 assertions, 1,932 instructions;
- resumable RFC/IEEE PBKDF2: 14 assertions, 710,698,425 instructions;
- unchanged synchronous PBKDF2/callback behavior: exact 2/257 cadence,
  40,842,273 instructions.

Reviewed closure SHA-256 values:

```text
8670a0cccb8e156ae039901b5657040dc023de34739c4fad4fd318248a0079f3  Anvil/Core/wifi_cmd.pbi
1fef5b309f9157638ffcf70ebc8b6155ee36ecfd0b929628a9e8f4e90a552017  RaspberryPi4/Lib/entropy.pi4
7333a7c5e19d278942ec0f61e422a24e67fc2b50f9f0be5407bbfaa5d817cfda  RaspberryPi4/Lib/pbkdf2.pi4
8fbe424ef90e4fff460f210badb14720ab30e2b7c29316692846eb387dff56a8  RaspberryPi4/Lib/wifi.pi4
8540bdbeab8449700c2227d58ac7c5ef8a70ac599c20bb8db0d8c60990fbc1ed  RaspberryPi4/Tests/pbkdf2_step_emitted_gate.pi4
0d01e52722ce13ab1d2f337d2445835e79c7b71212691aaeeb81ac56c9585164  tools/entropy_tryword_emitted_check.py
697206e22c2ecfc944cef81b2a2d661bc9daaf0e98f32838803154661e8e84fb  tools/pbkdf2_step_emitted_check.py
235e7fc1f6a63b2f13c6dbec1a4819e9868341f25fcf6895c7eb590343332c67  tools/wifi_link_policy_emitted_check.py
7b06de2300ddaf38c611e1b4cd177c401b3e2bc50a160fbc5d34be7a419ffae5  tools/wifi_recovery_emitted_check.py
```

An independent read-only review accepted the recovery surface after verifying
idempotent NOTASSOCIATED teardown, all other control-failure paths, event-drop
generation checks, cached-PMK fallback bounds, post-key-install persistence,
and candidate cleanup. This remains desk evidence; physical AP-loss recovery
and an indefinitely unanswered but normally running DHCP client require later
board observation.
