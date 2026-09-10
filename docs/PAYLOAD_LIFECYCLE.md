# Returning payload lifecycle

A returning payload temporarily borrows the processor from Anvil and returns
with `ret`. It is built with `--entry-returns`; an ordinary boot image does not
return.

## Ownership contract

The payload may use its declared image, BSS and stack ranges, the CPU state that
the payload ABI hands over, and devices it explicitly claims. It must preserve
Anvil's image and BSS and must not reconfigure unrelated devices. A payload that
overwrites the resident monitor cannot be recovered by copying a few network
variables back, so Anvil does not pretend otherwise.

Active bus masters are a separate ownership problem. GENET receive DMA can
write memory without the CPU, so Anvil disables it before the jump. A system
barrier followed by register readback must show the MAC TX/RX and DMA enable
bits clear or the jump is refused. This is a command/readback boundary, not a
GENET hardware-idle acknowledgement: the current driver has no cited idle or
empty bit that proves there cannot be one last already-issued write. The RX
arena remains reserved throughout the handoff. Display DMA is reset after a
return before the monitor uses it again.

The CYW43455 Wi-Fi path is polled PIO, not a live DMA writer. A returning
payload that did not claim the radio leaves it alone. On the next prompt turn,
the existing bounded Wi-Fi health worker distinguishes a still-associated
radio from a detached one; a detached radio follows the existing rejoin and
DHCP INIT-REBOOT path. The monitor does not upload roughly 609 KiB of radio
firmware after every payload or erase the radio's independent identity.

## Ethernet before and after the jump

`RunAt` performs this sequence:

1. Print and flush the entering notice while the launching network interface
   still exists.
2. Record whether GENET was active and stop its MAC and DMA. Refuse the payload
   if the stop fails.
3. Arm the optional deadman, disable/flush CPU caches when needed, and call the
   payload.
4. Preserve the payload's complete 64-bit `x0`, then immediately stop GENET
   again and require the barrier/readback boundary before touching cache,
   display, DHCP or console recovery. If this fails, print through the local
   UART and reset through the existing PM watchdog; do not resume the monitor
   beside an untrusted bus master.
5. Restore monitor caches and reclaim display DMA. If GENET was active before
   the jump, perform a full bounded controller, descriptor-ring, PHY and MAC
   reinitialisation. If it was inactive, leave it inactive. A failed restart is
   allowed to return to the monitor only after the common rebuild-entry stop,
   or a later failure cleanup, proves the MAC TX/RX and both DMA enable fields
   clear. If a stop command or its readback fails, print the complete captured
   payload `x0` through the local UART and reset through firmware before
   touching DHCP, console ownership or watchdog state.
6. Advance DHCP state by the actual elapsed time, re-derive network-console
   reachability and ownership, then stop the deadman.
7. Print and flush the final return value through the restored interface when
   it remains valid, and always through the local UART.

The full GENET start waits at most the driver's Ethernet link timeout (currently
five seconds). It runs inside the existing deadman return-cleanup window. A
very short deadman therefore also sets a very short bound on recovery; the
UART entering notice remains the last durable diagnostic if that watchdog
fires.

## Hardware state versus logical identity

A controller restart rebuilds hardware registers and DMA descriptors. It does
not clear software state with a different lifetime:

- wired MAC identity is revalidated;
- a static, link-local or unexpired leased primary address is retained;
- the direct-cable alias and DHCP-server listener are retained;
- unexpired DHCP-server client slots retain their absolute deadlines;
- the DHCP client retains its server, lease and renewal deadlines;
- the Wi-Fi row, association flags and listeners are not rewritten;
- wired ARP entries are flushed because they belong to the previous MAC-ring
  incarnation; other interfaces' neighbour entries are left alone.

After a return, one ordinary DHCP worker tick accounts for the time during
which the prompt was not running. A still-valid lease stays bound. Crossing T1
or T2 schedules the normal renewal or rebind. An expired lease is removed
before final network output, so Anvil never sends the return response from an
address it no longer owns. Static/link-local and direct-server state do not
become leases merely because hardware restarted.

Every rebuild which is not the genuinely-already-active shortcut first issues
the checked stop and readback before Probe, MAC or RX-region configuration.
`GenetStop` uses the fixed BCM2711 register block and does not depend on a
successful Probe. This makes an early configuration refusal and a later start
refusal share one safe down-state boundary instead of trusting an old software
flag.

If GENET reinitialisation fails *after a checked down boundary*, the controller
and `gEthUp` remain down, the logical record is retained for an explicit later
`net up`, and the return value is still reported locally. The network console
forgets a peer whose interface is no longer usable; it does not claim a response
was sent through a stopped link. If checked cleanup fails, no stopped-link claim
is made: the readback boundary is unsafe, so the full return value is printed
locally and the existing firmware-reset path is taken.

The raw Pi bring-up result is deliberately a four-result contract: `-1` means
the common stop or a later cleanup could not establish a safe down state, `0`
means failed after a checked down boundary, `1` means freshly started and `2`
means already active. Ordinary monitor callers go through one wrapper that
turns `-1` into a drained local diagnostic and firmware reset. The returning
payload owner consumes the same negative result itself so it can preserve and
print all sixteen hexadecimal digits of payload `x0` before resetting.

## Desk gate and remaining proof

Run the focused gate with the same compiler used for the monitor:

```text
python tools/payload_lifecycle_check.py --pmfc <path-to-pmfc>
```

It compiles the real Pi 4 monitor with `-S`, checks the emitted A64 call order,
refuses logical reset calls in the hardware-start procedure, and exercises
source/model/emission assertions covering inactive, active and inconsistent
controller flags; common rebuild-entry cleanup before early configuration;
command and readback cleanup refusal after both failed start and network-MAC
publication; four-result handling at every caller; static, alias,
direct-server and leased identity; elapsed lease expiry; bounded restart
failure; Wi-Fi isolation; console flush/rearm order; the deadman window; and
preservation of the payload return value. Mutation controls restore the old
unchecked cleanup and nonzero-is-success branches and require the gate to fail.

That gate cannot prove MMIO, PHY negotiation, DMA idle, UDP delivery or a
watchdog on real silicon.

Two companion gates execute decoded instructions from the real monitor rather
than relying on the separate lifecycle state model:

```text
python tools/payload_return_emitted_check.py --pmfc <path-to-pmfc>
python tools/eth_hwup_emitted_check.py --pmfc <path-to-pmfc>
```

The return gate executes `RunAt`, `CallAddr` and the Ethernet lifecycle through
entry, return, rebuild-entry and failed-restart cleanup. It checks complete
payload arguments and `x0`, restored monitor SP, exact MAC pointers/bytes and
RX-region arguments, driver/software state, and refusal before ordinary service
recovery. The bring-up gate separately executes raw and local-wrapper entries,
including genuine already-up, stale-active, pre-start refusal and unsafe cleanup.
Both require exact image and symbol SHA-256 values in existing-artifact mode,
guard their memory models, and reject targeted decoded instruction mutations.

GENET operations, printing, firmware reset and network-service effects are
explicit modeled seams. These gates do not prove physical DMA idle, PHY
negotiation, actual DHCP expiry, radio delivery or a working hardware watchdog.

The smallest attended board proof is:

1. record `net` (including its DHCP state), `wifi`, and GENET counters;
2. run a tiny returning payload over serial with Ethernet initially down and
   confirm it remains down;
3. bring Ethernet up with a static/direct-cable identity, launch the same
   payload through the wired console, and require both the entering and final
   `x0` lines at the host;
4. repeat with a live wired DHCP lease, once well before expiry and once with a
   deliberately short test lease that expires during a bounded payload;
5. force one bounded GENET-start refusal and require a local return report,
   inactive hardware state, retained logical row, and no false network reply;
6. repeat with Wi-Fi associated and then intentionally detached, confirming
   that Ethernet recovery never rewrites the Wi-Fi row and the existing health
   worker alone performs any rejoin.

All board steps require a fresh memory map, exclusive board ownership, and the
existing deadman policy. Deliberate failure and expiry cases need an attended
recovery path; they must not be inferred from the normal returning case.

### Build 24 normal-return result

Two small generated resident-model payloads, FP32 and INT8, were independently
length/SHA-verified and run with a 15-second deadman. Each bound once, checked
three distinct inputs, executed ten timed requests, checked final output and
returned x0=0 through the launching Ethernet console. Hardware caches were
restored, both interface identities and the existing direct-link client lease
survived, and a later Wi-Fi time command answered. Continuous uptime confirmed
there was no intervening reset. This proves the ordinary active-to-active
return on that board; it does not prove the untested failure/expiry cases or
full-model performance.
