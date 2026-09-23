# CYW43 bounded receive-glom integration

Status: the build-24 counter delta identified receive-glom loss, and the parser
is integrated into the production CYW43 transport. Desk gates cover the codec,
the real receive/queue path, receive termination, and function-2 FIFO access.
Silicon throughput validation remains a root-operated deployment step.

## Wire facts and limits

The reference is Linux 6.12 `brcmfmac/sdio.c`, especially
`brcmf_sdio_hdparse`, `brcmf_sdio_rxglom`, and
`brcmf_sdio_readframes`, plus `brcmfmac/bcmsdh.c`.

- SDPCM channel 3 is receive glom. Bit 7 in its raw channel byte distinguishes
  a descriptor from a superframe.
- The descriptor payload is a list of little-endian 16-bit segment lengths.
  Linux's default maximum is 32 entries (`BRCMF_DEFAULT_RXGLOM_SIZE`).
- `MAX_DATA_BUF` is 32 KiB and is documented as large enough for the biggest
  possible glom. The new parser accepts the full documented limit; it does not
  derive a smaller limit from an Ethernet MTU.
- The first segment contains the outer superframe header followed by the first
  inner SDPCM frame. Each later segment contains one inner frame. The final F2
  read is rounded to the negotiated block size.
- Inner frames may be data or event frames. Their true SDPCM lengths and data
  offsets, not descriptor padding, delimit what may be delivered.
- The outer header carries the flow-control and transmit-credit window. Linux
  does not treat inner subframe headers as additional credit updates.

## Integration contract

The main explicitly includes `RaspberryPi4/Lib/cyw43_rx_glom.pi4` immediately
before `cyw43.pi4`; libraries do not nest library includes. The parser owns one
32 KiB raw aggregate buffer and metadata for 32 frames. It performs no I/O.

1. When the ordinary first read finds a channel-3 descriptor, pass its complete
   declared frame to `Cyw43RxGlomLoadDescriptor`. Pass the negotiated F2 block
   size and the SDIO entry alignment.
2. Only a successful descriptor may authorize a superframe read. Read exactly
   `Cyw43RxGlomReadBytes()` bytes from F2, at the pointer returned by
   `Cyw43RxGlomReadPtr()`.
3. Call `Cyw43RxGlomAcceptSuperframe` after that complete read. It validates all
   inner headers in a first pass and exposes metadata only after all frames are
   valid. A malformed last frame therefore cannot cause an earlier frame from
   the aggregate to escape.
4. Apply `Cyw43RxGlomOuterFlowControl` and `Cyw43RxGlomOuterWindow` once. Walk
   indices `0 .. Cyw43RxGlomFrameCount()-1` in order. Feed event frames through
   the existing event decoder and data frames through the existing BDC/data
   decoder; do not create a second network dispatcher.
5. Retain the aggregate until every exposed frame has been consumed. Accessors
   return pointers into that buffer, so a second aggregate read must not
   overwrite it.

The delivery seam is a bounded transport queue, not a callback
from inside `Cyw43Send` or an ioctl poll. Re-entering `NetInput` while it is
building an ACK can recursively send another ACK and reuse the same transmit
scratch. The 64-slot raw-frame queue holds one retained documented 32-frame
aggregate and reserves room for one further maximum aggregate while a
synchronous ioctl advances past unrelated data to its matching reply. Per-entry
metadata prevents ordinary retained frames from repeating sequence/credit
accounting, while glom subframes advance receive sequence without overwriting
the outer superframe's accepted credit window. The top-level Wi-Fi pump drains
those entries through the existing
`HwLinkOfferRaw -> NetInput -> NetServiceInput` path.

Control, credit and event waits must never silently consume a data entry. If a
wait encounters ordinary data, it queues a complete frame for the top-level
consumer. If it encounters a valid glom, it queues the aggregate. A wait may
return a matching control/event result, but it may not advance the consumer's
data cursor. The transport refuses another F2 read before reserved capacity is
exhausted; overwriting an older frame is not an acceptable policy.

## Failure and FIFO alignment

A valid descriptor gives the exact rounded superframe read size. Even if an
inner header is malformed, the entire aggregate has already left F2, so the
next read begins on a new header.

An invalid descriptor cannot safely authorize a length guessed from a partial
list. Likewise, the current oversized ordinary-frame branch has read only 64
bytes. Both cases must terminate the current F2 receive frame before another
header read. Linux's `brcmf_sdio_rxfail` writes `SFC_RF_TERM` to function-1
`SBSDIO_FUNC1_FRAMECTRL`, then reads `RFRAMEBCHI/RFRAMEBCLO` until the residual
count becomes zero. Anvil performs one residual-count observation per service
call. Failure or deadline expiry latches the receive transport unsafe and
prohibits another F2 header read until an explicit transport reset; it never
guesses that alignment recovered and never spins an unbounded loop.

Function-2 traffic is a FIFO. Linux uses `sdio_readsb` for F2 and sets CMD53's
incrementing-address bit only for function 1 in the SG path. Anvil now passes
`incr=0` in every byte- and block-mode F2 transfer and keeps the FIFO address
fixed across chunks. This is a distinct, independently gated transport-contract
change; it is not claimed as the cause of the measured throughput fault.

## Acceptance evidence

The current executable gate constructs a three-frame aggregate containing
data/event/data, with the last meaningful byte immediately before SDIO padding.
It also covers malformed descriptors, 33 entries, 32 KiB overflow, alignment,
NEXTLEN mismatch, short and crossing subframes, invalid channels and offsets,
and a malformed final frame. Memory writes in the A64 runner are restricted to
the emitted image's BSS and stack.

The modeled F2 fixtures prove descriptor read, exact rounded superframe drain,
all frames delivered in wire order, an event retained between data frames,
outer credit applied once, invalid-superframe full drain, invalid-descriptor and
oversized-frame receive termination, unsafe-failure latching, data-before-reply
ioctl continuation, and fixed-address byte/block FIFO access. The board gate is
one exact-SHA Wi-Fi upload with before/after `wifi bus` and per-socket
`tcp status` snapshots; Ethernet coexistence must remain live throughout.
