# Recovery poll exclusion proof


### Recovery polling and partially applied ledger jobs (2026-10-31)

`QuicConnectionRecoveryPoll` now refuses with `QUIC_SENT_BUSY` while any Initial, Handshake or application sent ledger is locked. Bounded ACK/loss jobs can yield after only part of their event stream has been applied. Consuming a probe expiry during that interval would advance backoff and clear the armed timer against an intermediate state. The new refusal leaves the timer intact; the dispatcher must finish or cancel the ledger job and perform the required rearming before resuming recovery polling. This is a cooperative refusal, with no internal wait.

The live fixture requests an otherwise-due poll using a maximum timestamp while real ACK and loss jobs hold their locks. It compares every timer byte and all three lock owners before/after the refused call. These are lifecycle injection checks, separate from the real-clock two-consecutive-drop exchange, which still verifies actual timer expiries, fresh probes, peer ACKs, loss accounting, backoff reset and idle disarming.

Both physical resident488 Pi 4 peer-ID variants passed, captures364/365, including primary/extended assertions, independent peer/deadline/RTT checks and safe close. The first case exercised 14 locked ACK polls and five locked loss polls; observed lock spaces were Initial and application (mask5). Handshake-space refusal is implemented by the same guard but is not claimed as newly exercised wire coverage. Core/font/Vulkan health and watchdog-off checks passed. BCM2837 compiled, not executed; no resident change or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-poll-guard488/`. Viewed screenshots show launch state; record.json proves the current return.

Full recovery policy remains unfinished: time-loss timer priority, client no-flight/address-validation probes, handshake RTT integration, reliable data retransmission/ownership/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining off-link IPv6/TLS/device blocking. This guard protects a transaction boundary; it does not complete those policies.
