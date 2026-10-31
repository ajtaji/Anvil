# Connection recovery ownership proof


### Connection-owned recovery lifetime (2026-10-31)

`QuicConnection` now owns the RTT estimator, probe timer and bounded loss job. Begin initializes the estimator and timer. Recovery polling and loss stepping refuse a closing connection. Loss admission selects an owned packet-number space and refuses pending control/output work. Close disarms the timer immediately, even while shared TLS resources are held by another task; CloseStep cancels an active owned loss scan before discarding its ledger. Descriptor cleanup wipes the recovery state.

The live fixture uses these owned objects for the measured-deadline probe exchange. It then deliberately arms a timer and leaves an owned loss scan pending while a foreign TLS worker holds shared resources. Both Pi 4 cases verified immediate disarming, refusal of further poll/step calls, preservation of the foreign worker, and cancellation/release of the loss job before normal wipe and socket cleanup. This final timer arm is a lifecycle test, not an extra wire transmission.

Physical resident-488 tests used eight-byte and zero-byte peer IDs, captures 355/356, with independent peer authentication, ACK/loss and RTT/deadline trace checks. Both returned successfully; cores, font and Vulkan checks remained healthy and the deadman was disabled. BCM2837 compiled with its real adapter; it was not executed. No resident image changed. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-recovery-owner488/`.

This integrates ownership and teardown, not a complete recovery scheduler. The fixture still supplies send/ACK timing policy and explicitly arms the timer. Automatic rearming across sends, ACKs and key discard, repeated-loss recovery, reliable frame requeue, congestion/flow control, streams/QPACK/HTTP/3, off-link IPv6 and remaining TLS/device blocking are still open.

The source snapshots preserve the exact compiled bytes. `application-metrics.json` includes recovery close fault/checked fields, and `rtt-traces.json` contains independently checked timing traces. Screenshots were viewed; they show the monitor at payload launch because capture precedes the new return line. The current return is established by each record.json, not the older LASTRUN text visible in the screenshot.
