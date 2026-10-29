# TLS verification qualification on Anvil422

The original shared P-256 verifier (baseline source at2e03d5f3) and the new
joint two-bit public-scalar verifier ran on the physical Pi4. All51 existing
verdict/diagnostic cases passed. The final proof adds52 independently checked
cases covering generator and negated-generator keys, zero hashes, zero-scalar
refusals and point-at-infinity outcomes. All103 passed. Median timing for the
original ten positive cases fell from178231.5us to94790us, approximately47%.
The general multiplication helper and private-key ladder are unchanged.

Anvil422 was installed after full backup/candidate/boot-file verification and a
90-second quiet reboot. Its complete running image SHA matched; network, cores,
fonts, Vulkan and watchdog checks passed. Live verified HTTPS gzip/deflate took
573/493ms, with longest handshake calls266907/265409us, previously about347ms.
The long gzip call occurred in the TLS state query; service-only timing would
miss it. A secure WebSocket echo and graceful close also passed using resident
entropy. TLS arithmetic remains synchronous and there is still one connection.

The shared crypto proof compiled for Pi3 and RockPi. The first cross-build
correctly refused the Pi4-only cache include; it was removed from the compile
probe. RockPi correctly refused the Pi4 load address; its stated bootstrap RAM
range was then used. No other-board execution or emulator result is claimed.

Compressed members preserve exact proof, compiled payload, identity, report,
summary and monitor bytes. Manifest hashes apply after decompression. HTTP echo
bodies are omitted from public evidence because they contain connection metadata;
the timings and exact test source are retained. All board runs returned with
healthy postchecks. This is a throughput improvement, not a frame-budget claim.
