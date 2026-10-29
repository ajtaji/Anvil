# DNS reply ownership, lifetimes and TCP retry

The shared parser checks the question and its CNAME chain before returning addresses. TTLs constrain cache reuse, including one-delivery zero-TTL results and wrapping clocks. A matching truncated UDP response transitions the payload resolver to bounded TCP retry through its existing socket services.

The returning physical Pi 4 probes cover 30 reply cases, five cache boundaries, 16 TCP lifecycle cases and three invalid UDP triggers. Deterministic transport doubles exercise split prefixes and bodies, partial writes, connection failures, premature FIN, cancellation, malformed and mismatched answers, and both ordinary and wrapping deadlines. All passed on resident 416 with the candidate source in the test payloads.

A separate live TCP query to 1.1.1.1 for example.com used the resident TCP service and candidate DNS owner. Its 61-byte response contained two matching addresses and completed in 58 ms. The checker independently parsed the captured wire answer. This proves live TCP operation; the UDP truncation transition is covered by the deterministic test, not an on-wire truncation server.

Pi 3 monitor 54, Rock Pi 4C 161 and Pi 4 418 compile. Only Pi 4 was physically tested. The compressed monitor image is build 418, not a complete boot-medium bundle. Architecture and provenance checks pass, and the rebuilt guide was visually checked.

No DNSSEC, IPv6 or iterative authoritative resolution is claimed. The parser bounds an answer to 64 records and a CNAME chain to 16 hops. The TCP message buffer accommodates the 65,535-byte DNS length limit. TLS scheduling and concurrency remain separate open work.
