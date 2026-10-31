# Consecutive probe loss proof


### Consecutive probe loss on the physical Pi (2026-10-31)

The live builder now supports `--repeat-probe`, which enables the PTO fixture and makes the peer discard client PN1 and PN2 ciphertext before QUIC processing. The fixture polls the owned timer twice, sends fresh PN2 and PN3 only after the respective expiries, and relies on the shared automatic rearming path. It checks that timer expiry itself neither acknowledges packets nor removes bytes in flight. After authenticated ACK3, both missing packets are reported lost exactly once through the time threshold (their packet distances are below three), then idle recovery disarms.

Independent checking uses the Pi timestamps and peer authentication log: the second deadline is based on PN2's send time and twice the first PTO; PN3's armed deadline uses four times the first PTO; ACK3 resets to the newly measured RTT-derived PTO. Both dropped ciphertext digests are retained and distinct. The peer authenticated only PN0 and PN3 among these application packets. These are real encrypted UDP drops, not injected ACKs or synthetic clock advances.

Both physical resident488 Pi 4 cases passed, with eight-byte and zero-byte peer IDs and captures362/363. Primary/extended assertions, RTT/deadline oracles, safe close, core/font/Vulkan health and watchdog-off checks passed. BCM2837 compiled with its real adapter, not executed. No resident update or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-repeat488/`. The viewed screenshots retain launch/monitor state; record.json proves the current return rather than the older LASTRUN visible in the image.

This establishes two consecutive missing-probe recovery cycles, not unlimited recovery or reliable application data retransmission. The fixture still drives a bounded packet schedule and receive loop. Time-loss timer priority, client no-flight/address-validation policy, handshake RTT integration, reliable frame ownership/requeue/reclamation, congestion/flow control, streams/QPACK/HTTP/3 and remaining IPv6/TLS/device networking are unfinished. Existing single-drop and legacy packet-threshold modes remain available.
