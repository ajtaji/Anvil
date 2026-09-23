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

## Hardware acceptance (2026-09-10)

Pi build35 completed 2,429,080-byte RAM uploads over Ethernet and Wi-Fi. The
host observed orderly TCP closure on both (previous builds reported reset),
and board length plus SHA256 matched the source image exactly. Board transfer
times were308ms wired and1947ms wireless. These are individual transfer
measurements, not maximum throughput. Lost-ACK/cancellation/failure coverage
above is emitted-test evidence, not injected hardware failures. UNO Q build11
compiled successfully; it was not deployed or hardware-tested in this check.
