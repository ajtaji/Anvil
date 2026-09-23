# A board run, and the picture it comes back with

## The ruling

2026-09-11, after a payload ran four times and came back clean every time
while nothing reached the panel, and then drew a garbled frame:

> *"omg thats a garbled mess, you should build screen shots into the tests"*

So **every board run of a payload comes back with a picture**, and nobody has
to be watching the panel for that to be true.

## Why a picture cannot be taken afterwards

When a payload returns, the monitor prints. Printing goes through the console
grid onto the surface the payload left behind, so the frame being asked about
is destroyed by the monitor's own report that the payload returned - before a
prompt exists to type `p` at.

The frame therefore has to be copied out of the way **while it still exists**,
and read back from the copy. That is what the capture area is.

## The capture area

`RaspberryPi4/Board/memmap.pi4` declares it and argues its address at length.
In short:

| | |
|---|---|
| the area | `$0B000000 .. $0BBFFFFF`, 12 MiB |
| the header | `$0B000000`, one 4 KiB page |
| the pixels | `$0B001000`, 12,578,816 bytes |
| the magic | `$414E5653484F5431`, "ANVSHOT1" |

It is the first round megabyte above the V3D arena, which was the highest
thing this board had claimed, so it extends the reserved run upwards rather
than planting a region in a gap two other owners may want to grow into. It is
outside both payload windows, outside BSS, outside the framebuffer window it
copies FROM, and it is region 7 in `HwMonRegion*()` - so `w`, `fill` and
`copy` refuse it, which matters because a corrupted capture is a garbled frame
that reads as a display fault.

The size is set by the biggest screen this monitor brings up and not by the
panel: the DSI panel is 800 x 1280 x 4 = 4,096,000 bytes, this bench's HDMI
console is 1824 x 984 x 4 = 7,179,264, and a 1920 x 1200 mode would be
9,216,000. A capture larger than the window is **refused**, not truncated - a
short capture decodes as a torn picture and looks like a fault.

### The header

64-bit words in the first two cache lines of the header page. The logical pair
is what the picture is STREAMED as (the console's own coordinates, the same
numbers `p` puts in its `PIC` line); the physical trio plus the rotation are
what the bytes actually are.

| offset | word |
|---|---|
| +0 | the magic - **written last, cleared first** |
| +8 | sequence number, rises on every completed capture, never reset |
| +16 | logical width |
| +24 | logical height |
| +32 | pitch, physical bytes per row of the copy |
| +40 | rotation: 0, 90, 180 or 270 |
| +48 | tier: 0 cpu, 1 dma, 2 v3d |
| +56 | the payload's x0 (a capture on return) |
| +64 | physical raster width |
| +72 | physical raster height |
| +80 | bytes per pixel - 4, or the capture was refused |
| +88 | source: 1 HDMI, 2 DSI |
| +96 | who took it: 0 the payload asked, 1 the monitor took it on return |
| +104 | pixel bytes copied |

The magic is written last so that a reader which finds it is looking at a
complete capture, and cleared first so that an interrupted or refused one
reads as "there is no picture here" rather than as the previous run's.

### What is copied

The **presented physical frame** - what the panel is scanning. On this bench
the console is normally at 90 degrees: it draws into a 1280 x 800 buffer the
panel never scans and `ScrPresent` transposes the damaged band into the
800 x 1280 buffer the HVS reads. A capture of the drawing buffer would be a
picture of an intention, the same size and different bytes. On the V3D tier
there is no second case: the GPU presents its finished physical frame into the
same scan buffer.

## Two ways it gets filled

**The payload asks.** ABI 1.2 fills console slot 13,
`SvcScreenCapture()` - `#SVC_OK`, or `#SVC_EIO` when there is nothing behind
the console to photograph. Call it after `SvcFrameEnd`; it copies and does not
present. This is the only way a payload's own picture can be kept, because the
payload's frame does not survive its return.

**The monitor takes it on the way back.** `shot arm` arms one capture for the
next payload entry, and `boot mem <addr> shot` arms and boots in one line. The
copy is the FIRST statement after the payload returns, before a single
character is printed. The arm is one-shot: an arm that stayed set would
overwrite the picture somebody was still reading with the next run's, and the
next run is the one nobody was watching. A refused jump does not spend the arm.

## The console commands

| | |
|---|---|
| `shot` | stream the kept picture: one `SHOT` header line, then the same `PIC`/runs/`END` format `p` uses |
| `shot arm` | keep the frame the next payload leaves behind |
| `shot disarm` | put it back |
| `shot now` | keep the screen as it is at this instant |
| `shot status` | whether a capture is armed, and what is kept |
| `p` | unchanged: the LIVE screen |

The `SHOT` line is deliberately **not** part of the `PIC` stream.
`tools/pmfshot.py`'s three regular expressions are anchored whole-line and
cannot match it, so an existing host decodes the picture and ignores the line.

```
SHOT <seq8> <w8> <h8> <pitch8> <rot8> <tier8> <x0:16> <panelW8> <panelH8> <bpp2> <src2> <who2> <bytes8>
```

Upper-case hex, single spaces, fixed widths, one line - the same discipline
the `PIC` header is written under and for the same reason.

## The whole run, from the host

```
python tools/board_run.py <payload.pmf> --console-ip <board> [--out DIR]
    [--name NAME] [--board-ip A] [--console-port N] [--port N] [--addr HEX]
    [--tier dma|v3d|cpu] [--deadman S] [--trace HEX[:LEN]] [--timeout S]
    [--ask-seconds S] [--shot-timeout S] [--settle S] [--twin] [--no-shot]
```

One run is: ask the board where to stage (`map`); arm a one-shot listener and
stream the container (`net recv`); **prove it landed** by comparing the
board's own length and SHA-256 of the memory against the file on disk; pick a
renderer if asked; arm the deadman if asked; note the capture sequence number
(`shot status`); note the run number (`last run`); `boot mem <addr> shot`;
wait for the return line and its x0 - and if it does not come, ask the board
what happened (`last run`); read the payload's trace if asked (`readback`);
read the picture (`shot`).

It writes `<name>.png`, `<name>.json` (x0, timings, the header, the digest of
the decoded pixels, the transfer verdict) and `<name>.txt` (the whole console
transcript) into the output directory, and exits **non-zero** if x0 is not
zero or if no picture came back.

`--twin` is for a payload that never returns - a monitor twin. Nothing special
happens: the same run, without waiting for a return line, and the picture is
whatever the payload kept for itself through the ABI slot.

## Never wrap it in an outer `timeout`, and never pipe it through `tail`

Its own `--timeout` is the bound on the payload and nothing else needs to
impose one. A board that refuses to enter a payload now answers in the round
trip rather than running that bound out, so there is nothing an outer clock
can save you from - and there is a great deal it can cost. An outer `timeout`
kills the process where it stands: the picture, the verdict and any say in
what the board is left doing all go with it.

`tail` is worse, because it is silent by design. It prints nothing until the
tool exits, so a long run that is working looks exactly like a hang - which is
the state somebody decides to kill a run in. And the shell reports **tail's**
exit status, not the tool's, so a failed run comes back as a success.

Both of those happened on 2026-09-16:

```
timeout 600 python tools/board_run.py ... --deadman 15 ... 2>&1 | tail -30
```

twice, about ten minutes each. No output at all, an empty run directory, and
`EXIT=0`. The board had refused the payload - its load address was inside the
monitor - within milliseconds of each `boot mem`, and had been sitting at its
prompt ever since. The command to use is the plain one:

```
python tools/board_run.py <payload.pmf> --console-ip <board> --deadman 15 \
    --expect-x0 0 --out runs/<name> --name <name>
```

Send it to a file if you want to keep it (`> runs/<name>.log 2>&1`), or run it
in the background if it is long. Do not put a clock or a pager in front of it.

## What a run leaves behind, while it is still running

The record and the transcript are written after **every** step, each carrying
a `stage` field naming the step just reached:

```
map -> listener armed -> sent -> verified -> deadman -> boot ->
return -> trace -> picture
```

plus the terminal stages `listener refused`, `no transfer verdict`,
`upload did not verify`, `deadman refused`, `boot refused`, `still running`,
`deadman reset`, `restarted`, `never entered`, `processor exception` and
`outcome unknown`. A record that also carries a `finished` timestamp is one
the tool wrote the ending of; a record without one was killed where its
`stage` says it was. A payload whose return line was lost but which the board
says came back goes on through `return` with `return_line_lost: true` and an
`outcome` naming the evidence.

That is what makes a killed run legible. It used to write both files once, in
a `finally` - correct for every ending the tool controls, and worth nothing
against the one it does not, because an outer `timeout` ends the process with
no `finally` at all.

**An empty directory is now impossible.** The directory is not created until
the payload has been read and the staging address is known, so a run that
cannot start leaves nothing at all - and a directory is therefore evidence
that a board was spoken to.

## A long silence, and the host's firewall

**Measured 2026-09-16 on the bench Pi 4, build 151.** Three Kokoro runs of
158 s to 328 s of silent compute were reported "never returned"; each had
returned. The cause is on the host. The console is UDP, the PC's firewall is
stateful, and it admits the board's datagrams only while it remembers this
socket's recent traffic to the board. The cable was a Public network to the
PC, and the interpreter the runs used had an inbound allow rule for Private
networks only.

No payload is needed to show it - `sleep N` at the prompt, host silent until
the prompt is due:

| silence | interpreter | keepalive | reply |
|---|---|---|---|
| 60 s | allowed on Private only | none | arrived |
| 120 s | allowed on Private only | none | arrived |
| 150 s | allowed on Private only | none | **lost** |
| 300 s | allowed on Private only | none | **lost** |
| 300 s | allowed on Private and Public | none | arrived |
| 300 s | allowed on Private only | empty datagram every 20 s | arrived, and the sleep was not cut short |

With a payload: `RaspberryPi4/Examples/Diagnostics/pi4SilentReturn.pi4`, a
7.7 KB image that waits silently for a length read from memory. At 30 s the
line arrived. At 300 s the payload returned - its result block complete, the
capture on return taken with x0 = `12C` - and **not one datagram from any
address reached the host socket** between the boot line and the tool's next
command, which the board answered at once. Through the fixed tool, the same
300 s run returned and was seen, with 17 keepalives sent during it; and so did a
300 s run in the payload's four-core mode - its own caches on, 29,902,260
parallel jobs across the wait, none failed - with 18.

Candidates ruled out by the same evidence: the monitor forgetting its peer or
owner (the no-payload probe loses the line with the owner intact, and the
other interpreter receives it); the payload's use of the network, caches or
cores (no payload at all); the host read loop (the socket received nothing,
logged per datagram from any source).

**The fix, in `NetConsole`:** every receive calls `keepalive()`, which sends an
EMPTY datagram when nothing has gone to the board for `KEEPALIVE_SECONDS` (20,
above RFC 8085's 15 s floor and well inside the shortest loss measured). An
empty datagram is no keystrokes to the monitor.

## A missing return line is asked about, not believed

When no return line arrives inside `--timeout`, the tool does not say "never
returned". It waits up to `--ask-seconds` (default 60) for the board to answer
at all, then reads `last run`:

| what the board says | outcome | stage |
|---|---|---|
| nothing within `--ask-seconds` | **still running** - the payload holds the processor | `still running` |
| run record: returned | **returned with x0**, the line lost; trace and picture read as usual | `return` then on |
| run record: entered, board restarted, deadman armed | **reset by the deadman** | `deadman reset` |
| run record: entered, board restarted, no deadman | restarted from outside | `restarted` |
| run record: processor exception | **stopped at an exception**, with ESR, PC, FAR | `processor exception` |
| run number the same as before `boot mem` | **never entered** | `never entered` |
| no `last run` (build 151 and older), capture on return moved | returned, by the capture's x0 | `return` then on |
| no `last run`, nothing else to go on | **not known** - explicitly not "never returned" | `outcome unknown` |

Each is a full sentence in the output and the record. The monitor side is
`RaspberryPi4/Board/runrecord.pi4` in **build 152, built and not yet flashed**:
a record in the boot phase record's page (it survives a reset), written at the
jump, at the return (before the picture is taken) and in the processor
exception reporter, with the boot count at entry so a reset under a running
payload is detected. See chapter 4 of the guide for the command.

A related defect found the same day and fixed in build 152 (forum 876): the
capture sequence number is BSS and restarted at 1 on every boot while the
capture area, which is DRAM, kept the old picture's number - so the first run
after every reset was told its new picture was stale. The capture now
continues from the number the area holds.

Also found while gating this: the boot step waited for the WORDS "Its x0
register held", and a reply split between those words and the sixteen digits
stopped the wait with the value unread. It now waits for the whole return line
by expression.

## The exit codes

| | |
|---|---|
| `0` | the payload returned what was expected and its picture is on disk |
| `1` | the run started and failed. The directory says where it stopped |
| `2` | the run never started. Nothing was sent to the board, and nothing was written - not even the directory |

## A refusal is an answer, and it arrives at once

`boot mem` refuses for eight different reasons - the address lands inside the
running monitor, the last transfer did not arrive cleanly, the resident
secondary cores own the board until it restarts, the word after the address
was not `shot` - and every one of them prints its sentence and goes straight
back to the prompt. None of them is the payload's return line.

So the boot step ends on **either**: the return line, the processor-exception
marker, or the board's prompt coming back after the echo of the command. The
third is the refusal, and the tool then quotes the board:

```
!! THIS RUN FAILED:
   the board's prompt came back 0.1 s after `boot mem 500000 shot` and the
   payload's return line never did, so the board REFUSED TO ENTER THE PAYLOAD
   and nothing ran. The board said:
   !! resident secondary cores own this monitor until restart, so no
      payload was entered. Restart Anvil before run, go or boot mem.
```

**The tool keeps no list of refusal strings and is not going to.** What is
generic is the shape - the prompt came back and the line being waited for did
not - and what is specific is quoted verbatim from the board. A host tool that
matched on the monitor's wording would go silent again the first time one of
those sentences was reworded, which is the same failure in a newer shirt.

The echo is what makes the prompt usable: the reply to any command opens with
the prompt it was typed at, so a bare `pmf>` needle would decide that every
command had finished before it began. Only a prompt **after** the echoed line
belongs to the command. `net recv` is read the same way; `map` and `deadman`
are single commands that already end at their prompt, and their replies are
read for the monitor's own refusal markers.

Nothing is asked of the board after a refusal. There is no new capture to read
and no trace to dump, and streaming the previous run's picture back is exactly
how a refused run would acquire a screenshot it has no right to.

## Nobody listening on the console port

A UDP console has no connection to refuse, so the refusal arrives as an ICMP
port-unreachable that the operating system reports on the next receive - as
`WinError 10054`, "an existing connection was forcibly closed by the remote
host", which is a confusing thing to be told about a datagram and was an even
more confusing thing to be shown as a traceback. It is caught at the receive
seam, by name, and said as a sentence that carries the number:

```
!! THIS RUN NEVER STARTED, so nothing was sent to the board and nothing was
   written:
   nothing is listening on the Anvil console at 192.168.137.1:5555: this
   machine's datagram came back unreachable ([WinError 10054] ...). Either the
   board is not powered or not on this network, or the address or the port is
   not its console's ...
```

### The two checks that make a picture evidence

**The run count.** The board counts the runs it emitted and says so in `END`;
a lost datagram takes runs with it and the two numbers stop agreeing. A
decoder that ignored the count would write a plausible PNG of a picture with a
band missing.

**The sequence number.** The capture area keeps the last picture until
something overwrites it, so a run whose capture silently failed would stream
the PREVIOUS run's picture - perfectly well formed. `board_run.py` reads the
number before the run and fails a picture whose number did not move. This is
the one failure a magic number cannot catch.

## One command for a model run: `board_model_run.py`

On 2026-09-16 a payload had returned on the board's screen and its WAV still
did not exist minutes later, and the call that followed was *"write better
tools that dont waste so much time"*. A model run used to be eight steps, one tool call each -
upload the weights, upload the noise, `coretest status`, `board_run.py`,
`coretest status`, the readbacks, the conversion, the score - with a hand-off
between every two, and the weights went up again even when the same bytes
were already in memory.

```
python tools/board_model_run.py <manifest.json> --console-ip <board> --lease-file <BOARD-SHARE.md> --lane "<name>"
```

One invocation, one console connection, nothing in between:

1. **Lease.** It writes the live-holder callout and a transfer row in the
   shared-board file, re-reads it at once and again two seconds later, and
   backs off with a withdrawal row if another lease landed. It waits for a
   holder's release row first (`--lease-wait`, default an hour, ends in a
   sentence). It releases with a row in a `finally` - after a failure, an
   exception or Ctrl-C too - saying what the board was left doing.
2. **Identify.** `version`, `map` (nothing may land on the running monitor),
   `coretest status`, and `cache` - turned on for the digests if it was off,
   and put back at the end.
3. **Upload only what changed.** For each asset, `sha256sum <addr> <len>` of
   what is already in memory. Equal to the manifest's digest: `resident`, no
   upload. Otherwise `net recv`, the file over TCP, and the board's own length
   and SHA-256 of the memory it landed in.
4. **Run.** The payload to its stage address, verified; `deadman`, `last run`,
   `boot mem`. Waiting for the return line uses `board_run.py`'s own
   functions, imported - `NetConsole` with its keepalive, the echo-anchored
   reader, the refusal and exception handling, and `ask_after_silence` when the
   line does not come.
5. **The WAV first.** The moment the payload returns, the regions a WAV is made
   from are read with `readback` (crc32 per request) and checked against the
   board's `sha256sum` where the manifest asks; the WAV is written and ONE line
   printed: `WAV ready: <paths>`.
6. **The rest.** The other regions, `deadman off`, `coretest status`, the cache
   put back, the lease released - and only then the manifest's compare
   command, which never runs while the board is held.

Every run gets `<out>/<YYYYMMDD-HHMMSS>/` with each region, the WAVs,
`<name>.json` (rewritten after every step, with the timings) and `<name>.txt`
(the console transcript).

### The manifest

```json
{
  "format": "anvil-board-model-run 1",
  "name": "kitten-rosie",
  "base": "kitten-nano-0.8",
  "out": "pi4-rosie/board-model-run",
  "payload": {"file": "pi4-rosie/kitten-rosie.img.pmf",
              "sha256": "6e0c2bd0...", "stage": "0x03000000",
              "expect_x0": "0", "timeout_seconds": 900},
  "deadman_seconds": 15,
  "assets": [
    {"name": "weights", "file": "pi4/kitten.pmw",
     "address": "0x40000000", "sha256": "173baffd..."},
    {"name": "noise", "file": "pi4-rosie/kitten-rosie-noise.f32",
     "address": "0x54000000", "sha256": "9fcf6549..."}],
  "results": [
    {"name": "wave", "address": "0x57000000", "bytes": 2382400,
     "board_sha256": true},
    {"name": "trace", "address": "0x57E00000", "bytes": 256}],
  "post": {"wav": [{"from": "wave", "rate": 24000,
                    "file": "kitten-rosie.wav"}]}
}
```

Paths are relative to `base`, `base` to the manifest's folder, and `--base`
replaces it. Numbers may be strings (`"0x40000000"`, `"$40000000"`). A payload
`sha256` refuses a rebuilt payload; a region `sha256` requires a known digest;
`post.compare` is an argument list with `{python}`, `{base}`, `{out}`,
`{result.NAME}` and `{wav.NAME}` filled in. Unknown keys are refused, and so
is an asset whose file no longer has the manifest's digest - before anything
is sent. The ONNX compiler repository ships two: `examples/pi4/kitten-rosie.run.json`
and `examples/pi4/kokoro-sentence.run.json`.

### Proven on the board, 2026-09-16, build 160

The Kitten TTS Rosie manifest, twice in a row, each run its own lease:

| step | run 1 (after a reset) | run 2 |
|---|---:|---:|
| lease wait | 172.1 s (another lane was flashing) | 2.0 s (the confirming re-read) |
| identify | 2.1 s | 2.1 s |
| weights, 56,056,960 B | check 31.9 s + upload 37.6 s | check 31.9 s, **resident** |
| noise, 22,161,744 B | check 12.9 s + upload 14.9 s | check 12.9 s, **resident** |
| payload upload | 1.5 s | 1.4 s |
| run | 69.3 s | 69.3 s |
| readback, 4 regions | 6.0 s | 6.2 s |
| returned to "WAV ready" | 7.0 s | **5.1 s** |
| board time (total less lease wait) | **180.0 s** | **126.5 s** |

Run 1 printed its WAV line after every region, `deadman off` and `coretest
status`; the WAV now comes first, which is run 2's 5.1 s. The wave region took
4.97 s of it, the `readback` and the board's own `sha256sum` of 2.38 MB together.
Both waveforms were 2,382,400 bytes, sha256 `6e3b364685d1dc23...`, equal to an
earlier run of the same payload on build 151; both WAVs `9fa6b9bdfb3e602f...`, 0
samples clamped. Both runs exit 0, both ledger rows written and released.

**The check is a digest, and so is an upload's verdict.** SHA-256 on the board
ran at about 1.76 MB/s here. A resident asset costs the check; an asset that
has to go up costs the check and then the upload with its own verdict. After a
reset every asset pays both.

### Readback bursts, fixed at the reader

Found while building this, measured on build 151: `read_range` with its 1 MiB
requests lost 345,600 of 1,048,576 bytes to datagrams the host dropped, twice,
the second with no verdict at all. The board sends a request as one burst; the
host socket's default receive buffer (64 KB on Windows) overflowed whenever the
reader fell behind. `tools/anvil_readback.py` now raises the console socket's
`SO_RCVBUF` to 8 MiB once, reads back what was granted, and caps each request
at 256 KiB or half of the granted buffer's worth of reply, whichever is
smaller. Every tool that reads through it gets the fix.

## The gates

| gate | what it proves |
|---|---|
| `tools/screen_shot_emitted_check.py` | the SHIPPED capture, rotation map, tier report and the whole of `RunAt`, executed over a modelled turned panel on both tiers; the header; that the copy is of the scanned buffer and not the drawn one; that the frame is kept before the first character is printed. Plus the capture area's placement, size and protection against `memmap.pi4`'s own constants, and the slot against `abi.pbi` and the Pi 4's `HwCon` seam. Seventeen mutants must be rejected, including one that repaints first, one that restarts the sequence number after a reset, two that misplace the run record, and one that captures the logical surface on the turned panel. |
| `tools/board_model_run_check.py` | `board_model_run.py` against a scripted monitor over the real `NetConsole` and the real readback reader, with a real lease file: a stale asset digest and a misspelt key are refused before anything is sent; the lease is taken, confirmed and released on a good run, a refused boot and a silent board; a held lease is waited for and a wait past its bound is a sentence; a collision is withdrawn and retried; the first run uploads, the second finds both assets resident; the WAV is the stated conversion with clamped samples counted; the WAV line comes before the compare command. |
| `tools/anvil_readback_burst_check.py` | a whole `readback` reply sent before a byte of it is read, over real loopback sockets: 1 MiB into the default receive buffer must be lost, and 2,382,400 bytes through `read_range` as shipped must arrive complete with no retry. |
| `tools/board_run_parse_check.py` | `board_run.py`'s decoders against recorded `p` and `shot` streams, including four that must be refused. The live and kept streams must decode to the same pixels. |
| `tools/board_run_exception_check.py` | the control flow around a processor exception and a trace readback: that nothing is transmitted after a fatal marker, that an incomplete record is still terminal, and that a bad argument does no console or output work at all. |
| `tools/board_run_outcome_check.py` | the long-silence fixes, against a scripted monitor behind a scripted stateful firewall and no board: with the keepalive the return line arrives and nothing is typed at the running payload; without it the line is lost and the board is asked; still running, returned with the line lost, reset by the deadman, stopped at an exception, never entered, and an old monitor with and without a moved capture each reported as itself; no output anywhere says "never returned". Five mutants must fail it, one per decision. |
| `tools/runrecord_emitted_check.py` | the run record's own logic in `runrecord.pi4`, compiled and executed over seven scenarios, reading back every character `last run` prints; three mutants. A small fixture - the monitor's behaviour on silicon is a board run. |
| `tools/board_run_refusal_check.py` | the three defects of 2026-09-16, each against a scripted monitor and no board: a refused `boot mem` ends in the round trip rather than in `--timeout` and is reported in the board's own words; a run killed mid-step has already written a record naming that stage; a console with nobody listening is a sentence naming the address and the port, not a traceback. Plus the anchoring itself - a prompt with a command echoed after it is not a finished command. |

## Integration checkpoint, 2026-09-11

The earlier screenshot-lane note about an HTTP recursion refusal is historical:
the corrected HTTP implementation is integrated at `19b757d`. Do not omit HTTP
or substitute an old export when proving this service against the current tree.

The integrated tree subsequently built through `tools/build.py pi4`, centrally
counted as 83: 2,752,748 bytes, SHA256
`cc037774593b3c8cdaa88c0e37776121728b708b871e5381a5b7fcdd2038cde3`.
This was before the later initial-CNR fix documented in
`docs/USB_COLD_READINESS.md`; do not describe that artifact as carrying it.

Current focused checks with unified compiler SHA256
`171afd49dc7c964bdfca86de3c4e11e1d02458a16b13961d533368e47fc492e7`:

- `python tools/screen_shot_emitted_check.py --compiler <unified-IDE> --interp tools/a64/a64_interp.py`:
  PASS, 325,196 emitted instructions and all 13 mutants rejected.
- `python tools/board_run_parse_check.py`: PASS, 48 assertions over recorded
  responses. These are desk checks, not a new board capture.

`Anvil/Core/shotarm.pbi`, `tools/board_run.py`,
`tools/screen_shot_emitted_check.py` and `tools/board_run_parse_check.py` are
original project code. They contain no imported third-party implementation;
the provenance inventory deliberately omits uncited original files from its
file/upstream-pair table. The capture format and its reserved address are also
project decisions, not vendor-specified memory assignments.

The additional `memmap.pi4` vendor-spec classification covers architectural
cache maintenance used for the boot-phase record, not ownership of the chosen
screenshot region. Its primary reference is Arm's
[DC CIVAC instruction](https://developer.arm.com/documentation/ddi0601/2024-12/AArch64-Instructions/DC-CIVAC--Data-or-unified-Cache-line-Clean-and-Invalidate-by-VA-to-PoC?lang=en).
That instruction describes cleaning/invalidation to the point of coherency;
it does not guarantee DRAM preservation across an arbitrary board reset.

### Existing build 79: non-initializing diagnostics

The command paths in `f3d6ebb` accept these without hardware bring-up:

```
screen timing
touch trace
touch axes
touch bus
```

The first two print retained RAM observations. Axes reports the mapping without
I2C transactions; bare `touch bus` temporarily selects the configured bus in
software for reporting, then restores the header selection without mux/enable.
Console output itself can repaint the display, so these are not a substitute
for capturing an untouched payload frame.

Do not label bare `touch`/`touch status` read-only: they call `I2cUp` and
`HwTouchRestart`. Likewise `i2c speed` brings the controller up before reporting,
bare `screen` can turn it on, and `screen keyboard state` first attaches its
screen layer. None belongs in a non-initializing diagnostic transcript.

## Hardware evidence still required

The gates execute emitted code over a modelled panel. They cannot show that
the bytes at `#MON_FB_SCAN` are the bytes the glass is lit with, that a real
12 MiB region is free on real silicon, that a 4 MB copy fits in the window
between a payload returning and the console repainting, or that a picture
survives the trip over UDP 5555. Those are board facts and they are owed.
