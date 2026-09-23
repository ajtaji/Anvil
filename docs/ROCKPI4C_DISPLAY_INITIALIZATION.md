# Original ROCK Pi 4C display initialization

This is the contract for the original RK3399 ROCK Pi 4C v1.2 Mini DisplayPort
path. It does not describe the ROCK Pi 4C+ or the Raspberry Pi 4.

## Reference and ordering

The reference is Radxa kernel commit
`86a614bc15b3b1aeb3a9a9e395aedd088c70e35e`, checked against the distributed
`4.4.154-116-rockchip-g86a614bc15b3` kernel binary. The RK3399 TRM v1.1
Part 3 supplies the VOP register definitions. Comparing one register list
does not establish that the complete initialization sequence is equivalent.

`drivers/gpu/drm/rockchip/rockchip_drm_fb.c`,
`rockchip_atomic_commit_complete`, performs modeset enables before plane
commit. `drivers/gpu/drm/drm_atomic_helper.c`,
`drm_atomic_helper_commit_modeset_enables`, enables the CRTC before its
encoder. Therefore the first display is not one undifferentiated block of
register writes:

1. Establish power, bus clocks and reset ownership. Initialize Cadence
   firmware and the board's PHY/AUX path. Discover the sink and read EDID.
2. Select an advertised mode and establish the trained link's actual rate
   and lane count. Admit the pixel-clock, dimensions, memory bounds and
   DisplayPort transfer-unit calculation before committing timing state.
3. Start the VOP timing generator with image planes disabled. Program the
   complete output, post-processing and blanking contract, and observe a
   bounded frame boundary.
4. Commit the encoder route, DisplayPort timing and valid video stream.
   `cdn_dp_encoder_enable` owns the GRF selection of little VOP.
5. Configure the complete primary-plane attributes, then enable and latch
   that plane. Do not rely on a previous bootloader's scaler, alpha, channel
   or color-conversion state.
6. Verify link alignment and recurring scanout health before publishing the
   display capability. A mailbox command being sent is not proof that the
   downstream display works.

The Cadence transfer-unit arithmetic is retained from the independently
checked emitted implementation. `RockCdnPlanVideo` now separates admission
from mailbox writes, so an unsupported mode cannot partially program a
timing transaction before returning an error.

## Failure semantics

Each phase returns failure to its caller. A failed preparation cannot enable
the encoder or primary plane; a failed plane configuration cannot continue
to plane activation. A missing live link-status response, lost alignment,
missing frame boundaries or recurring VOP underruns leaves
`rock_display_ready` clear.

The diagnostic string is `DP08 SCANOUT READY`, not `VISIBLE`. Even successful
software checks require physical confirmation of a clean, stable picture
at the selected resolution. The previous 1024×768 visual proof is not proof
of 1920×1080 operation.

## Desk verification

`tools/rockpi4c_display_lifecycle_check.py` checks source ordering and accepts
`--image <flat-image>` to execute the compiled coordinating procedure in the
repository's A64 interpreter. Subsystem calls are modeled as successful or
failed, one stage at a time. It checks that failure never publishes readiness
or reaches a later hardware stage. This is a control-flow test, not a model
of the physical clocks, FIFOs, PHY or monitor.

The VOP and clock contracts have separate checks. Arithmetic and emitted
mailbox values are also checked independently; none of these gates substitutes
for the real display test. In-house isolation diagnostics are not part of
the ordinary board composition.

## Development transport

The existing FTDI recovery and verified RAM-loading route remains unchanged.
Display development does not require switching to USB programming or changing
persistent boot storage. A new image must carry its own build number and
verified hash; physical results belong to that exact image.
