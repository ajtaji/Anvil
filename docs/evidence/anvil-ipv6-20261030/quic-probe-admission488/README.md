# Cross-space probe admission proof


### Cross-space handshake probe admission (2026-10-31)

ProbeBegin now refuses admission with SENT_BUSY whenever any Initial, Handshake or application packet ledger is owned. Previously it checked the selected history but could admit against another space's active raw recovery job. Ordinary polling already excluded this order, but direct callers need the same protection. The check precedes probe mutation and leaves existing owners intact. This does not establish arbitrary interleaving safety for every other connection operation.

The isolated tests acquire real loss jobs in each of the three spaces before requesting an Initial or Handshake probe, verify refusal, unchanged probe phase, original lock owner and flight accounting, then cancel the jobs normally. Both success and partial-close scenarios run these cases: 2758 retry/probe assertions, plus the existing 104 scheduler assertions. Both physical cases retain deliberately dropped Initial PN0 recovery through fresh PN1 with identical plaintext hash, verified TLS and two dropped application probes. Independent RTT/deadline checks and core/font/Vulkan/watchdog-off health checks pass. Captures387/388 are viewed; current return is proved by record.json. BCM2837 compile only; no resident change or reset.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-probe-admission488/`.

Automatic packet selection, no-flight/address-validation recovery, fallback probes, broader handshake loss, reliable application frames, reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open. Audit other operations' reverse-order cross-space admission before a general dispatcher interleaves them.
