### Reclaiming acknowledged sent history (2026-10-31)

The shared sent ledger now uses ring storage while keeping absolute packet
numbers. `first` is the exclusive upper bound of a proven acknowledged prefix;
`issued` remains the next absolute number. Reservation uses issued modulo
capacity and refuses when the unpruned window is full or QUIC numbering is
exhausted. Reclamation never resets numbers, delivery totals or key epochs.

`QuicHandshakeSentPrune(s,budget)` reclaims at most1..64 contiguous sent-and-ACKed
slots, zeroing each slot. It stops at the first unacknowledged, lost-only or
reserved-unsent packet and refuses during an active ACK job. Callers must consume
all delivery events before reclamation. Already-pruned numbers are known to have
been sent and acknowledged: duplicate ACK ranges below first are validated for
syntax but skipped without visiting every old number or touching reused slots.
Commit refuses an old number; Lost on a proven acknowledged old number returns0.
Unsent gaps are never silently forgotten. Retained/new ranges still undergo the
entire ACK validation pass before any event is applied.

Application sender capacity admission now counts the unpruned window, not all
packets ever issued. The handshake sender and ACK handler also use ring indexing
for their separate CRYPTO metadata slots and check absolute-number bounds before
use. The live application dispatcher explicitly prunes after consuming the peer's
delivery event and completing its ACK job. Pruning is an explicit caller action;
it is not an automatic loss policy or permission to discard undelivered metadata.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-sent-prune488/`.
Physical Pi4 capture340 passes1241 independent ledger assertions: existing
Initial/Handshake behavior, level4, full histories, retained slot/guard/event
hashes, repeated four-slot wraparound with monotonically increasing numbers,
partial-budget pruning, old ACKs crossing reclaimed/live ranges, prefix blocked
by an unacknowledged or unsent number, unsent ACK refusal, busy pruning and
invalid budgets. Acknowledged counters and in-flight bytes remain consistent.

Final live captures341/342 under resident488 pass36 primary and all extended
assertions with eight-byte/zero-byte peer IDs. The authenticated peer ACK delivers
client PN0, the fixture reclaims exactly one slot, and first/issued both remain1.
Independent qlogs identify the matching server ACK packets (PN5/PN4). Exchange
elapsed1441690/436622us; maximum foreground gap1881/1917us, individual observations.
Both return x0=0 with healthy cores/fonts/Vulkan and watchdogoff. The real Pi3
adapter compiled, not executed. No resident image change or reset occurred.
Screenshots are retained return evidence, not UI/input/rendering claims.

The application owner still has128 physical slots. A blocking unacknowledged,
lost-only or unsent prefix can still exhaust that window; loss/retransmission and
safe retirement of such metadata remain open. This removes the unconditional
lifetime limit for acknowledged traffic, not all storage/backpressure limits.
Handshake metadata wrap indexing was reviewed and compiled in the live path;
a whole handshake exceeding128 packets was not exercised. Reliable retirement
frames, loss timers, RTT/congestion/flow, streams/QPACK/HTTP3 and remaining
IPv6/TLS/device work remain open. The previous run637 watchdog failure remains
unexplained and did not recur in these tests.
