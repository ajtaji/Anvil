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
