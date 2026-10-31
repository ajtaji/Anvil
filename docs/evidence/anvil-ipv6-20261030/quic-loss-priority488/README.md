# Loss scheduling priority proof


### Time-loss priority in connection polling (2026-10-31)

`QuicConnectionRecoveryPoll` now checks eligible owned packet-number spaces using the current RTT loss delay and packet threshold three before considering PTO. Return zero means no action now; `QUIC_RECOVERY_PROBE` (one) requests a probe; `QUIC_RECOVERY_LOSS` (two) requests a bounded loss scan. `recoveryLevel` is valid only on returns one/two. Negative values remain refusal/error results. A caller receiving two must run the selected space's scan with current policy, consume its events and poll again. Poll itself does not mark packets lost.

An unknown/stale scan requests work immediately. With valid scan results, the earliest loss deadline wins; any future loss deadline suppresses PTO dispatch even when the stored PTO candidate is earlier. The candidate is retained without advancing backoff. These are poll-driven candidates, not asynchronous timer callbacks. No loss work means normal one-shot PTO behavior resumes. Discarded/keyless spaces are excluded and locked ledgers still refuse polling. Negative timestamps are refused.

The physical Pi fixture adds 104 isolated scheduler assertions with synthetic timestamps and separate storage: stale scans in all three spaces, earliest-deadline selection, future/due loss priority over an artificially early PTO candidate, byte-for-byte preservation of that candidate, repeated scan requests, no premature loss marking, key/discard exclusion, idle behavior, one-shot application PTO and RTT-policy invalidation. They do not authenticate packets, own a socket or alter the live connection and are not wire-latency evidence.

Both resident488 Pi 4 peer-ID variants passed these assertions plus the separate real-clock two-drop exchange, locked-poll checks, independent peer/RTT/deadline/loss checks and safe close; captures369/370 were viewed and retained. Core/font/Vulkan health and watchdog-off passed. BCM2837 compiled, not executed. No resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-priority488/`. Current returns are proven by record.json, not older LASTRUN text in launch screenshots. Protocol priority follows RFC9002 sections6.1.2/6.2.1; implementation is independent.

Remaining work includes live dispatch of loss-scan requests in general traffic, client no-flight/address-validation policy, handshake RTT, reliable data ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining off-link IPv6/TLS/device blocking. This polling policy does not complete the connection controller or networking.
