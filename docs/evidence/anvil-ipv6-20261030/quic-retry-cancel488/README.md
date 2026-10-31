# Partial retry cancellation proof


### Partial CRYPTO retry cancellation stays closed to new output (2026-10-31)

Cancelling the raw loss job releases its ledger lock. A partially completed owned CRYPTO retry still has unprocessed bytes, so checking only that lock could admit another sender. SendBegin and RecoveryPoll now also refuse a remaining retry; application control output refuses it too. Calling LossStep after such cancellation closes the connection and returns a state error. It preserves already processed byte states and remaining work until normal close cleanup; no rollback or resumption is implied.

Two new isolated cases cancel Initial and Handshake retries after256 of600 bytes, leaving344. They check the released ledger lock, sender/poll/new-scan refusal, unchanged sender state, close transition and timer discard, plus processed/unprocessed/previously acknowledged byte states. Together with the successful retry cases,2536 assertions pass on each physical Pi run. These cases use synthetic histories, not wire handshake loss.

Both live connection-ID cases also passed independent handshake/application RTT and deadline checks, the existing two-dropped-application-probe exchange,104 scheduler assertions, live loss dispatch and safe cleanup. Captures379/380 were viewed and retained; record.json proves current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only. No resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-retry-cancel488/`.

Actual handshake loss/retransmission proof, application reliable frame ownership, no-flight/address-validation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.
