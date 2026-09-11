# A transfer needs the server, and leaves by the interface that can reach it

This describes the contract `get` and `put` are built on, and the two status
sentences that are derived from interface state rather than from the wired
port's compatibility globals. Both changes are source and emitted-code
proven only; the silicon ladder at the end has not been run.

## What a transfer requires

One setting:

```text
net server <a.b.c.d>
```

That is the only fact about a transfer that the board cannot work out for
itself. Everything else is already per-interface state:

| question | answered by |
| --- | --- |
| what is this board's address on that segment | `NetSrcFor(kind, server)` |
| which interface can reach the server | `NetIfForDest(server)` |
| what is the next hop | `NetNextHop(kind, server)` |
| what does the reply arrive on | whichever interface it arrives on |

`net.address`, `net.netmask` and `net.gateway` are **not** removed and are
not deprecated. They are the saved-address source — one of the three ways an
interface comes to hold an address, beside a DHCP lease and an RFC 3927
address the board probes for itself — and they are applied at boot and by
`NetStaticApply` through the same `NetAddressBound` tail a lease takes. They
simply stopped being a precondition for a transfer, because they never
described one.

## What that replaced, and what it cost

`get` and `put` went through `EthConfig()`, which demanded all four keys and
then wrote the first three into the **wired** interface's address row with a
bare `NetSetIPv4`.

Both halves were wrong on a board that owns an address row per interface. On
a bare cable this board comes up holding a probed and defended link-local
address, the served direct-cable alias beside it, and a lease on the radio —
three usable addresses, none of them in the settings store, all of them
answering the console. Refusing a transfer for want of `net.address` on that
board refuses for want of a fact the board is standing on.

So the addresses got typed, and that is the damage. On 2026-09-10, build 41,
four temporary `net.*` keys had to be typed to move one file, and the bare
`NetSetIPv4` then replaced a probed link-local address with an unprobed typed
one — with no `NetAddressBound` tail, so no provenance in `netif.pbi`, no
console re-derivation and no record that the address had changed. The four
keys then had to be removed again by hand.

## The shape now

`EthStart()` in `Anvil/Core/net_cmd.pbi`:

1. reads the server through `NetXferServer()` (`Anvil/Core/netcfg.pbi`) and
   refuses, before any hardware is opened, if it is absent, unparseable or
   `0.0.0.0`;
2. calls `HwLinkOpen(1)` — the board's live link re-check and default-door
   selection, which prints its own refusal;
3. asks `NetIfForDest(server)` which interface can reach that server, and
   refuses with the board's own address list if none can;
4. publishes that interface as the transfer session's `gXferKind`, readable
   through `XferKind()`;
5. resolves the next hop and binds the transfer's own port **on that
   interface**.

`NetResolveHop(kind, ip)`, `NetXferSend(kind)`, `NetXferPump(kind, ms)` and
`NetXferRun(kind)` all take the interface as a parameter. Nothing in the
transfer path reads `LinkKind()` any more: the selection is the board's
default outbound door and is a different question from "which interface can
reach this server". This is the shape `tcp connect` has used since
2026-09-08.

`NetXferPump` pumps **every addressed interface** through `LinkPumpAllNet`,
for the reason the console's pump does: the answer arrives on whichever
interface it arrives on, and a wait that listened only to the selected one
would sit out its whole retransmit budget on the wrong wire. Listening is not
route selection and does not disturb the operator's preference.

`EthStart` never calls `NetSetIPv4`. A transfer does not acquire, replace or
invent an address.

## The two status sentences

**A pin is not a fact about a cable.** `LinkSelect` now takes the pin as its
first argument. It used to be applied by the caller zeroing the other
interface's facts before calling, so `net link wifi` on a board with the
cable in, negotiated and addressed reached the "Wi-Fi, and the cable is out"
arm and stamped `#LINK_WHY_WIFI_NOCBL` — and `net` answered *"there is
nothing plugged into the Ethernet socket"* about a cable that was plainly
there. Three reason codes exist for the pin now (`#LINK_WHY_PINNED`,
`#LINK_WHY_PIN_BARE`, `#LINK_WHY_PIN_DOWN`) and their sentences say nothing
about the other interface, because under a pin the other interface is exactly
what the operator asked the board to stop considering.

**The address sentence follows the interface.** `NetAddrFromText(kind)` reads
`NetIfSrc(kind)` and `NetIPv4(kind)`. It read `gEthAddrFrom` and `gEthIp` —
the wired port's two compatibility globals — and both callers print it
directly underneath `LinkSay()`, which names the *selected* interface. On a
board carrying traffic over the radio with a self-assigned address on the
cable, `net` printed the whole RFC 3927 paragraph about an address the line
above had just said was not in use.

Neither fix changes any link to make a message true. Both read the message
off the link.

## Desk evidence

```text
tools/net_xfer_route_emitted_check.py
  PASS - 48 assertions, 15,055 A64 instructions
  four-key mutation rejected at assertion 1
  selection mutation rejected at assertion 14
  bind mutation rejected at assertion 16
  resolve mutation rejected at assertion 15

tools/link_status_truth_emitted_check.py
  PASS - 44 assertions, 6,658 A64 instructions
  pin-hides-cable mutation rejected at assertion 5
  wired-globals mutation rejected at assertion 36
  wired-address mutation rejected at assertion 41
```

Each gate extracts the production procedures verbatim from the product files,
compiles them against explicit seams, and executes the emitted A64. The
mutants restore the exact historical behaviour rather than a paraphrase of
it. The link, the route, the settings store and the interface rows are
modelled seams, so neither gate is a hardware result.

## What is owed on the board

Nothing here has run on silicon. The wired ladder is:

1. `net` with no `net.*` keys set at all — confirm the three addresses the
   board holds are printed and that the address sentence names the selected
   interface's provenance.
2. `net server <laptop>` alone, then `get` and `put` — the transfer must run
   with no other key typed, and `net` afterwards must show the wired row
   still holding its probed link-local address with `#NET_ADDR_LINKLOCAL`
   provenance.
3. `net link wifi` with the cable in — `net` must not say the Ethernet socket
   is empty, and the wired row must survive.
4. A server on the radio's subnet while the cable is preferred — the transfer
   must leave by the radio and complete with equal digests.
