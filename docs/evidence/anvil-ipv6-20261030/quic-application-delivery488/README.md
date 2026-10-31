### Application packet delivery ledger (2026-10-31)

The shared sent ledger in `Anvil/Network/quic_handshake_sent.pbi` now accepts
application number space4 as well as Initial0/Handshake2. Its existing API names
are retained. The same full-frame validation pass precedes delivery events;
wrong-space ACKs and acknowledgments of unsent numbers are refused. Validation
and event processing remain cooperative, at most64 slots per step. This is a
bounded history, not a complete recovery policy or an unbounded connection.

`QuicConnection` owns an application history, ACK job and128 sent slots. The
control sender checks history availability before reserving a PN, keeps history
reservation aligned with `applicationState.nextNumber`, and refuses divergence.
`QuicConnectionControlAccepted(c,now)` now requires the caller's monotonic send
time: after actual queue admission, it commits the packet BEFORE peer ACKs can
be processed. Its eliciting flag controls bytes in flight. Actual transmission
completion still separately clears the outgoing ACK-demand token. Ambiguous or
failed accepted sends close ownership. CloseStep cancels an owned application
ACK job and discards this history before storage release.

The live fixture now waits for a real authenticated peer ACK after sending its
ACK+PING. It decodes ACK/ACK_ECN through the shared application frame view and
runs the shared two-pass acknowledgment job. It verifies exactly one delivery
event, the correct packet length, all of that packet's in-flight bytes removed,
and largestAcked0. The receive packet is committed only after all its supported
frames have succeeded. The current continuation also handles padding/PING,
NEW_CONNECTION_ID and HANDSHAKE_DONE; general streams remain open.

Final evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-delivery488/`.
Identical final Pi4 payload on resident488, eight-byte/zero-byte peer IDs,
captures338/339:36 primary checks plus all extended assertions. Both independent
peer qlogs show their authenticated client PN0ACK+PING and server ACK range[0,0]
in exactly the packet the Pi reported processing (server PN5/PN4). Three refusal
probes also pass per run: wrong packet-number space, an unsent PN, and cancel
after validation but before application. Both refusal/cancel cases preserve
in-flight accounting and produce no delivery event. The real acknowledgment
then succeeds. ACK processing takes3 cooperative steps for this one packet.

Both runs returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff; no
resident update or reset. Exchange elapsed1439773/434225us, max foreground gap
1911/1940us, individual fixture observations. Actual Pi3 adapter compiled only.
Retained monitor screenshots are return evidence, not UI/input/rendering proof.
The earlier run637 watchdog failure remains unresolved and did not recur here.

Limitations: this owner currently has128 lifetime application packet slots;
exhaustion refuses further reservation without reusing a PN. Pruning/storage
policy is required for long-lived web transfers. Loss scheduling, retransmitted
frames, reliable RETIRE_CONNECTION_ID delivery, RTT/congestion/flow policy,
general stream dispatch, QPACK/HTTP3, key updates, Retry/migration, additional CID
handling and remaining IPv6/TLS/device work are not completed by this change.
ACK_ECN is decoded by the common path; a separate on-wire ECN test is not claimed.
