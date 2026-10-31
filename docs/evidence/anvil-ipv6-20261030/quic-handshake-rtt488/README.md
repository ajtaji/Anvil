# Handshake RTT integration proof


### Retained handshake receive timestamps and RTT (2026-10-31)

Shared receive APIs now offer `QuicConnectionReceiveBeginAt` and `QuicConnectionReceivePacketBeginAt`, taking the datagram dequeue timestamp in the same clock units as sent history/recovery. Values below -1 are refused before admission; -1 omits sampling. Existing Begin APIs remain wrappers supplying -1. Admitted receive storage retains the timestamp through cooperative decryption and ACK processing. After the ACK ledger reaches DONE, Core updates RTT before rearming PTO; `acknowledge.rttSample` records whether a sample was accepted. Initial/Handshake ACK delay is ignored. Eligibility and one-shot sampling stay in QuicRttAck. Timing errors fail the owned connection rather than silently fabricating a sample.

The live fixture captures time once per UDP dequeue and reuses it for coalesced packets. It records up to16 handshake samples separately from application samples. Both physical Pi cases passed the independent oracle replaying handshake then application RTT arithmetic and derived PTO/loss deadlines, the two-dropped-probe exchange, 104 isolated scheduler assertions, live loss dispatch and cleanup. The observed handshake sample was Initial PN0; no live Handshake-space sample is claimed. The first case's roughly one-second observation increases subsequent probe waits; it is retained rather than reset for faster tests. These are software dequeue observations, not hardware arrival timestamps.

Captures373/374 were viewed and retained; record.json proves each current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-handshake-rtt488/`. Protocol facts: RFC9002 sections5.1-5.3, https://www.rfc-editor.org/rfc/rfc9002.html#section-5.1; implementation is independent.

Client no-flight/address-validation policy, reliable frame ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP3 and off-link IPv6/TLS/device blocking remain open. This does not complete networking.
