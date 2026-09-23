# The Anvil Guide

The book: how to build Anvil, put it on a Raspberry Pi 4, talk to it, write a
payload, run that payload from a host machine, use all four cores, and replace
the monitor without losing the board.

The rest of `docs/` is the engineering record, with notes that describe each
piece of work and the boundary it establishes.
Those are written for somebody who already knows the machine. **This is the
path in.** Chapter 11 is the map back out to them, by topic.

**[AnvilGuide.pdf](guide/AnvilGuide.pdf)** — the whole book as one file.

## Chapters

| | | |
|---|---|---|
| 1 | [What Anvil is](guide/01_what_anvil_is.txt) | The resident monitor, the bootloader, the service table. What runs at which exception level. What a payload is; what a module is. |
| 2 | [Building Anvil](guide/02_building_anvil.txt) | The compiler, `PMF_COMPILER`, `tools/build.py`, the build number, what lands in `build/`. |
| 3 | [Installing on a Raspberry Pi 4](guide/03_installing_on_a_pi4.txt) | The ready-made boot-volume skeleton, then the layout with its reasons: firmware files, `config.txt`, the EL3 stub, first boot, the serial console and the network console, `version`, `map`. |
| 4 | [The console](guide/04_the_console.txt) | Why nothing but a command's answer lands on the command line and where background messages go (`messages`), who the network console belongs to and when a silent host loses it, and the commands people actually use, each with what it prints (including `last run`, pending build 152, and `usb link`, the raw registers of the link the USB host sits on, and `usb timing`, where the USB stack spent its time as counted on the board's own clock rather than a host stopwatch, `usb devices`, every device as its own descriptors describe it, and `measure`, which runs a command and prints what it cost on that same clock) — and what `SETTINGS.TXT` looks like on the medium. |
| 5 | [Writing a payload](guide/05_writing_a_payload.txt) | Placement flags, the service table (ABI 1.3), the deadman, what a payload must not do, and a complete payload that builds and returns a value. |
| 6 | [Running payloads from the host](guide/06_running_from_the_host.txt) | `board_run.py`, `board_model_run.py` (a model run from a manifest: uploads only of what is not already in memory, the run, readback, the WAV), `pi4_upload.py`, uploads with hash verification, readback, screenshots, what a refusal looks like, the run record's stages and exit codes, why a run is never wrapped in an outer `timeout` or piped through `tail`, the console keepalive a long silent payload needs, and how a missing return line is asked about rather than believed. |
| 7 | [Using all four cores](guide/07_all_four_cores.txt) | The parallel service, partitions, why bit identity holds, the five-second bound, and the one-payload-per-boot limit that is still open. |
| 8 | [Updating the monitor in place](guide/08_updating_the_monitor.txt) | `anvil_update.py`, the two points after which you must not reset, recovery. |
| 9 | [Driver modules](guide/09_driver_modules.txt) | PMFMOD v1: the container, what exists, and the loader that does not. |
| 10 | [Proving things](guide/10_proving_things.txt) | The gate set, the emitted-code interpreter, how to add a check, and why a listing is not proof. |
| 11 | [Where the engineering notes are](guide/11_the_engineering_notes.txt) | `docs/`, mapped by topic — and the rule that keeps this book current. |
| 12 | [Anvil on a Raspberry Pi 3](guide/12_the_raspberry_pi_3.txt) | Direct firmware loading through a Pi 3 EL3 stub into the complete `kernel8.img`, the DTB handoff and memory placement, lazy SD startup, and direct bundle replacement. |
| 13 | [TrueType font container](guide/13_truetype_t0.txt) | T0 opens a checked sfnt font or the first face of a collection, and refuses unsafe table directories with table and offset diagnostics. |
| 14 | [TrueType font metrics](guide/14_truetype_metrics.txt) | T1 reads bounded `head`, `maxp`, `hhea`, `hmtx` and optional `OS/2` metrics from an opened font. |
| 15 | [TrueType character mapping](guide/15_truetype_unicode.txt) | T2 maps checked cmap format 4 and 12 data and strictly decodes UTF-8 into caller-owned glyph IDs. |
| 16 | [TrueType outlines](guide/16_truetype_outlines.txt) | T3 expands bounded `loca` and `glyf` simple and composite outlines into font-unit points. |
| 17 | [TrueType rasterization](guide/17_truetype_raster.txt) | T4 rasterizes expanded quadratic outlines into bounded grayscale coverage and compares emitted pixels with independent fontTools geometry. |
| 18 | [TrueType pair positioning and layout](guide/18_truetype_layout.txt) | T6 applies checked legacy kern or selected GPOS PairPos values and lays out bounded UTF-8 glyph runs. |
| 19 | [TrueType console commands and defaults](guide/19_truetype_console.txt) | Load/select TrueType faces, choose a pixel height, and save or restore a default path with bitmap fallback. |
| 20 | [TrueType fonts in the resident Vulkan console](guide/20_truetype_vulkan_runtime.txt) | Use font slots in the Vulkan console, understand cache warming and fixed-cell fitting, and distinguish emitted and returning-payload proofs from resident visual acceptance. |

[`guide/00_OUTLINE.txt`](guide/00_OUTLINE.txt) documents the book itself: the
markup, the rules the chapters are written to, and the chapter plan. Files whose
names begin with `00_` are never rendered.

## Rendering the PDF

The chapters are written in the house `@`-markup — `@CHAPTER`, `@INTRO`,
`@SECTION`, `@CODE`/`@ENDCODE`, `@FRAG`/`@ENDFRAG`, `@NOTE`, `@TRAP` — and are
rendered by the PureMetal compiler repository's `tools/build_help_pdf.py`, the
same renderer that produces the shipped guides. Its `--book` option takes any
folder of chapter files, inside that repository or not:

```sh
python tools/build_help_pdf.py \
  --book   <path-to>/Anvil/docs/guide \
  --out    <path-to>/Anvil/docs/guide/AnvilGuide.pdf \
  --title  "The Anvil Guide" \
  --subtitle "Build it, install it on a Raspberry Pi 4, write payloads for it, and use all four cores." \
  --section-nav
```

Run it from the compiler repository's root (the directory that holds `tools/`
and `Help/`). It needs Chrome, which is the PDF engine; nothing is zipped and
nothing is written to the desktop — exactly one PDF appears where `--out` says.
`--section-nav` lists `@SECTION` headings in the contents as well as chapters.
Add `--keep-html` to leave the intermediate HTML beside the PDF when a layout
question needs answering.

**Every book in this family uses this one command**, with `--book`, `--out`,
`--title` and `--subtitle` changed. One renderer means two books cannot drift
into two formats.

## Keeping it current

Each public repository carries its book in `docs/guide/`, as chapter files and
as a rendered PDF beside them. The book is updated in the **same commit** as any
change to what a developer does — a command, a flag, a file name, a printed
message, a procedure, a boundary — and the PDF is re-rendered in that commit
too.

A book that lags the code is a **defect**, not a chore, and is filed and fixed
like any other. The test is not "did I break a chapter"; it is *would a
developer following this book now do something that does not work?*

## How the chapters are written

Three rules do most of the work, and they are stated in full in
`guide/00_OUTLINE.txt`:

- **Every claim is true today.** Not true in principle, not true once, not true
  after the fix somebody is writing. Where something is half done, the chapter
  says which half, in the place a reader would otherwise assume the whole.
- **Every command was run, or it is quoted.** A command line here was either run
  on a desk machine while the book was written, or reproduced exactly from the
  tool's own usage text or from a recorded board session.
- **"What you will see" follows every command**, because a reader who types
  something and gets output they cannot recognise has no way to tell success
  from a partial failure. Output taken from a recorded board session rather than
  a desk run says so on the spot.
