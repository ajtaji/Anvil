### Shared RTT and recovery duration arithmetic (2026-10-31)

`Anvil/Network/quic_handshake_sent.pbi` now provides `QuicRttInit`,
`QuicRttSample`, `QuicRttLossDelay`, `QuicRttPto` and `QuicRttDeadline`.
The path estimator is separate from packet-number spaces and accepts caller clock
units. Its recommended microsecond initialization is 333000 with granularity 1000.
ACK-delay decoding and sample eligibility remain caller responsibilities: only a
fully validated ACK with a newly acknowledged largest PN and at least one newly
acknowledged eliciting packet may supply a sample. Use receive time, not the time
when deferred processing finishes. Positive elapsed samples are required.

The implementation maintains raw minimum/latest RTT and adjusted smoothed RTT and
variation. Initial/Handshake ACK delay is ignored; application delay is capped
only after confirmation and cannot lower a sample below the observed minimum.
Weighted means use quotient/remainder arithmetic to avoid intermediate overflow.
The loss duration rounds upward; PTO duration and absolute deadlines saturate at
signed maximum. Application PTO is refused before confirmation. Backoff is an
explicit caller input, not a hidden counter or timer.

Protocol facts: [RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html), including
[verified erratum 7539](https://www.rfc-editor.org/errata/rfc9002). Variation is updated
from the previous smoothed estimate, as corrected by that erratum. The code is an
independent integer implementation; no appendix code is incorporated.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-rtt488/`.
The physical Pi4 under resident 488 passed 3,389 assertions (2,121 existing sent/loss
checks plus 1,268 timing checks), capture 348. An independent arbitrary-precision
Python oracle evaluates weighted sums directly, while the target uses overflow-safe
quotient/remainder decomposition. Cases cover first sample, delay clamping and
rejection, different packet spaces, confirmation, deterministic varied samples,
integer rounding, maximum signed values, saturated backoff/deadlines and refusal
without state mutation. The real Pi3 adapter compiled only. Image hash, map,
15-second deadman, confirmed return, viewed monitor capture, post-run cores/fonts/Vulkan
and watchdog-off checks passed. No resident update/reset or live latency claim.
A Python quoting error in the test generator was corrected before compilation;
no failed payload was run. The earlier run 637 watchdog incident remains unresolved
and did not recur.

These are timing primitives, not an automatic recovery controller. They do not
consume raw ACKs, select packet-number spaces, arm timers, manage PTO count or
retransmit frames. Next integrate eligible authenticated samples, retained send
timestamps and owned timer/loss-job cleanup, then exercise actual deadline-driven
probes. Reliable frame requeue/release, congestion/flow, streams/QPACK/HTTP3 and
remaining IPv6/TLS/device networking remain open. The live dropped-packet fixture
was not rerun for this additive math API; its previous evidence remains scoped to
its recorded source image.
