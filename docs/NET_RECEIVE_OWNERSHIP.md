# One consumer of an interface's receive queue

A frame comes off a receive queue exactly once. A queue with two readers
therefore has a rule about who gets a given frame whether anybody writes one
down or not — and when nobody does, the rule is "whichever reader got there
first", which means the reader that cannot deliver what it took throws it
away and nothing anywhere reports a loss.

This document is the rule, what it cost when it was missing, and where it is
enforced.

## The defect it was written for

Board run, 2026-09-11, Raspberry Pi 4, monitor build 55, a direct cable to
the bench machine. The board held two addresses on that cable — a probed
link-local `169.254.170.250/16` and the served alias `192.168.137.1/24` — and
a DHCP lease on the radio. With only `net server` set:

```text
put ktrc55.bin 57E00000 1000
The transfer goes out over the wired Ethernet from 192.168.137.1,
  which is the interface that can reach that server.
...
!! the transfer ended without completing
   tftp: gave up - every retry was spent with no answer
  frames received           5
  datagrams for us          3
  blocks                    3
  bytes                     1536
  retransmissions          11
  frames that would not send0
  the server's port         60134
```

The receiver had blocks 1 to 3 and nothing after them. A second attempt did
the same.

### The exchange the counters describe

1. The write request goes to port 69. The server answers `ACK 0` from an
   ephemeral port, 60134, and the board follows that port for every packet
   afterwards — `address requests sent 0` because the neighbour was already
   in the ARP cache, and `the server's port 60134` because the transfer
   identifier was learned correctly.
2. `ACK 0`, `ACK 1`, `ACK 2` reach the transfer's own pump: **datagrams for
   us 3**. Each one sends the next block: **blocks 3, bytes 1536**.
3. `ACK 3` reaches the board and is destroyed before the transfer sees it.
4. The board retransmits block 3 every two seconds for eight tries. The
   receiver has already stored block 3, does not answer a duplicate, and its
   own idle timer is restarted by each duplicate — so it never speaks again.
   Sixteen seconds of mutual silence, then `gave up`.
5. **frames received 5** is the transfer pump's own tally: the three
   acknowledgements plus two ARP requests answered during the stall. Frames
   the console's pump took are counted by the console's pump, not here.

One stolen acknowledgement is the whole fault. The rest is two correct
implementations waiting for each other.

### Why it was stolen

`NetXferRun` calls `OutBreak()` on every turn of its loop to ask whether a
key has been pressed. `OutBreak` reaches `NetConsolePump`, whose
`netcon_PumpOne` **drains** an interface: it takes frames off the queue,
hands each to `NetServiceInput`, and drops whatever that dispatcher does not
claim. A transfer's acknowledgement is exactly what the dispatcher does not
claim — a command is waiting for it, and `NetServiceInput` returns 0 to say
so. `LinkPumpKind` returns that 0 to its caller, which is the right answer
when the caller is the transfer's pump; `netcon_PumpOne` has no caller to
return it to, so it dropped the datagram.

The window is wide because the board holds an address on both interfaces.
`LinkPumpAllNet` polls every usable interface without waiting and then
blocks its whole 200 ms slice on ONE of them, rotating. A reply that arrives
while the slice is parked on the radio is still sitting in the wired queue
when the loop comes round to `OutBreak` — and the console's pump reads it
first.

This is the same rule that already exists one layer down. `HwLinkConsoleArmed`
in `RaspberryPi4/Board/hw_link.pi4` stands the radio's own rekey pump down
when the console consumes the radio's queue, and its header says why: "two
consumers of one firmware queue means whichever one does not deliver
keystrokes silently eats them." The rule was right; it had only been applied
to one of the two pairs of readers.

## The rule

**While a command is pumping an interface, that command is the only consumer
of that interface's receive queue.**

- `Anvil/Core/netif.pbi` holds `netif_rxOwner` — one scalar, because this
  monitor runs one command at a time — with `NetIfClaimRx(kind)`,
  `NetIfReleaseRx()` and `NetIfRxOwner()`.
- A command that is about to pump takes the claim: `EthStart()` for `get` and
  `put`, `CmdPing` and `ResolveName` for `ping` and `dns`. It is taken before
  the ARP resolve, because the resolve is the first thing that waits for a
  frame.
- `netcon_PumpOne(kind)` returns at once when `NetIfRxOwner() = kind`.
- `NetConsoleCommandDone()` releases it. That is the point every arm of every
  command already converges on — `get` alone has six ways out after it has
  taken a claim — and it runs before `ReadLine`, which is the next thing that
  pumps.

Standing down costs nothing. The command's pump hands its frames to the same
`NetServiceInput`, so ARP, ICMP, TCP, the DHCP service and the console's own
keystrokes are all still answered on that interface for the whole of the
command. `NetConsoleFlush` — the console's output — consumes no queue and is
not touched, which is why a transfer's progress and its final tally still
arrive at the host.

Only the claimed interface stands down. A transfer on the cable does not stop
the console pumping the radio.

## The second defect behind the first

`NetUdpBind` is ONE movable filter per interface and it belongs to whichever
synchronous command is waiting for a reply. The console was riding that same
filter, so from the moment `get`, `put`, `ping` or `dns` bound its own port,
the IP layer dropped port 5555 in `net_RecvUdp` — three layers below anything
that could notice. A board running a transfer could not be typed at over the
network at all: no cancellation, no second tool, nothing, until the prompt's
next `NetConsoleRearm` put the filter back. That rearm was the workaround.

A console is a permanent service on an interface, exactly like the
direct-cable DHCP server beside it, and `NetUdpListen`'s own header names "a
console plus a DHCP client" as what the listener table is for. The console's
port is now registered there, on the same two membership edges that publish
driver receive ownership, so the two cannot come to disagree about which
interfaces the console is on.

## What the bench receiver does, and why it is not the cause

`TftpBenchServer` in the private ONNX tree is strict and sequential, and two
of its properties turn one lost acknowledgement into a permanent deadlock:

- it does not answer a data block it has already stored — it skips it and
  waits again, which restarts its own two-second idle timer, so its
  re-acknowledgement never fires against a sender retransmitting every two
  seconds;
- it serves one client at a time, so a retransmitted *request* reaches a
  socket nobody is reading and is answered by nobody. That is why the first
  attempt of the night timed out at byte 0 rather than part way through: the
  acknowledgement of the request itself was the one that was stolen.

Neither is the cause. A sender that keeps its acknowledgement completes the
transfer against this receiver with no retransmission at all, which the gate
demonstrates. Both are worth knowing before reading a transcript from it.

## Desk evidence

```text
tools/net_xfer_pump_ownership_emitted_check.py
  PASS - 71 assertions
  console-drain   mutation rejected at assertion 2
  no-listener     mutation rejected at assertion 43
  no-release      mutation rejected at assertion 56
  no-retransmit   mutation rejected at assertion 33
  dup-ack-resend  mutation rejected at assertion 65

tools/net_xfer_route_emitted_check.py
  PASS - 55 assertions
  four-key  rejected at 1   selection rejected at 16
  bind      rejected at 18  resolve   rejected at 17
  no-claim  rejected at 13
```

The ownership gate compiles the real `net.pi4`, `netif.pbi`, `tftp.pi4` and
`link.pi4` with the production pumps spliced in verbatim, and drives a whole
put and a whole get over a modelled interface: replies arriving at each of the
two addresses the cable holds, an ephemeral server port, a file whose length
is an exact multiple of 512, an acknowledgement lost on the wire, duplicated
acknowledgements, and console and DHCP-service datagrams interleaved. The
`console-drain` mutant is the code that shipped in build 55, and it fails on
the first transfer.

No hardware was contacted. The wire, the peer machine and the console's
keystroke ring are modelled seams.

## What is owed on the board

1. `net server <laptop>` alone, then
   `put <name> 57E00000 1000` — expect `blocks 8`, `bytes 4096`,
   `retransmissions 0`, `duplicates ignored 0`, `gaps 0`,
   `frames that would not send 0`, and a `datagrams for us` of 9 (one per
   block plus the acknowledgement of the request).
2. `get <name> 57E10000` of the same file, then `crc32 57E10000 1000` against
   the host's — expect `blocks 9` (the last one short or empty), the same
   digest, and `retransmissions 0`.
3. During a transfer, type at the network console — the transfer must stop
   with "the transfer was stopped part way", which proves the console is
   reachable while a command owns the wire.
4. `net` afterwards — the wired row must still hold its probed link-local
   address with link-local provenance, the served alias beside it, and the
   radio's lease unchanged.
