### Cooperative application ACK output (2026-10-31)

`Anvil/Core/quic_connection_control.pbi` sends an application ACK with an
optional PING using owned output buffer16 and the shared packet worker. Begin
checks the connection/dispatch state, computes ACK delay with OUR advertised
exponent and irreversibly reserves an application packet number. It writes the
ACK and short header, then starts cooperative encryption. Step returns0 while
computing,2 when immutable ciphertext is ready,3 while awaiting actual transport
completion and1 after completion. Accepted is called only after queue acceptance,
never EAGAIN. Completed(result=0) means actual transmission succeeded; only then
is the captured ACK-demand token cleared. Newer demand survives a stale token.
Failures after reservation can consume a packet number and close the owner;
there is no rollback/reuse. Raw application APIs must remain serialized against
this operation, as documented by both interfaces.

The connection owns control phase/length/PN/token. Handshake send, receive and
TLS feed, plus peer-ID mutation, refuse while control ciphertext is outstanding.
Existing CloseStep cancels the shared application operation and closes the
socket before wiping owned storage. Scheduling, congestion/recovery policy and
reliable retirement delivery are not implemented by this sender.

The live dispatcher now commits an application receipt only after all frames
have succeeded. Its current supported set is PADDING, PING, HANDSHAKE_DONE and
NEW_CONNECTION_ID; other frame kinds are refused without receipt/ACK commit.
Receipt time is captured before authentication/processing. The sender transmits
ACK+PING and leaves ACK demand pending through encryption, submission and queue
acceptance. The peer checker requires a decoded authenticated ACK covering an
actual HANDSHAKE_DONE packet, not merely a received UDP datagram.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-ack488/`.
Identical final Pi4 payload, resident488, captures335/336 against eight-byte and
zero-byte peer IDs:36 primary checks each plus all application/confirmation/CID/
control assertions. The independent peers authenticated client PN0PING and ACKs
covering exactly server PN4 and PN3 respectively; unprocessed earlier numbers
were not acknowledged. The fixture checks competing Begin/early completion,
ready/accepted/completed state transitions, immutable ciphertext, demand retained
until actual TX success and duplicate completion refusal. No forced transport
failure, EAGAIN, stale-token or ACK-only integration run is claimed here; the
underlying receipt/token serializer has its earlier independent CPU evidence.

Both runs returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff. Exchange
elapsed1416621/411300us; maximum foreground service gap1947/1882us. These are
individual fixture observations. The actual Pi3 adapter compiled, not executed.
No resident update or reset occurred. Monitor screenshots are return evidence,
not UI/input/rendering tests. The prior run637 watchdog failure remains unresolved;
it did not recur in these tests.

Reliable RETIRE_CONNECTION_ID delivery, application sent-history/recovery and
ACK scheduling, general frame/stream dispatch, preferred-address/local-ID/reset
handling, congestion/flow, QPACK/real HTTP3, key updates, Retry/migration and the
remaining IPv6/TLS/device work remain open.

The first implementation called a private helper across a module boundary. The
layering gate rejected it; the final module owns its bounds helper. Both final
Pi4 runs and the Pi3 compile were repeated on the corrected source. Pre-correction
artifacts and the failed gate are retained in the adjacent
`quic-application-ack-development488` evidence directory.
