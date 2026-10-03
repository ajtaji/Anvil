# Pi 4 indexed image transform proof — 2026-10-03

`NeonVkChromeImageSpriteDrawTransformId` uses the atlas sprite's Q8 rotation,
camera, zoom, crop and tint geometry with each separate image's descriptor and
dimensions. The original atlas transform calls still bind the atlas descriptor.
The unindexed image transform call selects image ID 1.

The returning [RAM diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonMultiImageTransformProof.pi4)
on resident build 242 drew the atlas and separate image ID 1 beside image ID 16.
ID 16 was rotated clockwise by 90 degrees, then drawn again with a one-texel
crop, a 2× camera zoom and a green-channel tint. The 192-byte
[report](report.bin) passed the independent
[oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonMultiImageTransformProof.oracle.ps1):
the four rotated quadrant probes, cropped/tinted probe and unaffected atlas,
ID 1 and background probes matched exact BGRA words. Extreme X and camera
coordinates returned argument errors before changing the four draws or 24
vertices. The diagnostic also checked oversized replacement refusal, a later
successful ID 16 replacement and repeated teardown.

The signed PMF container was 1,340,652 bytes, SHA-256
`0f8d39921a621df735df57e37dfd74a0e724a2c210970c7987123ec39184f769`.
It was linked and staged at `$00700000`, verified on the board, and returned
`x0=$00D4CC38` under a 15-second deadman. The report SHA-256 is
`9278180c3d0b1c447daee9f46950ce957b4e506a88410e965a1665a0b1bc5a5b`.
The monitor reached a real `pmf>` prompt; `last run` 16 recorded a return and
the deadman was explicitly disabled.

The existing atlas-transform [diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSpriteTransformProof.pi4)
was recompiled against the shared transform routine and rerun. Its 1,317,540-byte
PMF container SHA-256 was
`27621009ca39b73e7c9d5241831f62c9ccf9ab96bada97995a5a56d408447189`.
The [128-byte regression report](atlas-regression-report.bin), SHA-256
`6fe9d005864ce6410d74dab4cc8ba70a237d622030acd46fa3d50cce4455dc00`,
passed the existing 32-word
[checker](../../../tools/vulkan_neon_sprite_transform_proof_check.py),
including three draws, 18 vertices, exact rotated/camera pixels and hostile
coordinate refusal. `last run` 17 returned and the deadman was disabled.

Both tests ran in RAM only. No monitor, boot medium or filesystem was changed.
This proves transformed drawing with separate ID 16 and coexistence with the
atlas and ID 1 on Pi 4. It does not prove all 16 separate IDs loaded at once,
other boards or installation of the updated monitor.
