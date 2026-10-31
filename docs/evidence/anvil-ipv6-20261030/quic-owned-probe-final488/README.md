# Owned handshake probe proof


### Shared owned handshake probe preparation (2026-10-31)

`QuicHandshakeSentProbeCookie` checks that a selected retained packet is committed, ack-eliciting and not acknowledged before returning its metadata cookie. `QuicConnectionProbeBegin(c,level,number)` validates owned Initial/Handshake metadata and the retained CRYPTO range, then locks that history. `ProbeStep` requeues at most256 bytes per call, preserving acknowledged byte states and packet accounting; completion releases the lock and returns ready for the normal sender. Repeated completed steps are inert. No packet is marked lost and no I/O is hidden. The caller still selects the packet after a PTO and must handle ranges that no longer yield sendable bytes or need a PING fallback.

Active probe preparation excludes new loss scans, control output, both-space send admission, receive admission and TLS feeding; the history lock also excludes ACK processing and polling. CloseStep releases an owned probe lock before discarding history, after the existing foreign-worker exclusion. A retry failure closes the connection; partial work is not rolled back.

Both physical Pi cases recovered the deliberately dropped Initial through this shared API: independent decryption found identical payload in fresh PN1, and the receiver authenticated PN1 without seeing PN0, then completed verified TLS. There are2678 isolated retry/probe assertions, including negative/ACKed packet selection, repeated admission, polling/both-space sender/receive/TLS-feed exclusion,256/256/88 preparation, unchanged in-flight/loss flags, retained ready ranges and closing after the first step in both handshake spaces. Synthetic close tests inspect the first cleanup stage; ordinary live close still verifies complete cleanup. The subsequent two-dropped-application-probe exchange and independent RTT/deadline checks also passed.

Captures385/386 were viewed and retained; record.json proves current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-owned-probe-final488/`.

Automatic probe packet selection, no-flight/address-validation recovery, PING fallback, broader handshake loss, reliable application frames, reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.
