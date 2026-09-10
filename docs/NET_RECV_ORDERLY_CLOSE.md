# `net recv` orderly close ownership

A successful upload is not complete at the TCP layer merely because the peer's
FIN and all preceding bytes have arrived. `NetRecvStep` first revokes the
listener, calls `TcpClose`, and publishes `NR_DONE` only with the connection on
the orderly close path. `NetRecvRelease` may relinquish exactly an
`NR_DONE`/`LAST_ACK` socket to ordinary `TcpTick` service. The socket remains
allocated while its FIN is acknowledged or retransmitted and is reclaimed after
the final ACK or retry exhaustion. This prevents the host from seeing an RST
after a byte- and SHA-complete upload.

All unsuccessful ownership remains abortive. Overflow, cancellation, and an
idle timeout call release without the exact success predicate and therefore
send RST for a live connection, even if that connection has independently
entered `LAST_ACK`. A peer RST has already destroyed the connection and must not
receive a responding RST. Pre-connection timeout and listener revocation have no
established peer to reset.

`tcp_multiif_emitted_check.py` executes these paths through real emitted
`NetRecvStep`, `NetRecvRelease`, TCP input/output, and wire frames on both wired
and Wi-Fi interfaces. It covers acknowledged success, lost-final-ACK retry
exhaustion, overflow from a failed `LAST_ACK`, connected cancellation and idle
timeout, peer RST with no response, and pre-connection timeout. Mutants removing
the success close or treating every `LAST_ACK` as successful must fail.
