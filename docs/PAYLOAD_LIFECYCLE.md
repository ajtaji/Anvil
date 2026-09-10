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
   reinitialisation. If it was inactive, leave it inactive.
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

If GENET reinitialisation fails, the controller and `gEthUp` remain down, the
logical record is retained for an explicit later `net up`, and the return value
is still reported locally. The network console forgets a peer whose interface
is no longer usable; it does not claim a response was sent through a stopped
link.

## Desk gate and remaining proof

Run the focused gate with the same compiler used for the monitor:

```text
python tools/payload_lifecycle_check.py --pmfc <path-to-pmfc>
```

It compiles the real Pi 4 monitor with `-S`, checks the emitted A64 call order,
refuses logical reset calls in the hardware-start procedure, and exercises 125
source/model/emission assertions covering inactive, active and inconsistent
controller flags; DMA-stop refusal; static, alias, direct-server and leased
identity; elapsed lease expiry; bounded restart failure; Wi-Fi isolation;
console flush/rearm order; the deadman window; and preservation of the payload
return value.

That gate cannot prove MMIO, PHY negotiation, DMA idle, UDP delivery or a
watchdog on real silicon. The smallest attended board proof is:

1. record `net`, `net dhcp`, `wifi`, and GENET counters;
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

All board steps require a fresh memory map, an attended lease, and the existing
deadman policy. No hardware result is claimed by this document.
