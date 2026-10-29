# Shared web client

The shared client lives in `Anvil/Network/web_client.pbi`. It combines bounded
URL parsing, request serialization, response framing and a cooperative exchange
loop. The monitor's HTTP and HTTPS commands use the same URL/request/response
components. `Anvil/Core/web_transport.pbi` selects the kernel service binding;
`Anvil/Network/web_payload.pbi` selects the application ABI binding.

This is ongoing implementation, not a declaration that all web protocols work.

## Application use

Include `Anvil/Network/web_payload.pbi` and call `WebPayloadBind(table)` with the
Anvil service table supplied on entry. ABI major 1, minor 6 and 88 slots are the
minimum; unsupported services retain their own capability refusals. The library
uses the existing DNS/TCP/TLS slots and does not require a new monitor ABI.

All storage belongs to the caller. Keep it alive until the exchange is closed:

1. Fill `WebUrl.host`, `hostCapacity`, `target`, `targetCapacity` with distinct
   writable buffers. Call `WebUrlParse(input, bytes, defaultSecure, url)`.
2. Call `WebRequestInit(request, url, method, methodLength, bodyLength,
   keepAlive, headerBuffer, headerCapacity)`. Use a nonnegative body length or
   `-1` for a chunked upload. Method and URL inputs are copied into the request.
3. Add headers using explicit name/value byte lengths, then call
   `WebRequestFinishHeaders(request)`. Host, Content-Length, Transfer-Encoding,
   Connection, Expect and Upgrade are owned by the serializer and cannot be
   overridden by an application header. Content-Encoding negotiation is the
   caller's choice; use `Accept-Encoding: identity` without a content decoder.
4. Initialize `WebResponse` with `WebResponseInit(response, lineBuffer,
   lineCapacity, headerBuffer, headerCapacity, headOnly)`. Set `headOnly` for
   HEAD requests. Use different request and response header buffers.
5. Call `WebClientStart(client, url, request, response, txBuffer, txCapacity,
   rxBuffer, rxCapacity, nowMs, timeoutMs)` on a fresh or closed client.
6. In the application event loop, call `WebPayloadService(sliceMs)` once and
   `WebClientStep(client, input, inputBytes, endBody, output, outputCapacity,
   nowMs)` for each active client. Service calls advance the real network;
   calling Step alone does not service Wi-Fi, DHCP or TCP timers.
7. Advance input by `client.consumed`. Consume `client.written` output bytes
   before reusing that buffer. Return value zero means pending, one means the
   complete response, and a negative value is a failure with transport closed.
   `endBody` says the supplied span is the last input span. Repeat it while
   draining the remaining serialized output. An output capacity of zero applies
   backpressure; body bytes are retained, not discarded.
8. Call `WebClientClose` when finished, or `WebClientCancel` to abort. A completed
   response can still be a non-success HTTP status; inspect `response.status`.

Start never waits for DNS or a connection. Each Step performs at most one
transport send and receive plus bounded serialization/parsing. A pending send
keeps its bytes until the transport accepts them. An early final server response
stops further upload and makes that connection ineligible for reuse.

The exchange deadline is measured from Start, using a wrapping 32-bit
millisecond clock. It is not extended by a dribbling peer. Timeout and
cancellation close the handle. The request serializer checks declared body
lengths and never silently shortens a header.

## Response metadata and connection reuse

`WebResponseHeader(response, lowercaseName, occurrence, destination, capacity)`
retrieves a final response header. Occurrences are zero-based; separate repeated
fields remain separate. A null destination and zero capacity query the value's
length. The returned value is trimmed and NUL-terminated; `-527` means absent.
Trailers cannot override final response headers. `WebResponseHeaderCount` counts
final header fields, excluding the status line and trailers.

After a complete response, inspect `response.reusable`. To send another request
to the **same origin**, prepare a new request and a separately initialized
response context, then call `WebClientNext(client, request, response, nowMs,
timeoutMs)`. Do this before resetting the previous response, whose reuse decision
Next must inspect. Keep the original host storage unchanged. There is no
pipelining; unread surplus bytes, an incomplete upload, peer close, ambiguous
framing and early server rejection prevent reuse. Close and start a fresh
connection for another origin.

Transfer framing supports Content-Length, chunked bodies with extensions and
trailers, close-delimited responses, HEAD, informational responses and no-body
statuses. Conflicting lengths, unsupported transfer codings, framing fields in
trailers, overlong metadata and premature EOF are explicit failures. Decoded
transfer bytes can be arbitrary binary data. Content-Encoding is a separate layer, decoded by the optional streaming
WebContent pipeline described below.

## Current limits and qualification

The URL parser accepts HTTP(S) ASCII hostnames and IPv4 forms; IPv6 literals,
and international host conversion remain open.
HTTP/2, HTTP/3, WebSocket upgrade and a managed cookie/authentication layer
are not supplied by this client. Applications may send ordinary
Authorization and Cookie fields explicitly. The existing TLS provider has one
connection because its cryptographic state is global; plain TCP has four payload
handles. Multiple client contexts do not remove those provider limits.

TLS always checks the chain, name, dates, CertificateVerify and Finished through
the existing provider. It requires a trusted clock and root store. Do not disable
verification to handle an unsupported peer.

On the Pi 4, a payload with caches off completed plain HTTP but hit the 15-second
watchdog during the subsequent TLS attempt. A payload using the established
cached-memory setup completed both real GETs: 99 ms HTTP and 796 ms HTTPS for a
577-byte chunked page. These are individual qualification samples, not general
latency guarantees. Uncached TLS work still needs bounded scheduling; there is
no claim that every underlying TLS/service operation meets a frame-time budget.

Physical tests also cover fragmented input, output backpressure, binary uploads,
short writes, early rejection, cancellation, deadlines, reset/error handling and
sequential reuse using transport doubles. The installed monitor remains build
405; new monitor compositions are compiled but not yet deployed. See the named
web-networking evidence archives and the vault checkpoint for exact run outcomes.

Live HTTPS qualification also passed known-length and chunked POSTs with exact
1,025-byte echoes, and two deterministic five-byte GET responses over one
connection. The public test service returned 402 when the test omitted a
User-Agent; including the normal request headers produced 200 responses.

## Redirects

The kernel and payload compositions also expose `WebClientFollowRedirect`.
After Step completes, call it with separate next URL, request and initialized
response contexts, caller-owned header/Location/scratch buffers and a
`WebRedirectOptions`. It returns zero when the next exchange is active, one
for a non-redirect final response, or a negative refusal. Continue pumping Step;
drain intermediate bodies without delivering them as the final representation.
Rotate two context/buffer sets, retaining the current set through each follow.
Initialize each next response with the correct HEAD semantics.

The helper resolves relative/root/network-path/absolute Location values, removes
literal dot segments while preserving escaped bytes and queries, rebuilds Host
and framing, reuses an intact same-origin connection, and opens a fresh
connection on origin changes. All hops retain the original total deadline.
Missing/duplicate Location, excessive hops and HTTPS downgrade are refused.
Downgrade requires an explicit option. POST 301/302 and non-HEAD 303 become GET;
307/308 preserve methods. Retained uploads require replayable input and unsafe
method replay requires explicit permission. A GET switch sets bodyLength to zero;
otherwise callers reset their original body source after following.

Cross-origin redirects copy only negotiation/User-Agent fields and, for retained
bodies, representation metadata. Authorization, Cookie and arbitrary custom
credentials are not copied across origins. Hop/framing and conditional/range
fields are rebuilt or removed. This layer does not manage a cookie jar.

Physical Pi qualification passed two-hop relative and absolute HTTPS redirect
chains (687 ms and 661 ms in these samples), including same-connection reuse,
final JSON response checks and a one-hop limit refusal. Thirteen separate policy
cases passed method/replay/downgrade/credential handling. The initial resolution
proof's two query-retention failures were caused by a short test input span;
both were corrected and verified in the subsequent policy proof.

## Compressed content

After response headers complete, call `WebContentFromResponse` with a separate
WebContent context, caller-owned 32 KiB history, an 11,008-byte workspace aligned
to eight bytes, and an explicit decoded-output limit. Missing encoding or
identity passes bytes through; gzip and zlib-wrapped deflate decode incrementally.
Unknown, stacked or duplicate encodings are refused. This does not change
WebClientStep's transfer-body output: feed those bytes into WebContentFeed.

Keep any unconsumed encoded bytes before calling Step for more. Pass endInput
only when HTTP framing has completed, and keep draining the decoder until it
returns one. Each call reports consumed/written counts and honors output
backpressure. Decoded data can precede its checksum, so successful completion
must be required before treating a download as verified. gzip supports optional
headers and concatenated members with CRC32/size checks; deflate checks its zlib
header, advertised window size and Adler-32. Preset dictionaries, raw-deflate
fallback, Brotli and Zstandard are not supported. Metadata and decoded output
are bounded. Malformed streams, bad checksums and premature EOF are failures.

The lower-level WebInflate decoder supports stored, fixed and dynamic Huffman
blocks, overlapping backreferences and a wrapping 32 KiB history. Contexts and
workspaces are separate for each stream. Table storage requires eight-byte
alignment; initialization rejects an unaligned workspace. A first physical
probe exposed this missing precondition with an alignment fault; its diagnostic
record was preserved and the board recovered before the corrected run.

Physical qualification passed 27 DEFLATE cases and 26 gzip/zlib cases using
independent standard-library fixtures and byte-for-byte comparisons. Live HTTPS
gzip and deflate bodies decoded to the expected JSON (693 ms and 571 ms in these
samples). A request expected by the test to be uncompressed had advertised gzip,
so the server correctly compressed it; the original test was marked failed and
a separate request explicitly requiring identity passed.

The shared TLS service also now refuses TCP resets and missing close_notify
instead of reporting successful end-of-stream, drains queued TCP data before
judging FIN, and retains authenticated closed state while plaintext is drained.
Eight physical service-owner tests passed using TCP/crypto doubles. This service
change was installed in builds 416 and 418. Live verified HTTPS gzip and
deflate requests pass on the updated resident image; injected transport faults
remain covered by controlled doubles rather than on-wire fault injection.


## DNS reply ownership and large answers

The shared DNS codec now binds `DnsParseReplyFor` to the outstanding host name,
IN/A question, and query ID. Answer addresses must belong to that question or its
CNAME chain, independently of record order. Name compression, aliases and record
counts are bounded; malformed, conflicting and truncated results are explicit
refusals. The packet-only `DnsParseReply` compatibility API still checks the
question and answer relationship, but callers with a host name should use the
bound API. The payload resolver, monitor lookup and time service do so.

`DnsResultTtl` reports the minimum TTL across the alias chain and returned RRset.
The payload resolver caps reusable entries at five minutes without extending a
shorter authoritative lifetime. A zero TTL is delivered once to the requesting
transaction and then discarded; it cannot become a reusable cached answer.
Expiry handles the millisecond counter wrapping.

A matching truncated UDP reply causes the payload resolver to retry the original
question over TCP. Two-byte length framing, partial sends/receives, cancellation,
premature closure and the original overall deadline remain enforced. The retry
uses the existing TCP service and releases its handle on every terminal path.
The codec accepts at most 64 answer records and 16 aliases; the TCP message buffer
holds the full 65,535-byte DNS message limit. This is not DNSSEC validation, AAAA
support, or an iterative authoritative resolver.

Physical checks cover 30 decoder cases, five cache boundaries, 16 TCP lifecycle
cases and three rejected UDP triggers. A separate live TCP query to a public
resolver returned two matching addresses in 58 ms; UDP truncation was exercised
with deterministic transport inputs, not an on-wire fault-injection server.


## TLS service scheduling

`Tls13FeedBytesLimited` accepts a maximum record count and returns the consumed
input length. A zero budget consumes nothing; partially received records remain
buffered. The legacy `Tls13FeedBytes` entry retains batch behavior. The shared TLS
client now processes at most one incoming record per advance and performs one
TCP send attempt per flush. Partial sends remain queued, and an impossible send
count is an explicit transport failure. Application plaintext is drained before
the receive buffer is reused.

This separates coalesced records and partial-send retries across service calls.
It does not make individual certificate verification or key-share arithmetic
resumable, and one TLS record can still contain several handshake messages.
There is no frame-time guarantee. Physical scheduling and transport-close checks
use controlled crypto/TCP doubles; live HTTPS qualification is recorded separately.

Installed419 passes live verified HTTPS gzip and deflate requests after reboot.
The longest measured handshake service calls remain about 347 ms; record budgeting
has not removed this arithmetic bottleneck. First open with cold root setup took
41 ms in this sample, while the following warm open took654 microseconds.


## WebSocket connections

The shared `websocket_frame.pbi`, `websocket_handshake.pbi` and
`websocket_client.pbi` compose over the same HTTP parser, TCP/TLS transport and
service handles. The SHA-1 dependency is `Anvil/Crypto/sha1.pbi`; it is used only
for the RFC 6455 upgrade accept value, with its previous streaming state preserved.
TLS certificate verification remains unchanged.

Initialization, with separate caller-owned buffers:

1. Parse a `ws://` or `wss://` address using `WebSocketUrlParse`. Its scratch
   capacity must be at least the input length plus three; fragments are refused.
2. Obtain a fresh unpredictable sixteen-byte nonce from a cryptographic RNG.
   Call `WebSocketRequestInit` with the request, URL, header buffer/capacity,
   nonce, a 25-byte key buffer, a 29-byte expected-accept buffer, and a 192-byte
   scratch area aligned to four bytes. Retain the expected-accept value.
3. Add authentication or one optional `Sec-WebSocket-Protocol` token through
   `WebRequestHeader`, then call `WebRequestFinishHeaders`. No extensions are
   negotiated. Connection and Upgrade fields are generated by the owner.
4. Initialize the response with `WebResponseInit`, then explicitly opt in using
   `WebResponseAllowUpgrade`. Ordinary HTTP clients still refuse 101.
5. Initialize `WebSocketFrame` with a 125-byte control buffer and an aggregate
   incoming-message limit. Call `WebClientStart` normally with TX capacity at
   least 131 bytes, then `WebSocketClientBind` with both contexts, expected accept,
   the offered protocol span (or null/zero), RNG callback, and scratch>=128 bytes.

The RNG callback takes `(destination, count)` and must return exactly `count`
only after filling it with fresh cryptographically unpredictable bytes. A failed
callback aborts the connection. There is no fixed-mask or counter fallback. This
is an explicit caller dependency; there is not yet a public kernel RNG slot.
The live proof supplies a fresh finite pool from the host OS CSPRNG for each
build, refuses exhaustion, and does not claim a resident RNG service.

Pump `SvcNetService` externally and call `WebSocketClientStep` with an output
buffer and current milliseconds. Zero means progress, one a data-frame boundary,
two a clean WebSocket close, and negative a failure. Consume `written` bytes on
every call. `opcode`, `messageKind` and `fin` describe the current frame/message.
Incoming fragmented messages retain UTF-8 state across continuation frames;
interleaved controls do not disturb them. Bytes may precede a later validation
failure, so consumers needing atomic text validation must wait for message FIN.
The client automatically replies to Ping and Close and preserves any frame bytes
coalesced with the HTTP 101 headers. Duplicate/incorrect accept fields, unsolicited
extensions or subprotocols, malformed frames, invalid UTF-8 and truncation fail.

`WebSocketClientSend` copies and masks one complete bounded message or control
frame into the TX buffer. Opcodes 1/2 send text/binary, 8 starts graceful close,
9/10 send Ping/Pong. A busy-TX state error is backpressure; retry after pumping.
Outgoing fragmentation is not implemented: the complete frame must fit TX.
Graceful close has a two-second overall deadline; `WebSocketClientAbort` closes
immediately. All contexts, URLs and buffers remain owned until termination.

Qualification: 29 receive-framing fixtures, 21 upgrade-handshake fixtures and
8 cooperative lifecycle cases ran on the physical Pi4. The first handshake
harness incorrectly treated a consumed byte count as completion; its failed
record remains retained and the corrected state-based harness passed. A real
`wss://httpbingo.org/websocket/echo` exchange verified TLS, upgraded, echoed
exactly 15 bytes, and closed cleanly in895 ms in this sample. Its longest Step was
551 us, excluding the separate network-service call containing synchronous TLS
arithmetic. An earlier test set the server's maximum fragment size below the
outgoing message and received a clean close without an echo; it is recorded as
failed, not counted as echo qualification.
