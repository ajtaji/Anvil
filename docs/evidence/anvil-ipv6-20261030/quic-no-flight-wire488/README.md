# Client no-flight wire proof


### Real client no-flight timeout proof and stopping point (2026-10-31)

The new `--no-flight` fixture mode makes the independent peer acknowledge the real client Initial while withholding queued CRYPTO output. Normal ACK generation, encryption and certificate verification remain active. The peer releases queued CRYPTO only from its authenticated Initial PING handler. No protected packet number is reused and no unreceived packet is acknowledged.

The Pi's dispatcher polls its actual clock, records the stable no-flight anchor/deadline, checks zero flight in all three spaces, consumes the expiry once, drives automatic data selection to exhaustion and sends the shared PING fallback. The peer then releases ServerHello and the remaining handshake, and verified TLS completes. The independent oracle recomputes the deadline from the first Initial RTT and checks that the peer logged the PING before any server CRYPTO output.

The isolated eight-byte-CID Pi4 run passed: 8297 retry/probe assertions, 104 scheduler assertions, real no-flight expiry 44 microseconds after its calculated deadline, Initial/Handshake PING content and accounting, verified TLS and independent RTT checks. Capture396 was viewed; record.json proves current return. Core/font/Vulkan/watchdog-off checks passed. Pi3 compiled only. Resident488 unchanged; no reset/update. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-no-flight-wire488/`.

An earlier combined run also passed the two application-drop scenarios, but its roughly one-second first RTT enlarged the compounded PTO waits to a 15.18-second payload. The final isolated test omits those already-proven drop scenarios and returned in about4.5 seconds of payload time (about6.3 seconds host boot observation). No RTT estimator reset or shorter invented deadline was used. The cause of the long first RTT is not established: peer logs show its ACK was generated promptly.

Stopping at the user's request. The zero-CID no-flight variant is prepared but not executed. Next work: exercise Handshake-key no-flight expiry and pending-event key changes, move fixture dispatch policy into the intended shared dispatcher, then continue broader recovery/application reliability/congestion/flow and HTTP/3. Networking remains unfinished.
