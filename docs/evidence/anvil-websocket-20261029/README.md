# WebSocket qualification on Anvil

Physical Pi4 tests used resident419 and returned to healthy network, cores, fonts
and Vulkan state with the watchdog off. The fixtures cover29 receive-frame cases,
21 upgrade-handshake cases and8 client lifecycle cases. HTTP response and client
regressions also passed. Controlled tests use transport/RNG doubles; the real
TLS/SHA1 and transport owners were used for the live WSS echo.

The live proof connected to wss://httpbingo.org/websocket/echo with certificate
verification, echoed exactly `Anvil websocket`, and completed a graceful close
in895ms. Its finite random pool was generated fresh by the host OS CSPRNG for
that build. It must not be reused as a production RNG or replayed for fresh
connections; the reusable client requires a cryptographic RNG callback.
Its551us maximum Step excludes separate network servicing and does not remove
the approximately347ms TLS handshake arithmetic block.

Two failed harness runs remain in the private qualification journal: the first
handshake loop confused consumed bytes with parser completion, and the first
live test set the server fragment limit below its outgoing message size. Neither
is counted as a pass. The corrected proofs are preserved here byte for byte.
The compiled420 monitor is included;419 remains installed. New WebSocket owners
run through the existing service ABI without requiring a boot update.

Gzip members contain exact source, report or image bytes. Manifest hashes refer
to decompressed bytes. No emulator was used. Other target builds passed, but
only the Pi4 has this physical qualification.
