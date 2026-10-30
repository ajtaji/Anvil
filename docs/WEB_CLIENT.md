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
HTTP/2, HTTP/3 and automated authentication flows remain open.
The bounded managed cookie library is described below.
Applications may send ordinary Authorization and Cookie fields explicitly.
WebSocket upgrade uses the shared WebSocket client described below. Anvil 424
supports four TLS slots over the four-handle payload TCP pool. Plain TCP and TLS
compete for that underlying pool; four TLS slots do not add four more sockets.

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
sequential reuse using transport doubles. Anvil 424 is installed and verified
on the Pi 4. See the named web-networking evidence archives for the scope of
each physical run; a fixture pass is not a live-server qualification.

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
Record budgeting alone does not make certificate/key-share arithmetic
resumable. The cooperative driver described below adds that scheduling; one
TLS record can still contain several handshake messages.
There is no frame-time guarantee. Physical scheduling and transport-close checks
use controlled crypto/TCP doubles; live HTTPS qualification is recorded separately.

Historical baseline: installed419 passed live verified HTTPS gzip and deflate requests after reboot.
The longest measured handshake service calls remain about 347 ms; record budgeting
had not removed this arithmetic bottleneck. First open with cold root setup took
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
can use resident ABI 1.10 slots 175/176 through `web_random.pbi`:
`WebRandomBind(table)`, `WebRandomReady()` and `WebRandomBytes(dst,n)`.
Binding checks the version, entry count and function pointers. Pass the bound
`webRandomBytesFn` directly as the WebSocket RNG callback. It has the required
signature; no payload callback wrapper is needed. Obtain the nonce through
`WebRandomBytes` and require an exact 16-byte return before building the request.
The initial 419 qualification used a fresh finite desktop entropy pool; the
current live proof uses resident randomness instead.

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


## Resident randomness

ABI 1.10 fills the previously reserved slots 175 `SvcRandom(dst,n)` and 176
`SvcRandomReady()`. The 200-entry table and all existing slots remain unchanged.
These calls, like all payload ABI calls, run on core 0. Requests must have a
nonzero destination and a length from 1 through 4096 bytes. Success returns
exactly the requested length. Invalid arguments return EARG; an absent provider
returns ENOCAP, and a busy call returns EBUSY. A provider which is temporarily
not ready returns EAGAIN; provider failure or a short/oversized result returns
EIO. Failed provider calls wipe the requested output span. Argument, absent-
provider and busy refusals do not touch output memory.

Readiness returns 1 after successful initialization, 0 for a provider still
waiting, or a negative error. The shared DRBG provider lazily gathers 48 bytes
from the existing hardware entropy owner, refuses failed/short/constant seeds,
and requires fresh reseeding once its generated-byte counter reaches 1 MiB.
Requests are bounded; this is not a claim of asynchronous entropy collection.
There is no fixed, counter or clock fallback. The provider saves and restores
SHA-256 and HMAC working state and wipes the snapshot afterwards, so an entropy
call between TLS advances cannot replace an in-progress digest or HMAC key.
Other targets can register their own provider through the shared service owner;
absence is explicit rather than being inferred from a board name or network flag.


Physical resident qualification on Anvil421: verified WSS upgrade, exact text
echo and graceful close in 729 ms. The initialized 16-byte nonce call took
389 us; maximum WebSocket Step was 547 us, excluding TLS service arithmetic.
No desktop entropy was included. The controlled service proof passed 37 result
checks and independent SHA-256, HMAC, DRBG and reseed comparisons. An initial
16-bit ABI header read was corrected to the actual 32-bit fields before this
qualification. All runs returned to healthy cores/fonts/Vulkan with watchdog off.


## TLS verification cost on Anvil 422

P-256 verification now computes its two public scalar products together with a
small two-bit table. The retained general multiplication entry and private-key
ladder are unchanged. Complete addition handles equal/opposite points and the
point at infinity. All 51 existing verdict/diagnostic cases and 52 additional
independently checked cases passed on the Pi 4. The original ten positive cases
had a median of 178,231.5 us; the final path measured 94,790 us, about 47% lower.
Shared crypto proofs compile for Pi 3 and Rock Pi; those are compile checks,
not physical execution claims for those boards.

After installing 422, live verified HTTPS gzip/deflate tests took 573/493 ms.
The longest handshake work was 266,907/265,409 us versus approximately 347 ms
before this change. TLS state queries also advance the handshake: the gzip
sample's long call occurred in the state query, so its 46,605 us maximum service
call alone would understate the stall. Include both call sites when profiling.
The first open spent 41,064 us loading cold roots; the warm open took 653 us.
At that revision verification remained synchronous and TLS permitted one connection. This
improvement does not establish a display-frame latency bound.

Anvil 423 also uses joint two-bit public windows for P-384 and P-521 issuer
verification. All 116 raw/DER and independently checked boundary cases passed
on the Pi 4. Typical nontrivial positive signatures cost 7-11% less; small-scalar
cases cost 1-3% more because of table setup. Shared proofs compile on Pi 3 and
Rock Pi. The register table grows by 6,912 bytes. Live verified gzip/deflate
HTTPS took 595/475 ms, with maximum handshake calls of 252,139/250,901 us.
Network round trips vary; the complete request is not claimed uniformly faster.
Evidence is retained in `docs/evidence/anvil-tls423-20261029`.

## Streamed HTTP events

Include `Anvil/Network/web_event_stream.pbi` to decode `text/event-stream`
incrementally from HTTP response body bytes. This is a shared parser, usable
with ordinary GET streams or streamed POST replies. It has no socket ownership.
Check HTTP status and Content-Type before feeding; pass decompressed bytes if
the response has content encoding. Continue servicing networking separately.

`WebEventStreamInit` takes the context and separate caller-owned line, data,
event-name, provisional-ID and last-ID buffers. The two ID buffers share a
capacity. All buffers must remain alive and must not overlap. Line capacity is
4..65536 bytes, data 1..1048576, event name 7..65536, IDs 1..65536. Data capacity
includes the internal trailing newline until dispatch. Length fields describe
UTF-8 byte spans, not NUL-terminated strings; event data can contain NUL.

Feed returns 0 for more input, 1 for one event, or a negative error. Advance
the input by `consumed`, retain any remainder, read `dataLength`, `eventLength`
and `lastIdLength`, then call `WebEventStreamNext`. Feeding a ready event again
returns 1 without consuming anything. Work is proportional to the supplied
input and bounded buffer sizes; callers choose a suitable slice size.

The parser handles CR, LF and CRLF, split UTF-8 and its replacement decoding,
one leading BOM, multiline data, comments, exact field-name matching, event
names and persistent IDs. IDs containing NUL are ignored. `lastId` commits at
each blank line, including an ID-only block. The default event name is message.
Valid decimal retry hints update `retry` and set the sticky `retryChanged`
flag; callers clear the flag after observing it. Oversized hints saturate at
2,147,483,647 ms. The initial hint is 3000 ms. Exhausted buffers return
`WEB_EVENT_LIMIT`; no event is silently truncated.

Call `WebEventStreamEof` only after consuming a ready event. It discards an
unfinished event and closes the parser; it never invents a final dispatch.
Network reconnection, retry scheduling and Last-Event-ID request headers remain
application policy. This is not the browser DOM EventSource API or an automatic
reconnector. Do not automatically replay non-idempotent POST requests.

Physical Pi4 qualification passed 44 fragmented/coalesced fixtures. A verified
HTTPS stream delivered three ping events at 473, 1564 and 2487 ms; the first
two arrived before response completion. An initial request received HTTP 402
and was refused. The successful request included the normal Anvil User-Agent;
the failed request is not counted as qualification. Shared fixtures also compile
for Pi3 and Rock Pi, without a physical execution claim for those boards.

## Bounded TLS connection pool

The kernel TLS service now owns four connection slots. Keep the positive handle
returned by `SvcTlsOpen` and pass it unchanged to send, receive, state and close.
Handles are not slot numbers: each successful open receives a fresh value, and
closed handles remain invalid when their slot is reused. A full pool returns
EBUSY; the underlying TCP pool can independently refuse a connection. No ABI
slot numbers or function signatures changed.

Large receive, transmit, handshake, input, name and plaintext-ring buffers are
separate for every slot. Switching saves 83 TLS working fields and the retained
certificate key into a 2392-byte snapshot, plus 17 client fields. The global
DRBG and trust-anchor store are shared and never rolled back. Restoring a
connection invalidates the AES-GCM key cache before another record uses it.
The layout gate refuses omitted working fields or an unsliced large buffer.

Calls remain serialized on core 0. This is overlapping connection lifetimes,
not concurrent execution of shared cryptographic arithmetic. NetService moves
one allocated connection per advance in round-robin order; State, Send and Recv
also request progress. Open only allocates a handle. With the cooperative driver, an already active worker
finishes its slice before another handshake enters shared scratch. Close wipes that slot's snapshot and buffers; payload return
closes every allocated TLS handle. Diagnostics list all allocated handles.

Physical qualification on Anvil 424 kept four verified HTTPS connections open.
Three exact replies completed at 1522, 1560 and 1615 ms while the fourth
delivered an event stream at 1560, 3613 and 5661 ms and completed at 5662 ms.
A secure WebSocket echo regression also passed. The real record-owner proof
matched four alternating AES-GCM records against an independent oracle.
Controlled lifecycle tests cover pool exhaustion, fresh and stale handles,
isolated state and wiping; separate regressions cover eight closure cases and
fourteen scheduling/partial-send cases. Evidence and scope are retained in
`docs/evidence/anvil-tls424-20261029`.


## Credentials and form submissions

`web_credentials.pbi` formats explicit byte spans with `WebCredentialBasic`
or `WebCredentialBearer`. A nonnegative result is the Authorization value's
byte length, without a NUL terminator. Pass it to `WebRequestHeader`, then
wipe the temporary buffer with `WebCredentialWipe`. The request header buffer
also retains the value until wiped after use. Buffers must be disjoint.
A null destination and zero capacity measure the validated value; short output
or invalid input returns an error without modifying the destination.

Use credentials only with verified HTTPS and the intended origin. The helper
has no transport and cannot enforce that choice. Basic rejects a colon in the
username and control bytes in either field; the caller chooses the negotiated
encoding and normalization. Bearer validates the token wire grammar, including
trailing padding. These helpers do not acquire/refresh tokens, select a realm,
retry a challenge or manage cookies. Existing redirect handling removes
Authorization on a change of origin.

`web_form.pbi` serializes one form field from already encoded UTF-8 bytes.
`WebFormInit(context, name, nameBytes, value, valueBytes, separator)` returns
the complete encoded length. Use separator 0 for the first field and 1 for
later fields. Keep inputs alive and unchanged while `WebFormOutput` emits into
disjoint output buffers; phase 4 means complete. Zero output capacity applies
backpressure. Even a one-byte buffer can split percent escapes correctly.
Each input is bounded to 1 MiB. Spaces become plus signs and literal plus,
ampersand, equals, tilde, NUL and non-ASCII bytes are escaped. No Unicode or
newline conversion is implicit. Sum field lengths for Content-Length, or use
a chunked request; set Content-Type to application/x-www-form-urlencoded.

All 46 physical fixtures passed. Real HTTPS Basic, bad-password rejection,
Bearer and exact form POST passed on Anvil 424 in 550/473/477/484 ms. These are
individual measurements. Evidence: `docs/evidence/anvil-web-values-20261029`.


The four-slot pool also passed a live different-origin run: an HTTP event stream
and another request to httpbingo.org overlapped verified HTTPS requests to
example.com and www.cloudflare.com. Expected page/trace content, TLSv1.3 trace
metadata and all streamed event IDs matched. Capture 257 supplements the
single-origin test in `docs/evidence/anvil-tls424-20261029`.


## Managed application cookies

Include `Anvil/Network/web_cookie_response.pbi`. `WebCookiesInit` receives a
context, caller-owned eight-byte-aligned storage, 1..64 slots, and an optional
domain-policy callback. Allocate `slots * WEB_COOKIE_STRIDE` bytes (3584 per
slot). Keep storage separate from URLs, headers, scratch and output. No shared
global jar or automatic disk persistence exists; choose a separate jar for
each session or account and call `WebCookiesClear` to wipe it.

`WebCookieStore(jar, url, field, bytes, now)` accepts one Set-Cookie field.
Use trusted Unix seconds for now. It stores name/value, host or authorized
domain, default/explicit path, expiry, Secure, HttpOnly and SameSite policy.
Max-Age takes precedence over Expires, and an expired replacement deletes the
matching cookie. Replacement preserves ordering. A full jar returns LIMIT;
expired entries are reclaimed when storing. Names are limited to 128 bytes,
values 2048, domains 253 and paths 1024. Malformed or oversized input is refused
rather than truncated. Invalid date/age attributes are ignored. The date parser
accepts ordinary HTTP dates and hyphenated legacy dates, with validated
Gregorian dates; it is not a locale-dependent date parser.

Without a domain callback, cookies stay host-only: a Domain equal to the host
is narrowed to host-only and a parent domain is refused. A callback receives
an explicit domain byte span and must return exactly 1 only for an authorized
registrable domain. It must reject public suffixes using an application policy
or maintained suffix data; the jar does not ship or download a public suffix
list. Host suffix boundaries are checked independently. Never use an
unconditional accept callback for arbitrary websites.

`WebCookieHeader(jar, url, now, sameSite, topLevelSafe, dst, capacity)` selects
cookies for the target and returns an explicit byte length, without NUL. A null
destination/zero capacity measures. A short buffer is refused before writing.
Longer paths precede shorter paths, then original creation order. Secure
cookies require HTTPS; a plain HTTP response cannot overlay a matching Secure
cookie. Prefix checks cover __Host- and __Secure-. SameSite defaults to Lax;
Strict requires sameSite=1, Lax additionally permits a safe top-level navigation,
and None requires Secure. The caller supplies those request-context facts.

This is an application HTTP API, not a browser script cookie API. HttpOnly
cookies may be sent over HTTP by this library; do not expose jar storage to
untrusted scripts. The caller must decide whether an incoming response is
eligible to set cookies (for example a first-party request). Partitioned
cookies, browser navigation/site calculation, IDNA and persistence are not
implemented. The modern prefix/SameSite behavior is based on a cited draft;
this is not a claim of full browser conformance to that draft.

After final response headers arrive, `WebCookiesCapture` processes separate
Set-Cookie fields using caller scratch. It returns the accepted field count or
the first error; earlier fields remain committed if a later one is refused.
`WebCookiesApply` removes all existing Cookie fields and writes the jar's
current selection into a request. It accepts adding-fields or finalized-but-
unsent requests and refuses once output has begun. Capacity is checked before
modifying headers. Scratch and removed header tail bytes are wiped.

For redirects, capture the intermediate response before following it, then
apply cookies for the new URL before the first Step on that hop. Start and
FollowRedirect do not send request header bytes themselves. Reapplying is
necessary even on the same origin: a server may have changed or deleted a
cookie. Do not simply copy the previous Cookie header.

Physical qualification and the retained failed-run diagnosis are in
`docs/evidence/anvil-web-cookies-20261029`. These shared libraries run in the
application; they do not require a new resident firmware image beyond the
already-qualified HTTP/TLS services.


## Cooperative TLS scheduling

The shared Crypto libraries provide resumable modular exponentiation, RSA,
X25519 and ECDSA operations. The resident TLS client can use these through
Core/tls_cooperative.pbi and the existing cooperative context backend. One
worker owns shared crypto scratch and retains the handshake/parser call stack
while yielding back to the caller. It does not change certificate verification,
use background cores, or enable timer preemption.

Include bignum.pbi before bignum_job.pbi. A zero-initialized BnPowJob owns
pointers to the output, exponent, modulus, and two nonoverlapping scratch
buffers under the existing BnModpow capacity/representation contract.
BnPowBegin returns 0 pending, 1 complete, -1 invalid, or -2 already active.
Begin performs the base conversion. BnPowBeginDeferred instead defers that
conversion to Step, which advances at most bitBudget limbs before beginning
the exponent phase. BnPowStep(job, bitBudget) then performs at most
that many exponent bits (two Montgomery multiplies per bit), returning 0
pending or 1 complete; an invalid budget returns -1 without changing the job.
The public scheduling budget must not depend on secrets. Independent jobs may
interleave when all writable storage is separate. BnPowClear wipes scratch and
the descriptor, including cancellation; output/exponent/modulus remain owned
by the caller. Do not abandon live operand storage or overlap its spans.

After the ordinary ec256/ecp/ecdsa dependencies, include ecdsa_job.pbi and
optionally ecp_job.pbi. EcdsaJobBegin accepts digest, key and signature spans
and a DER flag for P-256. EcpJobBegin accepts a curve identifier and raw
signature for P-384/P-521. Both copy/decode input before returning, return 0
pending or 1 completed, and return -2 if already active. Step returns 0 pending,
1 complete, or -1 inactive. Read the matching JobResult only after completion;
it is a verification verdict, not a pending-state indication. Existing error
codes distinguish malformed, invalid and unsupported cases. Cancel releases
ownership; public verification scratch is not promised erased. Hashes are
limited to 64 bytes. These verification jobs never handle private scalars.

Each ECDSA job exclusively owns its family's shared arithmetic scratch. Never
interleave synchronous ECDSA/ec256/Ecp operations with an active job. This is
an explicit scheduling requirement enforced by the TLS worker, not a claim of
thread safety or a per-connection arithmetic context. P-256 advances scalar
and affine inversions eight bits at a time and its joint multiplication one
window at a time; wider curves advance inversions one nibble at a time.

Physical Pi 4 evidence is in docs/evidence/anvil-tls-jobs-20261029. The P-256
and wider-curve suites check 103 and 116 verdict/diagnostic cases respectively;
24 modular exponentiation cases independently check results, interleaving,
budgets and cancellation. Pi 3 and Rock Pi compilation also passes, with no
physical execution claim for those targets.

RsaJobBegin copies the signature representative, modulus and public exponent.
Step advances one conversion limb or exponent bit. Result=1 means the public
operation completed: the caller MUST still validate PKCS#1/PSS encoding and
compare the expected digest. The existing TLS RSA verifier does both.
X25519JobBegin copies/clamps the scalar, and Step advances a fixed ladder bit
or fixed inversion unit; output is written only at completion. Completion and
Cancel wipe the private scalar and intermediate field elements. Both families
exclusively own existing scratch until completion/cancellation.

TlsCooperativeInstall requires an idle TLS pool and a qualified cooperative
backend in the composition. The current AArch64 backend requires EL3 and the
same core/address space; failure retains the synchronous path and is reported
at boot and by tls status. The shared libraries contain no Pi 4 hardware calls.
The Pi 4 composition also supplies the Pi 5 composition, but runtime support
on a different board/EL is not established by Pi 4 measurements.

The worker targets approximately 2 ms between yield checks. This is not a
hard upper bound: a single arithmetic unit, record operation or device I/O
can take longer, and one high-level HTTP step can call multiple services.
Certificate parsing yields between VM/native operations and anchor scans;
root-store reads use 4096-byte chunks, closing the shared file before each
yield opportunity and reopening it for the next chunk. A changed file size
or invalid read count is refused; this is not a filesystem snapshot against
concurrent edits. Reentrant loads are refused while a suspended load owns the
scratch. Cancellation clears that ownership and forces a later load to restart.
Individual open/read operations remain synchronous. Trust/entropy preparation is
part of connection progress: SVC_TLS_RESOLVING includes this preparation.
After a positive Open handle, callers must check State for preparation errors
and Close failed handles, just as for later DNS/TCP/handshake errors.

Close cancels/reaps an owned worker before releasing the connection and wipes
its private stack. Deadline checks run on resume. Other connections preserve
their own TLS snapshots; only one handshake worker enters shared arithmetic.
This is cooperative serialized execution, not concurrent thread-safe crypto.


Anvil 426 physical qualification: gzip and deflate returned HTTP 200 with
validated decoded content. Observed maximum NetService calls were 2.651 and
2.654 ms; state queries during handshake were at most 2.579 ms. High-level
HTTP Step maxima were 8.613 and 8.612 ms. Cold Start still took 20.804 ms;
the following warm Start took 691 microseconds. Full requests took 571 and
494 ms. These are observations, not latency guarantees. Build 425 without
parser yields had measured roughly 12.4 ms service and 23 ms HTTP Step stalls.

The live cancellation test closed connections during connecting and handshake
states, rejected their stale handles, and then completed two verified HTTPS
requests. Separate saved-context tests check cancellation inside private key
work, caller-slot restoration, stack locals, secret wiping and 31 RSA/X25519
cases. The updated modular job passed all 24 independent arithmetic cases.
Evidence is retained with the prior scheduling measurements under
`docs/evidence/anvil-tls-jobs-20261029`.

Anvil 428 separates Open from progress. Physical capture 285 measured handle
opens at 1-7 microseconds, successful cancellation before preparation and after
one preparation slice, stale-handle refusal, and two verified HTTP 200 gzip/
deflate responses. The first preparation call still took 19.635 ms; subsequent
request measurements reached 8.675 ms per call. This does not qualify TLS as
fully nonblocking. The cold storage path and the link's transmit waits remain
open work.

Build 429 scopes cooperative callbacks to the running worker, clearing them
when control returns to its caller and restoring them before resume. This
prevents unrelated calls from inheriting a suspended worker's yield callbacks.
The updated key-context fixture compiles and checks callback clearance plus
root-load cancellation notification, but its physical run is pending. The 429
image passed full-hash verification and startup health checks. Its following
TLS/storage diagnostic stopped in read-only network preflight before upload:
the console returned part of `net`, then no completed reply after recovery.
No 429 TLS diagnostic result is claimed.


The shared CYW43 credit-poll loop had no success condition for a newly opened
TX window: its wait used no ioctl id and requested no event, so receiving
permission to transmit could still leave it polling until the 100 ms timeout.
Build 430 adds the credit-ready exit after retaining received data and before
continuing an aggregate. Malformed frames and queue failures still take
precedence. Control/event waits retain their existing completion rules.
The 14-case controlled-RX policy fixture passed on the Pi (capture 287).
Build 430 is installed and verified by its complete live image digest; HTTPS
gzip/deflate and cancellation passed (capture 290). No measured latency
reduction or fix for the earlier lost console reply is claimed. Waiting when credits remain absent
and synchronous low-level transfers are still separate blocking work.


Build 429 capture 286 passed 31 cooperative key/context cases, including
worker-hook isolation and cancellation. Capture 288 then passed live HTTPS
and measured the root bundle file path separately: first open 18,273 us,
second open 1,097 us, 4 KB reads 282/196 us. After this deliberate storage
warm-up, the preparation cancellation call took 2,419 us. Build 430 repeated
this distinction (first open 18,336 us, second 1,078 us, preparation 2,401 us).
These results locate a cold file-open cost; they do not identify which mount
suboperation causes it or make file access asynchronous. Cores, fonts and
Vulkan stayed healthy and the watchdog was off after each returning run.

The earlier partial `net` reply was followed by a successful reconnect without
reset: prompt 0.66 s and complete `net` 0.79 s. The host's read-only recovery
prompt window is now 60 s instead of 5 s. Only allowlisted read-only queries
may be replayed; uploads, boot, reset and writes remain excluded.


## Bounded record decryption

Build 431 adds `Crypto/gcm_job.pbi`, a shared AES-GCM decrypt job for 96-bit
nonces and 128-bit tags. Begin copies its key/nonce/tag and derives H; Step
processes at most 256 bytes. AAD and ciphertext are authenticated before any
plaintext is written. Input/output may be identical or disjoint. The key can
be 128, 192 or 256 bits; byte counts are limited to 32 bits. Input buffers
remain alive and immutable through completion. One job is allowed; another
Begin returns busy. Cancel wipes private secrets and pointers, not caller
buffers. Each step reconstructs the AES state it needs, so other synchronous
AES/GHASH calls between steps cannot corrupt its progress.

The cooperative TLS driver installs a decrypt hook only while its worker runs.
The record layer still requires the exact authentic verdict before accepting
plaintext or advancing its sequence. Close cancels the job with the worker;
the shared cipher cache is invalidated after the hook. Compositions without
the hook retain the synchronous path. This does not yet split record encryption,
file opening, or synchronous link waits. No fully nonblocking TLS claim is made.

On the Pi, capture 292 passed 124 independent-vector cases: AES-128/192/256,
empty and partial blocks, 256-byte boundaries, full TLS-sized records, forged
tags with untouched output, in-place operation, busy refusal, cancellation,
restart, output guards and private-key wiping. Shared crypto scratch was
changed between every step. The maximum observed call was 559 us. An earlier
93-case run measured a 16,640-byte AES-128 synchronous decrypt at about 29.7 ms
versus about 0.41 ms per job step; total work is not claimed to improve by that
ratio. Final citation-only edits produced byte-identical raw and PMF payloads.
Pi 3 and Rock Pi compile the shared job; only Pi 4 has physical evidence here.

Build 431 was installed with a verified 430 backup and complete live-image
hash. Capture 294 passed HTTPS gzip/deflate and cancellation: the largest
service call in these two responses was 3,222 us, versus 8,694 us on 430;
HTTP Step peaked at 3,611 us. Network timing varies and these are observations,
not worst-case guarantees. Capture 295 passed four overlapping verified HTTPS
connections, including an event stream delivered before completion. Capture
293 passed the cooperative worker's 31 context cases with the new hook scope.
All runs returned with cores, fonts and Vulkan healthy, and watchdog off.


## Bounded encryption and accepted application sends (build 432)

The shared GCM job also encrypts in steps of at most 256 bytes, emitting the
final tag only when complete. Result 1 means successful encryption or authentic
decryption. Cancellation can leave partial ciphertext in caller buffers; it
must never be transmitted without the final tag. AES-128/192/256 are supported.
The cooperative TLS worker scopes the encryption hook just like decryption.

TlsClientSend now copies accepted application bytes into a per-connection
16 KB queue. The caller may reuse its buffer after acceptance. Progress
protects the queued record and only then sends it; sequence numbers advance
only after successful protection. Close discards pending bytes and wipes the
queue. Keep servicing an accepted send until completion; acceptance alone is
not a delivery acknowledgement. Four queues add 64 KB of plaintext storage.
Compositions without a cooperative driver keep synchronous progress behavior.

Physical capture 296 passed 217 independent-vector cases, including encryption,
decryption, in-place buffers, cancellation/restart and shared scratch changes
between every step. The maximum observed call was 673 us. The fixture's old
one-past-end initialization was corrected, and the expanded suite re-ran the
original cases. Captures 297 and 298 passed copied-buffer/connection isolation,
queue wiping and cooperative hook/context checks.

Build 432 was installed with a verified 431 backup, one reset, a 90-second boot
interval and live-image hash verification. Capture 301 sent 32,768 bytes to an
HTTPS echo endpoint and checked every echoed byte: 815 ms overall, 6,733 us
maximum WebClientStep and 3,154 us maximum service call. The first request
without User-Agent received HTTP 402 and is retained as a failed qualification;
the request with User-Agent passed. This does not establish the server's reason
for rejecting the first request. Capture 300 passed gzip/deflate contents with
a 3,603 us largest observed call. Its cancellation checker originally assumed
one progress call could not get past resolving; a cached lookup can reach TCP
connecting. The corrected checker permits connecting/handshake states while
still requiring successful close and rejection of the stale handle. The original
failed check and corrected recheck are retained separately.

These measurements are not worst-case guarantees. Cold file opening and link
waits remain blocking work; IPv6 web traffic and HTTP/2-3 remain open.


## Cold root-file opening: buffered exFAT checksum

Build 433 reads the exFAT up-case checksum input in 512-byte blocks instead
of repeating stream and cluster lookup for every byte. It still checks every
byte with the same checksum and rejects a short or failed read. The shared
filesystem change benefits all callers; it does not add a TLS-specific cache.

On the physical Pi, the in-memory filesystem regression passed, as did ten
checksum lengths through 32 KB and an injected read failure. The 8 KB case
fell from 13,324 to 358 microseconds, and 32 KB from 181,785 to 1,671
microseconds. These synthetic chained-volume timings are not USB timings.
The first fixture mistakenly left caches disabled and the board restarted
after recording a return; that run is retained as failed qualification.
The corrected fixture returned cleanly in 1.7 seconds with capture and health
checks passing. The legacy fixture arrays were sized to their intended counts.

With the same live root-file/HTTPS probe after boot, the first file-open call
measured 18375 us on 432 and 16484 us on 433. Gzip/deflate contents and connection
cancellation passed. This reduces one part of cold-open work; mount/read
ownership and synchronous device/link waits still prevent a fully nonblocking
claim. No IPv6 web or HTTP/2-3 completion is implied.

The candidate update initially hit a full boot partition. The current boot
image was untouched. Two obsolete candidate copies were matched against their
local archives before removal; recovery backups were retained. Candidate,
boot file and running build 433 were then verified by full hashes.


## Buffered exFAT up-case validation (build 434)

The two remaining mount-time up-case parsing passes now use a 512-byte word
window. Each pass invalidates that window before starting, so a different
mount or a checksum pass cannot leave it with stale bytes. Full structural,
skip-count, end-of-table and mandatory ASCII-mapping checks remain. Runtime
filename lookups keep their existing path. The fast mapping array now explicitly
contains all 256 entries that its parser populates.

The physical regression passed, along with compressed runs crossing a block
boundary, the final literal U+FFFF, truncated tables, zero/oversized skips,
trailing bytes, bad mandatory mappings and injected read failure. For a
synthetic 8,196-byte table the validation pass fell from 13,200 us to 315 us;
this is an in-memory chained-volume measurement, not an I/O latency bound.

The same cold root-file/HTTPS probe measured 16484 us on 433 and 14288 us on 434
for its first open. Gzip, deflate and cancellation passed. Installation retained
recovery backups and verified the candidate, boot image and running image by
hash; startup waited 90 seconds before readiness checks. Cores, fonts and Vulkan
remained healthy. Device waits and mount ownership are still synchronous;
this is reduced blocking work, not completion of nonblocking networking.


## Wi-Fi transmit credit primitive (build 435)

The shared CYW43 driver exposes `Cyw43TrySend(length)`. Callers stage their
Ethernet frame through the existing data-buffer API. The new operation validates
length, checks firmware credit once, then attempts at most one bus transfer.
`CYW43_IO_AGAIN` means no credit: the operation has not modified the TX buffer,
advanced the sequence or attempted a transfer. A bus failure is returned without
replaying the frame. The existing `Cyw43Send` compatibility API shares this code
and retains its bounded credit wait.

Fourteen physical Pi CPU cases passed: minimum and maximum frames, padding,
sequence wrap, closed/stale/ambiguous credit windows, invalid lengths, bus
failure, successful credit acquisition and timeout. The independent oracle checks
the entire transmit buffer and counters. Credit and bus outcomes are controlled
in this fixture; it is not a physical SDIO fault-injection test. The tested source
is retained verbatim; only explanatory comments moved afterward.

Build 435 was installed with a verified 434 recovery image, and its running image
was verified by hash after a 90-second boot interval. Live HTTPS gzip/deflate and
cancellation tests passed; cores, fonts and Vulkan remained healthy.

This primitive is shared by targets using the CYW43 driver. It is a prerequisite
for queued transmission, not a claim that the networking callers are now
nonblocking. Existing callers still use the synchronous API, and the bus transfer
itself remains synchronous. Pending-frame ownership, queue backpressure and wired
DMA completion must be integrated before removing those waits. Actual IPv6 web
traffic and HTTP/2-3 remain unfinished.


## Owned transmit FIFO qualification

`Anvil/Network/link_tx_queue.pbi` provides a shared, device-independent queue
for cooperative link transmitters. Each caller-owned 6,224-byte context holds
four copied Ethernet frames. Submission distinguishes accepted, full and invalid
requests; acceptance is not transmission. A consumer observes one head and
completes it with a generation and ticket. Would-block preserves the head;
success or a terminal transfer error retires it and wipes its storage. A reset
requires a newer generation and reports the number of discarded frames. Stale
completions cannot consume a packet belonging to the new generation.

The physical Pi test passed 33 operations, with independent comparisons of every
queue byte after each operation. It covers maximum frames, caller-buffer reuse,
full queues, ring wrap, failed transfers, repeated/stale completions, invalid
lengths, input aliasing, two independent contexts, generation changes and wiping.
The test returned normally; core, font and Vulkan health checks passed.

This queue is not yet installed in the live networking pumps. A consuming driver
must release its access to a frame before completion or reset: a DMA driver that
retains the supplied pointer requires a separate hardware-completion owner.
The existing GENET synchronous path retains the caller pointer and compares its
wrapping consumer counter with a plain `>=`; both ownership and wrap-safe
completion need addressing during integration. No wired hardware fix is claimed.


## GENET transmit ownership and wrapping completion (build 436)

GENET now copies each packet into a private 64-byte-aligned DMA buffer. A timed-out
caller can reuse its original storage without changing bytes that hardware may
still read. `GenetTrySend` submits without waiting; `GenetPollSend` checks the one
outstanding descriptor. Another submit cannot overwrite the owned buffer until
completion. A successful DMA disable/flush releases ownership; any failed stop
retains it. A failed producer write is treated as ambiguous and retains ownership.

Completion now requires the consumer index to equal the single outstanding
producer goal. The previous plain `>=` comparison falsely completed a wrapped
goal of zero while the old consumer remained 65,535. The synchronous compatibility
API uses the same submit/poll implementation and still has its bounded wait.

Twenty-one physical Pi CPU checks passed with controlled register outcomes,
covering counter/descriptor wrap, caller-buffer mutation, busy refusal, one-time
completion, ambiguous publication, register failure, timeout, failed/successful
DMA stop, maximum frames and invalid inputs. Exact retained buffer bytes were
checked. These are not Ethernet-wire or physical DMA fault-injection results;
the bench currently carries traffic over Wi-Fi. The change belongs to GENET's
hardware-specific backend, while the owned FIFO remains shared across targets.

Build 436 was installed and verified by running-image hash after the full boot
interval. Actual Wi-Fi HTTPS gzip/deflate and cancellation tests passed, along
with core/font/Vulkan health checks. Queue-to-driver integration, other backends'
completion ownership, SDIO waits, IPv6 web traffic and HTTP/2-3 remain unfinished.


## Live Wi-Fi protocol transmit queue (build 438)

Protocol sends and receive-generated replies now enter the same optional shared
submission interface. Both network pumps progress pending frames before/after
receive work. The CYW43 provider owns copied frames and attempts one head at a
time, without polling for credit or consuming receive traffic. Its public
`Cyw43CanSend` query leaves unavailable-credit submissions untouched. The SDIO
transfer itself remains synchronous.

The provider is composed into both Pi 3 and Pi 4/5 board roots. Pi 3 monitor 59
compiled successfully; physical acceptance here is on the Pi 4. Other hardware
kinds retain their existing backend. Console text output retains its synchronous
drain contract; protocol replies dispatched by that service use the queued path.

Address, radio transport/rejoin and readiness generations invalidate old pending
packets. Four slots provide explicit backpressure; a 100 ms packet deadline
expires stale work without a blocking wait. Terminal bus failures retire a frame
without replay. `net` reports pending, completed, dropped and credit-busy counts.
These distinguish accepted submissions from completed transfers.

All 26 physical adapter cases passed, including copied packet bytes, busy credit,
FIFO order, a full queue, address/radio/down transitions, wrapping deadlines,
backend fallback and bus failure without replay. An initial layering check
rejected a private readiness-helper call; the public API version passed the gate
and the physical suite. The final Pi 4 monitor is 438, with verified recovery and
running-image hashes and healthy core/font/Vulkan checks.

Actual gzip/deflate HTTPS and cancellation passed with
119 additional queued completions
and no added queue drops. A 32,768-byte HTTPS POST was echoed byte-for-byte by the
server with 134 additional queued
completions and no added drops. That run measured 727 ms overall,
maximum step 6695 us and maximum service 3503 us;
these are observations, not worst-case bounds.

Remaining work includes SDIO/device waits, other transmit backends, synchronous
console/storage paths, actual IPv6 web traffic and HTTP/2-3. This removes Wi-Fi
credit polling from the integrated protocol path, not all networking blocking.


## GEM submit/completion ownership (Pi 5 compile 439)

The RP1 GEM Ethernet driver now provides `GemTrySend` and `GemPollSend`.
Submission copies and pads the packet into driver-owned DMA storage, then returns
without waiting for wire completion. Only one descriptor is outstanding. Pending
or ambiguously published work keeps ownership; another request cannot overwrite
its buffer. Completion reads USED and status once, retires the descriptor once,
and counts only successful sends. The old `GemSend` API remains a bounded wait.

Replacing the DMA region is refused while started or while an unsuccessful stop
leaves ownership outstanding. Successful checked stop releases it; start verifies
that stop before rebuilding the rings. The timeout diagnostic now distinguishes
requesting a stop from proving it. These are backend prerequisites: the Ethernet
link adapter still calls the synchronous compatibility API.

All 27 checks passed on the physical Pi 4 CPU using controlled GEM register and
cache callbacks, including exact owned bytes, padding, maximum frame, caller reuse,
busy refusal, status failures, ambiguous submission, ring wrap, transmit faults,
and failed/successful stops. This does not qualify physical RP1 DMA or Ethernet
wire behavior. Evidence is in `docs/evidence/anvil-tls-jobs-20261029/gem-send430`.

Full Pi 5 build 439 passes after correcting two existing board-composition errors:
a hard-coded Pi 4 chip identifier and a payload network ABI flag confined to the
Pi 4 branch. The compiler target now supplies the chip and both branches declare
the included network ABI. Full Pi 4 build 440 also passes. Neither new monitor
was installed: the bench remains on verified Pi 4 build 438, healthy after the
returning test. IPv6 web traffic and HTTP/2-3 remain open, as do the remaining
synchronous device, console and storage paths.


## Shared DMA transmission service (installed Pi 4 build 441)

Ethernet protocol traffic now uses the same service-loop hook as queued Wi-Fi.
The new shared DMA queue calls bounded backend submit/completion callbacks;
one progress call submits or polls at most one head. It does not wait for the
wire, poll the PHY, or consume received packets. Pi 4 binds GENET, Pi 5 binds
GEM, and the queue policy has no hardware dependency. Other targets can bind
the same copy-owning completion contract.

Frames remain pending after driver acceptance and are counted complete only
when polled. Full queues refuse new work. A 100 ms deadline and address/device/
readiness changes retire obsolete queued packets. The driver retains its own
copy until completion or checked stop, even after the queue drops a request;
there is no ambiguous retransmission or overwrite of DMA-owned storage.

A board completion latch preserves the queued result when synchronous console
output harvests it before sending its own packet. Console output may still
wait, and queued protocol output can interleave with it. It cannot steal the
completion or substitute the outcome of its later frame. Short frames are
zero-padded to 60 bytes before the GENET backend.

All 31 physical Pi CPU cases passed with controlled driver outcomes, including
FIFO/full behavior, exact copied bytes, console interleaving, completion failure,
address/device/down changes, timer wrap, deadlines and ambiguous submissions.
These do not establish Ethernet wire behavior: the current bench uses Wi-Fi.
Full Pi 4 build 441 and Pi 5 build 442 compile; only 441 was installed, with
verified backup, candidate, boot-file and running-image hashes. After a full
90-second boot interval, core/font/Vulkan and networking checks passed. Live
Wi-Fi HTTPS gzip/deflate, cancellation and exact 32 KiB upload echo passed through
the new combined dispatcher. Detailed measured counters are in the evidence.

Remaining work includes synchronous device/storage/console paths, live Ethernet
qualification, IPv6 web traffic and HTTP/2-3. This is not a claim that all Anvil
networking operations are nonblocking or that the networking task is finished.


## IPv6 address endpoint qualification

The shared `ipv6_endpoint.pbi` now owns one caller-provided address through
explicit tentative, preferred, duplicate and failed states. DAD probes require
confirmed transmit completion followed by the retransmit interval. A queued
packet alone cannot assign an address. Failed/ambiguous sends fail the address;
not-sent results permit retry. Generation checks reject stale completions.

The endpoint validates Ethernet and IPv6 destinations, delegates ND validation
to the shared codec, detects duplicate NS/NA traffic while tentative, answers
neighbor solicitations for an assigned address, and produces byte-exact unicast
ICMPv6 echo replies. Tentative addresses never answer ordinary traffic. Caller
storage is bounded and checked for overlap; no RX pointer is retained.

All 42 physical Pi CPU cases passed with independently constructed packet bytes,
checksums, state expectations and output guards. They cover probe retry and
completion, two-probe timing, stale/double acknowledgements, conflicts, tentative
silence, neighbor replies, echo payloads, checksums, destination filtering and
alias refusals. This qualifies endpoint code, not live IPv6 connectivity.

Interface binding is next: the caller must join all-nodes and solicited-node
multicast before starting DAD, suppress local loopback appropriately, supply a
random initial delay, and reinitialize on interface generation changes. The live
Pi radio reports `allmulti = 0`; multicast acceptance/membership must be handled
before enabling this endpoint. Address configuration, routes, TCP IPv6 endpoints
and web transport binding remain incomplete. No new monitor was installed for
this isolated CPU test; the Pi remains healthy on build 441.


## Individual protocol transmit results

`LinkSendTracked(kind, frame, bytes)` returns a positive receipt for an accepted
packet, zero for refusal, or -2 when that link has no receipt provider. Unlike
`LinkSendFrame`, this path has no synchronous fallback. `LinkTxReceipt` returns
0 pending, 1 driver-completed, -1 failed, or -2 stale/unknown/expired. The caller
must retain the link kind with its receipt and service `LinkTxProgress`.
Completion is the driver's reported outcome, not proof of remote delivery.

Receipts carry a queue generation and ticket. Four retired outcomes are retained
separately from four pending packets; promptly poll them. Expiration or an
interface/address/device change cannot become a success or authorize replay of
an accepted packet. A receiver may have seen a packet whose outcome is unknown.
The queue layout version changed; contexts require the new size constant.
No caller-owned receipt pointer is retained. Calls remain serialized.

Shared Wi-Fi and DMA providers expose this contract, with Pi 3 Wi-Fi and Pi 4/5
board dispatch installing the hooks. Other boards without a provider explicitly
return unsupported. IPv6 can now inspect its own DAD probe instead of guessing
from aggregate completion counters; multicast and live endpoint binding are
still required before IPv6 web traffic is available.

Physical Pi CPU qualification passed 102 FIFO/receipt cases, 39 Wi-Fi provider
cases and 44 DMA provider cases, with controlled bus/driver outcomes. Existing
frame-copy, padding, queue, timeout and console-interleaving coverage remains.
Pi 4 build 443 and Pi 3 build 60 compile. These images were not installed in this
step; the bench remains on 441. No new Ethernet-wire or IPv6-web pass is claimed.


## MLD wire codec for multicast membership

The shared `ipv6_mld.pbi` builds MLDv2 any-source current-state, join and leave
records, plus compatible MLDv1 Report and Done packets. Reports contain a
Hop-by-Hop Router Alert, hop limit one and the ICMPv6 pseudo-header checksum.
The caller may use an unspecified source before acquiring a link-local address;
it must choose the assigned link-local source once available. All-nodes and
interface-local groups are not emitted as reportable memberships.

Query validation supports v1/v2 lengths, exponential v2 response and interval
fields, source-list bounds, and checksum-covered trailing data. Invalid router
sources, hop limits, missing/duplicate/incorrect Router Alerts, malformed source
lists and bad checksums are refused. Failure leaves the output view unchanged;
a successful view borrows packet storage. Interface destination ownership is
checked by the caller, allowing queries addressed to its unicast address.

The codec is independently implemented from RFC 9777, RFC 2710 and RFC 3590
protocol facts. Physical Pi CPU cases compare output bytes and guards against
independent packet construction. These tests do not establish live membership:
listener timers, version compatibility state, retransmission, device filters,
receive dispatch and endpoint binding still need integration. Anvil 441 remains
installed; no new monitor or reset was needed for this codec qualification.


## MLD interface compatibility policy

`ipv6_mld_policy.pbi` tracks the interface generation, protocol version, older
querier deadline, robustness and query intervals. A valid v1 general query
enters or refreshes v1 compatibility; a group-specific query does not switch the
whole interface. V2 queries cannot end an active v1 compatibility interval.
Expiry returns the interface to v2, including when no packets arrive: the caller
must call `IPv6MldInterfaceTick` from its service loop.

The caller tracks both generation and revision. A version transition increments
the revision so all pending query responses and retransmission timers can be
canceled before another report is emitted. A new generation resets interface
state and requires the same cancellation. The policy owns no group timers and
retains no packet pointer. Invalid packets, stale calls and backwards time leave
its state unchanged. Wire query intervals are converted from seconds to
milliseconds, with defaults for zero robustness and interval fields.

MLD source validation now requires the canonical `fe80::/64` prefix rather than
accepting the entire reserved `fe80::/10` range. The expanded physical Pi CPU
fixture passed 65 codec and policy cases, including exact expiry, refresh,
interleaved v1/v2 queries, malformed input and unchanged-state refusals.
Per-group scheduling, report retransmission, device filters and live IPv6 binding
remain outstanding; no live multicast or web-connectivity claim follows from
these CPU tests. The bench remains on Anvil 441.


## Owned MLD query source lists

`IPv6MldMergeSources` stores a bounded, unique unicast source set in caller-owned
memory. It removes duplicate inputs, preserves first-seen order, and validates
the entire union before writing. Invalid entries, aliasing and capacity overflow
leave existing storage unchanged. No received-packet pointer is retained.

`IPv6MldSourceReport` emits MODE_IS_INCLUDE records for source-specific queries
received by an any-source listener. Between one and 89 source addresses fit in
the 1500-byte IPv6 packet bound. The builder checks capacities and overlap before
writing, includes Router Alert, and checksums the entire source list. An empty
source set requires no response and is refused by this emission function.

The expanded physical Pi CPU fixture passed 89 checks, retaining codec and
interface-policy coverage and adding source unions, exact MTU output, duplicate
handling, atomic overflow and unchanged-buffer guards. Per-group scheduling and
live receive/filter integration remain outstanding. Anvil 441 remains installed;
these tests establish source-list behavior, not live multicast or IPv6 web traffic.


## Per-group multicast report scheduling

`ipv6_mld_group.pbi` now owns any-source membership scheduling for one group.
It tracks delayed query responses, pending source unions, join/leave repeats,
interface revisions and one outstanding transmit token. The caller supplies
randomized delays, validated input, owned source storage and service-loop calls.
A positive Step result is only packet preparation: Sent consumes a repeat only
on matching driver completion. Definitely-unsent work remains pending; an
ambiguous failure marks the membership failed until generation reinitialization.

Query and membership revisions are separate from the transmit token. A newer
query or join/leave change arriving during transmission survives the older
completion. General/group queries clear source filtering; source-specific
queries merge owned source sets and emit INCLUDE responses. Interface revision
changes cancel pending work and make old acknowledgements stale. No RX pointer
is retained, and output cannot overlap context or source storage.

In v1 mode, validated reports from other nodes can suppress pending reports.
The caller must exclude local loopback and validate the exact group first.
Every v1 leave emits one Done message; no optional Done-suppression setting is
required. Join repetition uses the v1 delay bound; v2 uses the v2 bound.

All 57 final physical Pi CPU scenarios passed, covering early/due timers,
unsent/retry, stale/duplicate completion, changes and queries during transmission,
v1 suppression, Done emission, revision cancellation, atomic source overflow,
backwards time and output/context overlap. Packet bytes and owned lists were
checked independently. This scheduler is not yet connected to live multicast:
receive-side report validation, device filtering, membership ownership and
network-loop binding remain. Anvil 441 remains installed and healthy.


## Incoming multicast report validation

`IPv6MldHeardReport` validates a received v1 report against an exact group
before the membership scheduler may suppress its own pending response. It
checks link-local source, hop limit one, Router Alert, destination, reported
group and checksum, and rejects reports from the local assigned address.
Unspecified-source reports do not suppress responses. The caller must also
exclude local Ethernet loopback and only invoke v1 suppression in v1 mode.
Code and reserved fields are ignored; trailing bytes remain checksum-covered.
No packet pointer escapes and validation changes no membership state.

The expanded 110-case packet/policy/source-list suite passed on physical Pi 4
under Anvil 441, including 21 receive-report cases. The RAM payload returned
normally; cores, fonts and Vulkan remained healthy. This adds the receive
validator but does not yet connect multicast membership to live device filters
or the network service loop. IPv6 web traffic and HTTP/2-3 remain unfinished.


## Shared IPv6 ingress dispatch

`NetSetIPv6InputHook` connects the common `NetInput` path to an IPv6 owner.
IPv6 frames now reach that owner before the IPv4-only destination filter.
Unicast must target the interface MAC; multicast must match the 33:33 mapping
of the IPv6 destination (RFC 2464 section 7). The owner still validates exact
IPv6 address membership, packet checksums and protocol state. Registration is
optional; without it IPv6 remains ignored. IPv4 and ARP retain their path.

The callback receives interface, frame, size, output buffer and capacity. It
returns zero, a negative error, or a complete 54..1514-byte Ethernet reply.
Reply size, EtherType and source MAC are checked before staging for the
existing automatic reply dispatcher. The callback must not retain RX pointers
or pump the network recursively; registration changes during delivery refuse.
IPv6 transport delivery belongs inside the IPv6 owner, never in stale IPv4
UDP/TCP receive coordinates. `NetLastProto` reports 0x86DD for this path.

All 23 physical Pi ingress cases passed with the real IPv6 endpoint, including
byte-exact echo/neighbor replies, bad checksums, multicast mapping, unjoined
groups, interface identity, invalid output contracts and handler replacement.
Existing IPv4 echo checksums/payload/padding and ARP reply bytes passed too.
The initial oracle expected unpadded IPv4/ARP frames; correcting it to Ethernet's
60-byte minimum passed against the unchanged captured payload results, without
repeating the board run. Anvil 441 returned normally with healthy cores/fonts/
Vulkan. This qualifies the receive seam; device filters and a resident IPv6
membership/service owner still need binding before live IPv6 traffic works.


## CYW43 multicast filter controls

`Anvil/Net/cyw43_multicast.pbi` provides bounded, serialized control-plane
operations for the existing shared CYW43 driver. `Cyw43MulticastSet` writes a
complete unique multicast MAC list (zero clears it); `Cyw43MulticastGet` copies
a validated list into caller-owned storage without exposing the borrowed RX
buffer. The 29-entry limit fits the existing 192-byte firmware argument buffer.
Invalid counts, unicast/broadcast MACs, duplicates, malformed/truncated replies,
insufficient output capacity and output overlap with driver scratch refuse.
Get refusals leave caller output unchanged. The owner must preserve memberships
belonging to other protocols when replacing the complete hardware list.

`Cyw43NeighborOffload` controls only `ndoe`; it leaves IPv4 ARP offload untouched.
A host IPv6 service can disable it before host-owned neighbor discovery. Calls
accept 1..100 ms deadlines and propagate busy, pending, timeout and firmware
errors. They do not change allmulti or promiscuous mode. Firmware acceptance
alone is not proof of multicast reception, and settings must be renewed after
a radio generation change.

The physical Pi CPU qualification passed all 45 cases through the real
CYW43 iovar serialization procedures, with controlled firmware/transport replies.
Exact command bytes, little-endian list counts, copied output and unchanged
output on refusal were checked independently. Anvil 441 returned normally,
cores/fonts/Vulkan healthy. These controls are not yet composed into the monitor
or exercised against the live radio; resident ownership and generation-aware
integration remain before IPv6 web traffic is available.


## Resident IPv6 link-local service: live Wi-Fi qualification

Anvil 444 now composes a shared host lifecycle and resident service with the
CYW43 multicast adapter. The adapter preserves existing multicast memberships,
adds all-nodes and solicited-node filters, verifies readback, then disables and
checks firmware neighbor offload. IPv4 ARP offload remains unchanged.
The host waits for a confirmed membership-report transmission before starting
randomized duplicate-address detection. Generation changes discard stale
receipts. Query sources and pending state remain in owned storage; receive
callbacks never configure the radio or recursively pump receive traffic.

The shared host lifecycle passed 40 physical Pi CPU cases, including pending,
unsent and stale completions, DAD conflicts, version changes, time bounds and
exact echo/neighbor reply bytes. The installed build 444 was checked against
its full image SHA-256 after a 90-second boot interval. Its live Wi-Fi address
answered all four Windows IPv6 link-local pings, with no loss (69-109 ms).
The IPv4 console, cores, font slots and Vulkan remained healthy.

The implementation is shared; Pi 4/5 composition enables the CYW43 adapter.
Pi 3 build 61 compiles the composition but does not activate it without a
resident entropy provider. Other link drivers still need multicast-filter
adapters. This is link-local neighbor discovery and echo, not IPv6 web access:
router discovery, routed addressing and TCP integration remain open, alongside
remaining TLS waits and HTTP/2-3. The verified build 441 recovery image is
retained on the Pi boot volume.

The final source exposes shared validation helpers through named public APIs.
Its rebuilt 40-case qualification image is byte-identical to the tested image.
Full monitor build 445 differs from installed 444 only in fourteen MOVZ
instructions carrying build-number/time constants (21 bytes); no protocol
code changed. Build 445 was compiled and compared, not installed.


## SLAAC lifetime policy

`Anvil/Network/ipv6_slaac.pbi` provides caller-owned per-/64 address lifetime
state, independent of the interface driver. `IPv6SlaacInit` copies the prefix
and interface identifier. `IPv6SlaacApply` consumes a validated matching PIO's
L/A flags and 32-bit valid/preferred lifetimes. On-link routing and autonomous
address lifetimes update independently; absence of L does not withdraw a route.
Malformed autonomous preferred lifetimes do not discard valid L information.

RFC 4862's two-hour reduction rules apply to an existing valid address, while
preferred lifetime always follows the accepted autonomous advertisement.
Infinite lifetimes are explicit; the largest finite wire value converts to
milliseconds without 32-bit overflow. Generation, clock, alias and argument
refusals leave the old state intact. Status reports lifetime eligibility,
not DAD success. A newly created or recreated address returns 1 so its owner
must run DAD before use. Only actual authenticated router advertisements may
set the authentication flag; Wi-Fi encryption or a known router is insufficient.

All 38 physical Pi CPU cases passed on installed Anvil 444, checking exact
state, address bytes and untouched record guards. The payload returned normally
with cores, font slots and Vulkan healthy. This shared policy is not yet wired
to live router advertisements. PIO decoding, router/prefix tables and resident
address ownership still precede routed IPv6 TCP and actual web requests.


## Router Advertisement copy-out codec

`Anvil/Network/ipv6_router.pbi` validates Router Advertisements through the
shared Neighbor Discovery parser, checks all-nodes or assigned-unicast
addressing, and copies router configuration and prefix records into caller-owned
storage. No output retains a pointer into receive memory. Every refusal leaves
both output spans unchanged, including insufficient prefix capacity.

The 88-byte router record contains the source address, optional MAC, hop limit,
flags, router lifetime, reachability/retransmit values, usable advertised MTU
and prefix count. Zero configuration fields remain zero for the owner to treat
as unspecified. Each 56-byte prefix record carries length, independent L/A
flags, valid/preferred lifetimes and a normalized network prefix. Records keep
wire order and repeated prefixes; non-/64 lengths remain available for routing.
The owner applies SLAAC identifier-length and lifetime rules separately.

Unknown options, unusable PIOs and out-of-range MTUs are ignored. Structural
option errors, wrong hop limit, checksum failures and ND fragments refuse.
Valid MTUs must be within 1280 and the caller's link ceiling. The last usable
MTU wins without an invalid later value erasing it. Prefix host bits are masked,
including non-octet and zero-length prefixes; link-local/multicast prefixes are
not installed from PIOs. This codec does not install routes or assign addresses.

All 45 physical Pi CPU cases passed on Anvil 444 with exact copy-out bytes and
unchanged output/guard checks. The payload returned normally, and cores, fonts
and Vulkan remained healthy. Resident router/prefix tables and solicitation
scheduling are still required before routed IPv6 TCP and web requests.


## Shared default-router list

`Anvil/Network/ipv6_default_routers.pbi` owns generation-scoped default-router
state in caller-provided storage for 2..16 entries. Each router has an independent
expiry and preference. Updates preserve omitted routers; a full list declines a
new router without evicting a live one. Zero lifetime withdraws only the named
router. Expiry and changes to membership/preference advance a revision so the
owner can invalidate cached next hops. Refreshing an unchanged router's deadline
does not require a new next-hop choice.

Selection prioritizes reachability, then advertised preference, and rotates
among equal-ranked entries. The caller marks only known-unreachable neighbors;
unknown reachability is assumed reachable. Reserved preference bits mean medium.
The selection result includes a mask of avoided higher-preference failed routers
for the owner to probe when sending actual traffic, subject to the RFC 4191
one-probe-per-minute limit. The table itself never sends packets or reads clocks.
Neighbor-cache updates, probe rate limiting and resident dispatch remain with
the integration layer.

All 34 physical Pi CPU cases passed on installed Anvil 444: insertion, refresh,
withdrawal, independent exact expiry, full-table retention, preference/failover,
equal-rank rotation, generation reset and invalid argument preservation. Exact
router slots, revisions and output guards were checked. The payload returned
normally, with healthy cores, fonts and Vulkan. This policy is not yet wired to
resident RA input or outbound IPv6 connections.


## Resident router discovery on Wi-Fi

Installed Anvil 447 integrates RA copy-out and the four-entry default-router
list into the shared resident IPv6 service. Once link-local DAD succeeds, the
service sends a randomized Router Solicitation and tracks its driver receipt.
Unanswered solicitations are spaced at least four seconds after confirmed
completion, with at most three confirmed sends. A valid RA with nonzero router
lifetime stops further sends after at least one solicitation has completed;
zero-lifetime advertisements do not stop discovery. A generation change clears
pending receipts and learned state. Control frames use the existing tracked
link queue, without recursive receive pumping.

Valid live RAs update independent default-router lifetimes and nonzero hop,
reachability, retransmit and MTU configuration. The latest prefix records are
copied into owned storage for subsequent address-management integration. They
are diagnostic snapshots, not a complete installed prefix list. `net` now
reports RA count, errors, confirmed solicitations, live default routers and
whether address configuration remains pending.

On the physical Pi 4, the final image was hash-verified after a 90-second boot
interval. The service confirmed one solicitation and learned the LAN's IPv6
default router and an advertised prefix. IPv4 console, cores, fonts and Vulkan
remained healthy. Build 446 first demonstrated live RA reception; build 447
corrected zero-lifetime/early-advertisement solicitation stopping and added the
confirmed-send diagnostic. Pi 3 build 63 compiles the final shared composition,
but activation still awaits its resident entropy provider. Pi 4/5 share the
active CYW43 composition; other link adapters remain unfinished.

This establishes live router discovery, not routed web access. Prefix-table
union, global-address DAD/membership, neighbor-cache ownership and IPv6 TCP/DNS
integration remain required. The existing TLS and HTTP/2-3 gaps remain open.


## Persistent on-link prefix policy

`Anvil/Network/ipv6_prefix_list.pbi` merges validated on-link advertisements
into a caller-owned, generation-scoped table with 1..64 entries. Prefix and
length identify entries, independently of the advertising router. Omitted
prefixes and L=0 preserve earlier information. L=1 with zero lifetime withdraws
only the matching prefix; each other entry retains its own expiry. A full list
declines a new prefix without evicting an existing live entry.

Host bits are normalized for lengths 0..128, including non-octet prefixes.
Longest-prefix matching returns length+1, distinguishing a /0 match from no
match. Infinite lifetimes are explicit and the largest finite 32-bit seconds
value converts to milliseconds without overflow. Membership changes and expiry
advance a revision; refreshing an unchanged prefix does not. The list is separate
from SLAAC address validity and preferred lifetimes. Inherent link-local routing
belongs to the interface owner; link-local and multicast PIOs are ignored.

All 36 physical Pi CPU cases passed on installed Anvil 447, including merged
information, overlap, independent expiry, withdrawal, infinite and maximum finite
lifetimes, generation reset, capacity retention, and unchanged state on invalid
arguments. Exact table bytes and guards were checked. The payload returned
normally and cores, fonts and Vulkan remained healthy. This policy is ready for
resident integration; the installed service still reports latest-prefix snapshots
and does not yet assign routed IPv6 addresses or open IPv6 web connections.


## SLAAC address ownership and duplicate-address detection

`Anvil/Network/ipv6_address_owner.pbi` combines shared SLAAC lifetime policy
with duplicate-address detection. A new address remains tentative until its
probe is confirmed sent and the DAD interval completes. Expiry, duplicate
conflicts and link generations invalidate pending receipts; late completions
cannot revive an address. Deprecated addresses retain receive service until
valid lifetime expires. Refreshing a duplicate does not make it usable.

The caller must keep link-local ownership and membership ready. This owner
copies its IID and verifies the exact solicited-node group, permitting reuse
of the existing membership only while that prerequisite holds. Independent
on-link routing policy remains separate.

All 34 physical Pi CPU cases passed on installed Anvil 447, including exact
DAD and echo packets, pending/failed/retried receipts, lifetime transitions,
conflicts, stale generations, buffer overlap and clock validation. The payload
returned normally; cores, fonts and Vulkan remained healthy. This is shared
library qualification, not yet resident address assignment or IPv6 web traffic.


## Address-owner clock boundary

The composed address owner now uses the SLAAC lifetime engine's stricter clock
ceiling before any mutation. This prevents an out-of-range timestamp from
being interpreted as an expired lifetime after the nested engine refuses it.
Both initialization and existing-owner calls reject that boundary unchanged.
All 36 physical Pi CPU cases passed on Anvil 447, including two new upper-clock
refusal cases. The payload returned normally with cores, fonts and Vulkan healthy.


## Resident SLAAC address assignment

Anvil now merges validated Router Advertisement prefixes into a persistent
on-link list and up to four independent SLAAC address owners per interface.
Each /64 address uses the confirmed link-local IID and exact solicited-node
membership. The service keeps address validity, preferred lifetime, duplicate
checks and transmission receipts separate. Omitted prefixes survive later
advertisements. Link loss or failed link-local ownership discards address use.
Non-/64 prefixes remain eligible for on-link routing without creating a SLAAC
address. Eight on-link prefixes fit per interface; full tables retain live entries.

Address work runs cooperatively between receive dispatches. Pending DAD receipts
are checked before scheduling at most one new address probe per service turn;
no nested receive pump or wait is introduced. Received Neighbor Solicitations
and echo requests dispatch to the appropriate assigned address. Router
Advertisements may target a preferred or deprecated local address. Unauthenticated
advertisements retain the RFC 4862 two-hour validity rule. Status reports show
individual tentative, preferred, deprecated, duplicate, failed or expired states.

Installed Pi 4 builds 448 and 449 learned the real router's ULA prefix and
completed DAD. Each build answered all six host IPv6 echo requests, using
32-byte and 1,200-byte payloads, with zero loss. The host neighbor entry resolved
the learned address to the Pi's actual Wi-Fi MAC. Full running-image hashes,
cores, fonts and Vulkan were checked after installation. Build 449 is the final
installed image; its verified 448 backup remains on the boot drive. The shared
composition also builds for Pi 3 (build 65); its resident IPv6 activation still
requires a board entropy provider.

This proves live address assignment and inbound neighbor/echo traffic. Outbound
neighbor-cache ownership, IPv6 TCP/DNS and web requests remain unfinished, as do
remaining TLS blocking work and HTTP/2-3. No IPv6 web result is claimed here.


## Queued neighbor resolution and reachability probes

`Anvil/Network/ipv6_neighbor_owner.pbi` composes neighbor discovery packets
with the shared reachability policy and explicit link-completion receipts.
Resolution emits a multicast Neighbor Solicitation; later reachability probes
use unicast IPv6 and Ethernet destinations. Both use the same packet encoder,
including checksum construction. The original DAD solicitation remains unchanged.

A pending send suppresses additional probes. The retry interval starts when
completion is reported. Definite queue refusal restores the wire-attempt budget
and backs off without spinning; ambiguous failure consumes an attempt. Three
wire attempts without resolution report failure so the caller can fail queued
data and invalidate dependent routes. The caller owns overall operation deadlines.
Generation and token checks reject old completions, including after a valid
advertisement or upper-layer confirmation has already established reachability.

Learned router hardware addresses start stale. Valid advertisements retain the
solicited/override/router rules, including reporting a router-to-host transition.
Input validation covers checksums, target identity, assigned IPv6 destination,
Ethernet destination, and nonzero unicast hardware addresses. The caller still
owns the bounded cache table, source assignment, data queue and route selection.

All 55 final physical Pi CPU cases passed on installed Anvil 449: exact multicast
and unicast solicitation bytes, DAD compatibility, queued/failed/refused sends,
retry exhaustion, advertisements racing completions, hardware-address changes,
router demotion, and invalid argument/generation/clock/buffer cases. The payload
returned normally; cores, fonts and Vulkan remained healthy. This shared owner
is ready for resident cache integration. Outbound IPv6 TCP/DNS and web requests
remain unfinished; this qualification does not claim live outbound web traffic.


## Resident neighbor cache and Pi-initiated IPv6 echo

Installed Anvil 450 adds eight owned neighbor entries per interface. Validated
Router Advertisement and Neighbor Solicitation hardware options seed stale
entries; advertisements and matching forward-path confirmations update
reachability. Every entry keeps its source, generation, pending link receipt
and token separately. Only unused or failed slots may be reused. Link loss
invalidates the table, and a full live table refuses new entries rather than
silently evicting active state. Probes run cooperatively between receive calls.

The explicit diagnostic `net ipv6 ping <assigned-source> <destination>` starts
one asynchronous echo. `net ipv6` shows addresses, cache entries and its result.
The source must currently belong to exactly one active interface. On-link
prefixes and link-local destinations select direct neighbors; other destinations
select a default router while considering known neighbor failures. Link-local
sources cannot cross a router. The job rechecks source, route and cache generation,
uses tracked transmission, validates the reply checksum and random echo data,
and has a ten-second total deadline. The console remains available throughout.
This explicit-source interface does not claim automatic RFC 6724 source selection.

Echo states are 0 idle, 1 resolving, 2 queued, 3 awaiting reply and 4 verified.
Errors distinguish cache capacity (-880), source/argument refusal (-881), busy
(-882), route loss (-883), link failure (-884), router demotion (-885), source
or interface loss (-886), timeout (-887), and failed/replaced neighbor (-888).
Reported elapsed time includes neighbor resolution and queueing, not just RTT.

On physical Pi 4 build 450, a Pi-initiated link-local router echo completed in
85 ms, and a ULA echo to the PC completed in 198 ms after neighbor resolution.
Both replies passed the full payload/checksum checks. An unassigned source was
refused. The PC then received all six inbound echo replies from the Pi at
32-byte and 1,200-byte payload sizes, with zero loss. Running-image hash,
cores, fonts and Vulkan passed; the verified 449 backup remains on the boot drive.
The shared composition also builds as Pi 3 build 66, with activation still
waiting on that target's entropy provider.

This proves local-link outbound resolution and echo, plus retained inbound
operation. Off-link traffic, automatic source selection, rate-limited probing
of avoided preferred routers, generic queued data, IPv6 TCP/DNS/web, remaining
TLS blocking work and HTTP/2-3 are still unfinished.


## Shared IPv6 TCP wire boundary

`Network/ipv6_tcp.pbi` emits a fixed IPv6 header around a caller-prepared TCP
segment and validates received TCP packets through the shared IPv6 parser.
It checks unicast addresses, segment bounds and TCP data offsets, calculates
the full pseudo-header checksum, and excludes extension headers and Ethernet
padding from the transport length. A computed zero checksum remains zero.
Build refusal preserves packet bytes; parse refusal preserves the borrowed
view. The endpoint still owns address assignment, routing, neighbor resolution,
socket state and link transmission.

All 28 independent wire/view cases passed on physical Pi 4 build 450, including
maximum Ethernet payload, odd lengths, MSS options, stale and zero checksums,
destination extensions, atomic fragments, rejection of fragments requiring
reassembly, corruption, truncation and aliases. Output guards remained intact.
The RAM proof returned normally; cores, fonts and Vulkan remained healthy.
Evidence is under `docs/evidence/anvil-ipv6-20261030/tcp616`.

This is a qualified transport codec, not a connected IPv6 socket or HTTP result.
The resident monitor is still build 450. Family-aware TCP socket integration,
asynchronous route resolution and actual IPv6 web traffic remain next.


## IPv6 TCP sockets and live HTTP server traffic

Anvil 451 connects IPv6 to the existing TCP state machine. Each socket saves
its address family and both 16-byte addresses across socket switches. Matching
includes interface, family, local/remote addresses and ports. Active IPv6 opens
use `TcpConnect6(kind,source,destination,port)` with an explicit assigned source.
Neighbor resolution is cooperative: the existing `NET_TCP_E_ARP` pending result
means pump and retry for either family. The callback never waits or pumps RX.
Wildcard listeners accept either family; accepted children retain their family.
Reset responses preserve the selected connection's complete endpoint, and loss
of its assigned source closes it rather than moving it to another address.

The shared service hooks validate source ownership and resolve direct on-link
neighbors or a default router. Every IPv6 send rechecks routing and neighbor
usability. IPv6 stages TCP after a 40-byte header; IPv4 keeps its existing layout.
IPv6 advertises and caps data at 1,220 bytes, the minimum-MTU baseline, until
path-MTU discovery is integrated. No separate TCP state machine was introduced.

The physical CPU passed the existing IPv4 multi-interface and upload regression
plus an IPv6 socket suite: pending resolution, active handshake, socket switching,
reset isolation, borrowed receive dispatch, data in both directions, source loss,
passive acceptance and listener rearming. These used scripted links, not live
IPv6 client traffic. The resident build also compiles for Pi 3 as build 67;
IPv6 activation there still requires an entropy provider.

Build 451 was installed with a verified build 450 backup. After a 90-second boot
interval, the complete running image hash matched. Over actual Pi Wi-Fi, concurrent
IPv4 and IPv6 connections to `http serve 8080` each reused their connection for
`/health`, `/` and `/missing`. Both returned 200, 200 and 404 with matching bodies
and correct lengths. The temporary server was stopped afterward. Cores, fonts,
Vulkan and the disabled watchdog passed the post-checks. Full evidence and final
monitor image are under `docs/evidence/anvil-ipv6-20261030/socket451`.

This proves live local-link IPv6 HTTP server traffic. Outbound IPv6 HTTP/DNS,
automatic source selection, path-MTU handling, off-link validation, remaining
TLS blocking and HTTP/2-3 are not yet complete. The legacy IPv4-named pending
error constant is retained for API compatibility, including IPv6 ND waits.


## Outbound IPv6 HTTP and ABI 1.11

Anvil 452 adds `SvcTcpOpen6(destination16,port)` in previously reserved net
slot 88. The 200-entry ABI table and all existing slots remain unchanged.
It returns an ordinary TCP handle, used with existing send, receive, state
and close operations. The destination is copied; the resident owner selects
and retains the source/interface, resolves neighbors cooperatively, and uses
the same bounded pending-open and socket-generation cleanup as IPv4.

Route selection considers the longest on-link prefix, default routers and
the selected link for equal routes. Within that outgoing interface, assigned
public source addresses are compared using RFC 6724 rules: exact destination,
appropriate scope, preferred lifetime, matching default policy label, then
common prefix capped at the configured prefix length. Tentative/expired addresses
are excluded. Anvil currently assigns neither mobile nor temporary addresses,
and does not retain router-to-prefix associations. This is source selection
for the currently owned address types, not a claim of complete dual-stack
destination ordering or configurable policy tables. Loopback, mapped and
IPv4-compatible destinations are refused by this physical-link selector.

The shared URL parser accepts bracketed IPv6 literals and retains their
brackets in HTTP Host fields. The request serializer validates the literal;
malformed brackets, ports and zone identifiers are refused. Plain HTTP can
open IPv6 literals through both kernel and payload web adapters. Payloads
read slot 88 only on ABI 1.11 or newer; older kernels continue supporting the
existing IPv4 APIs. HTTPS literals remain explicitly refused until certificate
IP-address verification and the TLS connection adapter are integrated.

Physical Pi validation passed 47 URL cases, 20 source-selection/request-wire
cases and the eight existing HTTP lifecycle scenarios. Redirect and upload
builders compile with the shared address dependency. The complete resident
composition also builds for Pi 3 as build 68, with its IPv6 entropy prerequisite
unchanged.

Using the actual resident ABI on physical Pi 4 build 452, a returning payload
fetched `http://[fd3f:f605:b7f1:cfd6:f0d4:2621:4d4:d168]:18080/ipv6-proof`
from the PC over Wi-Fi. Anvil automatically chose its assigned ULA source.
The PC verified the exact 101-byte request, including bracketed Host authority.
The Pi received HTTP 200 and all 20,000 body bytes with the expected SHA-256;
the complete response was 20,101 bytes and took 281 ms from client start to
completion. Report guards were unchanged. The temporary PC server was removed,
and the Pi returned with healthy cores, fonts, Vulkan and disabled watchdog.
The running 452 image was hash-verified after a 90-second boot interval; a
verified 451 rollback image is retained. Evidence and final image are under
`docs/evidence/anvil-ipv6-20261030/client452`.

Live local-link HTTP now works in both directions over IPv6. AAAA DNS and
dual-stack selection, IPv6 TLS/literal certificate verification, scoped URI
zones, off-link validation, path-MTU handling, remaining TLS blocking and
HTTP/2-3 are still incomplete.


### Shared AAAA DNS codec qualification

The shared DNS codec now provides DnsBuildQueryType and DnsParseReplyTypeFor
for A and AAAA records. Existing A-only entry points retain their signatures.
AAAA answers preserve all 16 network-order bytes through DnsResultIp6; query
name/type matching, CNAME ownership and minimum TTL checks share the existing
parser. Wrong-family and failed results cannot expose stale addresses.
Query building now refuses oversized labels and wire names before writing
them, including the 255-byte wire-name boundary.

Physical Pi 4 build 452 ran the new codec in a returning RAM payload: 45 reply
cases, eight query-boundary cases, and five existing cache cases passed.
Evidence is in docs/evidence/anvil-ipv6-20261030/dns653. This qualifies the codec;
the resident DNS owner and web adapter still need AAAA integration. The boot
image remains 452, and this codec change has not been installed in that image.


### Resident AAAA resolver: ABI 1.12

Build 453 installs SvcDnsResolve6(name,destination16) in reserved slot 89.
A successful call copies 16 network-order bytes and returns 16. Pending,
busy and error results preserve caller output; callers continue to pump the
network service. Existing IPv4 resolution and the 200-slot table are unchanged.
A and AAAA queries share the cooperative DNS owner, retry deadline and TCP
fallback. Cache keys and in-flight identity now include the requested type,
so one hostname can retain both address families without cross-delivery.
Each family currently exposes the first matching answer; multi-address
connection racing and destination ordering are not yet implemented.

The physical Pi passed 45 codec reply cases, eight query-boundary cases,
five legacy cache cases, twelve typed-cache assertions, 32 TCP fallback
scenarios, and nine pending-type/output assertions. One host test expectation
incorrectly used -100 for SVC_EARG; it was corrected to the ABI's -102, and
the original board report was rechecked without a redundant board run.

The complete monitor also builds for Pi 3 as build 69. Pi 4 build 453 was
installed with a verified 452 rollback, allowed 90 seconds to boot, and checked
against its full running-image hash. The live ABI test resolved both AAAA
and A records for one.one.one.one through the configured DNS resolver, then
alternated repeat calls to verify that both cached answers remained distinct.
Full reports, compiled proofs, boot image and install checks are under
`docs/evidence/anvil-ipv6-20261030/resolver453`.

AAAA resource records are queried over the existing IPv4 resolver transport;
this does not yet provide DNS server transport over IPv6. The web adapter
still uses IPv4 for hostname resolution and IPv6 for explicit HTTP literals.
Connecting the new resolver to automatic dual-stack HTTP/TLS, multi-address
selection, off-link IPv6 validation, remaining TLS blocking and HTTP/2-3
remains open.


### Dual-family plain HTTP and explicit DNS selection

The shared HTTP transport can now resolve AAAA hostnames through ABI1.12 and
race IPv4/IPv6 connections. IPv4 starts immediately. IPv6 becomes eligible
after 250ms or IPv4 failure; both handles are polled on every subsequent step.
The winner closes the other handle, and cancellation closes both. Numeric IPv4
addresses never become AAAA queries. Older ABI1.6/1.11 bindings retain IPv4
hostname support. TLS connections retain the existing verified TLS adapter;
this change does not add IPv6 TLS.

This is an IPv4-first bounded fallback, not full RFC8305 Happy Eyeballs.
The resident resolver still serializes uncached queries, each family currently
provides its first answer, and the WebClient deadline bounds the exchange.
Parallel DNS queries and complete destination ordering remain future work.
Eighteen physical transport scenarios passed, including competing attempts,
cleanup/cancellation, busy handles, DNS contention, older bindings, literal
addresses, TLS delegation and timer wrap. The eight existing HTTP lifecycle
regressions also passed.

A source review found that an explicit net.dns setting was ignored whenever
DHCP supplied a resolver. A shared Core policy now selects the explicit
resolver on its routed interface; removing net.dns restores per-interface
DHCP selection. Invalid or unreachable explicit values return no resolver
instead of silently using another. Console DNS, payload DNS and NTP use this
one policy. It affects new lookups, without changing address leases, routes,
persisted settings or already cached/in-flight query results. Twelve physical
policy cases passed, with lease and route inputs unchanged.

On installed Pi4 build455, the real payload resolved a hostname through a
temporarily selected public DNS resolver, opened the resulting LAN IPv6 ULA,
and fetched HTTP200 with all20,000 expected bytes in450ms. The PC verified the
106-byte request and exact hostname Host header, and the complete20,101-byte
response matched its body hash. The initial run through the LAN's default
resolver produced no usable DNS answer; it is retained as a failed result,
not a pass. The explicit-resolver run also verified native console DNS.
The temporary net.dns setting was removed and the PC server closed afterward.
A separate literal-IPv6 run with the updated adapter also verified20,000 bytes.

Build455 is installed and its full live image hash checked after90seconds
of boot time. A verified453 rollback remains on the stick. Pi3build70 compiles;
cores/fonts/Vulkan/watchdog checks passed on the Pi4. Build454 was an intermediate
compile only. Evidence is under docs/evidence/anvil-ipv6-20261030/web455.

Proven here: physical library/ABI hostname-based HTTP over LAN IPv6, with
actual DNS and TCP traffic. Public off-link IPv6, DNS transport over IPv6,
IPv6 TLS, complete multi-address racing, remaining TLS blocking and HTTP/2-3
remain open. Native console HTTP command integration requires a separate
coverage audit; a library client proof must not be treated as that audit.


### Native console HTTP on the shared client

Anvil457 moves `http get` onto the shared WebClient, including its IPv4/IPv6
connection adapter and response framing. Plain HTTP still refuses HTTPS URLs;
redirects are displayed without following them. The command streams the body,
retains a bounded preview, supports cancellation and applies a30-second deadline.
Failure or completion closes the connection. It no longer uses the legacy
IPv4-only HttpGet path. The implementation is shared Core code; Pi3build72
compiles it, with physical acceptance on Pi4.

The actual procedure first passed a20,000-byte IPv6 exchange as a RAM payload.
After verified installation and90seconds of boot time, six native prompt cases
passed: IPv6 literal, IPv6 hostname, IPv4 chunked response, redirect without a
follow-up request, truncated-body refusal, and HTTPS-scheme refusal. The two
IPv6 cases received20,000 bytes. Temporary DNS selection was removed without
saving settings, and local test servers closed. The rollback is build456;
full running-image hash, cores, fonts and Vulkan checks passed. Evidence:
`docs/evidence/anvil-ipv6-20261030/native457`.

The first installed candidate456 exposed missing IPv6 neighbor progress in
the command pump and timed out before connecting. Build457 advances shared
lease/protocol services without re-entering the console dispatcher.

This closes native plain-HTTP integration coverage. At build457, TLS still needed dual-family
connection support; public off-link IPv6, IPv6 DNS transport, full multi-address
racing, remaining service stalls and HTTP/2-3 remain open.


### Shared dual-family TLS dialing

Anvil458 uses the same bounded IPv4/IPv6 connection selector for plain HTTP
and TLS. IPv4 starts immediately; IPv6 becomes eligible after 250 ms or an
IPv4 failure. Both TCP attempts are polled while DNS work progresses, and the
losing attempt is closed when one connects. Cancellation, timeout, failure and
payload return close pending attempts. Each TLS slot keeps its own dial state.
The existing hostname is retained for SNI and certificate verification. No trust
or TLS verification check was bypassed. The kernel uses direct service calls;
payloads bind the same algorithm to the existing ABI. Pi3build73 compiles the
shared implementation; physical validation was on Pi4.

Physical RAM checks passed 18 connection-selection cases, eight HTTP lifecycle
cases, isolation of four TLS slots, and seven TLS dialing/cleanup cases.
Installed build458 passed full running-image SHA, cores, fonts and Vulkan checks
after a 90-second boot interval. The verified rollback is build457.

For live IPv6 TLS, a temporary DNS server returned no A address and a LAN ULA
AAAA address for httpbingo.org. The Pi connected over IPv6 to a transparent TCP
relay, which forwarded encrypted bytes to the public server over IPv4. Anvil
itself completed TLS 1.3, verified the server certificate against its existing
root store, and received HTTP200 with the expected 100-byte body. The relay did
not terminate TLS. This proves IPv6 TLS on the LAN, not public off-link IPv6.
An ordinary public HTTPS request also passed after removing the relay, along
with all six native plain-HTTP regression cases. Temporary DNS overrides were
removed without saving settings; local servers and the relay were closed.
Evidence: `docs/evidence/anvil-ipv6-20261030/tls458`.

Still open: public off-link IPv6, DNS transport over IPv6, multiple addresses
per DNS answer and full address racing, remaining service stalls, HTTP/2-3,
and a complete managed-cookie policy. IPv6 literal certificate identities are
not added by this hostname-dialing change.


### Cold TLS storage pause qualification (build463)

Network service diagnostics now separate 14 phases and retain the phase timings
inside the slowest whole call. Root-store diagnostics measure storage readiness,
file open, read and close. On a cold Pi4, build460's 15.772 ms service maximum
contained 15.657 ms in TLS, including a 14.252 ms root-file open. This identified
filesystem mount work rather than handshake arithmetic as the dominant pause.

The shared exFAT implementation now reads each 12-sector boot region in one
bounded request, retaining checksums, signatures, reserved-byte and geometry
checks for primary and backup regions. Its up-case table uses 4 KiB read windows;
validation still resets the cache and checks the entire table. The 32 KiB table
fixture uses nine reads instead of 65. Root loading also yields after the initial
metadata open/close when its budget expires, before starting a data read. No file
handle remains open at that yield point.

| Cold physical run | Whole service maximum | Root-file open maximum |
| --- | ---: | ---: |
| build460, instrumented baseline | 15.772 ms | 14.252 ms |
| build461, boot-region batching | 9.627 ms | 8.058 ms |
| build463, 4 KiB up-case windows and initial yield | 5.641 ms | 5.495 ms |

These are observed maxima for these runs, not guaranteed latency bounds. The
final run passed certificate-verified public HTTPS gzip/deflate body checks.
A separate cold restart confirmed cancellation at the new preparation yield:
state remained preparing, close succeeded, the stale handle was rejected, and
subsequent verified HTTPS requests completed. All 120 boot-region cases passed
on physical Pi4, including 512/1024/2048/4096-byte sectors and error paths; the
full filesystem regression and buffered up-case validation also passed.

Build463 was installed with a verified build461 rollback and checked by full
running-image SHA after a 90-second quiet boot interval. Cores, fonts, Vulkan and
watchdog state passed. Pi3build77 compiles the shared changes; Pi3 was not
physically tested. LAN IPv6 TLS was rechecked using an encrypted-byte relay:
Anvil verified the public server certificate and received the expected HTTP200
body. The relay did not terminate TLS; public off-link IPv6 remains unproven.
Temporary DNS overrides and relay processes were removed.

The initial filesystem open remains synchronous (about 5.5 ms in this cold run),
so TLS blocking is reduced, not finished. Storage bring-up on an unavailable
medium is not bounded by this evidence. Public off-link IPv6, IPv6 DNS transport,
full address racing, HTTP/2-3 and complete managed-cookie policy remain open.
Evidence: `docs/evidence/anvil-ipv6-20261030/service463`, including the rejected
MMU test-harness run and its corrected physical proof.


### Shared checksum CPU cost reduction (build464)

The shared exFAT checksum accumulator now performs four byte steps per loop,
with the unsigned 32-bit rotate/add arithmetic inline. Byte loads require no
alignment. Boot checksums accumulate the same three byte ranges around the
excluded VolumeFlags and PercentInUse fields; up-case checksums use the same
accumulator across their existing 4 KiB windows. Read counts and all validation
checks are unchanged.

Physical Pi4 tests passed all 120 boot-region cases and the full filesystem
regression. The independent checksum oracle now covers 28 sizes, including
four-byte tails and window boundaries. A valid 512-byte-sector boot-region
check fell from 276.7 to 65.9 microseconds in the memory-backed fixture. The
32 KiB up-case checksum fell from 1367.9 to 617.9 microseconds with nine reads
in both runs. These CPU fixture timings do not represent disk throughput.

After installing build464 and waiting 90 seconds before readiness checks, the
same cold HTTPS probe passed verified public gzip/deflate content checks. The
observed whole-service maximum fell from 5.641 to 5.067 ms; initial root-file
open fell from 5.495 to 4.922 ms. This is about another 10% reduction in this
cold service measurement, not a guaranteed latency bound. The filesystem open
remains synchronous and is still the largest observed pause.

Build464 passed full running-image SHA, cores, fonts, Vulkan and watchdog
checks; build463 is retained as verified rollback. Pi3build78 compiles the
shared change, without a physical Pi3 claim. Temporary DNS settings were
removed. Evidence: `docs/evidence/anvil-ipv6-20261030/checksum464`. The archive
also retains the rejected first expanded fixture: its declared case list and
hardcoded emitted body disagreed. The corrected builder emits both from one
list, and the rebuilt physical run passed. Networking remains incomplete;
the remaining synchronous open and previously listed IPv6, HTTP/2-3 and cookie
policy work are still open.


### Filesystem stage attribution (build465)

Optional shared exFAT diagnostics now measure partition discovery, boot
validation, system-directory scanning, up-case checksum and decoding, ASCII-map
construction and path lookup. The standalone driver receives an optional clock
callback; it does not depend on a hardware timer or output routine. The shared
file seam binds Anvil's microsecond clock. `tls status` exposes counts, totals
and maxima; counts include failed operations that reached the timed stage.
Repeated binding of the same clock preserves accumulated measurements.

Startup had already performed some filesystem operations, so this run records
status before and after the cold HTTPS probe. Subtracting counts and totals
isolates one mount and 47 path lookups during root-store loading:

| Stage | Calls during probe | Total time |
| --- | ---: | ---: |
| Partition discovery | 1 | 0.261 ms |
| Boot validation | 1 | 1.382 ms |
| System directory | 1 | 0.829 ms |
| Up-case checksum | 1 | 0.541 ms |
| Up-case decoding | 1 | 0.487 ms |
| ASCII map | 1 | 0.192 ms |
| Path lookup | 47 | 53.699 ms |

The 47 lookups correspond to the initial metadata open and 46 bounded root-file
reads, each with its own reopen/close. Mean path lookup was 1.143 ms. Stored
maxima retain startup history and must not be presented as per-request maxima.
The observed cold root open was 4.967 ms and the whole-service maximum 5.113 ms;
this diagnostic build is not claimed as another latency improvement.

The physical filesystem fixture passed the full regression, 28 checksum lengths
and deterministic clock/counter/invalid-input checks. Installed build465 passed
verified public HTTPS gzip/deflate content checks, full running-image SHA,
cores, fonts, Vulkan and watchdog checks. Build464 is the verified rollback;
Pi3build79 compiles the shared implementation. DNS overrides were removed.
Evidence: `docs/evidence/anvil-ipv6-20261030/mount465`.

The trace identifies repeated directory reads and boot metadata work as further
optimization targets. No validation was removed, and the initial filesystem
open remains synchronous. Networking and the previously listed remaining
protocol work are not complete.


### Directory reuse during bounded root reads (build466)

The shared exFAT driver now retains two 4 KiB directory windows independently
of the file-data sector cache. This avoids fetching the same directory entries
again when the root loader reopens its file after each bounded read. No shared
file handle is held across a yield. Mounts, reader changes, writes (including
failed writes), buffered FAT changes and discarded FAT edits invalidate the
windows. Directory checks and stream bounds remain enforced. Read-ahead stays
within a cluster; failure in an unrequested sector falls back to the original
single-entry read, preserving its error behavior.

The identical cold HTTPS probe on the physical Pi 4 measured:

| Measurement | Build465 | Build466 |
| --- | ---: | ---: |
| 47 path lookups, total | 53.699 ms | 8.227 ms |
| Mean path lookup | 1.143 ms | 0.175 ms |
| System-directory scan | 0.829 ms | 0.536 ms |
| Cold root open, maximum | 4.967 ms | 3.853 ms |
| Whole network service, maximum | 5.113 ms | 4.023 ms |

These are individual cold-run observations, not worst-case guarantees. Stage
count/total differences exclude startup activity. Boot validation still took
1.373 ms and the initial open remains synchronous; TLS blocking is not finished.

The first post-restart probe was correctly refused with SVC_ESTATE because SNTP
had timed out and the clock contained only an untrusted restored floor. It did
not exercise root loading and is retained as a failed probe, not a performance
sample. A requested SNTP synchronization established network time, after which
certificate-verified public HTTPS gzip/deflate content checks passed. Temporary
DNS overrides were removed. No certificate or time checks were bypassed.

Physical RAM tests passed the full filesystem regression, 28 checksum lengths,
clock diagnostics, cache hits across intervening file reads, key separation,
boundaries, reader rebinding, successful and partial failed writes, buffered
FAT remapping/discard, and both optional and required read failures. Build466
was installed and its full running-image hash verified after the full boot and
readiness interval; cores, fonts, Vulkan and watchdog checks passed. Build465
is retained as rollback. Pi3build80 compiles the same shared implementation;
physical Pi3 execution was not tested. Evidence, including the refused first
probe and successful synchronized rerun:
`docs/evidence/anvil-ipv6-20261030/directory466`.

Remaining IPv6/off-link/PMTU and DNS transport work, HTTP/2-3 and managed-cookie
policy remain open alongside the synchronous first-open work.


### Validated boot-header reuse (build467)

Boot validation compares immutable main/backup geometry directly from the
checksum-validated snapshots. It no longer rereads two sectors solely for that
comparison. It also rejects a main header whose immutable geometry differs
from the initial header used to configure the mount. VolumeFlags and PercentInUse
remain allowed to differ in the backup. Checksums and signatures still cover
both complete boot regions.

The physical RAM fixture confirms four device reads instead of six for boot
validation, all 46 compared bytes, the allowed mutable fields, both region
checksum failures, required read failures and changed bootstrap geometry.
The full filesystem/cache/checksum regression also passed. An initial fixture
asserted a dirty-volume latch for a clean read failure; its failed result is
retained. The corrected test checks the required read-error code. No product
change was needed for that test correction.

On the identical cold, certificate-verified public HTTPS gzip/deflate probe:

| Measurement | Build466 | Build467 |
| --- | ---: | ---: |
| Boot validation | 1.373 ms | 1.050 ms |
| Cold root open, maximum | 3.853 ms | 3.515 ms |
| Whole network service, maximum | 4.023 ms | 3.674 ms |

These are individual run observations. Before/after counter differences exclude
startup activity. The initial open is still synchronous; this does not complete
TLS blocking. Build467 is installed and verified by its full running-image hash,
with build466 retained for rollback. Cores, fonts, Vulkan and watchdog checks
passed, and the temporary DNS override was removed. Pi3build81 compiles the same
shared source; physical Pi3 execution was not tested. Evidence:
`docs/evidence/anvil-ipv6-20261030/boot467`.

Remaining cooperative first-open, IPv6/off-link/PMTU and DNS transport,
HTTP/2-3 and managed-cookie work remains open.


### Mount stage preparation (compiled build468; installed build467)

Shared exFAT mounting now separates reset, six validation stages and final
publication of the mounted volume. The existing public ExFatMount entry point
still drains all stages synchronously. These are private primitives, not an
asynchronous API: there is no new yield, ownership lease or TLS latency claim.
The stages retain the same partition, boot, system-directory, up-case checksum,
decoding and ASCII-map checks and timing counters.

The physical Pi fixture passed the full filesystem/checksum/cache/boot regression
and checks that no intermediate stage publishes a mounted volume, invalid stages
perform no reads, a later checksum failure leaves the volume unmounted, and the
normal entry point can recover and complete. Capture91 returned zero with healthy
cores, fonts, Vulkan and watchdog state. Pi4build468 and Pi3build82 compile; 468
has not been installed. The Pi remains on verified build467. Evidence:
`docs/evidence/anvil-ipv6-20261030/mount-stages468`.

Before these stages may yield, the shared filesystem facade needs ownership and
cancellation handling: another operation must not replace or reuse partial mount
state. Wiring a pause into the current global-state mount without that protection
would be unsafe. Cooperative cold open and the remaining networking protocols
are still unfinished.


### Owned mount jobs (compiled build470; installed build467)

The shared exFAT driver now provides ExFatMountBegin, ExFatMountStep,
ExFatMountCancel and ExFatMountPending. Begin returns a positive owner handle
without device I/O, or zero on refusal. Step returns zero while pending, one on
completion or minus one on failure. Cancel accepts only the current handle;
stale handles cannot affect another operation. Handles do not wrap. The existing
ExFatMount API drains the same stages synchronously.

A pending mount refuses competing mounts and volume/file/directory operations.
An open file or dirty mounted volume also prevents replacement. Reader rebinding
cancels an unfinished job. If a provider changes its reader during a callback,
the old result is discarded before publication; further reads from the cancelled
step are refused. Beginning another mount is prohibited until that active step
has returned. This is serialized ownership, not an SMP synchronization primitive,
and individual device callbacks remain synchronous.

Physical Pi tests passed the full filesystem/checksum/cache/boot regression,
competing and stale handles, completion, cancellation at all six boundaries,
reader rebinding, cancellation during a reader callback, subsequent-read refusal,
read failure, handle exhaustion and preservation of open/dirty volumes. Final
capture95 returned zero with healthy cores, fonts, Vulkan and watchdog state.
The compiler rejected an earlier test's guarded recursive callback, so that test
was rewritten without recursion; no compiler check was weakened.

Pi4build470 and Pi3build84 compile the shared implementation. Build470 has not
been installed; the Pi remains on verified467. Evidence:
`docs/evidence/anvil-ipv6-20261030/mount-owner470`.

The filesystem facade and TLS cancellation path do not yet use this job API.
They still need to coordinate ownership before cold TLS opening can yield.
No new HTTPS latency improvement is claimed. Remaining networking work includes
that integration, IPv6/off-link/PMTU and DNS transport, HTTP/2-3 and managed cookies.


### Cooperative TLS volume preparation (installed build472)

The shared filesystem facade now owns staged mount jobs. FsMountBegin and
FsMountPathBegin perform no device I/O; FsMountStep returns 0 pending, 1 ready
or -1 failed. FsMountCancel accepts only the current token. Competing operations
are refused before changing volume or path state. Reader replacement invalidates
an unfinished job, including replacement inside a device callback.

The shared block-backed HwFilePrepareBegin/Step/Cancel seam exposes these jobs
to TLS without a Core-to-filesystem dependency. A suspended TLS worker releases
its matching preparation token when cancelled. Files stay closed across yields.
The UNO Q backend explicitly reports unsupported preparation and retains its
ordinary firmware-open fallback. Non-cooperative root loads remain synchronous.

The strict exFAT Begin API still refuses open or dirty volumes. The legacy
synchronous ExFatMount retains its explicit replacement semantics, including
recovery when a failed dirty-volume unmount would otherwise strand another
partition. FAT32 fallback, unmount and that recovery path are synchronous stages;
this change is serialized ownership, not SMP locking or a hard device-I/O bound.
Corrupt exFAT metadata is never reinterpreted as FAT32.

Physical capture96 passed facade ownership, competing/stale handles, seven
cancellation boundaries, same-volume completion, callback reader rebinding,
cancellation during failed unmount, dirty-volume recovery, sparse FAT32 metadata
fallback and the existing checksum/cache/boot regressions. The sparse FAT case
checks mounting, not arbitrary FAT data reads.

Actual verified HTTPS tests on installed472 cancel an unopened connection and
a connection suspended during preparation, reject stale handles, then fetch and
decode gzip and deflate responses successfully. Cores, fonts, Vulkan and watchdog
checks pass. Root open/preparation timing now records the maximum individual
Begin, Step or Open call; a separate elapsed counter includes yields. Timing
results below distinguish these from the whole network service call.

Observed maximum root preparation step: 1036 us (previous unsliced root open3515 us). Maximum root-open elapsed time including yields: 3091 us. Maximum whole network service call: 3866 us. These are observed maxima, not worst-case guarantees; the earlier whole-call maximum was3674 us.

Pi4build472, Pi3build86 and UNO Q build100 compile the relevant shared contracts;
only Pi4 is physically validated. Evidence: docs/evidence/anvil-ipv6-20261030/tls-mount472.

Remaining TLS atomic work and synchronous device callbacks are not fully bounded.
IPv6 off-link/PMTU, IPv6 DNS transport/address selection, HTTP/2-3 and managed
cookies remain open. This is not a claim that networking is finished.


### TLS arithmetic measurements and shorter slices (installed 474)

The shared cooperative TLS driver now records count, total time and maximum
atomic time for each P256, wide-curve, RSA, X25519 and GCM Begin/Step operation.
Intervals between yield checks are timed separately; final474 also includes
worker-entry and worker-return boundaries. These timings do not include time
spent suspended. Status dispatch uses an optional hook, so targets without the
cooperative driver retain their existing implementation.

The physical 473 HTTPS profile did not use RSA. P256 steps peaked at 609 us,
wide-curve Begin at 986 us, wide-curve Step at 182 us, X25519 Step at 212 us and GCM
decrypt Step at 411 us. The longest interval between checks was 2392 us, showing
that individual arithmetic jobs alone do not account for all uninterrupted work.
The cooperative policy now uses a 1 ms soft slice instead of 2 ms. It still allows
an indivisible operation to exceed the remaining slice; no hard deadline is claimed.

On the same cancellation/verified-HTTPS workload, maximum whole service call
was 2823 us on 473 and 2846 us on 474. Final maximum
interval without a yield check was 2393 us. Network
traffic varies between runs, so this is measured evidence rather than a universal
latency guarantee or a reduction in total cryptographic computation.

Both runs cancelled unopened and suspended-preparation TLS handles, rejected
stale handles and then completed certificate-verified gzip/deflate HTTP 200
requests. Core/font/Vulkan/watchdog checks passed. Pi 3 build 88 compiles; only
Pi 4 build 474 was physically validated. Evidence:
`docs/evidence/anvil-ipv6-20261030/tls-slices474`.

Interval endpoint labels in diagnostics: -1 worker entry, 0 roots, 1 X509,
2 P256, 3 wide EC, 4 RSA, 5 X25519, 6 decrypt, 7 encrypt, 8 worker return.
A long interval identifies where to investigate; it does not by itself identify
which internal operation consumed the time. Remaining TLS atomic gaps,
IPv6 off-link/PMTU/DNS transport, HTTP/2-3 and managed cookies remain open.


### Cooperative TLS transcript hashing (installed 475)

The unchecked interval between decryption and X.509 validation included hashing
an entire handshake message. The new Tls13TranscriptAppend hashes at most 512
bytes per chunk when a cooperative hook is installed, saving the connection's
SHA snapshot before each yield. Another service may use the global SHA context
while it is suspended. All seven handshake call sites check Append's result;
a stopped callback causes terminal refusal 26 and invalid input refusal 27.
The existing synchronous Tls13TranscriptAbsorb API remains available, and Append
uses it directly when no cooperative hook is installed. Certificate verification,
Finished validation and cryptographic primitives are unchanged.

Physical capture 101 passed 22 independent hashlib comparisons covering SHA-block
and chunk boundaries, empty input, synchronous compatibility, unrelated SHA work
between chunks, cancellation at all five boundaries of a 1537-byte input,
terminal retries, negative length and null input. A 4096-byte unsliced append
measured 2285 us versus at most 287 us between chunk callbacks; 16384 bytes measured
9138 us unsliced versus 287 us per interval. This fixture intentionally performs
unrelated hashing inside each callback, so its total elapsed time is not a TLS
throughput comparison.

On actual verified HTTPS with preparation cancellation, the observed whole-service
maximum changed from 2846 us on 474 to 1993 us on 475.
The longest unchecked interval changed from 2393 us
to 1579 us. Final endpoints:
[-1, 5]; endpoint 9 denotes transcript hashing.
These are observed maxima, not hard worst-case bounds.

A separate test passed four overlapping certificate-verified HTTPS connections,
including an event stream and three complete replies, exercising connection-state
switching through the new yields. Board core/font/Vulkan/watchdog checks pass.
Pi 3 build 89 compiles the shared changes; only Pi 4 build 475 is physically validated.
Evidence: docs/evidence/anvil-ipv6-20261030/tls-transcript475.

Remaining atomic TLS and device work, IPv6 off-link/PMTU/DNS transport,
HTTP/2-3 and managed cookies remain open.


### Cooperative key-share setup (installed 476)

The shared TLS key-share path now checks its cooperative budget between complete
DRBG requests and before deriving the public key. Each DRBG request remains
atomic; no mutable HMAC state is suspended. The requests, entropy refusal,
private-key generation and eight-attempt derivation limit are unchanged.
The optional Tls13SetupPauseHook is installed only while the worker runs, and
cleared when it yields or is cancelled. Endpoint 10 identifies these checkpoints.
A refused checkpoint terminates the handshake with the existing refusal 26.

Physical capture 104 passed 25 control-flow tests: all 18 cancellation boundaries
of the bounded retry path, each entropy request failing, retry exhaustion,
successful setup, synchronous fallback and an already-failed connection.
These tests use deterministic RNG/key-derivation doubles and make no cryptographic
correctness claim. Real DRBG/X25519 are exercised by the live HTTPS tests.

On the same cancellation and certificate-verified HTTPS workload, observed maximum
whole service changed from 1993 us on 475 to 2237 us
on 476; the longest unchecked interval changed from
1579 us to 1518 us.
Final interval endpoints: [9, 7].
These are observed maxima, not hard timing guarantees.

Four overlapping verified HTTPS connections also passed, including three complete
replies and an event stream. Core/font/Vulkan/watchdog checks passed. Pi 3 build 90
compiles the shared changes; only Pi 4 build 476 is physically validated.
Evidence: docs/evidence/anvil-ipv6-20261030/tls-setup476.

The 1 ms slice remains a soft scheduling policy. Remaining atomic device/TLS work,
IPv6 off-link/PMTU/DNS transport, HTTP/2-3 and managed cookies remain open.


### IPv6 DNS transport (installed 477)

The shared payload resolver now accepts an explicit IPv6 resolver through
`settings set net.dns6 <IPv6-address>`. Read it with `printenv net.dns6`, or
remove the override with `settings remove net.dns6`. These commands change the
in-memory settings; persistence still requires the existing `settings save`.
Use an unbracketed numeric address, without a zone suffix. Route/source selection
uses the shared IPv6 service. No interface with an IPv4 address is required.

For uncached payload A and AAAA queries, this setting takes precedence over the
IPv4 resolver policy. Invalid settings or an unavailable IPv6 route are reported,
not silently replaced by a DHCP resolver. With the setting absent, the existing
IPv4 UDP/TCP fallback is unchanged. Console DNS and NTP retain their IPv4 policy.
Existing cached records retain their TTL and query-type ownership.

IPv6 resolver requests use TCP directly, a permitted first-choice transport in
[RFC 7766 section 5](https://www.rfc-editor.org/rfc/rfc7766.html#section-5).
They share the bounded TCP DNS owner: partial writes/reads, two-byte framing,
question/ID/type validation, cancellation, and the original 4.5-second deadline.
No UDP listener is acquired. The resolver consumes one of the existing four
payload TCP handles while a query is pending and releases it on completion,
failure or cancellation. Resource contention does not extend the deadline.

Physical Pi validation:

- 64 transport cases cover IPv4/IPv6 TCP with A/AAAA answers, malformed/truncated
  replies, partial progress, busy handles, disconnects, timeout and cancellation.
- Eight startup cases cover IPv6 without IPv4 usability, bad configuration,
  missing routes, invalid names, busy/open failures and cleanup; 24 policy cases
  cover the unchanged IPv4 selection plus IPv6 parsing and untouched outputs.
- Actual public A/AAAA answers for one.one.one.one arrived over LAN IPv6 TCP DNS
  in 311/85 ms, followed by six cache hits at the millisecond timer resolution.
  The temporary LAN resolver forwarded unchanged requests upstream over IPv4.
- A controlled hostname, anvil-ipv6.test, resolved through IPv6 DNS and returned
  the exact 20,000-byte HTTP body over IPv6 in 591 ms, with HTTP status 200.
- Certificate-verified HTTPS, compression and cancellation regression passed.
  Core/font/Vulkan/watchdog checks passed, and temporary settings/listeners were
  removed. The first DNS harness attempt used an unsupported settings verb and
  stopped before changing settings or booting a payload; its transcript is kept.

Pi 4 build 477 is installed and physically tested; Pi 3 build 91 is compile-only.
Evidence: docs/evidence/anvil-ipv6-20261030/dns-ipv6-477.

This proves LAN IPv6 DNS and hostname-based web traffic, not public off-link IPv6.
IPv6 UDP DNS, automatic resolver discovery, scoped resolver selection, off-link
and PMTU work, remaining atomic TLS/device work, HTTP/2-3 and managed cookies
remain open. The networking implementation is not complete.


### RDNSS advertisement decoder qualification

The shared `Anvil/Network/ipv6_rdnss.pbi` provides
`IPv6RdnssDecode(packet, bytes, local, rows, capacity)`. Each output row contains
16 address bytes and the unmodified 32-bit lifetime in seconds. The result is
the record count or a negative refusal. This is a codec, not a resolver list:
interface scope, expiry, withdrawal and selection remain the caller's job.

The decoder uses the existing Neighbor Discovery validation for checksums,
link-local RA sources, hop limit 255, option framing and fragment refusal.
It accepts the all-nodes destination or the caller's assigned local address.
Invalid DNS options are discarded as whole options; unrelated valid options
remain available. Capacity and span checks precede all output writes.
Multiple options and duplicate addresses retain their wire order. Zero and
infinite lifetimes are preserved for the future repository owner.
Protocol facts: [RFC 8106 sections 5.1 and 5.3.1](https://www.rfc-editor.org/rfc/rfc8106.html#section-5.1).

Thirty cases passed on the physical Pi running monitor 477, capture 112.
Coverage includes malformed envelopes/options, multicast and unspecified
resolver rejection, mixed valid/invalid options, unicast/multicast destinations,
multiple lifetimes, duplicates, exact/insufficient capacity, overlapping storage,
and the maximum 127-address option. Independent expected bytes and untouched
output/report guards were checked. Board health checks passed.
Evidence: docs/evidence/anvil-ipv6-20261030/rdnss-decoder477.

The resident monitor is unchanged. Automatic RDNSS learning is **not enabled**;
the per-interface lifetime repository, link-generation cleanup, scoped transport
selection and live advertisement-to-DNS integration remain to be implemented.


### Per-interface RDNSS repository qualification

`Anvil/Network/ipv6_rdnss_list.pbi` now provides caller-owned storage for 3..16
learned DNS servers per interface. Init, Apply, Tick, Get and Clear require the
correct interface identity and generation. A newer generation clears old state;
stale operations cannot modify or select from the replacement. Clear supports
loss of usability within the current generation.

Apply validates an entire advertisement batch before mutation. Zero lifetimes
withdraw addresses, finite lifetimes expire on the extended monotonic clock,
and infinity remains eligible until replaced or withdrawn. Renewal preserves an
existing entry's position. Newly retained addresses precede older entries in
input order. Full storage evicts the earliest-expiring entry, breaking ties
against the least-preferred entry. Lookup expires stale entries before copying
an address. Invalid inputs leave state and destination bytes untouched.

Fifty-one lifecycle steps passed on the physical Pi, capture 114, checking the
complete state of two interfaces and buffer guards after every operation.
Coverage includes renewal/withdrawal, capacity pressure and ties, zero/infinite
and maximum finite lifetimes, clocks beyond 32 bits, overflow limits, input
aliasing, failed batch atomicity, link changes, cross-interface isolation and
idempotent link-down cleanup. Core/font/Vulkan/watchdog checks passed.
Evidence: docs/evidence/anvil-ipv6-20261030/rdnss-list477.

At the repository-only checkpoint, monitor 477 did not connect this storage
to RA reception or DNS selection. The resident integration follows below.


### Resident scoped DNS integration: build 478

The shared IPv6 service now decodes RDNSS options after validating router
advertisements, copies their addresses into each interface's lifetime repository,
and clears them on link teardown or generation change. Eight entries per interface
are retained independently of default-router lifetime. DNS queries prefer explicit
IPv6 settings, then usable explicit/DHCP IPv4 resolvers, then routable learned
IPv6 resolvers. An explicit unusable IPv4 setting does not silently select RDNSS.

Scoped IPv6 TCP selection keeps a learned server on its receiving interface,
including when the same link-local address exists on another link. The pending
DNS query retains a copied address, interface and generation, and rechecks the
lease before progressing its TCP connection. Withdrawal, expiry or link changes
close the pending query with a state error; its original deadline is preserved.
Existing unscoped TCP callers retain their interface-selection behavior.

Physical Pi tests passed 64 transport cases, 13 resolver-start/pending-lease cases,
the existing pending query-type checks, and 19 scoped route/lease cases. The
controlled interface tests execute the actual selection and repository code with
hardware-state doubles; they are not a live router-advertisement claim. Captures
116/117 contain final scope/DNS results. The DNS host checker initially had an
incorrect AAAA expectation after its extension; it was corrected against the same
captured report, without rerunning or changing the physical test.

Build 478 was installed after verifying the 477 rollback, candidate and boot file.
After one restart, a 90-second quiet interval preceded readiness checks. Its full
running image hash matched. Pi 3 build 92 compiled from the same shared changes;
Pi 3 physical execution is not claimed.

Capture 118 resolved a hostname through an explicit IPv6 DNS test server and
retrieved the exact 20,000-byte HTTP body over LAN IPv6: status 200, 891 ms.
Capture 119 resolved public A/AAAA records with both manual resolver settings
absent: first AAAA 424 ms, first A 33 ms, subsequent cached results 0 ms.
This alone does not distinguish DHCP from RDNSS selection. Capture 120 passed
verified HTTPS, cancellation and compressed-response regression checks. Every
physical run returned normally with cores/fonts/Vulkan healthy and watchdog off.
Temporary resolver overrides and host test listeners were removed.

Evidence: docs/evidence/anvil-ipv6-20261030/rdnss-integration478.
Automatic RA-to-DNS-to-web selection still needs a trace that proves its resolver
source and interface. Public off-link IPv6 and HTTP/2-3 remain unfinished, as do
remaining atomic TLS/device work. LAN IPv6 traffic is not evidence of public IPv6
reachability. The bounded managed application cookie library is already described
above; broader browser cookie/site behavior is outside that implemented subset.
