# Automatic handshake probe selection proof


### Bounded automatic handshake probe selection (2026-10-31)

`QuicConnectionProbeBegin(c,level,-1)` now selects retained Initial/Handshake data automatically. The existing explicit packet-number mode remains available. Admission retains the connection-wide history exclusion. An active probe holds its selected ledger for the whole search and preparation; each Step inspects one packet or prepares at most256 retained bytes. The new owned candidate query skips unsent, non-eliciting and acknowledged packets. Zero metadata and zero-byte ranges are skipped; invalid owned metadata closes the connection. Previously lost but still retained data remains eligible without another loss declaration.

Automatic preparation checks its bounded range for sendable bytes after retry marking. Fully acknowledged or reclaimed ranges cause selection to continue. Step returns0 pending,1 ready for the normal sender, or2 exhausted without data. Completed outcomes repeat inertly. Exhaustion releases ownership but does not send a PING or implement no-flight/address-validation policy. These remain explicit follow-up work. Close cancels during selection or byte preparation through the existing owned cleanup path.

Both physical Pi cases use automatic selection to recover dropped Initial PN0 as fresh PN1; independent decryption verifies identical plaintext hashes and different protected datagrams, while the peer receives only PN1 and completes verified TLS. The subsequent two-dropped-application-probe exchange and independent RTT/deadline checks pass. There are8240 retry/probe assertions plus104 scheduler assertions. Eight new scenarios run in both handshake spaces: useful later packet after several ineligible packets; full CRYPTO acknowledgment/exhaustion; close during selection; close during preparation; previously lost data; reclaimed prefix; malformed metadata; and zero-byte metadata. Tests check unchanged accounting/flags on every step, ready-range states, owner exclusion and repeated results. The first-stage synthetic close checks supplement the existing complete live close proof.

Captures389/390 are viewed and retained; record.json proves current return. Core/font/Vulkan/watchdog-off checks pass. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-auto-probe488/`.

No-flight/address-validation recovery, PING fallback after exhaustion, broader handshake loss, reliable application frames, reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open. Other operations still need a reverse-order cross-space admission audit before general interleaving.
