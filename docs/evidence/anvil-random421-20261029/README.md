# Resident entropy and secure WebSockets

Anvil421 was installed on the physical Pi4 after verifying the419 backup and
candidate boot image. Its running image hash matched after the full90-second
boot interval. Network, cores, fonts, Vulkan and watchdog postchecks passed.

The shared service and DRBG proof passed37 result checks plus independent
SHA-256, HMAC and HMAC-DRBG/reseed comparisons. It uses a controlled entropy
provider to prove absent/busy/invalid/not-ready/short/failing paths, output
wiping and preservation of streaming crypto state. A first physical trial
caught a16-bit read of a32-bit ABI header field in the new payload binding;
the corrected trial passed. Failed records are retained separately.

A real verified WSS echo used resident slots175/176 for the nonce and outgoing
frame masks, with no desktop random pool. It echoed the exact15-byte text and
closed cleanly in729ms. The initialized16-byte nonce request took389us;
maximum WebSocket Step was547us, excluding the separate TLS service work.
These are single samples, not latency guarantees. Certificate arithmetic is
still synchronous and the TLS provider still has one connection.

Pi3 and RockPi builds passed; only Pi4 has physical qualification here. Missing
entropy providers return ENOCAP. Gzip members preserve exact proof, result and
image bytes; manifest hashes apply to decompressed content. No emulator used.
