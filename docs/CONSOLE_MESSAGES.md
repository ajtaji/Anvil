# Background messages never touch the command line

Forum topic 791. Rule in force from the build that carries this change.

## The rule

A message for the user is never written to the command line.

- Anything that is not the direct answer to the command just typed is a
  **message**: the network console arming or moving to another address, a DHCP
  lease being renewed or dropped, the radio reporting that the link is gone or
  being recovered, a mid-session Wi-Fi rekey, the mouse search, the screen
  refusing memory that is not safe to draw into, the editor refusing a key.
- A message is never written into the console's command-line stream, whether
  or not a line is being typed. That holds on the serial line, on the network
  console and on the HDMI or DSI screen.
- The command line carries the `pmf> ` prompt, the typed input, and the output
  of the command that was run. Nothing else.

This replaces an earlier plan, recorded on the topic, to print a notice on its
own line and then redraw the prompt and the half-typed text. Nothing of that
plan was ever built.

## What was wrong

Background services printed through the ordinary console path. At the prompt
that put a sentence straight after `pmf> `, and into the middle of whatever was
being typed, on all three consoles at once. The capture that filed the topic
was on build 101: a Wi-Fi group-key rekey notice starting on the prompt row,
later rekey and recovery notices filling the command row below it.

## Where to read messages

| Console | How messages are seen |
|---|---|
| Serial line | `messages` |
| Network console | `messages` |
| Screen | The banner's status row shows the newest unread one; `messages` prints them all |

`messages` prints the log oldest first and marks it read, which clears the
banner. Its first line is for a script:

```
messages <total> kept <lines> lost <n>
```

`total` counts every message since the monitor started, `kept` the lines still
held, and `lost` the lines pushed out to make room plus any bytes that arrived
faster than they could be kept. Then each message: its number and the seconds
since start, and its lines indented beneath it. A line with nothing visible in
it is not kept; a byte that cannot be shown as itself is kept as `\xNN`. The format, as the real code
prints it under the emitted-code gate below:

```
pmf> messages
messages 3 kept 4 lost 0
Messages from background services, oldest first. These are never
printed on the command line; this is where they are read.
  #1  at 1 s
      The network console is now listening on:
          192.168.137.1 port 5555, over the wired Ethernet
  #2  at 3 s
      Wi-Fi: group key rekeyed.
  #3  at 4 s
      Wi-Fi: lease renewed, 7200 s
```

`messages` takes no arguments; anything after it is refused and nothing
changes. The log holds 64 lines of up to 159 characters each; a longer line
continues on the next.

On the banner, the newest unread message rides at the end of the status caption
(see [BANNER_STATUS_ROW.md](BANNER_STATUS_ROW.md)):

```
2026-09-16 13:40:12 CDT    112 F    2 new messages: Wi-Fi: group key rekeyed.
```

It is the last part of the caption, so a narrow surface clips it before the
clock, and it is gone within a second of `messages` being run.

## How it works

**One seam, at the byte layer every console shares.** On the Pi 4 every byte
the monitor prints goes through `UartWrite` in `RaspberryPi4/Lib/uart.pi4`,
which puts it on the PL011 and copies it to the screen mirror and to the
network console's tap. Code that runs on behalf of nobody at the keyboard
brackets itself:

```
UartMessageBegin()
... anything that prints ...
UartMessageEnd()
```

Every byte written inside the bracket goes to a ring instead, and never to the
PL011, the screen mirror or the network tap. `Anvil/Core/messages.pbi`
registers the drain that turns the ring into lines of the message log. The
bracket nests; one outermost bracket is one message. The UNO Q's console write
(`ArduinoQ/Board/qcon_q.unoq`) carries the same five procedures under the same
contract.

- **No log, no diversion.** Until a drain is registered, a bracket is counted
  and ignored and every byte goes where it always went. Diagnostics and
  examples that include the console library without the monitor are unchanged,
  and so is the boot log: the board registers the drain (`MessagesStart()`)
  immediately before its first prompt.
- **A fault is not a message.** The fatal exception report leaves every bracket
  (`UartMessageAbandon()`) before it prints, so a fault taken inside a
  background service still reaches every console. Its raw PL011 record was
  already independent of all of this.

**The brackets are around contexts, not sentences.** No individual message is
special-cased or silenced:

| Where | What runs inside the bracket |
|---|---|
| `Anvil/Core/parse.pbi`, `ReadLine` | Every service the prompt's idle loop runs: the network console's rearm and pump, link-local, the TCP/HTTP poll, mouse, touch, the soft keyboard, the screen service, the Wi-Fi link tick, DHCP, NTP, the fan and the temperature sample. A service added to that loop later is covered without being named. Also the mouse search and the screen service that run as the prompt opens, and the editor's refusal of a key it cannot honour. |
| `Anvil/Core/rxbreak.pbi`, `OutBreakByte` | The network poll a long command makes while it prints, to notice Ctrl-C. |
| `RaspberryPi4/Lib/wifi.pi4`, `WifiServiceEapolFrame` | A mid-session EAPOL-Key frame, whichever pump delivered it - the prompt's, or the one inside `ping` or a transfer. |
| `RaspberryPi4/Board/cache.pi4`, `RunAt` | The lease and console re-derivation after a payload returns, before the payload's result lines. |

The typed character's echo is outside every bracket by construction: the
editor applies input at the top of the prompt's loop, never inside the service
block.

## What did not change

- The prompt is still exactly the five bytes `pmf> ` with no newline, printed
  once per command line, and `board_run.py`, `pi4_upload.py` and
  `anvil_readback.py` match the same stream. None of them read a background
  notice; the "listening" lines they wait for are the output of the command
  they typed.
- A command's own output is not a message, including everything a command
  prints about the network while it runs (`dhcp`, `wifi join`, `net`).
- The boot log, up to the first prompt, prints on every console as before.

## Proof

`tools/console_messages_emitted_check.py`, with
`RaspberryPi4/Tests/console_messages_emitted_gate.pi4`.

- **Executed.** The real console write, line editor, message log and banner
  caption run on the A64 model. The harness maps the PL011's flag and data
  registers and records every byte the real `UartWrite` puts on the wire. One
  command line is typed twice with identical keystrokes: once alone, and once
  with background messages fired on an empty line, with text before the caret,
  with the caret in the middle, nested, and with no trailing newline. The whole
  wire stream must equal the quiet pass twice, byte for byte; the screen mirror
  and the network tap must match inside the fixture; the edited line must come
  out the same; every message must be in the log with its number; the banner
  caption must name the newest; `messages` must print the exact listing and
  clear the banner; the log must stay bounded and count what it drops; a
  program with no log must keep every byte; a fatal report must reach the wire.
- **Source.** Every call in `ReadLine`'s loop outside a bracket must be input
  handling, so an unbracketed service fails the gate; the rekey entry, the
  Ctrl-C poll, the payload-return housekeeping and the fault report are checked
  where they are; both boards' console writes must divert before any transport,
  start the log before the first prompt, dispatch `messages`, and print the
  prompt exactly once.
- **Mutants.** A message's newline let through to the wire; the diversion
  ignored; the banner kept quiet; a service moved outside the bracket; the
  rekey entry unbracketed; the fault report left inside a bracket. Each must be
  caught.

```
PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> python tools/console_messages_emitted_check.py
python tools/console_messages_emitted_check.py --source-only
```

`tools/rxbreak_emitted_check.py` additionally requires the Ctrl-C poll's pump to
run inside a bracket and the bracket to be closed.

## Proven on the Raspberry Pi 4, build 164

Build 164 carries this change unchanged. Over the network console: `messages`
answered `messages 2 kept 3 lost 0`, message #1 at 47 s being the USB mouse and
keyboard search that used to print after the first prompt; `vers` was typed and
left for 75 s and every byte the console sent in that time was exactly `vers`,
after which `ion` and Enter ran `version` normally. A screenshot of the screen
console showed every `pmf> ` line holding only the typed text and each command's
answer. Evidence: Anvil `_work/pmfline791-flash163/prove164.log`, `idle164.log`,
`screen-164.png`.

The same run found forum 892: message #2 was a line of nine spaces - what was
left once the log dropped bytes it could not show. Since then a line with no
visible character is not kept and does not start a message number, and a byte
outside printable ASCII (other than tab, carriage return and newline) is stored
as the four characters `\xNN`, so such a message says what it held. Gate case
10 and the `blank_kept` mutant cover it.

## The same day's second console defect: a silent host kept the console

Forum topic 888. The network console answers one host at a time: the first
datagram while nobody owns it makes that endpoint the owner, others get `BUSY`,
and ownership used to be released in one place only, when a command finished.
A datagram that never finished a command therefore kept the console for good.
Reproduced on build 151 from two endpoints: B `version` answered; A sent one
empty datagram at the idle prompt; B `version` was answered `BUSY`; A sent a
bare CR and got the prompt; B `version` was answered again. Host tools had been
sending an empty keepalive at the idle prompt, which is how it was hit.

`Anvil/Core/netconsole.pbi` now:

- never lets an EMPTY datagram take the console or be answered; from the owner
  it only counts as the owner still being there;
- at the prompt only (`NetConsoleCommandDone` marks it, `NetConsoleCommandBegin`
  in the board's loop ends it the moment a line is taken), treats an owner as
  lapsed when another endpoint sends and either nothing the owner sent is still
  waiting and nothing is typed on the line, or it left a half-typed line and has
  sent nothing for `#NETCON_OWNER_IDLE_MS` (60 s). A lapsed owner's half line is
  erased on every console by `TextEditDiscard` (the editor's own backspace,
  space, backspace echo) and is never run;
- never lapses an owner while its command runs, however silent.

Gate: `tools/netconsole_owner_emitted_check.py` (the real console code on byte-
valid UDP frames; a running command keeps its console across 120 s, a one-byte
owner with nothing typed lapses, a recent half line is kept and a 60 s silent one
is discarded, waiting bytes count as progress, an owner's empty keepalive counts
as presence) with four mutants: an empty datagram claiming, an owner that never
lapses, one that lapses mid-command, and a half line kept for the next host. The
discard echo is checked byte for byte on the wire by
`tools/console_messages_emitted_check.py`.
