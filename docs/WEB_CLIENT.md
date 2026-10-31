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


### Resolver provenance and same-poll DNS completion: build 481

`net` / `net ipv6` now distinguish DHCP IPv4 DNS, current advertised IPv6
resolvers, and the last payload network DNS selection. The retained selection
records resolver address, interface, origin, query type and outcome. A matching
accepted answer has result 0; pending is -110; other negatives identify failure
or cancellation. Cache hits do not invent another network query, and payload
cleanup preserves a completed record. No queried hostname is retained.

On build 479, capture 122 established that the unconfigured public lookups used
DHCP IPv4 DNS at the LAN router. No RDNSS entries were learned from the observed
advertisements. This resolves the ambiguity in the previous checkpoint; it does
not establish successful automatic IPv6 resolver selection.

The diagnostics exposed a resolver completion defect, filed as forum topic 1530.
A TCP reply could complete inside `paynet_DnsStep` during the caller's resolver
poll, yet that step returned before staging the answer for delivery. The caller
then saw an empty cache and started another question. The live HTTP request
returned its correct body but sent one A query and seven AAAA queries.

The step now stages a newly completed TCP result before returning. Eight physical
regressions all failed before the fix (capture 124) and all passed afterward
(capture 125): A/AAAA, IPv4/IPv6 resolver transport, zero/positive TTL. The first
answer returns without reopening DNS. Zero TTL permits only that delivery;
positive TTL permits the next cache lookup without another connection. Existing
64 transport cases, 13 start/pending-lease cases and query-type checks also pass.

Build 481 was installed and verified against its full running image hash, with
479 rollback retained. Build 480 was staged but never booted; the final status
renderer uses the service's published clock rather than calling a private helper
across modules. Pi 3 build 95 compiles from the same shared source.

The installed image's live hostname test now sent exactly one A and one AAAA
query and received the exact 20,000-byte IPv6 HTTP body, status 200 in
804 ms. This is a single correctness regression, not a general
throughput claim. Verified HTTPS, cancellation and compressed-response tests
also passed. Core/font/Vulkan/watchdog checks passed throughout.

Evidence: docs/evidence/anvil-ipv6-20261030/dns-completion481. The archived
build-479 HTTP result passed its body check but failed the exact DNS-query-count
assertion; its wire log and the expected failing CPU regression are retained.
Automatic RDNSS needs a suitable live advertisement-to-web qualification. Public
off-link IPv6, HTTP/2-3 and remaining atomic TLS/device work remain open.


### Bounded TLS ALPN foundation: build 482

The shared TLS handshake now supports an optional, copied ALPN offer through
`Tls13SetAlpn(protocols, bytes)`, called after initialization and before building
ClientHello. Its input is the RFC 7301 sequence of one-byte name lengths and
nonempty opaque protocol names, bounded to 256 total bytes. Empty input disables
ALPN. Invalid lists are refused rather than truncated. Existing callers do not
advertise ALPN and retain their HTTP/1 behavior.

The TLS 1.3 EncryptedExtensions handler accepts exactly one offered protocol,
rejecting malformed, duplicate and unoffered selections. The selected name is
available through `Tls13Alpn(destination, capacity)` only in the connected state:
it returns its byte count, zero for no selection, or -1 for a state/buffer refusal.
Names are opaque bytes, not zero-terminated strings. Certificate and Finished
verification are unchanged. An application requiring h2 must require that exact
selection; an absent selection does not establish HTTP/2 support.

Both the copied offer and selection belong to the connection snapshot, which is
now 2,920 bytes. Save/restore/wipe coverage includes the new state. The layout
checker also accepts the exact base of a per-slot buffer, as well as that base
plus an offset; its previous false refusal is tracked in forum topic 1531.

On the physical Pi 4 running build 482, capture 131 passed 21 ALPN wire/guard
cases, including both protocol choices, absence, malformed lengths, duplicates,
unoffered names, a maximum 255-byte opaque name and undersized output. This is a
codec fixture with a transcript stub, not a full ALPN handshake. Capture 132
passed independent AES-GCM record comparisons while switching connection
snapshots with different offer/selection contents, then verified complete wipe.

Capture 130 passed the existing certificate-verified HTTPS, cancellation and
gzip/deflate regressions on the installed monitor. The maximum observed web call
was 2,188 microseconds and the whole-service maximum was 1,991 microseconds in
this run. These observations are not universal upper bounds. Core, font, Vulkan
and watchdog checks passed. Pi 3 build 96 compiles from the shared implementation.

The boot partition refused the first candidate write while holding over 1 GB of
accumulated images. The boot file remained unchanged. Four redundant candidate
images were removed only after their full hashes matched retained backups, and
the failed candidate was rewritten. Candidate, boot file and full running image
were then verified. Build 481 remains at `1:/B481V482.IMG` for rollback.

Evidence: `docs/evidence/anvil-ipv6-20261030/alpn482`. This is the handshake-library
foundation: the application-facing TLS service has not yet exposed the offer
and selection, and no live h2 negotiation or HTTP/2 exchange is claimed. Next are
that service integration and the HTTP/2 engine. HTTP/3, public off-link IPv6,
automatic RDNSS-to-web qualification and remaining atomic TLS/device work remain
open.

Protocol references: [RFC 7301 section 3](https://www.rfc-editor.org/rfc/rfc7301.html#section-3)
and [RFC 8446 section 4.2](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.2).
These supply protocol facts; no implementation code was copied.


### TLS ALPN service integration: ABI 1.13, build 483

Reserved network slots 90 and 91 now expose `SvcTlsOpenAlpn(host, port,
protocols, bytes)` and `SvcTlsAlpn(handle, destination, capacity)`. The table
remains 200 entries; no old index or signature changes. The two-argument open
at slot 80 retains no-offer behavior. Unsupported target capabilities retain
the existing service-table refusal behavior.

Open validates and copies the bounded offer before returning its handle. The
copy belongs to the connection through asynchronous preparation, DNS and TCP;
it is applied after TLS initialization and cleared on close. The selected-name
getter performs no network progress. It returns EAGAIN until the client is open,
zero for no negotiated protocol, or a byte count without a terminator. Invalid
or too-small destination storage is refused without a partial write. ABI entry
points check caller buffers against payload memory before dereferencing them.

On the installed physical Pi 4, two overlapping verified connections to
httpbin.org negotiated h2 and http/1.1 respectively after the shared caller
input buffer had been overwritten. The legacy open negotiated no protocol.
Pending getters, undersized destinations with unchanged sentinel bytes, stale
handles and six invalid-input refusals passed. The longest observed service
call in that probe was 2332 microseconds, not a worst-case
bound. Existing verified HTTPS gzip/deflate and cancellation tests also passed.

The first live probe had an incomplete memory-translation lifecycle: it enabled
translation without constructing tables and the watchdog reset the board. A
second probe completed the network checks but omitted cache/translation teardown,
so Vulkan was inactive on return. These failures are retained separately from
the final successful qualification. The probe now constructs the tables with the
required device mappings and flushes/disables caching and translation before
return. Its builder refuses missing setup/teardown or an intervening early return.
After recovery and the final run, cores, fonts, Vulkan and watchdog checks passed.
Forum topic 1532 records the probe defect; it was not a TLS or compiler failure.

Build 483 and its full running image hash were verified; build 482 remains at
`1:/B482V483.IMG` for rollback. Pi 3 build 97 compiles. The payload guide was
rebuilt and its changed pages visually checked. Evidence:
`docs/evidence/anvil-ipv6-20261030/alpn-service483`.

This proves actual verified ALPN negotiation through the application service.
It does not yet provide an HTTP/2 request engine. Existing WebClient calls remain
HTTP/1-only and must not send HTTP/1 bytes after negotiating h2. Next are shared
HTTP/2 framing, HPACK, stream state and flow control. HTTP/3, public off-link IPv6,
automatic RDNSS-to-web qualification and remaining atomic TLS/device work remain
open.

### HTTP/2 frame foundation: physical build 483 qualification

The shared `h2_frame.pbi` module decodes the nine-byte HTTP/2 frame header
incrementally, without consuming payload bytes. It validates advertised frame
limits, mandatory payload lengths and zero/nonzero stream rules. Unknown frame
types and undefined receive flags remain available to the connection engine;
the reserved stream bit is ignored. Errors latch until explicit reinitialization.
The output helper validates before writing, clears undefined base-protocol flags
and emits an exact connection preface with caller-provided storage.

Physical Pi 4 tests passed 38 explicit cases at every header split (380 cases),
including malformed lengths, SETTINGS acknowledgements, reserved bits, extension
frame types, the default limit and the maximum 24-bit length. Output canaries,
small-buffer refusals, invalid arguments and the exact preface also passed.
Capture 138 returned zero with all cores, fonts and Vulkan healthy and watchdog
off. The same fixture also compiles for Pi 3 (not executed there).
No monitor update or reset was needed. The first qualification failed due
to indexed structure storage; the implementation now uses explicitly addressed
bounded byte storage. The rejected report is retained, not counted as a pass.

Evidence: `docs/evidence/anvil-ipv6-20261030/http2-frame483`.
This is a frame foundation, not an HTTP/2 request engine: payload semantics,
SETTINGS application, HPACK, continuation ordering, stream state and flow control
remain connection-layer work. Existing HTTP/1 requests are unchanged.

### Explicit protocol negotiation through the web transport

`WebTransportOpenAlpn(connection, protocols, bytes)` adds opt-in ALPN using
owned TLS offer storage; `WebTransportAlpn(connection, destination, capacity)`
reads the selected opaque protocol without advancing network work. The legacy
`WebTransportOpen` continues to offer nothing. Protocol-aware callers must check
the negotiated value before sending bytes in that protocol. No HTTP/1 client
call opts into h2 implicitly.

Payload binding requires ABI minor 13 and at least 92 entries for the optional
ALPN pair. Older tables still bind for existing operations; an explicit ALPN
request/getter returns the unsupported-service error. Kernel binding calls the
same TLS owner directly. A missing connection, missing host, invalid offer span
or nonempty offer on plaintext is refused before opening a connection.

On the physical Pi 4 running 483, overlapping verified h2 and http/1.1
connections passed through these transport APIs after their caller offer buffer
was overwritten. Pending selection, short-buffer canaries, close/stale selection,
legacy no-offer behavior and older-table rebinding/refusal passed. A rebuilt
HTTP/1 HTTPS gzip/deflate and preparation-cancellation regression also passed.
Captures 139 and 140 returned zero with healthy cores, fonts and Vulkan, watchdog
off, and the temporary DNS override removed. Pi 4 monitor 484 and Pi 3 monitor
98 compile; those new monitor images were not installed. Payload-side testing
uses the already installed 483 TLS ABI. Evidence:
`docs/evidence/anvil-ipv6-20261030/web-alpn483`.

HTTP/2 payload handling, HPACK, continuation sequencing, stream state and flow
control remain unfinished. Negotiation and frame helpers do not by themselves
constitute HTTP/2 request support.

### Bounded HPACK decoding and a real HTTP/2 GET

`hpack_decode.pbi` provides a caller-owned decoding context with the RFC 7541
static table, dynamic entries, all literal forms and indexed fields, integer
bounds, table-size changes and Huffman decoding. The immutable lookup tables
are independently arranged from Appendix A/B protocol constants. No external
HPACK implementation is copied into or linked into Anvil.

Initialize with `HpackInit(context, table, capacity)` using 4096..16384 bytes of
table storage. The initial permitted/chosen table size is 4096. Apply effective
local SETTINGS changes between blocks with `HpackSetLimit`; a pending minimum
survives later increases until the peer sends the required update. `HpackBegin`
takes a complete compressed block, independent field-output storage and a header
list limit. Buffers must remain valid and nonoverlapping during decoding.
`HpackNext` returns 1 for a complete field, 2 for more bounded work, 0 at block
completion, or a latched negative error. Names and values are opaque byte spans,
not terminated strings; the spans remain valid until the next call. Never-indexed
literals expose the sensitive flag. HTTP/2 field semantics remain the client's
responsibility.

String steps consume at most 128 encoded input bytes. Eviction scans the retained
prefix once. Decoded names are copied before eviction can invalidate their source.
The implementation caps compressed blocks and decoded header-list accounting at
65536 bytes, per-field workspace at 32768 bytes, dynamic storage at 16384 bytes,
integers at signed-31-bit values/five continuation octets, and leading table-size
updates at two. Invalid indexes, required-update omissions, invalid Huffman EOS
or padding and exceeded limits fail closed. A decoder error requires discarding
the connection/context; it is not a recoverable per-header warning.

The final physical Pi 4 run passed 59 cases and 751 exact decoded fields against
independent vectors, including all 256 Huffman byte values, duplicate entries,
name references surviving eviction, an 8 KiB decoded field, a 512-entry table,
large eviction/insertion and 18 malformed-or-limit refusals. Input consumption,
dynamic references, table accounting and output guards passed. The longest observed step
was 97 microseconds; that is an observation, not a worst-case guarantee. The same
shared codec compiles for Pi 3 with the Pi 4-only MMU harness omitted. It was not
run on Pi 3. The optional host vector generator uses hpack 4.2.0 only as a test
oracle. Both generators reproduced the qualified tables/vectors exactly.

A separate physical probe composed the shared transport, frame and HPACK code
for a certificate-verified HTTP/2 GET of `https://httpbin.org/uuid`. It negotiated
h2, exchanged SETTINGS, sent request headers, decoded eight response fields and
received HTTP 200 with a 53-byte valid JSON UUID body. Six received frames were
processed; the longest observed response decode step was 13 microseconds.
Capture 145 returned zero with healthy cores, fonts and Vulkan, watchdog off and
the temporary DNS override removed. The first probe incorrectly treated an empty
receive queue as EOF; topic 1534 records the correction to check connection state
before reading. Its rejected report is retained separately.

This proves an actual HTTP/2 request/response through the shared building blocks.
The probe's bounded polling loops are qualification code, not the reusable
asynchronous connection engine. Production stream lifecycle, semantic header
validation, full control-frame rules, flow control, multiplexing and WebClient
integration remain unfinished. Existing HTTP/1 behavior is unchanged. HTTP/3 and
the broader networking gaps remain open. Evidence:
`docs/evidence/anvil-ipv6-20261030/hpack-http2-483`.


### Asynchronous HTTP/2 GET connections

`Anvil/Network/h2_client.pbi` now implements a shared, caller-owned HTTP/2
connection engine. It explicitly negotiates h2 over the existing verified TLS
transport. `H2ClientStep` performs at most one send, one receive, or one HPACK
step per call; it does not wait for network progress. The application separately
pumps the existing network service. Transport calls can still perform bounded
TLS work, so this is not a hard real-time latency guarantee.

Create an `H2Client`, a parsed HTTPS `WebUrl`, and `H2Buffers` with disjoint,
persistent storage: 16384-byte tx and rx buffers, a 65536-byte compressed-header
buffer, 4096-byte dynamic table, 8192-byte field workspace, 1024-byte `controls`
queue, and 1..16 `H2Stream` records. H2ClientRequest and WebClientStartAuto also
require a separate 65536-byte `requestBlock`; GET-only H2Client callers may leave
that pointer zero. Keep the origin host alive throughout the connection. Start only a
fresh or explicitly closed context; starting again does not close an old handle.
`H2ClientStart(context, url, buffers, now, timeout)` establishes ownership.
`now` and `timeout` use the caller's same monotonic units; elapsed time is modulo
32 bits and timeout must be 1..2147483647. The whole-connection deadline remains
an upper bound; optional independently renewable stream deadlines are described below.

State 1 waits for TLS, state 2 exchanges the preface/settings, and state 3 can
accept requests. `H2ClientGet(context, target, bytes)` copies an origin-form
GET target (use the validated output of `WebUrlParse`) and returns a positive
stream ID or `H2_BUSY`. GET uses static/literal HPACK and END_STREAM. General methods, headers and
request bodies use the shared WebRequest API described below. The peer concurrency
limit and header-list limit are respected. Multiple requests can be active on
one connection, and response HPACK state persists across streams.

`H2ClientStep` returns zero for progress/no event, a negative latched error, or
FIELD, DATA, END, RESET or GOAWAY. Events and their byte spans remain stable until
`H2ClientConsume`. FIELD exposes the opaque name/value spans, sensitive flag and
stream ID. Informational headers and trailers are exposed too; inspect the
block status/trailer state when distinguishing them. DATA exposes only content
bytes, excluding padding. Consumption queues connection/stream WINDOW_UPDATE
credit for the complete DATA payload, including padding. Parsing is backpressured
while an event is outstanding. This stalls incoming parsing for all streams,
but Step can advance outgoing writes without changing the retained event or its
spans. Callers should consume promptly. After consuming END or RESET, `H2ClientRelease` frees
that caller-owned stream slot for another monotonically increasing stream ID.

The engine validates SETTINGS values, ACK state, continuation ordering, frame
payload bounds, receive windows and send-window arithmetic; handles PING,
RST_STREAM and GOAWAY; and rejects unsolicited push. HTTP response checks include
lowercase field names, prohibited connection fields, pseudo-header order and
uniqueness, status, field-value controls, content length, informational responses
and trailers. `H2ClientCancel` cancels the entire connection, and `H2ClientClose`
releases transport ownership. Graceful NO_ERROR shutdown is described below; automatic connection-error
GOAWAY transmission remains unfinished. Opt-in automatic WebClient protocol
dispatch is described below. Per-stream cancellation and minimal processing of
late closed-stream frames are described below.
Connection-level protocol errors close the connection. Stream WINDOW_UPDATE,
response-body and field semantic errors are isolated as described below; other stream-local failures remain unfinished. The
existing HTTP/1 WebClient remains the default; HTTP/2 is explicit opt-in.

Physical qualification on Anvil 483 passed 40 cases through a fake transport
running on the Pi, with three-byte writes, five-byte reads, injected pending
operations, stable-event checks and independently decoded outgoing headers.
It covers interleaved streams and persistent HPACK, padded DATA credit, a
70000-byte body, informational/trailer headers, malformed messages, reset,
GOAWAY, cancellation, deadlines, drained EOF and queued bytes after closure.
The first expanded run was rejected because its fake transport injected a
zero-byte read after reporting CLOSED despite retaining queued data. Topic 1535
records that fixture correction; the rejected report remains in the evidence.

A separate real-network run negotiated h2 with certificate verification and kept
two requests active simultaneously: `https://httpbin.org/uuid` returned a valid
53-byte JSON UUID, and `/bytes/70000` returned all 70000 bytes. The latter exceeds
the initial 65535-byte receive window. Total elapsed time was 989330 microseconds;
the maximum observed client step was 2523 microseconds and separate network
service call 2937 microseconds. These are observations, not worst-case bounds.
Captures 149/150 returned zero with healthy cores, fonts and Vulkan, watchdog off,
and the temporary DNS override removed. The same shared code compiled for Pi 3;
that compile-only fixture was not run. No monitor update was needed. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-engine483`.

Networking is not complete. Alongside the HTTP/2 limitations above, HTTP/3/QUIC,
remaining atomic TLS/device work, automatic RDNSS-to-web qualification and public
off-link IPv6 traffic remain open.


### Cancel one stream while others continue

`H2ClientCancelStream(context, streamId)` queues RST_STREAM with CANCEL (8),
marks that request reset and exposes the normal RESET event. Consume the event
and then release its slot as usual. Other streams and the TLS connection remain
active. A zero return means cancellation was accepted, not that the wire frame
has already been sent. Continue pumping `H2ClientStep` and network service.
If an output frame, event, or final completion is pending, cancellation returns
BUSY without changing state; finish that pending work before retrying. Unknown
or already completed/reset IDs return STATE. Whole-connection Cancel is unchanged.

Header assembly and HPACK decoding can continue after cancellation, even when
its caller-owned slot is released and reused for a newer stream. The decoder
is detached from the old slot and suppresses its application fields while still
updating connection compression state. Late HEADERS/CONTINUATION on closed IDs
receive the same bounded decoding; late DATA is discarded and credited only at
connection level, including padding. Frame, compression, padding and connection
window limits still apply. Older odd IDs are known closed because this client
allocates consecutive odd IDs; no unbounded tombstone list is needed. Unknown
idle/server-initiated response streams still fail. This uses the minimal closed
stream processing permitted by RFC 9113 section 5.1, rather than emitting frames
on an already closed stream. Unsolicited push remains disabled and refused.

The physical CPU suite now passes 46 cases. Six additions cover cancellation
before a response, during CONTINUATION and during HPACK decoding; reuse of the
cancelled slot while a header block is unfinished; and late frames after normal
completion or a peer reset. Subsequent live-stream headers reference dynamic
entries introduced by discarded headers. Checks verify exact CANCEL wire output,
connection credit for discarded padded data, no delivered cancelled content,
BUSY behavior and successful completion of the other streams.

A separate verified-TLS test kept two requests active to httpbin.org, cancelled
`/delay/5`, and received all 70000 bytes from `/bytes/70000` on the same connection.
Elapsed time was 991774 microseconds, maximum observed client step 2594 and
separate network service call 2768 microseconds. These are observations only.
Captures 151/152 returned zero; cores, fonts and Vulkan remained healthy, watchdog
was off and the temporary DNS override was removed. Shared Pi 3 compilation also
passed, without a Pi 3 hardware claim. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-cancel483`.

Automatic connection-error GOAWAY transmission remains unfinished, alongside
the broader TLS, IPv6 and HTTP/3 work.


### Shared WebRequest headers and flow-controlled uploads

`H2ClientRequest(context, request)` accepts a fresh, finalized `WebRequest`
and returns a positive stream ID, BUSY, or a negative error. It supports the
existing request methods, custom headers, fixed lengths and unknown lengths.
The request context remains caller-owned and must live until the stream closes.
Its header offset advances on acceptance; remaining body bytes and completion
state are maintained as DATA is queued. Use the DATA call's return count to
advance input. The request's consumed field changes only on accepted DATA calls.
Refused requests leave their request context and stream allocation untouched.

The pure `H2RequestEncode` helper translates the bounded WebRequest header
buffer to HTTP/2 pseudo-fields and lowercase regular fields. It checks the
Host/port against the TLS connection, removes HTTP/1 connection and chunking
framing, permits only `TE: trailers`, and enforces the peer header-list limit.
It expects a WebRequest-built input, not arbitrary untrusted HTTP/1 wire input.
All output fields are literal never-indexed fields; there is no encoder dynamic
table or Huffman encoding. Cookie and authorization values therefore are not
inserted into an encoder table. Header blocks may span HEADERS/CONTINUATION;
outgoing fragments stay contiguous before any unrelated frame can be queued.
The existing 32768-byte WebRequest header limit and 65536-byte encoded block
storage apply. Buffers must be disjoint, persistent caller-owned storage.

`H2ClientData(context, streamId, body, bytes, endBody)` copies and queues at most
16375 body bytes per call, limited by both stream and connection send credit.
The positive return is the accepted byte count; retain the remaining input and
retry after BUSY. Continue pumping Step and network service between calls.
Repeat endBody when retrying the final input span: END_STREAM is queued only
when that final span is fully accepted. A known length ends automatically at
zero remaining bytes; inconsistent final lengths are refused. Unknown-length
bodies use DATA, without HTTP/1 chunk framing. A zero-byte final call can queue
END_STREAM even with no send credit; its zero return is successful acceptance.
Acceptance means queued, not yet transmitted. Once final response headers are
known, further body calls return BUSY while the response is drained. If the
response completes before the upload, only that unfinished request side is
closed with RST_STREAM(NO_ERROR); the complete response is preserved.

HEAD responses may describe a representation Content-Length without delivering
that many body bytes. Nonempty response DATA for HEAD is rejected. Other stream
events, cancellation, release and connection ownership retain their contracts.
WebClientStartAuto, described below, integrates this engine with WebClient.
The original HTTP/1 default remains unchanged.

On physical Anvil 483, all 46 existing engine regression cases and eight new
upload cases passed. The new cases cover connection-credit exhaustion during a
70000-byte body; five-byte stream windows with binary unknown-length input;
zero-credit empty termination; HEAD metadata; a roughly 31 KB header block
requiring CONTINUATION; an early 413 stopping a partially sent body; and refusal
of a foreign origin or invalid TE. Independent host HPACK decoding checks the
exact outgoing fields, DATA bytes, flags and early-response reset. The fake
transport uses short writes/reads and injected pending results on the Pi.

A separate certificate-verified HTTPS POST to httpbin.org uploaded 70000 bytes.
The 70314-byte JSON response echoed every body byte and the custom request
header. Elapsed time was 1994279 microseconds, maximum observed H2ClientStep
2529 and separate network service call 2447 microseconds. These measurements
exclude the separate Request/Data calls and are not worst-case guarantees.
Captures 154 through 156 returned zero; cores, fonts and Vulkan stayed healthy,
watchdog was off, and the temporary DNS override was removed. The shared source
also compiled for Pi 3, without claiming a physical Pi 3 run. No firmware update
was required. Evidence: `docs/evidence/anvil-ipv6-20261030/http2-upload483`.

Remaining work includes automatic connection-error GOAWAY transmission
and stream-local error isolation, as well as the
broader remaining TLS, off-link IPv6/RDNSS qualification and HTTP/3 work.


### Negotiated transport and HTTP/1 ownership transfer

`H2ClientStartNegotiated` takes the same arguments and ownership contract as
H2ClientStart but offers `h2` followed by `http/1.1`. An h2 selection follows
the existing engine. Selection of http/1.1, or no ALPN selection, enters state
4 without sending any HTTP/2 preface or request bytes. Unknown selections and
ALPN service errors fail closed. The original H2ClientStart still offers only
h2 and refuses fallback. The connection deadline also applies while awaiting
handoff in state 4. ALPN support is required; this entry does not silently
reopen through a legacy service table that lacks it.

`H2ClientTakeHttp1(context, destinationConnection)` moves the verified connection
from state 4 into a fresh/closed, disjoint WebConnection. A nonzero destination
handle, alias of the source, or any other source state is refused without a
transfer. On success the source handle and ownership are cleared. Closing the
old H2Client cannot close the moved connection.

`WebClientAdopt(client, connection, request, response, tx, txCapacity, rx,
rxCapacity, now, timeout)` initializes an HTTP/1 exchange around an already-open
transport and moves ownership into WebClient. It performs no second open or TLS
handshake. Argument/state failures leave the source connection owned by the
caller; close it or correct the arguments and retry. As with Start, the client
must be fresh or closed and all contexts/buffers must be disjoint and live.
The caller must establish HTTP/1 selection before adopting; do not adopt an h2
connection. Adopt receives the exchange deadline parameters explicitly; retain
the original start time when a single deadline must cover negotiation too.

Physical qualification on Anvil 483 passed ten negotiation/ownership cases plus
the 46-case HTTP/2 regression. The new suite checks exact offers and wire bytes,
explicit HTTP/1 and absent-ALPN fallback, strict-h2 refusals, unknown selection,
timeout, cancellation, ALPN errors, alias/busy-destination refusal, invalid then
successful adoption, repeated close/take, and the unchanged legacy start path.
Each exchange opens once and closes once, using short reads/writes and injected
pending results. The first host report checker used two wrong numeric expected
errors; topic 1536 records its correction. The original rejected check and its
raw report are retained beside the successful recheck of the same report.

Actual verified HTTPS negotiation selected h2 at httpbin.org and passed the
70000-byte POST echo test. Two TLS 1.3 servers without an ALPN selection then
passed handoff into WebClient: www.openbsd.org returned HTTP 200 and 3622 bytes;
www.sqlite.org returned HTTP 200 and 9008 bytes. Both bodies matched independently
fetched reference hashes exactly, and instrumentation confirmed one TLS open and
one close per exchange. Their observed elapsed times were 1089190 and 595979 us;
maximum Step calls 4282/2442 us and service calls 4319/2583 us. These are observations,
not scheduling guarantees. Existing HTTP/1 gzip/deflate and preparation-cancel
qualification also passed. Shared Pi 3 compilation passed, without a hardware
claim. Captures 157-162 returned zero and the Pi remained healthy on monitor 483.

The earlier GNU/FSF live attempts returned transport timeouts and are retained
as failures. Later desktop GNU connections also timed out; the desktop FSF
connection used TLS 1.2, which this TLS 1.3 implementation does not support. Neither
failed attempt is counted as fallback qualification or certificate validation.
Evidence: `docs/evidence/anvil-ipv6-20261030/http-negotiation483`.

These APIs supply negotiation and a tested ownership handoff used by the
unified WebClient entry below. HTTP/2 lifecycle work, remaining TLS work,
off-link IPv6/RDNSS qualification and HTTP/3 remain open.

### Automatic WebClient protocol dispatch

`WebClientStartAuto(client, url, request, response, tx, txCapacity, rx,
rxCapacity, h2Context, h2Buffers, now, timeout)` explicitly opts into HTTPS ALPN
negotiation through the existing WebClient Step/Next/Cancel/Close API. The original
WebClientStart remains HTTP/1. Plain HTTP, an allowUpgrade response, or an older
payload service table without ALPN uses HTTP/1 directly. HTTPS offers h2 then
http/1.1. Explicit HTTP/1 selection or absent ALPN moves the same verified TLS
connection into the HTTP/1 path without another open or handshake; unknown
selections fail closed. The exchange deadline includes negotiation and fallback.

Use fresh or closed contexts and finalized WebRequest/initialized WebResponse
objects. All contexts, URL host and buffers must remain live and disjoint until
Close. The caller supplies the H2Client and H2Buffers storage, including their
existing bounded frame, header-block, HPACK and stream storage. WebClient owns
that H2 context exclusively: do not independently pump it, submit another stream,
or share it with another WebClient. This interface supports sequential reuse;
advanced multiplexing still uses H2Client directly. HTTP/1 tx/rx storage remains
required for fallback. Context layouts changed; recompile callers together.

`client.protocol` is 0 during negotiation, 1 for HTTP/1 and 2 for HTTP/2.
`response.versionMajor` is initialized to 1 and becomes 2 for HTTP/2. HTTP/2
response events populate WebResponse directly, without fabricated HTTP/1 framing.
Status and duplicate final fields use the existing header lookup API. Informational
fields count against metadata limits but do not appear in final header lookup;
trailers follow the stored final-header terminator and cannot override them.
The eight-informational-response, line, header-storage and total-metadata limits
are enforced. `WEB_RESPONSE_STREAM` identifies an ongoing HTTP/2 response body.
WebResponseFeed remains an HTTP/1 framing parser and refuses versionMajor 2.

Keep pumping the network separately and call WebClientStep with the usual body,
output and time arguments. `client.consumed` is the upload byte count accepted
by that call; retain/retry the remainder, repeating endBody for the final span.
`client.written` is the response output count. Partial or zero-capacity output
preserves pending DATA until consumed. Fixed and unknown-length uploads use H2
flow control. HEAD representation lengths do not require body bytes. An early
final response stops further upload submission; completion waits for any queued
request-side reset/control bytes to drain. The existing Step return convention
is unchanged: pending 0, completed 1, negative error.

`WebClientNext` reuses the same origin, transport and HPACK state after a reusable
response, and renews the exchange deadline. Keep the previous response available
until Next returns; supply a fresh request and initialized next response. GOAWAY
prevents reuse. `client.sent/received` count actual protocol bytes for the exchange;
the first H2 exchange includes connection preface/control traffic. Peer reset
returns WEB_CLIENT_STREAM_RESET (-555), with its code in `client.h2ResetCode`.
Cancel, errors and Close release the owned connection; repeated Close is safe.
Automatic redirects, managed cookies and content decoding are separate facilities.

Physical Anvil 483 qualification passed 24 new automatic-client cases, the 46-case
H2 regression, and existing HTTP/1 gzip/deflate/preparation-cancel checks. New cases
cover metadata, tiny output buffers, upload windows, unknown binary lengths, HEAD,
early rejection, limits, reset/GOAWAY, cancellation/deadlines, sequential reuse,
explicit/absent ALPN fallback, legacy services, upgrades and plaintext. Independent
host HPACK decoding checks exact outgoing fields and bodies.

Actual verified HTTPS uploaded 70000 bytes to httpbin.org/post and checked the
70316-byte echo and custom header. A second /uuid request reused the same H2/TLS
connection. Observed elapsed times were 2299609 and 83729 microseconds; maximum
Step calls 2626 and 92 microseconds. OpenBSD and SQLite then passed HTTP/1 fallback
through the same API, with exact independent body hashes (3622 and 9008 bytes),
one TLS open/close each, and maximum Step calls 4282 and 2438 microseconds.
These are observations, not worst-case guarantees. Shared Pi 3 compilation passed;
only Pi 4 was physically tested. Captures 163-166 returned zero with cores, fonts
and Vulkan healthy, watchdog off and temporary DNS overrides removed. Monitor 483
was unchanged. Evidence: `docs/evidence/anvil-ipv6-20261030/webclient-auto483`.

This is not a complete HTTP/2 implementation. Graceful local GOAWAY and stream-local
error isolation remain work, alongside remaining TLS compatibility/blocking work,
off-link IPv6/RDNSS qualification and HTTP/3.


The former TX-priority limitation was physically reproduced in forum topic 1538.
A POST stalled after 88 bytes of its first DATA payload while the peer had its
SETTINGS acknowledgment and final 413 response ready. The current engine timed
out (-552), having read only the initial nine-byte SETTINGS frame; 37 incoming
bytes stayed unread. The peer would resume writes after its response was read.
Capture 167 returned zero and the Pi remained healthy. This is failed networking
behavior, not a passing exchange. The original checker expected 18 received bytes;
its corrected check confirms the defect from the same immutable report without
another board run. Evidence: `docs/evidence/anvil-ipv6-20261030/http2-duplex-repro483`.
That evidence records the unfixed behavior. The scheduler correction is described below.

### Duplex progress and bounded control output

H2ClientStep now alternates pending writes with receive/HPACK work, performing
at most one send, one receive, or one bounded HPACK step per call. A write returning
zero or BUSY no longer prevents reading a waiting response. Retained events remain
stable while outgoing work progresses. Cancellation and deadlines still apply.

Incoming control replies use a separate caller-owned 1024-byte `controls` queue.
SETTINGS/PING acknowledgments, receive-credit updates and early-response resets
cannot overwrite a partially sent frame. Queued controls drain at frame boundaries,
after any ongoing HEADERS/CONTINUATION sequence. Receive credit becomes available
only after the complete WINDOW_UPDATE reaches the transport, including when a write
ends partway through a frame. Exhausting the control queue fails explicitly with
H2_LIMIT; it does not drop replies or allocate unbounded storage.

The separate `requestBlock` prevents inbound HPACK blocks from overwriting unsent
outgoing header fragments. H2Buffers and H2Client layouts changed: recompile callers
and initialize the new pointers with persistent, disjoint storage. Start requires
controls; Request requires requestBlock; GET-only clients do not require requestBlock.
Direct callers draining output after END must wait for txLength, controlLength and
requestHeaderBytes to become zero. WebClient performs that drain before completion.

Physical qualification on Anvil 483 passed the original stalled-upload case with
its unchanged 500-tick fixture deadline: status 413 and the exact two-byte response
were delivered, the committed 16375-byte DATA payload remained intact, and the
final reset/credit frames were correct. Seven further cases cover zero/BUSY writes,
PING and SETTINGS during a stalled upload, retained DATA with outgoing progress,
bounded queue exhaustion, timeout, cancellation and unknown-length uploads.
A separate two-stream test decoded the first response while a 31 KB header block
for the second request was still being sent. Independent HPACK decoding verified
all 31 large fields, contiguous CONTINUATION frames and deferred PING acknowledgment.

All 46 engine cases, eight upload cases and 24 automatic-client cases passed on
the final source. An intermediate candidate failed the closed-transport drain case;
that failed report is retained alongside the corrected run. The final scheduler
drains queued final output before treating known EOF as an exchange failure.

Actual verified HTTPS again uploaded 70000 bytes and checked the complete echo,
then reused the same connection for /uuid. Observed elapsed times were 2017929 and
103676 microseconds; maximum Step calls 2606 and 91 microseconds. HTTP/1 fallback
downloads from OpenBSD and SQLite matched independent reference body hashes.
These are measurements, not worst-case guarantees. Shared Pi 3 compilation passed;
physical qualification was on Pi 4. Monitor 483 remained installed, with healthy
cores, fonts and Vulkan, watchdog off and temporary DNS overrides removed.
Evidence: `docs/evidence/anvil-ipv6-20261030/http2-duplex483`.

### Optional per-stream deadlines

`H2ClientDeadline(context, streamId, now, timeout)` sets or renews a deadline for
an active stream. Use the same monotonic units as Step. Timeout 0 disables the
stream deadline; positive values up to 2147483647 use modulo-32-bit elapsed time.
Invalid arguments or inactive/unknown streams are refused without changing the
deadline. The connection deadline remains an independent upper bound; this call
does not extend it. Streams without an explicit deadline retain prior behavior.

Step checks all bounded stream slots. Expiry stops new submissions on that stream,
queues RST_STREAM(CANCEL), and reports H2_RESET with `stream.resetCode=8` and
`stream.localError=H2_TIMEOUT`. Other active streams and the connection remain
usable. Read these fields before Release. The stream structure changed, so
recompile callers and allocate stream storage using SizeOf(H2Stream).

A borrowed FIELD or DATA event remains stable until consumed, even if its stream
expires. The reset event follows consumption; late fields still update HPACK state
while discarded content restores connection credit. Expired streams receive no
new stream credit. If the control queue has insufficient room, the reset waits for
transmit progress rather than closing the connection. Release refuses a stream
whose reset notification is still pending. A caller retaining an event indefinitely
still blocks incoming parsing by the existing event-ownership contract.

Physical Anvil 483 qualification passed eight cases: isolated expiry, expiry with
retained DATA/FIELD, disabling, renewal, clock wrap, simultaneous expiry and deferred
reset under a saturated control queue. Exact reset frames, preserved borrowed bytes,
HPACK continuity, completed sibling streams, credit and single close ownership were
checked. All 46 engine and seven duplex cases also passed.

A real certificate-verified HTTPS test assigned a half-second deadline to
httpbin.org/delay/5 while receiving httpbin.org/bytes/70000 on another stream of the
same connection. The delayed stream reported H2_TIMEOUT and the sibling completed
HTTP 200 with all 70000 bytes. Observed total elapsed time was 1105830 microseconds,
maximum Step 2533 and separate service call 3026 microseconds, not worst-case bounds.
Captures 177-180 returned zero with cores, fonts and Vulkan healthy, watchdog off
and temporary DNS settings removed. Monitor 483 was unchanged. Shared Pi 3
compilation passed; physical proof is Pi 4 only. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-deadlines483`.


### Graceful HTTP/2 connection shutdown

`H2ClientShutdown(context, now, timeout)` starts bounded NO_ERROR shutdown on an
established HTTP/2 connection. `now` and `timeout` use the same clock units as
`H2ClientStep`; timeout must be 1 through 0x7fffffff. Repeated calls do not extend
the original deadline. New GET/request submissions return `H2_STATE`, while
existing streams can continue receiving responses and uploading through
`H2ClientData`. Continue stepping, consuming events and servicing the network.
The connection-wide deadline remains an independent upper bound.

The client queues one GOAWAY with last processed peer stream ID zero (server
push is disabled). A full control queue postpones that frame until space becomes
available. Existing partial writes and request HEADERS/CONTINUATION sequences
remain intact. Borrowed response fields and body data remain stable until
consumed. Per-stream deadlines and cancellation continue to work during drain.

Once all streams, retained events and outgoing frames have drained, the client
closes its transport and Step returns `H2_DRAINED` (6), with state 5. This is a
terminal status, not a retained event: it does not require Consume. Later Step
calls keep returning that status, and Close does not close the transport twice.
An expired shutdown deadline instead closes immediately with `H2_TIMEOUT`.
`H2ClientCancel` and `H2ClientClose` retain their immediate behavior. This API
belongs to the explicit H2Client interface; do not call it on the H2 context
owned by an active automatic WebClient request.

Physical Pi 4 qualification under Anvil 483 covered idle and active connections,
shutdown expiry, immediate cancellation, peer GOAWAY, a borrowed DATA event,
stream expiry during drain, and a full 1020-byte control queue. Eight upload
cases passed with shutdown requested before body submission, including a
70000-byte flow-controlled upload, unknown-length bodies, empty END_STREAM,
HEAD, large request headers and early rejection. All 46 engine and eight
stream-deadline regression cases passed. Captures 181-185 used deterministic
transport fixtures on the physical processor.

Capture 186 used actual certificate-verified HTTPS to httpbin.org: /uuid and
/bytes/70000 completed concurrently on one connection after shutdown began,
then the transport closed gracefully. Total response bytes were 70053; observed
elapsed time was 1008747 microseconds, maximum Step 2446 microseconds and separate
network service 2718 microseconds. These observations are not worst-case bounds.
All six captures returned zero with cores/fonts/Vulkan healthy, watchdog off and
temporary DNS settings restored. Shared Pi 3 compilation passed; hardware
qualification remains Pi 4 only. No monitor update was required. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-shutdown483`.

Automatic connection-error GOAWAY transmission and stream-local protocol-error
isolation remain unfinished, alongside broader TLS, off-link IPv6/RDNSS web
qualification and HTTP/3 work.


### Isolating stream window-update errors

A zero WINDOW_UPDATE increment on an active stream now resets that stream with
wire PROTOCOL_ERROR (1) and `localError=H2_PROTOCOL`. An increment that would
overflow its send window instead uses wire FLOW_CONTROL_ERROR (3) and
`localError=H2_FLOW`. The caller receives H2_RESET, consumes it and can release
the failed stream; other requests keep their connection and make progress.
Invalid idle/future or even stream IDs remain connection protocol errors. A zero
connection-window increment is now H2_PROTOCOL, and connection-window overflow
remains H2_FLOW; both still terminate the connection.

Local reset transmission and notification use the same bounded pending-reset
mechanism as stream deadlines. A full control queue postpones the reset without
closing siblings. A stream awaiting notification cannot be released. Partial
outbound frames remain intact. Closed-stream frames receive the existing minimal
processing: ignored response fields still update HPACK state, and discarded
DATA restores connection credit without restoring stream credit.

Physical Pi 4 capture187 reproduced the previous connection-wide failure for
both zero and overflowing stream increments. Capture188 passed nine targeted
cases: those errors with a valid sibling, control-queue congestion, late HPACK
and DATA plus a closed-stream update, connection-window zero/overflow, invalid
idle/even IDs, and a valid increment with two successful responses. Wire reset
codes, local errors, complete sibling content, credit and one final transport
close were independently checked. Captures189-191 passed all46 engine cases,
eight stream-deadline cases and eight graceful-shutdown cases. These use
deterministic transport fixtures on the physical processor, not an external
server serving malformed traffic. Shared Pi3 compilation passed; physical
qualification is Pi4 only. All captures returned zero with healthy cores,
fonts and Vulkan, watchdog off; monitor483 was unchanged. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-stream-window483`.

This change does not complete stream-local error isolation. Response-body,
receive-window and response-field isolation are described below; other stream
error paths still need work. Automatic connection-error GOAWAY transmission, remaining TLS,
off-link IPv6/RDNSS web qualification and HTTP/3 also remain unfinished.


### Response-body errors and discarded connection credit

Malformed response DATA now resets the affected stream instead of terminating
unrelated requests: DATA before final response headers, prohibited nonempty
content on HEAD/204/304 responses, and content exceeding its declared length
use wire PROTOCOL_ERROR (1) with local H2_PROTOCOL. A short body detected at
END_STREAM also yields RESET rather than END. Its earlier DATA events may
already have been delivered; callers must treat the response as failed when
that reset arrives. Stream receive-window exhaustion uses wire
FLOW_CONTROL_ERROR (3) with local H2_FLOW.

Rejected and late closed-stream DATA still consumes connection credit, including
padding. A pending discard-credit counter queues a connection WINDOW_UPDATE when
control space is available. Credit becomes available to the peer only after
that complete frame is sent. This avoids losing credit or closing a healthy
sibling when reset and credit frames meet a full control queue. Graceful shutdown
also waits for pending discarded credit. No new caller buffer is required, but
the H2Client structure changed and callers must recompile.

Connection-wide receive-window exhaustion, idle-stream DATA and invalid padding
remain connection errors. Integer resource limits and corrupt HPACK
retain their existing behavior; field semantics are covered below, and this is not complete stream-local
protocol-error isolation.

Physical Pi 4 capture 192 reproduced three prior connection-wide failures.
Capture 193 passed 15 targeted cases covering the body errors above, padded
excess and valid bodies, full control-queue congestion, fatal connection/padding
errors, and valid empty HEAD/204 responses. HEAD metadata and reduced receive
windows were seeded in the fixture to isolate those branches; this does not
claim a new externally negotiated receive-window API or a real HEAD request in
that fixture. Exact reset codes, local errors, delivered body bytes, completion
counts, outgoing credit and restoration to 65535 connection bytes were checked.
Captures 194-196 passed all 46 engine, eight deadline and eight shutdown cases.
These are fragmented deterministic transport fixtures executed on the physical
processor, not public-server malformed-traffic tests. Shared Pi 3 compilation
passed; no physical Pi 3 claim. All five captures returned zero with healthy
cores/fonts/Vulkan and watchdog off; installed Anvil 483 was unchanged. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-body-errors483`.

Other stream error paths and automatic connection-error GOAWAY transmission
remain unfinished, alongside remaining TLS,
off-link IPv6/RDNSS web qualification and HTTP/3.


### Malformed response-field isolation with HPACK continuity

Semantic field failures now produce a stream RESET with wire PROTOCOL_ERROR (1)
and local H2_PROTOCOL. This includes the existing field-name/value, pseudo-header,
status and Content-Length validation failures. Missing status, an informational
response with END_STREAM, and invalid trailer semantics use the same path.
Previously emitted FIELD events may already have been consumed; the reset marks
the whole response as failed. No fields from the rejected remainder are exposed.

The client continues decoding the rest of the rejected compressed block. Dynamic
insertions still update the shared HPACK table, even after the reset notification
has been consumed and the old stream slot released. Valid sibling requests can
therefore reference that table without reopening their connection. This also
applies when invalid trailer framing is recognized before decoding its fields.
Pending resets retain the existing bounded-queue behavior. Corrupt HPACK,
interrupted CONTINUATION sequences, numeric resource limits and remaining
frame-level errors retain their existing failure behavior.

Physical Pi 4 capture 197 reproduced uppercase-name, missing-status and
duplicate-status connection-wide failures. Capture 198 passed 18 targeted cases:
field validity, pseudo-header/status ordering, prohibited fields, invalid and
conflicting lengths, informational END_STREAM, invalid trailers, a continued
malformed block, full control-queue congestion, valid fields and dynamic reuse,
and fatal Huffman/continuation errors. The malformed-block cases append a new
HPACK entry and make the sibling response reference it; successful sibling body
completion checks continued decoder synchronization. Wire reset/local codes,
completion counts, content and credit were checked. Captures 199-201 passed all
46 engine, eight deadline and eight shutdown regressions. These are fragmented
transport fixtures on the physical processor, not malformed public-server
traffic. Shared Pi 3 compilation passed, without a physical Pi 3 claim. All five
captures returned zero with healthy cores/fonts/Vulkan and watchdog off; Anvil
483 was unchanged. Capture 200 initially suffered a stalled screenshot transfer
and a prompt timeout. A later fresh readiness probe recovered the same retained
capture and report without rebooting or rerunning the payload; the original
failed transfer record is preserved alongside the recovered evidence. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-header-errors483`.

Remaining work includes other stream/frame-error classifications and automatic
connection-error GOAWAY transmission, plus the broader TLS, off-link IPv6/RDNSS
web qualification and HTTP/3 work. This is not a complete networking claim.


### Legacy priority hints and contextual PRIORITY frame errors

The client does not schedule requests using deprecated dependency-tree hints.
Well-formed PRIORITY payloads are therefore ignored, including self-references
and hints for idle streams. HEADERS still accounts for the mandatory five-byte
priority prefix, including padding and CONTINUATION handling, without interpreting
the unused dependency. This adds no priority scheduler and allocates no stream
state for a hint. RFC 9113 section 5.3.2 deprecates the older signaling scheme.

A malformed PRIORITY length on an active stream is consumed within the fixed
16384-byte receive limit, then produces wire FRAME_SIZE_ERROR (6) and local
H2_FRAME_SIZE through RESET. The shared frame decoder itself remains strict:
only the connection engine, with established settings, no pending continuation
and a known active stream, handles that error as stream-local. Pending resets
retain bounded queue behavior. Oversized frames, zero stream identifiers,
malformed hints without an active stream, interrupted header sequences and
short HEADERS priority prefixes remain connection failures. This conservative
escalation policy does not enlarge receive buffers or bypass framing checks.

Physical Pi 4 capture 202 reproduced connection closure from legacy priority
self-references and a short active-stream PRIORITY. Capture 203 passed 16 cases:
active/idle/even hints, ordinary hints, padded and continued priority HEADERS,
malformed active lengths 0/4/6/16384, full control-queue congestion, and five
fatal boundary/order cases. Exact reset/local codes, request completion,
content, credit and close ownership were checked. Captures 204-205 passed all
46 engine and eight shutdown regressions. These are fragmented deterministic
transport fixtures on the physical CPU, not external-server malformed traffic.
Shared Pi 3 compilation passed; no physical Pi 3 claim. All four captures
returned zero with healthy cores/fonts/Vulkan and watchdog off. Installed Anvil
483 was unchanged. Evidence:
`docs/evidence/anvil-ipv6-20261030/http2-priority483`.

Connection-error GOAWAY remained unfinished at this checkpoint; the following
section records its implementation and transport-drain qualification.


### Connection-error GOAWAY and verified TLS output draining

Peer connection failures now enter H2_STATE_ERROR_DRAIN (state 6). Step returns
zero while finishing pending output, then returns the original negative error
and retains it in the failed state. Continue pumping Step and network service;
a latched error during state 6 is not permission to reuse the connection.
New requests are refused, incoming bytes are no longer parsed, and no new
application events are emitted. Existing partial frames and contiguous outgoing
HEADERS/CONTINUATION sequences complete before queued GOAWAY. A prior graceful
NO_ERROR GOAWAY can be followed by the connection-error frame.

Wire errors are PROTOCOL_ERROR (1), FLOW_CONTROL_ERROR (3), FRAME_SIZE_ERROR (6),
COMPRESSION_ERROR (9), and ENHANCE_YOUR_CALM (11) for local decoding/storage
limits. Last processed peer stream ID remains zero because server push is
unsupported. Transport/caller failures and pre-negotiation errors close directly;
they are not all classified as peer protocol errors. Explicit cancellation and
Close remain immediate. Error output is best effort, bounded by the original
connection deadline, any active shutdown deadline, and a 65536-work-step budget.
Transport failure, unavailable drain support or budget expiry retains the
original connection error; explicit Cancel reports H2_CANCELLED.

TLS Send accepts copied plaintext into a queue; it does not prove that records
have reached TCP. Shared TlsClientDrain and ABI 1.14 slot 92 now return 1 only
when accepted plaintext and protected records have passed to TCP, 0 while pending,
or a negative error. This is not a peer acknowledgement. The 200-entry table and
all previous signatures are unchanged. WebTransportDrain binds the optional slot
only for minor >=14 and count >=93, returns ENOSYS without it, and treats plaintext
TCP send acceptance as already handed to TCP. Cooperative TLS advances one bounded
slice per drain call; synchronous fallback targets retain their existing behavior.

Both graceful and connection-error shutdown now pump transport drain after their
HTTP/2 buffers empty. Graceful shutdown cannot report H2_DRAINED on an older monitor
without the service. WebClient's H2 adapter waits through error draining instead
of trying to submit another upload or prematurely reporting response completion.
This corrects forum finding 1543: the previous graceful path could close TLS while
accepted GOAWAY bytes were still queued.

Physical Pi 4 qualifications under installed 483 exercised the new shared code:

- Capture 211: eight production TLS queue cases with controlled crypto/TCP seams,
  including copied input, delayed progress, partial records, a blocked transport,
  transport failure, closed/pending states and invalidated handles.
- Capture 212: 19 error-GOAWAY cases covering exact wire codes, queue pressure,
  write and drain failures, deadlines, cancellation, unsupported drain and no
  further receives. Repeated pending drain results must precede close.
- Capture 213: three failures during real request output, preserving a partial
  DATA frame, a 31-field HEADERS/CONTINUATION block, and queued control frames.
- Captures 214-216: all 46 engine, 12 graceful-shutdown and 26 WebClient cases.
  Graceful tests include pending/failing/unsupported drain; WebClient tests include
  GET and a flow-blocked POST receiving connection errors.

These deterministic transport/crypto seams are not malformed external-server
traffic or independent cryptographic validation. Initial capture 206 had an oracle
that wrongly rejected a deadline-truncated GOAWAY header; its corrected check
validates the exact prefix. Capture 210 exposed an outdated expectation for the
previously implemented stream-local truncated-body error. The expected WebClient
stream reset is now checked. Original failed host checks remain in the evidence;
the final suites passed without weakening successful-output framing requirements.

Full Pi 4 build 485 and Pi 3 build 99 compiled. Build 485 was installed with a
verified 483 rollback, candidate and boot-file readback, one restart, a 90-second
quiet boot interval and full running-image SHA verification. The initial separate
candidate write failed before the boot file was touched. Only two old candidate
images were removed, each after hash matching its retained backup; the update then
completed. No unique rollback was removed. The guide PDF was rebuilt and its
changed section and adjacent pages visually checked.

Live capture 217 on build 485 completed certificate-verified HTTP/2 HTTPS
requests to httpbin.org /uuid and /bytes/70000: 70053 bytes, two completed
streams, successful resident TLS drain and graceful transport closure. It took
1244348 us; observed maxima were Step 2513 us, network service 2949 us
and drain 33 us. This run found the queue already drained on its first
check; pending progress is covered by the controlled physical fixtures above.
These observations are not worst-case timing guarantees. Cores, fonts and Vulkan
remained healthy, watchdog off. Pi 3 has compile evidence only.

Evidence: `docs/evidence/anvil-ipv6-20261030/http2-error-drain485`.
Broader TLS compatibility/blocking, public off-link IPv6 and automatically learned
RDNSS web qualification, and HTTP/3 remain open. This is not a complete networking
or HTTP/2 conformance claim.

### WebSocket close output ownership (2026-10-30)

WebSocket clean close now requires both Close frames and transport output drain.
TLS send acceptance alone does not prove that queued plaintext reached TCP.
`WebSocketClientStep` returns progress while draining, stops receiving or echoing
more frames in that state, and keeps the existing two-second close deadline.
Transport drain errors, including unavailable ABI support, are returned instead
of a false clean close. Explicit Abort remains immediate. A peer TCP half-close
does not skip sending the local Close reply.

The shared implementation uses the ABI 1.14 drain service already installed in
Anvil 485. No monitor replacement was required. The CPU fixture now composes the
current HTTP and transport owners instead of an obsolete transport replacement.
Physical Pi 4 capture 218 reproduced discarded TLS output and the missing reply;
capture 219 passed all 16 final cases. These cover delayed and failing drain,
partial writes, missing service, timeout, cancellation, local and peer close,
TCP half-close, TLS closure before reply, and repeated terminal calls. Independent
frame decoding checks masked client output. Delayed-output tests use controlled
transport callbacks, not an external server or independent cryptography test.

Live capture 220 used resident randomness and certificate-verified TLS to
`wss://httpbingo.org/websocket/echo`, echoed all 15 bytes and completed normal
close. Elapsed time was 690 ms; maximum observed Step was 2038 us, network
service 1860 us and drain 33 us. The live queue was ready on its first drain
check; controlled tests establish pending behavior. These timings are observations,
not worst-case guarantees. Cores, fonts and Vulkan remained healthy, watchdog off.
The same shared fixture compiled for Pi 3; it was not run on a physical Pi 3.

Evidence: `docs/evidence/anvil-ipv6-20261030/websocket-drain485`.
Remaining TLS blocking/compatibility, public off-link IPv6/RDNSS qualification,
and HTTP/3 are still open.

### QUIC wire layer and current timing evidence (2026-10-30)

`Anvil/Network/quic_wire.pbi` starts the shared QUIC v1 transport work for HTTP/3.
It supplies checked 62-bit integer encoding/decoding, untrusted packet boundary
parsing, packet-number reconstruction, and outgoing Initial/0-RTT/Handshake
headers. The implementation was written from the protocol definitions in
[RFC 9000](https://www.rfc-editor.org/rfc/rfc9000.html) sections 16-17 and the
[RFC 9001](https://www.rfc-editor.org/rfc/rfc9001.html#section-5.4.2) header
protection sample requirement. No implementation was copied.

Integer decoding accepts legal nonminimal widths; frame-type canonical encoding
must be enforced by the future frame decoder. Header parsing preserves protected
bits without interpreting them, bounds connection IDs and token/packet lengths,
and identifies coalesced packet boundaries. Version Negotiation permits the
version-independent longer connection IDs; unknown versions return an explicit
unsupported result after exposing only invariant fields. Retry tokens and tags
are only located, not authenticated. Packet-number reconstruction takes the
largest previously authenticated number; its result still needs authentication.
Writers validate arguments and capacity before changing output. These routines
allocate nothing and contain no network waits or private driver state.

Physical Pi 4 capture 222 under Anvil 485 passed 463 cases: 261 integer cases,
81 packet cases, 79 packet-number cases, 31 outgoing header cases and 11 null or
negative argument refusals. Independent Python expectations check complete output,
guard bytes, truncation, all integer widths, overflow limits, reserved/protected
bits, short/long/Retry/Version Negotiation formats and coalescing. Pi 3 compilation
passed without a physical Pi 3 claim. Capture 221 initially failed one Python
expectation at the maximum packet-number boundary: it omitted the guarded upper
bound in RFC 9000 A.3. The corrected oracle passes all 452 retained first-run
cases; original failed and corrected reports are both kept. Runtime code did not
change to satisfy that correction. Cores, fonts and Vulkan remained healthy;
watchdog off. No monitor update or storage mutation was needed.

This is not yet a QUIC connection or an HTTP/3 request path. Required remaining
work includes packet protection and Retry integrity, TLS handshake over CRYPTO
frames with transport parameters, frame parsing and stream reassembly, ACK/loss
recovery and congestion/flow control, UDP ownership and timers, QPACK and HTTP/3
control/request streams, and live interoperable verified requests. Reuse shared
crypto and network owners; do not create a second TLS or IP implementation.

The retained live service counters were also read without restarting the Pi.
The longest call was 2948 us: HTTP server/TCP contributed 1719 us and TLS 1221 us.
The largest individual TLS phase was 1698 us. Root open peaked at 1054 us, root
read at 506 us, and exFAT boot validation at 1065 us. These cumulative observations
are not worst-case guarantees. `PayNetService` explicitly runs maintenance once
before draining receive within the remaining slice; no service was skipped merely
to make a strict timing limit appear to pass. The current advertised IPv6 prefix
is private ULA, with a link-local router and DHCPv4 DNS; it still does not prove
public off-link IPv6 or automatically learned RDNSS web traffic.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-wire485`. TLS/device blocking
and compatibility, public IPv6 qualification and full HTTP/3 remain open.

### QUIC packet protection, shared crypto ownership (2026-10-30)

`Anvil/Network/quic_crypto.pbi` adds QUIC v1 Initial client/server key derivation,
traffic-secret key derivation, AES-128-GCM packet protection, header protection
and authenticated reserved-bit rejection, using existing shared SHA/HMAC/HKDF,
AES and bounded GCM jobs. It implements protocol facts from
[RFC 9001 sections 5.1-5.4](https://www.rfc-editor.org/rfc/rfc9001.html#section-5).
Callers include those crypto modules before this module. Key derivation runs one
small HKDF operation per step; packet work uses the existing 256-byte GCM steps.
There is no socket, allocation, driver state or network wait in this layer.

`QuicInitialKeysBegin` and `QuicTrafficKeysBegin` use a zero-initialized
`QuicKeyJob` and `QuicKeys`; `QuicKeyJobStep` returns pending (0), ready (1), or
a negative error. Cancel wipes an unfinished key job and its partial keys;
completed keys remain caller-owned until `QuicKeysWipe`. The 32-byte supplied
traffic secret must not alias its destination. Only AES-128-GCM/SHA-256 and
QUIC v1 are implemented; no cipher negotiation or key update is implied.

`QuicPacketJobBegin` takes the last authenticated packet number for decrypt,
or the full unique packet number for encrypt. Its caller owns the packet buffer
and job until completion; pending output must not be sent or consumed. One
explicit packet owner shares the existing GCM job. A busy job is refused before
packet mutation, and cancellation cannot cancel another owner. Decrypt verifies
the tag before writing plaintext. Bad authentication restores the original wire
packet; authenticated invalid reserved bits are rejected before plaintext too.
Cancellation instead requires discarding the partially processed packet. Keys,
nonces and header-mask scratch copied into jobs are wiped at termination. The
connection owner must enforce packet-number uniqueness, authenticated receive
state, cipher usage limits and key-phase transitions.

When TLS record code shares this address space, bind
`QuicCipherInvalidateHook` to `Tls13RecInvalidateCipher` before use. This clears
the TLS installed-key cache before QUIC touches shared AES/GCM scratch. The two
new GCM queries expose busy state and the verified-before-plaintext phase without
changing existing GCM Begin/Step behavior.

Physical Pi 4 capture 224 under Anvil 485 passed 49 independent cases: published
client/server Initial packets, all packet-number widths, a high full packet
number, all 16 tag-byte corruptions, header/cipher corruption, wrong key,
authenticated reserved bits, busy owners, cancellation and secret clearing.
Two cases interleave real TLS record protect/unprotect operations between QUIC
steps and after completion, checking the full RFC packet outputs and TLS
plaintext. A Python oracle using `cryptography` AESGCM/AES-ECB also reproduces
the RFC 9001 Appendix A packets byte for byte. Its first text extraction missed
the server payload's final three bytes; this was corrected before board testing.

The final run measured 164 us maximum key step, 225 us maximum packet Begin,
and 527 us maximum packet Step. These are fixture observations, not universal
latency bounds. Capture 223 retains the initial 47-case proof. Pi 3 shared-module
compilation passed; its compile-only harness omits the Pi 4 cache transitions
after the first attempt exposed a platform-helper difference. No physical Pi 3
claim is made. Both Pi 4 runs returned normally; cores, fonts and Vulkan remained
healthy, with watchdog off. No monitor or boot image update was required.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-crypto485`.
This provides packet cryptography, not a live QUIC connection or verified HTTP/3
request. Retry integrity, TLS-over-CRYPTO transport parameters, frames/streams,
recovery/congestion/flow control, UDP ownership, QPACK and interoperable live
qualification remain. Initial keys are public protocol keys, not peer identity
verification. Remaining TLS/device blocking and compatibility and public off-link
IPv6/RDNSS web qualification also remain open.

### QUIC Retry integrity (2026-10-30)

`QuicRetryJobBegin` extends the shared QUIC crypto owner with v1 Retry integrity
from [RFC 9001 section 5.8](https://www.rfc-editor.org/rfc/rfc9001.html#section-5.8).
It accepts contiguous caller-owned storage containing one original-destination-ID
length byte, that ID (0-20 bytes), and the full Retry packet including its 16-byte
tag. This prefix can occupy receive headroom; it is never sent on the wire.
Keeping it contiguous avoids copying an entire packet during admission. The
caller retains this storage until the existing `QuicPacketJobStep` completes or
`QuicPacketJobCancel` cancels the operation.

With `writeTag=0`, the job checks all tag bytes before returning a result and
leaves the input unchanged, including on failure. With `writeTag=1`, it writes
the outgoing tag only on completion. Invalid original-ID lengths, packet kinds
and versions are refused before mutation. Retry shares the existing GCM job,
busy-owner refusal, bounded authentication steps and TLS cipher-cache invalidation
contract. It uses the RFC's fixed v1 key/nonce; those public values provide no
peer-identity verification. The connection owner still must enforce Retry timing,
the original connection-ID context, acceptance at most once and connection-ID
matching before using a token or restarting its Initial exchange.

Physical Pi 4 capture 225 under Anvil 485 passed all 82 cases: the earlier 49
packet-protection cases plus 33 Retry cases. An independent AESGCM calculation
reproduces the published Appendix A.4 Retry packet. Checks cover tag generation
and verification, zero/max-length original IDs, a multi-step 1024-byte token,
all 16 tag-byte corruptions, changed original ID/header/token, busy owners,
cancellation, TLS-record interleaving and malformed-input refusal. Entire output
buffers and guard bytes are compared; secret/job ownership checks also pass.

Retry Begin peaked at 117 us and Retry Step at 122 us in this fixture. Across all
82 cases, packet Begin peaked at 225 us and Step at 525 us. These are measured
observations, not worst-case bounds. Shared-module Pi 3 compilation passed without
a physical Pi 3 claim. The Pi 4 returned normally; cores, fonts and Vulkan stayed
healthy, watchdog off. No monitor/boot image change was required.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-retry485`.
TLS-over-CRYPTO transport parameters, frame/stream handling, ACK/loss recovery,
congestion/flow control, UDP ownership, QPACK and live verified HTTP/3 traffic
remain, along with remaining TLS/device blocking and compatibility and public
off-link IPv6/RDNSS web qualification. Retry integrity alone is not a QUIC
connection or an authenticated web request.

### QUIC transport-parameter validation (2026-10-30)

`Anvil/Network/quic_parameters.pbi` adds bounded parsing and connection-ID
binding for the v1 transport parameters described in
[RFC 9000 sections 7.3 and 18.2](https://www.rfc-editor.org/rfc/rfc9000.html#section-18.2).
It shares the existing checked QUIC integer decoder and contains no driver,
socket, allocation or cryptographic state. The existing TLS handshake remains
unchanged; its QUIC extension/CRYPTO integration is still to be implemented.

Zero-initialize `QuicParameters`, then call `QuicParametersBegin` with immutable
input, peer role and separate caller-owned `QuicParameter` entry storage.
`QuicParametersStep` handles one parameter per call, returning pending (0),
complete (1), or a latched negative error. Local resource policy permits at most
16384 input bytes and 64 parameters, including unknown parameters. Each step
performs at most 64 duplicate comparisons. Capacity exhaustion is explicit;
input is not silently truncated. Unknown extensions and legal nonminimal
integer encodings are accepted, while duplicate IDs are refused. Begin validates
buffer ranges and overlap before mutation.

Validation covers integer encoding/length, UDP payload minimum, stream-count
limits, ACK exponent/delay, active connection-ID minimum, connection-ID lengths,
reset-token length, migration-flag emptiness and preferred-address structure.
Client-supplied server-only parameters are refused. Required Initial connection
IDs and the server's original destination ID must be present. A preferred
address cannot accompany a zero-length Initial source ID. Entries contain raw
input offsets/lengths and decoded values for known integer fields; absence and
protocol defaults remain distinguishable for the connection owner.

`QuicParametersFind` exposes no entries while pending, after failure or after
`QuicParametersCancel`. After completion, `QuicParametersCheckIds` compares the
received parameters with the IDs actually used in Initial/Retry packets. It
checks required or forbidden Retry-ID presence as well as byte-for-byte matches.
Only apply limits after parsing, ID binding and TLS peer authentication all
succeed. Keep input, job and entry storage alive and unchanged while consuming
the returned spans. This module alone establishes no TLS identity or connection.

Physical Pi 4 capture 226 under Anvil 485 passed all 64 cases. Independent
expectations compare full entry IDs, offsets, lengths and numeric values, with
input preservation, buffer guards, pending/failed lookup refusal, cancellation,
role checks, malformed lengths, known/unknown duplicates, numeric boundaries,
preferred-address constraints, Initial/Retry ID mismatches and the 64-entry
capacity boundary. The largest observed step was 93 us in this fixture, which
does not change the monitor's cache state; it is not a worst-case guarantee.
The same shared fixture compiled for Pi 3 without a physical Pi 3 claim. The
Pi returned normally, cores/fonts/Vulkan healthy and watchdog off. No firmware
or boot image update was needed.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-parameters485`.
TLS extension/CRYPTO integration, frame/stream handling, recovery/congestion/flow
control, UDP ownership, QPACK and live verified HTTP/3 remain. Remaining TLS
blocking/compatibility and public off-link IPv6/RDNSS web qualification remain
open; these parameter tests do not establish any live web-traffic result.

### TLS handshake interface for QUIC (2026-10-30)

The existing shared TLS handshake now has an explicit QUIC mode, following
[RFC 9001 sections 4 and 8](https://www.rfc-editor.org/rfc/rfc9001.html#section-4).
It reuses the existing key schedule, certificate/CertificateVerify processing,
transcript and Finished verification. No alternate verification path was added.
The normal TLS record mode remains the default after `Tls13Init`.

After Init and before ClientHello, call `Tls13SetQuicParameters` with a separate
48-byte configuration block, local parameter bytes and peer-parameter storage.
Each connection owns its own configuration and buffers for its full lifetime.
The six native integers in the block hold local pointer/length, peer
pointer/capacity, received length and received flag. Input and output buffers
must remain disjoint and alive. Local/peer parameter storage is limited to
16384 bytes. TLS treats the bytes as opaque; the QUIC owner validates local
parameters before sending, and uses `QuicParameters` plus connection-ID checks
on the received parameters before applying them after authentication.

In this mode ClientHello includes extension 57, requires an ALPN offer, has an
empty legacy session ID and returns raw handshake bytes. EncryptedExtensions
must contain a selected offered ALPN and exactly one transport-parameter
extension; peer bytes are copied into the supplied buffer. A received flag alone
is not proof of a completed valid handshake. Client Finished also returns raw
handshake bytes; normal TLS still emits the encrypted record. TLS record input,
record application output, record alerts and TLS KeyUpdate are refused in QUIC
mode. The owner maps TLS alerts to QUIC connection errors and supplies QUIC's
own packet protection/key-update machinery.

`Tls13FeedQuic(level, input, bytes)` accepts already authenticated, ordered
CRYPTO data: level 0 Initial, 2 Handshake or 3 application. Each call consumes
at most 256 bytes and stops at a handshake-header/message boundary so the next
call rechecks the encryption level after a state transition. It returns consumed
bytes, zero for empty input or -1 for terminal failure. The existing TLS message
handlers still run on completion; this input bound is not a new worst-case
latency guarantee for certificate processing. The owner must handle CRYPTO
offsets/reordering/retransmission, packet-key availability/discard, application
data ordering and QUIC handshake confirmation. TLS's connected state alone does
not mean QUIC's handshake-confirmed state.

Connection snapshots are now 2928 bytes: the extra native integer saves the
configuration pointer. Referenced buffers are not deep-copied. The existing
connection pool allocates and indexes snapshots using `TLS13_CONTEXT_SIZE`;
ordinary Init resets the pointer to zero.

Physical Pi 4 evidence under Anvil 485:

- Capture 227 passed 29 codec/ALPN cases, including the legacy cases and QUIC
  offer/selection, missing/duplicate extension, buffer refusal and received-byte
  validation through the shared parameter decoder. This fixture stubs transcript
  append and is not a certificate-handshake proof.
- Capture 228 passed connection switching with four real AES-GCM records and
  independent ciphertext expectations, including configuration-pointer isolation,
  existing certificate/ALPN state, cache invalidation and snapshot wiping.
- Capture 229 passed 15 tests using the full shared TLS source and real
  X25519/HKDF/HMAC/AES-GCM. They cover fragmented ServerHello/EncryptedExtensions,
  level changes at and within message boundaries, 256-byte input slices, forbidden
  TLS KeyUpdate/record APIs, correct and corrupted server Finished, application
  secrets, raw client Finished and unchanged legacy Finished ciphertext.
  Deterministic keys and selected starting states isolate these checks: this is
  not certificate-chain verification or a live authenticated QUIC peer.

All runs returned normally with healthy cores/fonts/Vulkan and watchdog off.
Pi 3 codec compilation passed without a physical Pi 3 claim. Full Pi 4 crypto
compilation passed after replacing an unsupported multi-value Case in the new
receive wrapper; the earlier codec/context fixtures did not include that wrapper.
Their exact pre-fix source and unchanged relevant procedure comparison are
retained. No monitor/boot image update was made.

Evidence: `docs/evidence/anvil-ipv6-20261030/tls-quic485`.
Next remains the QUIC connection owner: frames/streams, CRYPTO reassembly,
recovery/congestion/flow control, UDP integration and QPACK, followed by live
certificate-verified HTTP/3. The new interface does not yet provide that request
path. Existing TLS compatibility/device-blocking and public IPv6/RDNSS web
qualification remain open.

### IPv6 UDP wire support (Pi 4 build 485)

`Anvil/Network/ipv6_udp.pbi` adds shared UDP emission and borrowed receive
views using the existing IPv6 packet parser and checksum implementation.
The checksum is mandatory; computed zero is emitted as `FFFF`. UDP length
controls the delivered data and checksum, excluding trailing IP/link padding.
Extension headers and atomic fragments use the common IPv6 parser; other
fragments need reassembly. This ordinary-packet API excludes jumbograms and
zero-checksum tunnel exceptions. Address ownership, scope, port binding and
multicast membership belong to the endpoint, not this wire codec.

Physical capture 230 on Pi 4 build 485 passed 40 independent byte/view cases,
including 1200-byte QUIC payloads, minimum-MTU packets, corrupt/absent checksums,
padding, extensions, fragments and pointer/output refusals. Cores, fonts and
Vulkan remained healthy; watchdog off. The same UDP source compiled for Pi 3
after removing Pi 4 cache lifecycle calls from the compile-only harness; its
initial refusal is retained. There is no physical Pi 3 claim.
Evidence: `docs/evidence/anvil-ipv6-20261030/ipv6-udp485`.

This is packet support, not a live UDP socket or HTTP/3 request. Existing IPv6
DNS currently uses TCP. The generic payload datagram API, QUIC connection
ownership/recovery and QPACK remain to be integrated.

### IPv6 UDP stack integration

The shared stack now uses `NetUdp6BuildFrom` for unicast emission through the
existing assigned-source, route and neighbor hooks. It returns 1 with a frame
in `NetOutBuf`/`NetOutLen`, or 0 with `NetError` (zero means a pending neighbor).
Datagrams are limited to 1232 data bytes until path-MTU discovery is integrated.
No alternate route/neighbor implementation or synchronous wait is introduced.

IPv6 ingress validates the checksum and assigned local address, observes port
bindings/listeners, and exposes the tuple with `NetUdpRxFamily`, `NetUdpRxFrom6`
and `NetUdpRxTo6`. Address pointers borrow the current receive frame; payload
bytes use the existing UDP scratch. `NetServiceSetUdp6Hook` registers a separate
resident consumer. IPv6 never enters the IPv4 DHCP/NTP/DNS/console handlers.
The callback must copy what it retains and must not pump another receive.
The unicast endpoint does not yet enable multicast socket delivery.

Physical capture 232 passed 31 cases using the real shared stack and extracted
dispatcher, with controlled source/neighbor and protocol-owner callbacks. They
cover family isolation, legacy DHCP dispatch, stale hook results, listeners,
invalid sources/checksums, exact emitted frames and pending/error resolution.
The first harness used `NetDefaults` instead of the complete `NetInit` reset
and expected a byte count from a Boolean builder; its refused report is retained.
The corrected expectations and setup passed without changing production code.
Full Pi 4 build 486 and Pi 3 build 100 compiled. This controlled packet test is
not a live UDP exchange or physical Pi 3 qualification.

Pi 4 build 486 was then installed with a verified 485 rollback, a single
restart and a 90-second quiet boot interval. Capture 233 completed two real
certificate-verified HTTPS/HTTP/2 streams (70,053 bytes), including resident TLS
draining and graceful close. This run took 1.265 seconds; maximum observed
client step/service costs were 2,525/2,723 microseconds. These observations are
not worst-case latency guarantees. Cores/fonts/Vulkan stayed healthy and the
watchdog was off. Evidence: `docs/evidence/anvil-ipv6-20261030/udp6-ingress486`.
Generic payload UDP sockets and live QUIC/HTTP/3 remain open.

The final module-boundary correction exposes shared `IPv6UnicastAddress` and
`IPv6UdpSpanValid` checks instead of cross-file private calls. The layering
gate refused the intermediate form; that refusal and source snapshots are
retained. Capture 234 passed the 31 integration cases again, and capture 235
passed 28 IPv6 TCP cases. Recompiling the 40-case UDP wire fixture produced a
byte-identical PMF container to capture 230; the equivalence is recorded.
Final full monitors are Pi 4 build 487 and Pi 3 build 101.
Build 487 was installed and its running-image SHA verified after the full boot
interval, retaining verified 486 and 485 candidates as rollbacks. Capture 236
repeated the two live verified HTTPS/HTTP/2 responses and graceful drain/close:
70,053 bytes in 1.078 seconds, maximum observed step/service 2,532/2,362
microseconds. Board health passed and the watchdog was off.


### Payload datagrams: ABI 1.15

Anvil now appends UDP slots 200-207: Open, SendTo, Receive, Peek, Status,
Close, Service and Discard. `Anvil/Network/udp_payload.pbi` validates the
table before binding. The resident owner is shared across compositions,
including networking targets without the TCP/TLS payload group. Prior slots
and signatures retain their meanings. The guide documents the fixed records,
limits, serialized caller contract and asynchronous completion semantics.

Four sockets own interface/port pairs, with eight copied receive datagrams
and one copied pending send each. Whole-message receive, zero-length packets,
peek/discard, queue-drop counts, generation-tagged handles and payload-return
cleanup are supported. Protected control ports cannot be stolen. Link receipts
are polled; losing a receipt never retransmits an accepted datagram. ARP uses
tracked submission too. This does not promise a hard bound for existing device
maintenance or claim that link completion means peer delivery.

Physical captures 241 and 244 passed 115 owner/dispatch checks each. The final
fixture removes a private helper dependency flagged by the publication gate. An initial IPv4 endpoint refusal exposed a
typed-pointer byte-array access discrepancy: raw reads saw the right bytes but
the compiled typed accessor did not. The endpoint validator now uses explicit
byte reads and passes valid/invalid-address tests. The compiler discrepancy
itself remains open, recorded in forum post 4365; earlier refusals are retained.

Pi 4 build 488 and Pi 3 build 102 compiled. Build 488 is installed and verified
by its entire running-image hash after a 90-second boot wait; 487 is retained
as a verified rollback. Capture 242 exchanged six real datagrams through the
new ABI with a desktop echo peer: IPv4 lengths 0, 17 and 1472; link-local IPv6
lengths 0, 17 and 1232. The desktop independently checked every payload byte.
Observed total exchange time was 71977 us and maximum Service time 531 us.
These are observations, not deadline guarantees or public off-link IPv6 proof.

Capture 243 then passed real certificate-verified HTTPS/HTTP2 regression:
two streams, 70053 bytes, graceful TLS drain/close, ABI minor 15. Elapsed time
was 1060759 us; maximum step/service times 2569/2690 us, drain 32 us.
Cores, fonts and Vulkan remained healthy; watchdog off. No physical Pi 3 claim.
Evidence: `docs/evidence/anvil-ipv6-20261030/udp-sockets488`.

QUIC connection ownership, CRYPTO reassembly, recovery/flow/congestion control,
streams and QPACK still need implementation and live HTTP/3 qualification.
Remaining TLS blocking/compatibility and public off-link IPv6/RDNSS web
qualification are also open. A UDP socket API is not a complete web stack.


### QUIC CRYPTO receive framing and reassembly

`quic_crypto_stream.pbi` adds a borrowed CRYPTO frame reader and a caller-owned
receive context for each encryption level. It accepts nonminimal variable
integers, checks complete lengths and the 62-bit offset limit, and leaves the
view unchanged on malformed input. Packet authentication must precede feeding
the stream; the module does not authenticate packets or peers.

Initial, Handshake and Application contexts are independent; 0-RTT CRYPTO is
refused. Each context owns a data ring and presence bitmap. Storage capacity
is 4096 through 262144 bytes, in multiples of eight, with capacity/8 bitmap
bytes. This is a forward offset window from the consumed position, not an
unbounded sparse-offset store: data outside that window returns LIMIT even
if fewer actual bytes have been retained. The connection owner must map that
resource refusal to CRYPTO_BUFFER_EXCEEDED or provide more storage; it must
not acknowledge and silently lose handshake data.

Put checks at most 16384 bytes and validates all retained overlaps before
writing. Equal retransmissions do not add data; conflicting retained bytes
are refused atomically. Already consumed prefixes are ignored, not retained
for later comparison. Peek offers at most 4096 contiguous bytes and stops at
a ring boundary; Consume accepts only the latest offer, including partial
TLS acceptance. Init invalidates borrows and clears the bitmap, not payload
bytes. Seal rejects a TLS receive-level transition with any older data left
unconsumed; sealed levels accept old retransmissions but no new bytes.
Caller-owned contexts and storage must remain exclusive and unmodified.

Physical capture 246 on Anvil 488 passed 486 checks, including a deterministic
independent byte-map oracle, out-of-order data, duplicates, conflicting late
overlaps, wrap, partial consumption, empty high-offset frames, length overflow,
encryption-level changes, aliases and work bounds. Capture 245 passed the
earlier suite. The full fixture also compiled for Pi 3; it was not run there.
Cores, fonts and Vulkan remained healthy; watchdog off. Evidence is in
`docs/evidence/anvil-ipv6-20261030/quic-stream488`.

This is physical execution of the receive component, not a live QUIC handshake.
The installed monitor stays at 488. Connection ownership, frame dispatch and
TLS handoff, recovery, streams, QPACK and live HTTP/3 qualification remain open.


### Reassembled QUIC bytes handed to TLS

`Anvil/Network/quic_tls_receive.pbi` adds `QuicCryptoTlsStep` after the complete
shared TLS includes. The caller restores the correct TLS connection and
selects its receive stream; this adapter does not own or switch connections.
It offers at most 256 contiguous bytes to `Tls13FeedQuic` and consumes exactly
the accepted count. A gap or empty/sealed stream returns zero. TLS still checks
message boundaries and encryption levels, and retains the existing key schedule,
certificate processing and Finished verification.

After a successful receive-level transition, the old stream must seal without
unconsumed data, including a gap followed by retained bytes. TLS failure or a
failed transition poisons the stream (phase 3); Put and Step then refuse until
fresh Init. Any negative Step result requires connection closure. A transition
error can occur after TLS accepted bytes: its state is not rolled back. The
caller must not retry on another stream or continue the connection. Restored
TLS context and stream/storage require exclusive ownership for the call and
across cooperative hooks. Input slicing is not a wall-clock certificate-work
bound; install the existing cooperative TLS hooks. Packet authentication must
precede insertion into receive streams.

Capture 248 on Anvil 488 passed 18 scenarios using real shared TLS, X25519,
HKDF and Finished processing: reordered/duplicate input, single-byte fragments,
Initial-to-Handshake transition, wrong levels, gapped old data, Finished with
trailing data, bad Finished, application tickets, forbidden KeyUpdate, exact
consumed offsets, sealed-idle calls and repeat refusal after poisoning. Existing
raw/record Finished output checks remain in the suite. Deterministic starting
states isolate the boundaries; this does not prove certificate-chain processing
or a live authenticated QUIC peer. The returning payload completed in 2.5 s;
that is fixture duration, not handshake latency. Cores/fonts/Vulkan were healthy
and the watchdog was off. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-tls488`.

Installed build 488 is unchanged. Packet dispatch, connection ownership,
ACK/loss/congestion/flow handling, streams, QPACK and live HTTP/3 web traffic
remain open, alongside the remaining TLS and off-link IPv6 qualification work.


### Initial and Handshake packet frame decoding

`QuicHandshakeFrameRead` in `quic_handshake_frames.pbi` reads one complete
plaintext frame for Initial (level 0) or Handshake (level 2), returning its
consumed byte count. It supports PADDING, PING, ACK/ACK_ECN, CRYPTO and transport
CONNECTION_CLOSE. The borrowed view remains unchanged on errors; unused fields
are zero after success. Following frames are not consumed. CRYPTO data and close
reasons are borrowed bytes, not copied or interpreted as strings.

ACK ranges are checked for subtraction underflow before acceptance. The view
contains largest acknowledged, raw unscaled delay, total range count and a
borrow of the encoded first range plus subsequent gap/range pairs. ECN counters
are decoded but not validated against packet history. At most 64 ACK ranges are
accepted per call; LIMIT is a local resource refusal, not a claim of malformed
peer traffic. Packet-history checks, delay handling and ACK effects remain the
connection's responsibility. A one-byte PADDING call bounds decoder work, but
the packet dispatcher must separately bound its number of calls.

Known application-only frames return LEVEL, unknown types FORMAT. This decoder
elects to refuse nonminimal frame type encodings with LEVEL (the connection maps
that to PROTOCOL_VIOLATION); other variable integers accept nonminimal encodings.
This is a stricter dispatch policy than the standalone CRYPTO reader's generic
integer decoding, not a change to that reader. RFC 9000 section 12.4 permits
receiver rejection for nonminimal frame types. Input pointer/length and output
alias checks precede parsing. Malformed/truncated fields must cause connection
refusal, not skipping an unknown amount of packet data.

Capture 249 on Anvil 488 passed 5,444 scalar assertions across 340 frame cases
and four argument checks: independently encoded ACK ranges, ECN, all prefixes
of representative frames, forbidden and unknown types, nonminimal integers,
underflow, range limits, CRYPTO overflow and unchanged output on failure. The
full fixture compiled for Pi 3 without a physical execution claim. The Pi 4
returned normally with healthy cores/fonts/Vulkan and watchdog off. Evidence:
`docs/evidence/anvil-ipv6-20261030/quic-frames488`. Build 488 remains installed.

This is decoding, not an authenticated connection. Packet protection must be
removed successfully before acting on frames, and a received packet must not
be acknowledged until every frame has been applied successfully. Connection
ownership, frame effects, ACK generation/loss/congestion/flow handling, streams,
QPACK and live HTTP/3 traffic remain open. Earlier TLS and public off-link IPv6
qualification gaps remain open too.


### Handshake packet receipt and ACK generation

`quic_handshake_ack.pbi` adds one caller-owned tracker per Initial or Handshake
packet-number space. Init accepts 1 through 64 range slots, each two native
integers (inclusive low/high). Seen is read-only duplicate lookup. Record is
called only after packet authentication and successful application of every
frame; it inserts/merges ranges and returns new versus duplicate receipt. No
range pruning is performed. Capacity exhaustion is an explicit local resource
refusal, and the connection must not acknowledge an unrecorded packet or silently
forget history. Context and entry storage remain exclusively owned and unmodified
between API calls. Application packet spaces are not implemented by this API.

Write produces a type-2 ACK with zero delay for handshake spaces, canonical
integer encodings and all retained ranges. Capacity is checked before writing;
short output refuses without changing bytes or the demand token. No receipts
returns zero bytes. ECN feedback is not emitted. The caller protects the frame,
submits it through UDP, and calls Sent with the captured token only after actual
send acceptance. Write does not clear pending demand or imply network delivery.

Each ACK-eliciting receipt, including a duplicate, advances the demand token.
An older send completion cannot clear demand created after its snapshot. A
non-eliciting receipt changes the ranges but does not create or advance demand;
an older ACK completion can therefore clear the demand it covered without
starting an ACK-only response loop. The token exhaustion guard refuses before
mutation. This is caller-interleaved bookkeeping, not a thread-safety promise.
ACK scheduling, failed-send retry, packet protection and recovery remain with
the future connection owner.

Capture 250 on Anvil 488 passed 5,535 assertions using an independent Python
packet-number set and wire encoder. Coverage includes duplicate lookup, range
bridging, descending insertion, 0 and maximum packet numbers, full capacity,
refusal without mutation, exact ACK bytes and output guards, decoding generated
ACKs, stale send completion, ACK-only receipts, aliases and token exhaustion.
The same full fixture compiled for Pi 3 without execution there. The Pi 4
returned normally with cores/fonts/Vulkan healthy and watchdog off. Evidence:
`docs/evidence/anvil-ipv6-20261030/quic-ack488`. Installed Anvil remains 488.

This is not a live QUIC connection or HTTP/3 request. Connection ownership and
UDP integration, frame effects, ACK scheduling, loss/congestion/flow handling,
streams, QPACK and actual authenticated HTTP/3 traffic remain open. The earlier
TLS compatibility/device-blocking and public off-link IPv6 work also remains.
