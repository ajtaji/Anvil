# Dropped Initial probe proof


### Dropped Initial recovered by a fresh handshake probe (2026-10-31)

The live fixture's optional `--initial-probe` mode now waits for the real Initial PTO, requeues retained CRYPTO bytes in256-byte service-separated steps, and sends them with a fresh packet number. The peer drops Initial PN0 before passing it to its QUIC receiver. An independent Initial decryptor records packet/payload hashes and verifies PN1 carries the identical plaintext payload with different encrypted bytes. No private TLS key or plaintext is published.

The Pi verifies the selected Initial space, one timeout/backoff increment, unchanged in-flight accounting before retransmission, PN1 output, doubled1200-to2400 in-flight bytes, and no LOST flag on PN0. PTO requests a probe rather than declaring loss. The server authenticates PN1, completes certificate-verified TLS, and the later application exchange still passes. Its qlog must contain Initial PN1 and exclude PN0. Handshake RTT now samples PN1. The test's isolated requeue loop covers the first Initial only; a general handshake probe dispatcher/no-flight policy remains open.

Both physical Pi 4 connection-ID cases passed the independent hash/packet-number/timing checks,2536 retry/cancellation assertions,104 scheduler assertions, separate two-dropped-application-probe exchange, live loss dispatch and safe cleanup. Captures381/382 were viewed and retained; record.json proves current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only. No resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-initial-probe488/`.

General handshake/address-validation recovery, packet loss retransmission beyond this PTO probe, reliable application frames, lost-prefix reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.
