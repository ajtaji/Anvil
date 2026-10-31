### RTT sampling from completed ACK evidence (2026-10-31)

The shared sent-history ACK job now retains whether its largest packet was newly
acknowledged, that packet's send timestamp, whether any new delivery elicited an
ACK, the raw delay field, and whether its timing evidence was consumed.
`QuicRttAck` requires successful completion and consumes eligible evidence once.
It refuses incomplete/cancelled jobs, invalid clocks/exponents and owner aliases.
A newly acknowledged largest packet need not itself elicit ACKs if another newly
acknowledged packet did. A duplicate largest packet never supplies a new sample.
The ACK-delay shift saturates before overflowing. This adapter uses microseconds;
initialize its path estimator and supply receive timestamps/caps in those units.
The caller still authenticates the packet and preserves the job owner's lifetime.

The live fixture now calls this adapter after validated application ACK completion,
using the timestamp captured when the UDP datagram was dequeued, before crypto and
frame processing. It reads the authenticated peer's delay exponent/cap parameters.
It retains up to four sample traces (largest PN, receive/send timestamps, raw delay,
exponent, cap, level and confirmation). A separate host checker matches their ACK
numbers and quantized delays to the independent peer log and recomputes statistics
using arbitrary-precision arithmetic. The timestamps include local transport
queuing; they are not hardware wire timestamps or a general latency benchmark.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-rtt-ack488/`.
Physical Pi4 CPU capture 349 passed 3,513 assertions, including 124 new eligibility
checks. Cases include a non-eliciting largest with another eliciting delivery,
old largest with fresh lower packets, non-eliciting-only delivery, repeated calls,
partial/cancelled ACKs, invalid clocks, alias refusal and saturated delay decoding.
Live captures 350/351 passed all 36 primary and extended checks for eight-byte and
zero-byte destination IDs. Both took two samples: PN0 and PN4, whose ACK covered
three later probes. The discarded PN1 still produced exactly one loss event.
The derived PTO durations were 123622/112377 us; maximum foreground service gaps
were 1888/1897 us. These are individual-run measurements, not comparative claims.
The real Pi3 live adapter compiled only. All hashes/maps, deadman guards, returns,
viewed monitor captures and post-run core/font/Vulkan/watchdog-off checks passed.
No resident update/reset. The earlier run637 watchdog incident remains unresolved
and did not recur.

The production helper now enforces sample eligibility, and the live fixture uses
it, but production connection scheduling still needs integration. Derived PTO
values were checked, not armed. The loss fixture still sends probes explicitly
and disables its time threshold to isolate packet-threshold loss. Owned timer and
loss-job lifecycle, deadline-driven probes, reliable frame retransmission/release,
congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.
