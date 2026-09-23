# Raspberry Pi 3 GPU support

The current Pi 3 GPU code is a small V3D identity/domain probe and a reusable VC4 render-list builder/executor for an offscreen RGBA8888 clear. It is not a Vulkan implementation, compositor, or display-scanout renderer. The clear path submits a 39-byte CT1 render control list to a private 64×64 target and waits for CT1 completion. The returning proof payload invalidates the target and validates every pixel and surrounding guard region; those checks are proof-payload logic, not part of the reusable `Pi3Vc4RunClear` routine. Neither path writes the scanout framebuffer.

The V3D probe validates the firmware DTB's V3D node and bus mapping, checks the firmware power-domain state, verifies the supported EL3/MMU context, and reads the hardware IDENT registers. The render path refuses unsupported identity or memory extents, requires the caller to own the verified watchdog, and uses cache-line-aligned ownership ranges. If reset cannot prove quiescence, it parks with the watchdog armed until reset rather than returning while the GPU may still own memory. It captures controller status for diagnosis; the binner's startup OUTOMEM interrupt is not treated as a CT1 error when no binner job is active.

## Hardware proof

On Raspberry Pi 3 Model B, Build35-bound returning payload `vc4_clear_payload.img` (36,600 bytes, CRC32 `6D076882`, SHA-256 `2923dbf3a3790bd6d1347cfc79639634e80db8dad482c4ae4e59233bc3264ba1`) returned cleanly under the verified 15-second watchdog. The production V3D probe succeeded; the power domain changed from off to on and IDENT0 was `0x02443356`. The CT1 clear completed in 6 μs, all 4,096 pixels matched `0xFF20C080`, all target, RCL, and guard checks passed, and the command returned to the prompt. The pre-submit interrupt value was `0x4` (startup binner OUTOMEM); PCS was `0x100` before and after, showing that this status was independent of the completed CT1 job.

Evidence is `_work/pi3-build35-vc4-clear-diag2/live-clear-v2-run.jsonl`, SHA-256 `0ed675dcf55caf2ae92e80b5eeee3331b16f52e303f309eb85fae65862e5f3c3`. This is a bounded offscreen proof, not a throughput or display-performance benchmark. The 6 μs figure is the measured CT1 job interval, not total probe/setup time.

## Reference basis

The implementation follows Raspberry Pi Linux downstream `rpi-6.12.y` commit `9c40c75f681b0b8882db9b624dfec8f81ff492f2`, especially `drivers/gpu/drm/vc4/vc4_gem.c` for submission/cache handling, `drivers/gpu/drm/vc4/vc4_irq.c` for interrupt meanings, `drivers/gpu/drm/vc4/vc4_render_cl.c` for the clear RCL, and `drivers/pmdomain/bcm/raspberrypi-power.c` for firmware power-domain control. Register and packet definitions are in the matching V3D/VC4 headers in that tree. This reference supports the current clear-only path; triangle rendering, shader/QPU submission, presentation, and Vulkan remain unimplemented.
