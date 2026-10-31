### Cooperative acknowledgment-based loss detection (2026-10-31)

`quic_handshake_sent.pbi` now provides `QuicHandshakeSentLossBegin/Step/Cancel`
for all three number spaces. The caller supplies a monotonic current time,
positive loss delay in the Commit clock's units, and packet threshold of at
least3. The ledger's completed authenticated ACK state supplies largestAcked.
A scan holds the ledger lock and visits at most64 slots per call. Step returns0
for more work,1 for a loss event and2 when done. The event retains number, byte
count, send time, cookie, previous flags and removed in-flight bytes.

Only unacknowledged in-flight packets preceding an acknowledged packet are
eligible. Packet distance or elapsed send time can trigger loss. Sent facts and
frame metadata remain retained; the scan clears in-flight accounting once and
sets the existing lost flag. It does not erase history or manufacture delivery.
Late ACKs still work and do not subtract flight bytes again. Already-lost,
ACKed, unsent and non-flight records are ignored. An unacknowledged tail or a
space without an ACK needs probing/PTO, not this declaration. These conditions
follow [RFC9002 section6.1](https://www.rfc-editor.org/rfc/rfc9002.html#section-6.1).

At DONE, nextTime is the earliest remaining eligible packet's deadline, or0 if
none. Addition saturates at the signed clock maximum instead of wrapping.
The supplied delay must come from the path's RTT/reordering/granularity policy;
this API does not estimate RTT, run a timer or implement PTO. Cancellation
releases ownership and preserves any loss events already emitted. Those frames
must be requeued/consumed or the connection closed; there is no rollback or
permission to free their metadata. A connection using an external loss job
must finish/cancel it before attempting history discard or connection close.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss488/`. Physical Pi4,
resident488, capture343:2121 independent ledger assertions pass, including the
prior ring/ACK regressions plus packet/time thresholds, exact deadline boundary,
no-ACK/newer-tail protection, ACK-only versus padded packets, skipped unsent
numbers, late ACK after loss, repeated scans, exact loss-event metadata/order,
busy admissions, a64-slot cooperative boundary, cancellation before/after an
event, invalid clock/delay/threshold/alias arguments and deadline saturation.
The independent Python state tracks flags, accounting and event hashes; the Pi
executes the compiled routines. Supplied timestamps simulate loss conditions;
this is not a dropped-datagram wire experiment.

The payload returned x0=0, with healthy cores/fonts/Vulkan and watchdogoff.
Image/map/report/screenshot are retained; the screenshot is monitor return
evidence, not UI/input/rendering validation. The actual Pi3 target compiled,
not executed. No resident update or reset occurred. The earlier run637 watchdog
incident remains unresolved and did not recur.

This adds detection and preserved loss events, not retransmission or a complete
recovery controller. Path RTT/PTO timers, frame ownership/requeueing, congestion
responses, retirement-frame delivery and safe release of lost metadata remain
open. Lost records still block prefix pruning until acknowledged. Streams,
QPACK/HTTP3 and the remaining IPv6/TLS/device items also remain open.
