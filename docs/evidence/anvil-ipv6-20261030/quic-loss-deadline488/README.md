# Validated loss deadline proof


### Validated loss-deadline state (2026-10-31)

Sent history now retains the next deadline and policy from a completed bounded loss scan. `QuicHandshakeSentLossTime(s,delay,threshold)` returns a positive deadline, zero when no loss timer is needed, -1 when a fresh scan is required, or an error below -1. A locked ledger refuses the query. The result is published only at scan completion, not after a partial event stream.

Fresh ACK application, explicit loss and admission of a new scan invalidate the stored result. Cancelling a rescan leaves it unknown. A changed delay or packet threshold requests a new scan without destroying the previous policy result. Duplicate ACKs and newer tail sends preserve a still-valid deadline; the tail cannot precede the largest acknowledged packet. Pruning acknowledged prefixes preserves the result, while discard clears it. No-flight and no-eligible-prefix cases are known idle without a scan.

Physical Pi 4 resident488 passed 4,647 assertions, including 268 additional checks covering completed/partial/cancelled scans, policy changes, fresh versus duplicate ACKs, late ACKs after loss, tail sends and explicit invalidation. Both live peer-ID variants also passed the existing consecutive-drop and locked-poll tests, captures366/367/368 across CPU and live runs. Independent peer/RTT/deadline checks, safe close, core/font/Vulkan health and watchdog-off passed. BCM2837 compiled with its real adapter, not executed. No resident update or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-deadline488/`; viewed screenshots show monitor launch state, while record.json proves the current return.

The connection dispatcher does not yet consume this query to give time-based loss priority over PTO. That integration remains next; this change supplies validated, bounded-scan state rather than assuming an old deadline is current. Client no-flight/address-validation, handshake RTT, reliable retransmission/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining IPv6/TLS/device work are still open.
