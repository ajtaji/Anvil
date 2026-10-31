### Shared probe timer and physical deadline-driven output (2026-10-31)

`QuicProbeTimer` provides Init, Arm, Poll, Acknowledged and Discard in the shared
sent/recovery module. Arm computes the earliest eligible Initial/Handshake/
Application deadline from RTT and the latest eliciting send times, using -1 for
an unavailable space. It excludes application data before confirmation. Poll
emits one expiry, disarms and increments bounded backoff; expiry does not change
packet delivery/loss state. A fresh authenticated ACK resets backoff only when
the caller also certifies address validation. The caller must rearm after ACKs,
sends and key discard; the ACK method alone does not recompute the deadline.
Discard prevents further polling or arming until explicit reinitialization.
No asynchronous callback or borrowed packet storage is hidden in the timer.

The live builder's new `--pto-probe` mode implies deliberate peer loss of PN1.
After receiving the first authenticated ACK, the Pi arms from its measured RTT
and PN1 send time, then keeps servicing foreground work while polling. Only after
expiry does it send fresh PN2. The peer authenticates PN2 and acknowledges it.
Before that ACK, the loss scanner reports no loss even though the PTO elapsed.
Afterward, the RTT-derived time threshold identifies PN1 once; the PN distance is
only one, so the packet threshold cannot explain this result. Backoff is reset,
the idle timer disarmed and timer ownership discarded during fixture cleanup.
The earlier explicit three-probe loss mode remains available separately.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-pto488/`.
Physical Pi4 capture 352 passed 3,916 CPU assertions, adding 403 timer checks.
These cover space selection/ties, application confirmation, deadline boundaries,
single firing, no eligible space, invalid admission preserving state, validated
ACK reset, cancellation and 65 repeated expiries through saturated backoff.
Live captures 353/354 passed all primary/extended checks for eight-byte and
zero-byte IDs. The peer received PN0 and PN2; PN1 was discarded before decryption.
The host checker matched ACK traces and recomputed RTT and the armed deadline.
PTO intervals were 116284/125092 us; Poll observed expiry 10/32 us after those
deadlines. Probe queue admission followed expiry; those figures are not physical
transmit timestamps. Maximum foreground service gaps were 1884/1913 us.
The real Pi3 adapter compiled only. All hashes/maps/deadman/returns, viewed monitor
captures and post-run cores/fonts/Vulkan/watchdog-off checks passed. No resident
update or reset. The older run637 watchdog incident remains unresolved and did
not recur. A lost deadman-arm reply in the CPU run was recovered by reading its
actual status, without rearming or restarting the program.

This verifies one timer-driven probe and subsequent time-based loss in the live
fixture. It does not yet prove repeated wire loss recovery, reliable frame
retransmission or production Core scheduling. The caller still determines keys,
outstanding eliciting spaces and address-validation/no-flight probe policy.
Integrating timer and loss-job ownership into connection dispatch/close, rearming
on all events, reliable frame requeue/release, congestion/flow, streams/QPACK/
HTTP3 and remaining IPv6/TLS/device networking remain open.
