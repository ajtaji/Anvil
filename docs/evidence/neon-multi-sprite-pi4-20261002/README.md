# Multiple Neon sprites through Vulkan on Pi 4

On 2026-10-02, a returning RAM payload on Raspberry Pi 4 Anvil build 242
registered a legacy RGBA sprite and multiple stable-ID RGBA sprites in the
shared TrueType/sprite atlas. A 478-pixel-wide entry forced the shelf to wrap;
the payload verified the atlas rows before rendering. Four Vulkan draws emitted
24 vertices. Eight exact BGRA pixel probes matched the expected cleared,
cropped, scaled and tinted sprite pixels. The report recorded zero native
faults. A deliberately oversized two-image layout was refused before Vulkan
command or atlas allocation.

The 1,302,452-byte `.pmf` container had SHA-256
`cb60dc06a6d77fc7c44be2ad444f776605c199cba5045ec6a7d709c238f8f010`.
The board verified the transfer digest, ran it from `$700000`, and returned
report pointer `$0093C740` in 4.0 seconds under a 15-second deadman. Anvil
then answered at a real `pmf>` prompt over Wi-Fi with build 242, and the
deadman was explicitly turned off. No monitor image, storage or boot medium
was written. The proof used a 64×64 offscreen attachment, so pixels were read
back from that attachment rather than captured from the physical display.

Stable sprite IDs are 1–16. Source memory must remain valid until replaced or
cleared, and registration is allowed only while the adapter is destroyed.
Atlas placement is checked before allocation. The processor packs and uploads
the atlas and prepares vertices; V3D performs sampling, blending and drawing
through the shared Vulkan command path. This is a bounded Pi 4 proof, not a
complete desktop Neon renderer or another board's backend.

The saved [report.bin](report.bin) is checked independently with:

```text
python tools/vulkan_neon_multi_sprite_proof_check.py docs/evidence/neon-multi-sprite-pi4-20261002/report.bin
```

The checker also rejected a deliberately changed pixel. The existing
sprite-transform diagnostic was recompiled against this atlas change and
rerun on the Pi 4; its [report](transform-regression-report.bin) passed the
three-draw rotation/camera pixel oracle. The complete Pi 4 monitor also compiled, but resident build 242 was
not replaced. Source, report and payload hashes are in
[manifest.json](manifest.json).
