### Standalone application probe output (2026-10-31)

The shared control sender now accepts PING without pending ACK demand. It still
includes an ACK when one is pending; an empty request (no ACK and no PING) is
refused before packet-number reservation. Clock and exponent admission is checked
before reservation even for PING-only output. The connection records controlHasAck
for the admitted packet. Successful transmission consumes an ACK token only when
that packet actually carried an ACK; a standalone probe cannot consume ACK demand
that belongs to another packet. Output ownership, unique PN reservation, encryption,
transport-admission history and actual-transmission completion remain separate.

The live fixture completes the initial ACK+PING exchange and consumes/prunes the
peer's acknowledgment of client PN0. With no pending ACK, it then sends fresh PN1
containing only PING. It verifies empty-request and negative-clock refusals do not
consume a number, exact probe lengths30/22 for eight-byte/zero-byte destination
IDs, absent ACK token, immutable ciphertext through actual TX and retained
in-flight accounting. The independent peer requires a decoded authenticated PN1
with exactly one PING frame, not a UDP packet count or a local return code.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-probe488/`.
Both physical Pi4 runs under resident488, captures344/345, pass36 primary and all
extended assertions; independent peer checks pass for both destination-ID lengths.
Exchange elapsed441660/440278us and maximum foreground gap1882/1909us in these
individual runs. Both returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff.
The actual Pi3 adapter compiled but was not executed. No resident update/reset;
retained monitor screenshots show return evidence, not UI/input/rendering proof.

This supplies probe output, not PTO scheduling or retransmission policy. The
fixture does not process a peer ACK of PN1 before closing and does not inject loss.
No test of a newly arriving ACK demand during probe transmission is claimed; the
completion branch explicitly leaves it untouched when controlHasAck is false.
RTT/PTO ownership, dropped-packet recovery, reliable frame retransmission, safe
release of lost metadata, congestion/flow/streams/QPACK/HTTP3 and remaining
IPv6/TLS/device work remain open. The earlier run637 watchdog failure remains
unresolved and did not recur here.
