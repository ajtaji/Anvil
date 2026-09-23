# Display connection lifecycle

`Anvil/Core/screen_connection.pbi` is the board-independent connection policy.
It does not call hardware. A board registers a polling interval, claims one
`PROBE`, `ATTACH`, `DETACH`, or `REDRAW` action from
`ScreenConnectionNextAction(nowMs)`, performs one bounded hardware step, and
returns the exact action token and result through `ScreenConnectionComplete`.
An in-flight token prevents re-entry. Probe `PENDING` preserves an asynchronous
sample; it is distinct from sampled HPD absence. Two absent samples separated
by the polling interval are required before detach.

Attach and redraw failures pass through detach before retry or quarantine, so
DMA and partial surfaces are quiesced before policy forgets them. Registration
cannot be replaced while active. Disable is accepted only from a settled state
with no claimed action, asynchronous operation, or surface owner. Presentation
drains remain inhibited outside `ATTACHED`; the backend may perform the first
DMA initialization while `REDRAWING`, but the firmware surface stays blank and
no visible output is published until that copy and unblank both succeed.

## Raspberry Pi 3 backend

The Pi 3 composition is the first backend using this lifecycle. A headless cold
boot allocates no framebuffer. Before enabling the MMU it validates and maps the
fixed renderer and firmware VC reservation as Normal Non-Cacheable. After the
MMU is live, the service samples physical HDMI HPD without blocking the prompt.
Only the first definitive cold-start HPD observation can adopt firmware boot
state. When that observation is connected, the backend reads EDID, requires the
firmware's inherited physical geometry to equal the preferred base DTD, validates
an allocation inside the reserved VC range, initializes it through DMA, powers
the display, and unblanks it. Disconnect quiesces pending presentation and DMA
before blanking and detaching. UART remains available throughout.

The shared EDID parser retains pixel clock, active size, sync starts and ends,
totals, interlace, and sync polarity. Invalid or missing EDID is not cable
absence, and no unverified mode is published. On the tested Pi 3 firmware,
selector, timing, primary-plane, and power property calls did not produce a
nonzero timing readback. A boot that first observes HDMI absence therefore
allocates nothing; a later plug remains retryable but is not published as a
working late modeset. A reconnect likewise cannot claim the stale boot geometry.

This implementation enables HDMI connection handling on Pi 3. Pi 4, UNO Q, and
ROCK Pi 4C compile with the shared policy included, but they have not registered
new hotplug backends. This change does not add Pi 3 DSI support and does not
establish boot or physical display behavior on any board.

## Validation

Run the emitted shared lifecycle, EDID, and Pi 3 framebuffer contracts with the
current PureMetalForge application:

```text
python tools/screen_connection_contract_check.py --compiler <PureMetalForge.exe>
python tools/edid_parse_check.py --compiler <PureMetalForge.exe>
python tools/pi3_framebuffer_contract_check.py --compiler <PureMetalForge.exe>
```

Compile the board compositions through the counted build wrapper:

```text
python tools/build.py pi3 --compiler <PureMetalForge.exe>
python tools/build.py pi4 --compiler <PureMetalForge.exe>
python tools/build.py unoq --compiler <PureMetalForge.exe>
python tools/build.py rockpi4c --compiler <PureMetalForge.exe>
```

These are compilation and emitted-code checks. Hardware probes verified the
cold inherited 1920x1080 allocation, DMA, power-property, and unblank contracts.
They do not prove late headless-to-HDMI mode activation, which remains
unsupported on the tested firmware, or replace a supervised cold connected boot
that confirms visible output and detach behavior.
