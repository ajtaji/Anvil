# Handshake PING fallback proof


### Initial and Handshake PING probe output (2026-10-31)

`QuicConnectionSendProbeBegin(c,level,peerBytes)` admits an explicit PING-only probe through the existing shared Initial/Handshake sender. It bypasses CRYPTO selection, optionally includes pending ACKs, and uses the existing 1200-byte long-header packet, fresh number, cooperative protection, immutable output, transport-acceptance and actual-completion paths. Acceptance records an ack-eliciting packet with zero CRYPTO bytes and rearms recovery. No retained data is marked sent by a PING. Normal SendBegin still clears the whole output job, including the new ping flag.

The caller retains timeout and address-validation policy. This operation provides the output needed when automatic selection returns exhausted; it does not itself implement the client no-flight timer. RFC9002 sections6.2.2/6.2.4 were checked for the distinction between no-data probe content and the required client timer policy. No code was copied from its pseudocode.

The physical fixture explicitly drives Initial selection to exhaustion after the CRYPTO bytes are acknowledged/reclaimed, then sends a PING. It also directly exercises a Handshake PING before Finished so the peer still has its Handshake keys. These are wire/output tests, not claims that a no-flight PTO fired. Both connection-ID cases independently verify one PING, padding, no CRYPTO and 1200 bytes at the peer in each space, plus exact 1200-byte flight increments, unchanged retained-byte boundaries, correct flags and zero copied bytes. Existing immutable-output/refusal checks apply to these sends. Both cases now obtain a real Handshake-level RTT sample and independently verify it along with the Initial/application samples and deadlines.

The dropped Initial recovery, two dropped application probes, 8240 retry/probe assertions and104 scheduler assertions still pass. Captures391/392 are viewed; current return is proved by record.json. Core/font/Vulkan/watchdog-off checks pass. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-fallback-probe488/`.

Still open: automatic client no-flight/address-validation timer and probe dispatch, broader recovery, other operations' reverse-order admission, reliable application frames/reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work.
