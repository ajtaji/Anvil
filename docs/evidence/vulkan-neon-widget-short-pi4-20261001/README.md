# Current-tree Neon widget short-run evidence

`report.bin` is the exact 256-byte returning diagnostic report. SHA-256: `8E8F6B31859BB11CD1B915C7839C29FB4237E926A87527B334541879FF3183C2`.

The 2026-10-01 short mode ran one current-tree production Neon widget frame on Pi 4. It verified 109 quads, 47 draws, 654 vertices, 35 box calls, 12 text calls, 74 glyph quads, four expected scissor calls, one display-DMA operation, zero DMA fallback/refusal, zero pending presentation/backend error, and 12 pixel probes. The scene defines five scissor states; this diagnostic records four expected set/clear API calls and does not independently count distinct states. Report slot 62 is zero, indicating that capacity stress was skipped. Paired scene checks and the three-second display hold were also skipped; no screenshot was produced.

The signed PMF was 1,408,064 bytes with SHA-256 `419DC48FA8688894BA49C425BF536C8ABFC2B419CA176DD2194DE32FC5E918DE`. Build 223 had CRC `5BC668D0`; the payload returned `x0=0x9C6F38` in 2.4 seconds under a 15-second deadman. No flash or reset occurred.

The historical 2026-09-26 all-15-scene proof at commit `a6b9a93` includes the prior widget frame and paired fan/line checks, with capture 27. It covers that historical source, not the current-tree paired-scene path. See `docs/evidence/vulkan-paired-all15-20260926/manifest.json`.
