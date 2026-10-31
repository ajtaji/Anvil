# Live loss dispatch proof


### Authenticated traffic drives loss dispatch (2026-10-31)

The live QUIC fixture now consumes `QuicConnectionRecoveryPoll` loss requests after the authenticated application ACK and RTT update. It verifies return `QUIC_RECOVERY_LOSS` and the selected application space, preserves in-flight accounting/backoff until the scan begins, then starts the bounded scan at the recorded real clock using the selected space. Scan events are consumed with foreground service between steps. Polling after completion must return idle. Legacy packet-threshold-only fixture mode retains its explicit scan policy.

Both physical Pi 4 connection-ID cases passed the two-dropped-datagram exchange, scheduler dispatch, independent peer/RTT/deadline checks, 104 separate synthetic scheduler assertions and safe close. The peer authenticated only the surviving probe; two missing packets produced two loss events. New report fields 5C8/5D0/5D8 record dispatch checked/start/completion; the independent oracle verifies ordering after ACK receipt. Captures371/372 were viewed and retained; record.json proves the current return, not older LASTRUN text. Core/font/Vulkan checks and watchdog-off passed. BCM2837 compiled only; no resident update/reset.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-dispatch488/`. This proves live integration in the connection fixture, not a complete web client dispatcher. Client no-flight/address-validation policy, handshake RTT, reliable frame ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining off-link IPv6/TLS/device blocking remain open.
