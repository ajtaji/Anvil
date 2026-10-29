# PNG and compressed sprite decoding on Anvil

PNG memory and file loading now have explicit scratch-backed shared APIs. The
current qualification is below. The earlier stream-only milestone is retained
after it as dated history. Legacy signatures remain unchanged; an optional shared decoder installation now enables PNG/BMP selection through them.

## PNG APIs and current physical qualification

Include Core/crc.pbi with its existing standard #CRC_POLY contract, then
Graphics/neon_png_decode.pbi. The decoder reuses that CRC owner; no CRC algorithm
or polynomial is duplicated. NeonByteSpan/Overlap now have a shared owner in
neon_byte_ranges.pbi, used by PNG and the inflater. Moving those helpers preserves
the complete capture455 inflater PMF byte for byte, with current closure hashes.
The decoder contains no file, device, allocator, renderer or board dependency.

NeonPngInspect(info,encoded,bytes) validates the entire container and every chunk
CRC before publishing104-byte/aligned8 NeonPngInfo on qualified64bit targets.
It returns0 or a negative error. Info includes width/height/depth/type/interlace,
channels, concatenated IDAT size, exact filtered size and required workspace.
Palette/transparency pointers borrow immutable source bytes. Keep source alive
and unchanged while using those pointers; metadata is not an owned image.

NeonPngDecode(outInfo,encoded,bytes,rgba,capacity,colourKey,mask,maskCapacity,
scratch,scratchCapacity) supplies explicit output/scratch storage. OutInfo is the
existing16-byte/aligned8 NeonSpriteAssetInfo. Scratch is aligned8, disposable,
and must have Inspect.workspaceBytes. It holds inflater workspace, concatenated
IDAT, filtered rows and temporary RGBA. No hidden allocation occurs. Output has
width*height*4 bytes; optional mask has one byte per pixel. All used spans must
be valid/representable and pairwise disjoint, including metadata, source and
scratch. ColourKey -1 disables it; otherwise0..0xFFFFFF uses the existing RGB()
byte layout, keyed pixels become transparent black. SourceBytes1..16777216 and
dimensions1..1024 per axis. Caller serializes APIs, including the shared CRC
table initialization; concurrent calls/32bit targets are not qualified.

All15 legal PNG colour/depth pairs are implemented: grayscale1/2/4/8/16,
RGB8/16, indexed1/2/4/8, grayscale-alpha8/16 and RGBA8/16. Both normal and
Adam7 passes, all five byte filters, packed samples, PLTE and tRNS are handled.
Output is straight top-down RGBA8. Sixteen-bit samples reduce to their high byte;
grayscale below8 bits scales to0..255. Transparency compares original sample
precision before conversion; palette alpha defaults255 beyond supplied tRNS.
There is no colour-management/gamma/profile transform. Ancillary chunks are
CRC checked then ignored; unknown critical chunks refuse. APNG animation is
not implemented; only its compatible PNG default image can be decoded.

Chunk type, IHDR uniqueness/order/fields, PLTE/tRNS ordering/size,
contiguous IDAT, IEND and exact end of source are checked. The zlib stream must
produce exactly the calculated filtered bytes; invalid filters,
CRC/Adler errors and malformed/truncated streams refuse. All validation and
conversion finish in scratch before publishing any output metadata/RGBA/mask.
On any refusal those caller outputs remain unchanged; scratch is disposable.
PNG errors ARGUMENT-23000, FORMAT-23001, TRUNCATED-23002, CAPACITY-23003,
CHECKSUM-23004; underlying inflater errors propagate unchanged. A malformed
container may have several defects; the first encountered error is reported.

neon_service_png.pbi adds NeonServiceSpriteLoadPNGMemory/File with the same
scratch-backed decode parameters plus destination slot (and file input buffer
for File). Bind/open the existing graphics service first; File additionally
requires AnvilFileBind. Decoding precedes resident upload, so a decode refusal
does not replace a texture. Handles/zero-failure and extension status follow the
existing sprite client. Glyph/frame ownership is unchanged. File uses the existing
bounded file-handle client and its close/retained-handle contract. Existing
Unconfigured SpriteLoadMemory/File signatures still select BMP; PNG has explicit APIs
because it requires additional caller scratch. Optional automatic legacy dispatch is documented below. Allocating convenience
wrappers are not implemented.

Final Anvil361 capture458 passes81 cases/209 assertions: all15 colour/depth pairs
both ordinary and Adam7, small/empty-pass edge dimensions, every filter, split/
empty IDAT chunks, indexed alpha, exact16-bit transparency, colour key, CRC/Adler,
malformed ordering/type/size/header/palette/sample, truncation/capacity and16
argument/alias/wrap refusals. Exact output is20752 RGBA bytes/5188 mask bytes;
all failed outputs and metadata retain sentinels. Every info field/borrowed offset,
output/workspace guard and reserved report byte is independently checked.
Pillow independently checks generated8-bit/palette pixels. For packed grayscale
its expanded-L tRNS comparison differs from the original sample identity, so only
RGB is cross-checked there; alpha is pinned from original samples and the PNG
contract. Sixteen-bit expected values are generated from original full samples.

The current PNG3 interoperability rules are explicitly exercised: unknown
ancillary chunks with the reserved bit set are ignored (unknown critical still
refuses); tRNS high bits outside the sample depth are masked; an empty indexed
tRNS leaves all entries opaque; out-of-range palette indices render opaque black.
Unused trailing IDAT bytes are ignored after a fully validated zlib prefix.
neon_inflate_prefix.pbi adds NeonInflateZlibPrefix: it first asks the unchanged
strict decoder, and on a format refusal may retry once at its candidate consumed
boundary. Only a complete strict decode plus Adler pass can return success. This
can decode twice when trailing container bytes exist; it does not weaken the
strict Raw/Zlib APIs or their byte-identical capture455 qualification.

Review of the current specification found the earlier strict behavior in457
too restrictive for those cases. Original457 source/plan/checker/results are
retained; final458 includes six added cases and corrected expectations for two
existing cases. A bad Adler checksum with trailing IDAT bytes still refuses.
The qualified fixtures establish these interoperability rules, not a claim of
complete PNG/APNG decoder conformance, colour management or maximum-size timing.

Eight decoded images cover mixed colour/depth/transparency/Adam7 paths through
actual resident Vulkan textures. CPU image/scratch bytes are erased after upload.
The final image passes164736 compared sprite pixels plus three background probes,
and was visually inspected. The verifier rejects3771 planted report/image faults.
One943-byte RGBA16 Adam7 fixture was created as1:/NPNG457.PNG through Anvil's own
verified RAM upload/save commands, exact-byte reloaded, then read by the real
file-handle API and displayed in the final scene. It remains on the drive as a
test fixture. No boot image/firmware/reset/Bluetooth operation occurred.

The whole final suite returns0 in1.9hostseconds; this is not a maximum-capacity
decode benchmark, per-frame timing or spare-workload claim. UnoQ compiles only.
All final cores/font/Vulkan/timeouts remain healthy/deadmanoff. Historical456
passes75cases/171assertions before file/argument additions and broader sample
variation; its original checker/plan/source and results are retained separately.
Initial grouped-array fixture syntax was corrected before upload. The first
file-existence check deliberately observed not-found; the command wrapper raised
on that expected refusal. Its transcript and the subsequent verified creation
are preserved, without upload/reset silence or retries of a storage mutation.

Build/check: tools/build_neon_png_app.py and tools/neon_png_app_check.py with the
pinned tools/neon_png_cases.json corpus. This qualifies explicit shared PNG APIs,
not JPEG/other formats, full Neon or Vulkan completion. Mandatory source gates
still apply. No source publication claim follows from the board results.

## Earlier compressed-stream qualification (capture455)

## Contract

Include Anvil/Graphics/neon_inflate.pbi. NeonInflateRaw and NeonInflateZlib take
state, workspace, workspaceBytes, source, sourceBytes, target and capacity. They
return a nonnegative exact decoded byte count or a negative error. There are no
renderer, board, allocator, file, callback or service dependencies in the decoder.
The implementation follows the format facts in [RFC1951](https://www.rfc-editor.org/info/rfc1951/)
and [RFC1950](https://www.rfc-editor.org/info/rfc1950/), independently written for
the existing language. PNG integration follows the [W3C specification](https://www.w3.org/TR/png-3/).
No third-party decompressor source or sample implementation is incorporated.

The qualified64bit State is88 bytes/aligned8. Workspace needs8192 bytes/aligned8;
its contents are disposable. Source/target are byte-addressable, may be unaligned,
and must not overlap each other, state or workspace. State/workspace cannot alias.
SourceBytes1..16777216; capacity0..16777216. With capacity0 a nonnull valid one-byte
target span is still required, although no byte may be written. Positive address
spans must not wrap. The caller keeps all storage valid for the synchronous call.
Calls using independent storage do not share decoder state; no threads were tested.
These pointer/word contracts are qualified on AArch64, not32bit targets.

Argument refusal occurs before state/workspace/output writes. Other failures may
leave a decoded prefix in output; output is DISPOSABLE until the return is success.
State.produced counts that prefix and State.error gives the failure. For zlib,
source/sourceBytes/offset describe the inner DEFLATE body after header validation;
they do not include the two-byte wrapper header or four-byte checksum. Remaining
bit padding is ignored, but trailing full bytes inside the declared stream refuse.
No concatenated-stream or partial-consumption success is supplied by this API.

Stored, fixed and dynamic blocks, canonical Huffman lengths and overlapping
length/distance copies are implemented. History persists across blocks and has a
32768-byte maximum. A smaller zlib CINFO window is enforced. Oversubscribed trees,
incomplete trees other than the permitted sole one-bit symbol, missing EOB,
illegal repeat lengths, reserved symbols and impossible distances refuse. An empty
distance alphabet is accepted until a match requires it. Zlib checks method,
header modulus/window, rejects preset dictionaries and verifies Adler32. No gzip
wrapper or preset dictionary API is implemented. Output-capacity checks precede
each literal/stored run/match write. Byte loads handle unaligned table/input data.

Errors: ARGUMENT-22900, TRUNCATED-22901, FORMAT-22902, CAPACITY-22903,
CHECKSUM-22904, DICTIONARY-22905. A malformed/truncated stream can admit more than
one description; the first encountered failure is returned. There is no maximum
input/output timing guarantee, incremental yield interface or per-frame decoding
claim. Decode assets outside drawing; container integration must bound its work.

## Physical qualification

Final Anvil361 capture455 passes69 compressed cases and93 assertions. Every one
of306945 decoded success bytes is compared to independent Python zlib output by
the host verifier. The deterministic corpus covers stored/fixed/dynamic streams,
empty/unaligned data, multiblock history, every length/distance base and maximum
extra value, distance32768, overlapping distance1, repeat16 across alphabets,
nonzero final padding, malformed trees/headers/repeats/reserved symbols, truncated
streams, capacity failures, CINFO distance limits and Adler failure. Seventeen
argument refusals preserve the complete88-byte state; the source-decoded final
image also remains intact. Output and workspace guards pass for every case.

Failure-produced and consumed counts are bounded diagnostics, not all independently
pinned to exact values. Failed output is not compared as a usable image. The
checker compares all success bytes, error codes/guards, reserved report bytes,
and294912 native image pixels plus four background probes. The decoded64x32 RGBA
grid is copied into a resident sprite, its CPU source erased, then actually drawn
through Vulkan at the configured canvas scale. The PNG capture was inspected.
The verifier rejects910 planted report/image corruptions. This is not a PNG file
decode: only the compressed raw RGBA stream is exercised here.

The final payload returns0 in7.0hostseconds, including all fixtures and buffer
initialization. This is not a decompression throughput or frame-rate measurement.
Historical454 passes the earlier64cases/80assertions/256343bytes before the table/
alias extension. Final UnoQ client compiles only; no runtime/GPU result there.
All final cores/font/Vulkan/display checks pass, zero display timeouts/deadmanoff.
No firmware update/reset, storage write or Bluetooth operation was required.

Build with tools/build_neon_inflate_app.py --target pi4 --compiler <compiler>
--out <fresh directory>; tools/neon_inflate_cases.json pins the corpus. Readback
is checked by tools/neon_inflate_app_check.py. Mandatory source gates still apply;
source publication and the broader Neon/Anvil Vulkan goal remain unfinished.


## Automatic PNG/BMP selection in legacy loaders

The existing SpriteLoadMemory/File service and native signatures now use a
shared decoder selector. The default remains the original BMP24/32 decoder.
Include neon_sprite_decoder_png.pbi after the existing Core CRC owner and
install an aligned caller-owned workspace with NeonSpriteDecoderPngInstall.
The unchanged legacy calls then select PNG or BMP from the encoded content.
NeonSpriteDecoderPngReset restores BMP. Explicit PNG APIs remain available.
JPEG, GIF, other image codecs and allocating convenience wrappers are not
implemented by this change.

NeonSpriteDecoderInstall accepts the same eight-argument decode contract
and a file-source byte limit, allowing further decoders without copying
upload or file code. Installation, reset and nested decoding refuse while
the decoder is active. Refused installation preserves the selected decoder
and workspace. Unexpected positive decode status becomes a provider error.
Installed code and scratch must remain valid; callers serialize operations.
Busy is -21325; an invalid positive provider status becomes -21326.
Custom providers must retain the decoder's validation and transactional
output contract; registration is not a hostile-code sandbox.

PNG uses its existing explicit workspace requirements and decode limits.
Install requires an aligned, representable span of at least 8192 bytes;
NeonPngInspect gives the exact image-specific workspace size. Too little
workspace refuses before publishing outputs. The installed file limit is
16 MiB; BMP's internal limit remains 4194432 bytes. Legacy file helpers query
the active decoder's limit. The native helper also refuses an oversized
read count and validates its encoded destination span before file access.

Pi4 capture 497 passes the unchanged 133 BMP/file checks plus 43 new registry/
PNG integration checks. It loads 1:/NPNG457.PNG using legacy SpriteLoadFile,
uploads the same encoded PNG using legacy SpriteLoadMemory, resets decoding
to BMP and successfully loads another BMP. It erases caller image/encoded/
scratch buffers before drawing. Independent readback checks 572 PNG RGBA
bytes, 143 mask bytes, 18304 PNG display pixels and 300 existing BMP pixels.
The checker rejects 109 changed reports/images. The source and PNG decoding
algorithm are reused; this is loader integration evidence, not a new codec
conformance or maximum-image performance claim.

An earlier capture496 used the original fixture helper names. The final
fixture has its own names; its changed binary was physically retested rather
than assumed equivalent. Both complete images are byte-identical.

The same pure application compiles for UnoQ only. The complete Pi4 native
composition also compiles with all three native entry points and the PNG
installer referenced so their code is emitted. That diagnostic was neither
installed nor executed; native HwFile-wrapper runtime remains unverified.
Anvil 370 remains installed, with healthy cores/font/Vulkan, zero display
timeouts and deadman off. No boot-image update, reset or storage write was
needed. Full engine effects/physical input and broad Vulkan remain open.
