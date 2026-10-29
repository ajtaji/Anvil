# Anvil 416 networking qualification

The installed Pi 4 image was read back in full before and after restart. Its SHA-256 is recorded in manifest.json. The previous 405 image remains a verified rollback on the board. The compressed image is a monitor image, not a complete boot-medium bundle.

Shared HTTP/1 supports streaming request bodies, bounded response framing, redirects with replay and credential policies, reusable connections, and identity/gzip/zlib-deflate decoding. The TLS owner now distinguishes authenticated closure from TCP truncation and drains queued TCP data before deciding EOF. Certificate, hostname, signature and time verification remain enabled.

The JSON records are exact checker results. CPU proofs execute on the physical Pi 4; TLS closure boundary cases use deterministic TCP/crypto doubles and are not wire-level fault injection. The two live checks use resident 416 and publicly trusted HTTPS: identity and gzip/deflate responses decoded and verified. Public echo bodies and their origin-address fields are not included.

Pi 3 monitor 53, Rock Pi 4C 160 and Pi 4 416 compiled after the owner-boundary fixes. Only Pi 4 has physical qualification here. The architecture, provenance and guide checks pass. The guide's affected pages were rendered and visually checked.

The separate historical export checker still reports existing repository allowlist, generated-artifact and private-path findings; it is not reported as passing. No allowlist, architecture baseline or provenance waiver was changed to obtain acceptance.

This is not complete web compatibility: TLS remains one global connection and its handshake arithmetic is synchronous. IPv6/IDN, HTTP/2 and HTTP/3, WebSocket upgrades, Brotli/Zstandard and managed cookies remain outstanding. No display-frame budget or browser conformance is claimed.
