### Physical QUIC probe loss detection (2026-10-31)

The live interoperability fixture now supports `--drop-probe`. After the first
application exchange is acknowledged, the independent peer discards the second
short-header datagram before passing it to its QUIC receiver. The discarded
ciphertext's length and SHA-256 are retained. Anvil sends fresh probes with packet
numbers 1 through 4. The peer authenticates 2, 3 and 4 as PING-only packets and
requires that 1 never appeared in its authenticated receive log. There is no TLS
bypass, simulated acknowledgment, packet-number reuse or receiver state injection.

Before consuming the later ACKs, the shared loss scanner reports no loss. After
three delivery events, largestAcked is 4 and only the missing probe remains in
flight. The packet threshold of 3 then reports PN1 exactly once with its original
length and send timestamp, reducing in-flight bytes to zero. The lost record
remains retained: prefix pruning refuses to pass it. A repeated scan emits no
second event. The fixture uses an effectively disabled time threshold to isolate
packet-threshold behavior; it is not an RTT/PTO or time-loss test.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-wire-loss488/`.
Physical Pi4 captures 346/347 under resident 488 pass all 36 primary and extended
checks with eight-byte and zero-byte destination IDs. Discarded probes were
30/22 bytes. Both runs observe three later delivery events and one loss event,
with zero fixture faults. Exchange times were 447028/443206 us and maximum
foreground service gaps 1898/1901 us in these individual runs. The real Pi3 adapter
compiled but was not executed. Hash/map checks, confirmed return, retained monitor
captures, post-run cores/fonts/Vulkan and watchdog-off checks passed. No resident
image update or reset was needed; captures are not rendering/input qualification.

Only the fixture, builder and independent peer changed; the shared loss detector
needed no correction for this experiment. The first compile attempt used an
unsupported default procedure argument in the fixture and failed before producing
a payload. It was corrected to an explicit argument before either physical run.
The prior run637 watchdog incident remains unresolved and did not recur here.

This proves real lost-packet detection and accounting, not recovery of reliable
application data. RTT/PTO scheduling, owned recovery job cleanup, retransmitted
frame ownership and safe lost-prefix release remain next, followed by outstanding
congestion/flow, streams/QPACK/HTTP3 and IPv6/TLS/device work. ACK/PING alone do not
prove retransmission of a reliable frame. Existing non-loss mode remains the
builder default; the loss mode explicitly requires its matching peer configuration.
