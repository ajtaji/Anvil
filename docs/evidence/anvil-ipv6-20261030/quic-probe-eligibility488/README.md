# Probe eligibility proof


### ACK-eliciting flight and probe eligibility (2026-10-31)

Sent history now maintains an outstanding ACK-eliciting packet count and the latest accepted ACK-eliciting send time. ACK-only and padding-only sends do not advance that time. ACK application, explicit loss and bounded loss scanning remove a packet from the count exactly once; a late ACK of a lost packet does not subtract it again. Discard clears both fields. Pruning does not erase the latest send anchor while older packets remain outstanding.

`QuicHandshakeSentProbeTime` returns that time when eligible packets remain, -1 when none remain, or an error below -1. It refuses a locked ledger rather than reading a partially applied ACK/loss transaction. It does not implement address-validation anti-deadlock probes or loss-time priority. The live PTO fixture now queries this state when arming its application probe and when checking idle disarm, replacing the generic last-send timestamp and hardcoded empty-flight argument.

Physical Pi 4 resident488 passed 4,379 CPU assertions (including 463 additional checks) and both live eight-byte/zero-byte CID cases. These retain independent peer authentication and RTT/deadline/loss oracles plus recovery-close checks. Captures357/358/359 were retained and viewed; current returns are recorded separately from the previous LASTRUN visible in the capture. Core/font/Vulkan health and watchdog-off checks passed. The real BCM2837 adapter compiled, not executed. No resident image changed. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-probe-eligibility488/`.

These are shared recovery inputs, not a complete scheduler. Automatic send/ACK/key-discard rearming, repeated-loss recovery, reliable frame retransmission, congestion/flow control and HTTP/3 request streams remain open. Remaining IPv6 and TLS/device blocking work is also unfinished. Protocol facts follow RFC9002 sections6.2/6.4; implementation and test oracle are independent.
