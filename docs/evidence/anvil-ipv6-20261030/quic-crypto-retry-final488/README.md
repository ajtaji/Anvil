# Bounded CRYPTO retry proof


### Bounded retry of lost handshake CRYPTO (2026-10-31)

Owned loss processing now resolves Initial/Handshake loss events against retained packet metadata and requeues their CRYPTO ranges through QuicCryptoTxRetry. It marks at most256 bytes per subsequent LossStep, returning pending until the range is processed, then exposes the original loss event. Acknowledged/reclaimed bytes remain retired; payload bytes remain intact. Application-space events retain their external frame-owner contract. Bad metadata or byte-store failure closes the connection. The active loss scan owns the ledger throughout; SendBegin refuses it before changing sender state. A new scan cannot replace an unfinished retry. After cancellation of a partial retry, close rather than attempting another scan; no rollback is promised.

The physical fixture adds 2468 isolated assertions across Initial and Handshake contexts. Each sends a600-byte retained range, acknowledges an interior100-byte range, generates a synthetic loss event, checks256/256/88 progress, sender/new-scan exclusion, intact payload bytes and every byte's retry/acknowledged state, two remaining ready ranges, one event and completed scan behavior. These are synthetic ledger tests, not dropped-handshake wire retransmission evidence.

Both Pi 4 live cases also passed the existing separate two-dropped-application-probe exchange, handshake/application RTT oracle, 104 scheduler assertions, live loss dispatch and safe cleanup. Captures377/378 were viewed and retained; record.json proves the current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only. No resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-crypto-retry-final488/`.

Fresh packet creation remains the sender's responsibility. Live handshake loss/retransmission proof, lost-prefix reclamation, application reliable frame ownership, no-flight/address-validation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.
