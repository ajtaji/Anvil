# Client no-flight timer proof


### Stable client no-flight recovery timer (2026-10-31)

`QuicConnectionRecoveryRearmAt(c,resetBackoff,now)` adds an explicit clock for entering a client no-flight wait. The legacy Rearm wrapper passes an unknown clock and preserves an existing anchor. RecoveryPoll starts a wait once when no eligible Initial/Handshake ack-eliciting packet remains and the peer has not acknowledged any Handshake packet or confirmed the handshake. It prefers available Handshake keys, otherwise Initial keys. Polling and legacy rearming do not slide the anchor. A key-space transition preserves that anchor; losing all usable keys ends the wait. All-ledger ownership refusals precede mutation.

A delivered expiry enters a consumed state so further polls cannot repeatedly increase backoff without a send. An accepted ack-eliciting packet returns recovery to normal sent-history anchors. A Handshake ACK or handshake confirmation disables this special wait. Loss requests still precede PTO decisions. Rearm validates and builds a candidate timer before publishing it and the wait fields. The connection dispatcher still must consume the event and submit the probe; this change does not add hidden I/O.

There are 57 new controlled-clock assertions executed on the physical Pi: absent keys, ACK-only padded traffic, first anchor/deadline, busy loss ownership, preference for new Handshake keys without deadline drift, complete key loss/re-entry, legacy rearming, invalid-clock refusal, exact-boundary one-shot expiry, preserved backoff, return to a real sent-history anchor, Handshake ACK validation, and close. Total retry/probe assertions are 8297, plus104 existing scheduler assertions.

Both existing live connection-ID cases still recover the dropped Initial, send independently verified Initial/Handshake PINGs, complete verified TLS, obtain both handshake-level RTT samples and survive two dropped application probes. Independent timing/packet checks and core/font/Vulkan/watchdog-off checks pass. Captures393/394 are viewed; record.json proves current return. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-client-wait488/`.

The new no-flight deadline itself is proven with controlled clocks on silicon, not yet with a peer withholding its handshake response until a real-time probe. That wire scenario and automatic event-to-probe dispatch are next. Broader recovery, reverse-order admission in other operations, reliable application frames/reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work are still open.
