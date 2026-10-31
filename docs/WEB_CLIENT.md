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


### Handshake plaintext packet processing

`quic_handshake_packet.pbi` combines frame decoding, CRYPTO receive storage and
processed-packet tracking. The caller must first authenticate/decrypt the packet
and bind its connection, encryption level and reconstructed packet number. A
job starts zeroed, borrows immutable plaintext (at most 65535 bytes), and keeps
the matching initialized receive and ACK contexts/storage exclusively owned.
Begin refuses overlapping packet/job/storage and mismatched levels. It is not
a decryptor, connection selector or peer-identity check.

Step returns 1 for more work, 2 for an ACK event, 4 for completion, 5 for peer
close, 6 for duplicate discard, or a negative fatal error. It decodes one frame
or copies at most 16384 CRYPTO bytes per call. An ACK event remains pending until
the connection applies it to sent-packet history and calls Accept, or calls
Reject on failure. Close exposes the borrowed reason/code and terminates the
job without acknowledging the packet or applying subsequent frames. Already
processed packet numbers are discarded without interpreting their payload or
changing ACK demand, including malformed or empty duplicate payloads.

Receipt is recorded only after the entire packet succeeds. A malformed tail,
rejected ACK event or exhausted receive/history storage leaves the packet
unacknowledged. Earlier CRYPTO bytes may already have been queued: failure is
terminal and requires closing the connection, not retrying or rolling back.
Run TLS consumption after packet completion. A completed/discarded job can be
reused; active, failed or close jobs cannot begin another packet. Repeated Step
on a terminal job returns the same result without applying effects again.

Capture 251 on Anvil 488 passed 120 integration assertions: event waiting and
accept/reject, delayed receipt commit, duplicate suppression, malformed tails,
peer close, 20000-byte CRYPTO data split at 16384 bytes, receive/history limits,
out-of-order packets, source aliasing and wrong states/levels. These are synthetic
plaintext packets; no live packet authentication or sent-history validation is
claimed by the fixture. The complete fixture compiled for Pi 3 without execution
there. Cores/fonts/Vulkan stayed healthy, watchdog off. Evidence is in
`docs/evidence/anvil-ipv6-20261030/quic-packet488`; installed build 488 is unchanged.

The next integration remains the connection's UDP/protection/send path, including
actual ACK history validation, scheduling and retry, packet-number ownership,
loss/congestion/flow handling, streams and QPACK, followed by certificate-verified
HTTP/3 web traffic. Prior TLS and public off-link IPv6 qualification work is open.


### Protected handshake packets enter receive processing

`quic_handshake_receive.pbi` wraps the existing bounded header protection/GCM
job and handshake packet processor. The caller selects the connection, keys,
level and last authenticated largest packet number. Begin checks storage/key
separation, Initial/Handshake kind and shared crypto availability. It processes
one in-place long packet, exposing its declared consumed length; coalesced tail
bytes remain untouched. Malformed unauthenticated headers and bad tags discard
without frame, receive-buffer or ACK-history effects. Authenticated reserved
bits and frame violations remain fatal. Crypto internal errors are not hidden
as authentication drops. BUSY refuses before parsing and does not cancel or
overwrite another crypto job.

Only successful packet unprotection starts frame processing. Step then uses the
existing more/ACK-event/complete/close/discard results. Accept/Reject apply to
the pending ACK event, whose sent-history validation still belongs to the
connection. Cancel terminates only this job and requires discarding the packet
and closing the receive connection; partial state is not rolled back. Packet,
key, context and receive storage must stay alive and exclusively owned. The
public read-only `QuicHandshakeStorageCheck` now shares admission checks between
the plaintext and containing protected-packet jobs, without duplicate lookup
before authentication. TLS cipher invalidation remains the existing hook.

The connection still owns CID/address/role checks, key installation/discard,
AEAD usage limits, largest authenticated packet-number updates and peer identity.
Initial packet protection is not server authentication. This wrapper supplies
neither a socket nor a completed TLS handshake, and does not implement 0-RTT,
application packets, Retry or Version Negotiation processing.

Capture 252 on Anvil 488 produced 464 assertions across 29 scenarios using
independently protected Python AEAD inputs and real shared crypto on the Pi.
They cover both handshake levels, every altered tag byte, wrong keys, valid
reserved-bit violations, authenticated malformed frames, duplicates, ACK events,
cancellation, another crypto owner and coalesced-tail preservation. One original
oracle expectation incorrectly expected a parsed length after BUSY; the actual
length correctly stayed zero. The retained report passes all 464 assertions
with that expectation corrected. Original identity/check plus corrected cases
and check remain archived; runtime code and physical execution were unchanged.

Capture 253 reran all 120 plaintext packet integration assertions after the
shared admission refactor and passed. The complete protected-receive fixture
also compiled for Pi 3 (no physical execution claim). Both Pi 4 runs returned
with healthy cores/fonts/Vulkan and watchdog off. Evidence is under
`docs/evidence/anvil-ipv6-20261030/quic-receive488`; build 488 remains installed.

Actual UDP connection/send ownership, sent-packet history, ACK scheduling/retry,
loss/congestion/flow handling, streams, QPACK and live authenticated HTTP/3 remain
unfinished, as do the earlier TLS and public off-link IPv6 qualification items.


### Live UDP protected-handshake integration

Captures 254 and 255 on Anvil 488 connected the resident UDP ABI to the shared
protected handshake receiver, CRYPTO storage, receipt history, ACK encoder and
packet protection. A temporary independent desktop peer sent three 1200-byte
Initial packets: a damaged tag, a valid CRYPTO/PING packet and its duplicate.
The Pi validated the source endpoint and fixture CIDs, discarded the bad tag,
queued exactly three CRYPTO bytes, discarded the duplicate, and sent exactly
one protected 1200-byte ACK. The desktop independently removed header protection,
decrypted that response and checked its entire header and ACK/padding plaintext.
No extra replies were observed. Fifteen board report assertions passed per run.

The final fixture additionally refuses a second protected send so its fixed
outgoing packet number cannot be reused. It services UDP and the watchdog during
bounded crypto/packet steps, waits for link send completion before retiring ACK
demand, closes the socket and wipes its keys. Both runs returned with healthy
cores/fonts/Vulkan, no held crypto job and watchdog off. Build 488 is unchanged.
The reproducible builder and independent peer are `tools/build_quic_udp_live.py`
and `tools/quic_udp_live_peer.py`; the fixture uses the recorded desktop/Pi test
endpoints, ports 55442/55013 and public deterministic Initial keys. Evidence,
wire transcripts, reports and exact images are archived under
`docs/evidence/anvil-ipv6-20261030/quic-udp488`.

This is a live IPv4 UDP boundary qualification with a controlled protocol peer,
not a TLS handshake, a certificate-verified peer, or an HTTP/3 request. Its four
byte setup datagram is test coordination, not QUIC. It supplies no reusable
connection owner or general packet-number allocator; outgoing CRYPTO, sent-packet
history, retransmission, loss/congestion/flow handling, streams and QPACK remain
open. Earlier TLS and public off-link IPv6 qualification items are also open.


### Handshake sent-packet history and ACK application

`quic_handshake_sent.pbi` supplies separate Initial/Handshake ledgers. Reserve
allocates a monotonic packet number before encryption; abandoned numbers remain
unsent and cannot be reused. Commit records transport acceptance once, in
increasing packet-number/time order. Reservation or successful encryption alone
is not sending. Padded or ACK-eliciting packets enter the per-space in-flight
byte count. Loss removes in-flight bytes without erasing sent history, so late
ACKs remain valid. Connection/key epochs, transport submission and global
congestion accounting still belong to the caller.

Each ledger uses 1 through 4096 caller-owned 32-byte slots, retained until space
discard. Exhaustion is a loud local LIMIT, not an invalid-peer finding, and is
not permission to reset packet numbers. Init requires a zeroed or discarded
context; restarting numbering requires a new connection/key epoch. It must not
be used to restart numbers on Retry. Discard does not implement key erasure or
connection-wide congestion updates. Calls and borrowed storage must be serialized
by the owner; the busy field prevents cooperative interleaving, not CPU races.

A decoded, authenticated ACK starts a job against its matching number space.
The job validates the complete ACK against actual sent slots before any packet
state changes. Each step visits at most 64 slots. Only after validation does it
emit newly acknowledged packet events, carrying packet number, byte count,
send time, cookie, previous flags and removed in-flight bytes. Repeated ACKs
emit no new events. A late ACK of a lost packet does not subtract bytes twice.
The ledger refuses public writes while the job owns it. Range bytes remain
immutable until completion; ECN validation and RTT/delay interpretation remain
external. Cancel during validation leaves packet state unchanged; cancelling
application may leave acknowledged packets and requires connection termination,
not rollback. Accept the receive processor's pending ACK only after this job
reports DONE; otherwise reject/close.

Capture 256 passed 311 report assertions against an independent packet ledger,
including exact slot contents, event metadata/order, skipped/unsent numbers,
late invalid ranges, duplicate and post-loss ACKs, cancellation, ownership,
malformed range views, capacity refusal and a full 4096-packet history. The full
fixture compiled for Pi 3 without a physical execution claim.

Capture 257 integrates the ledger into the live UDP fixture. After independently
checking the Pi's protected ACK, the desktop sends a fresh protected ACK-only
Initial acknowledging Pi packet zero. The Pi validates that event against its
actual transport submission, applies it before accepting the receive event,
clears its in-flight bytes and emits no ACK loop. All 20 board assertions and
independent peer checks passed. Cores/fonts/Vulkan remained healthy and watchdog
was off. Evidence is `docs/evidence/anvil-ipv6-20261030/quic-sent488`; installed
Anvil remains 488. The earlier compile-only UDP draft was corrected to translate
successful Accept (zero) back to the receiver loop's MORE result before running.

This adds sent-history validation and a live integration example, not a full
connection/recovery implementation. Outgoing CRYPTO ownership, timer/retransmission
policy, RTT/ECN/congestion/flow handling, streams/QPACK and a certificate-verified
HTTP/3 request remain open, along with earlier TLS/public off-link IPv6 work.
Protocol references: [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000.html#section-13.1)
and [RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html#section-6.4).


### Retained outgoing CRYPTO data

`quic_crypto_send.pbi` adds caller-owned outgoing byte rings for Initial,
Handshake and Application CRYPTO streams; 0-RTT is refused. Capacity is 4096
through 262144 bytes, in multiples of four, plus a two-bit-per-byte state map.
Append copies at most 16384 bytes and initializes each newly exposed state;
Init does not clear whole backing allocations. Offsets remain monotonic through
ring wrap and are checked against the CRYPTO offset-plus-length limit.

States distinguish fresh, transmitted, retry-ready and acknowledged bytes.
Sent is called after transport acceptance, not frame generation. Retry and Ack
validate the whole retained range first and refuse never-transmitted bytes
without partial mutation. Neither late send completion nor retry can resurrect
acknowledged bytes. Already reclaimed prefixes are harmless no-ops. Packet
numbers and validated sent-packet metadata remain external: only a legitimate
packet ACK permits applying its CRYPTO ranges here.

Find scans at most 4096 positions and borrows a contiguous ready slice; it
returns a next scan offset when no ready data occurs within that budget.
The owner must copy the slice before reclaiming/reusing its storage. Frame
writes an exact CRYPTO frame, including a range crossing ring wrap, with no
writes on capacity refusal. Reclaim releases only the contiguous acknowledged
prefix and at most 16384 bytes per call. It is not secret erasure. The owner
serializes all access and discards stream storage with its keys; Init must not
restart offsets within a live encryption-level stream.

Capture 258 on Anvil 488 passed 523 report assertions against independent byte
and state arrays: exact data/metadata with guards, generated frame bytes,
partial scans, ring wrap, buffer exhaustion, out-of-order ACKs, retry/ACK races,
never-sent refusal, retired ranges, aliases and the 62-bit offset boundary.
The complete fixture also compiled for Pi 3 without a hardware execution claim.

Capture 259 extended the live UDP example. The Pi sent retained CRYPTO bytes
under packet zero; the independent peer verified them but withheld its ACK.
A fixed test timer marked that transmission lost and requested retry. The Pi
rebuilt the same CRYPTO range under fresh packet one. The peer independently
unprotected and decrypted both packets, checked their full headers and contents,
then acknowledged both. Sent-history validation and the byte store retired the
three retained bytes exactly once, including the late ACK for the lost copy.
All 23 report assertions and peer checks passed; no extra responses occurred.
The fixed timer and three-byte payload are deliberate fixture controls, not a
production recovery policy or real TLS handshake.

Evidence is under `docs/evidence/anvil-ipv6-20261030/quic-send488`. Both physical
runs returned with healthy cores/fonts/Vulkan and watchdog off; Anvil 488 is
unchanged. General connection/TLS output ownership, recovery timing, RTT/ECN,
congestion/flow control, streams/QPACK and a certificate-verified HTTP/3 request
remain open, as do the earlier TLS and public off-link IPv6 items. Protocol
references: [RFC 9000 sections 13.3 and 19.6](https://www.rfc-editor.org/rfc/rfc9000.html#section-13.3)
and [RFC 9001 section 4.1.3](https://www.rfc-editor.org/rfc/rfc9001.html#section-4.1.3).


The first publication layering check rejected calls to private receive-module
span helpers. Outgoing retention now owns those helpers locally. The original
refusal is archived rather than reported as a pass. Final captures 260 and 261
passed the same 523 retention assertions and 23 live-retry assertions plus the
independent peer checks. The final Pi 3 fixture compiled too. The standalone
retention image remained byte-identical; the combined live fixture changed.
Final source snapshots are under `sources-final` in the same evidence directory;
original runs and snapshots remain available. Health checks still passed and
Anvil 488 remains installed.


### TLS output admission into retained CRYPTO

`Tls13ClientHelloCapacity()` is a read-only conservative output bound used by
both the existing ClientHello builder and its callers. `Tls13QuicOutputCapacity()`
returns that bound for a ready QUIC ClientHello, 36 for client Finished, or zero
when no QUIC output is ready. It does not advance TLS or create an error; key
share preparation can still be pending.

`quic_tls_send.pbi` connects those builders to retained CRYPTO storage. Begin
selects the correct Initial/Handshake stream and checks output capacity, retained
free space, offset range and ownership before invoking a TLS builder. Admission
refusals leave TLS, transcript, job and stream unchanged. The conservative bound
may exceed the actual message size. The caller must select the matching TLS
context, supply independent storage and serialize access through TLS hooks.

The job is explicitly in a building phase during synchronous TLS work. A yield
callback cannot start copying its unfinished output, and a second Begin on the
same job is refused. Once the builder returns, Step retains at most 256 bytes
per call from the immutable owned output buffer. This supports messages larger
than one retained-buffer Append. After Begin returns, copying does not use TLS
globals, so other TLS contexts may run. The job exclusively owns appending to
its CRYPTO stream until completion. An unexpected intervening append is detected.

TLS has already advanced by the time copying begins. Build failure, copy-state
failure or cancellation poisons the stream and requires connection close; it
must not rebuild the message or roll back the transcript. Output generation is
not transport submission, handshake confirmation or permission to discard keys.
Begin retains existing cooperative TLS hooks; the byte-copy limit is not a
wall-time bound on TLS cryptographic work.

Capture 265 on Anvil 488 passed 79 assertions with full shared TLS crypto and
independently constructed ClientHello bytes, X25519 public key and Finished
HMAC/transcript hashes. Checks include capacity/queue refusals without TLS
mutation, wrong level and aliases, ring wrap, a maximum-length opaque parameter
extension producing a message larger than 16 KiB, partial-copy cancellation,
interleaved append detection, builder failure, legacy-mode exclusion and a real
TLS yield-hook attempt to copy during building. Parameters/keys/states are
controlled fixtures, not a certificate-chain or live peer qualification.

Capture 263 separately passed all 18 existing TLS receive/crypto scenarios,
including ordinary record-protected Finished, after sharing the capacity check.
The final output fixture compiled for Pi 3. Its initial Pi 3 attempt refused
historical Pi 4 compatibility includes; the deterministic fixture now resolves
shared crypto owners and does not include or exercise hardware entropy adapters.
A proposed recursive Begin test was refused by the compiler; building-state
Begin refusal is tested directly and Step is tested through the real callback.
No recursion restriction was bypassed. Earlier drafts passed on captures 262/264;
the final implementation and assertions are qualified by capture 265.

Evidence is `docs/evidence/anvil-ipv6-20261030/quic-output488`, including the two
compile refusals. Final physical checks left cores/fonts/Vulkan healthy and
watchdog off; installed Anvil remains 488. This is TLS-to-buffer integration,
not a live QUIC handshake. Actual connection/TLS packet scheduling, production
recovery, RTT/ECN/congestion/flow handling, streams/QPACK and certificate-verified
HTTP/3 remain open, alongside earlier TLS and public off-link IPv6 qualification.


### Live certificate-verified QUIC/TLS interoperability

The physical integration fixture now composes the shared TLS output/receive,
CRYPTO retention/reassembly, packet protection, ACK history and UDP APIs against
an independent aioquic 1.7.0 server. It generates fresh connection IDs and X25519
material from the board's entropy-seeded DRBG. The server uses a disposable
P-256 certificate chain. The test CA is passed explicitly to the payload; no
operating-system trust store changes or verification bypasses are used. The
validity clock is a recent build-host timestamp, not qualification of a public
clock-bootstrap mechanism. Rebuild for a new test session.

The client checks the peer address and connection IDs, authenticates packets,
validates ACKs against sent history, and hands accepted CRYPTO bytes to ordinary
TLS certificate, hostname, CertificateVerify and Finished validation. It checks
the peer's transport parameters against the observed server Initial source ID
and original destination ID. ClientHello and client Finished use retained output.
Initial keys and their sent-history flight accounting are discarded when the
first Handshake packet is sent. The server independently verifies client Finished
and records a non-resumed, non-early-data handshake with ALPN h3. The client also
authenticates a subsequent protected 1-RTT packet.

The first instrumented composition had a 97.011 ms maximum gap between network
service calls. Connecting the existing P-256 ECDSA and X25519 jobs, with exclusive
scratch ownership and service calls between arithmetic units, reduced that
measured gap to 1.477 ms in capture 270. X509 parsing also uses its pause hook.
The P-256-only verifier belongs to this controlled certificate fixture, not a
replacement for the wider-curve production verifier. No cryptographic algorithm
or verification requirement was weakened. The shared crypto and network libraries
remain target-independent; the test's MMU/entropy composition is explicitly Pi 4.

The largest complete TLS receive call still took 126.594 ms while servicing the
network internally. This is cooperative service within the call, not a claim
that its outer API returns in 1.477 ms or that all networking is nonblocking.
That run's complete fixture time was 1.403 seconds, including transport waits.
Individual run times are observations, not handshake latency guarantees.

Physical results on unchanged Anvil 488:

- Capture 270: all 12 positive checks; independent server Finished verification.
- Capture 268: wrong hostname refused with TLS chain-invalid and X509 verdict 56;
  the peer never completed the handshake. This preceded the arithmetic hooks.
- Capture 271: a one-bit leaf-signature mutation was rejected with X509 verdict
  52 through the cooperative verifier; the peer never completed the handshake.
  The mutated signature was independently rejected before the physical test.
- Capture 269 supplies the synchronous-verification timing baseline. Capture 267
  completed the handshake but its original checker incorrectly expected X509
  success to be zero; the documented success value is 32. The unchanged report
  passes the corrected oracle. Both original and corrected evidence are retained.
- Capture 266 stopped before network traffic because the initial harness expected
  the wrong DRBG success value. Two earlier compile refusals are retained too.

All completed board sequences returned x0=0 and left cores, fonts and Vulkan
healthy with watchdog off. No monitor image was replaced or reset. Evidence is
`docs/evidence/anvil-ipv6-20261030/quic-live488`, including peer qlogs, raw reports,
source/payload identities, public certificates, dependency download hashes,
and the independently verified host-loopback baseline. Private server keys are
excluded. Source snapshots distinguish earlier harnesses from the final one.

Reproduction entry points are `tools/quic_tls_live_peer.py` (prepare disposable
credentials, validate the peer locally, start/stop the independent server) and
`tools/build_quic_tls_live.py --compiler ... --out ... --public ...`. Negative
build modes are `--wrong-name` and `--bad-signature`; the latter requires the
peer's separately prepared invalid-signature chain. Install aioquic 1.7.0 into
an isolated host dependency directory. The peer and payload use the explicitly
configured lab addresses and ports; use the normal leased, range-checked RAM
runner and verify both the board report and the peer result.

This is a real TLS handshake over protected QUIC packets, not an HTTP/3 request.
The final 1-RTT packet's application frames are not interpreted; HANDSHAKE_DONE,
application packet-number space/ACK handling, production connection scheduling,
Retry and recovery timers, RTT/ECN/congestion/flow control, streams/QPACK and a
certificate-verified HTTP/3 request remain open. Fixture teardown closes its
UDP socket and stops the disposable peer; it is not a production QUIC close
state machine. Earlier TLS compatibility/device blocking and public off-link
IPv6/RDNSS qualification also remain open.


### Select the TLS worker before installing its execution context

The TLS driver previously installed its connection-specific crypto hooks and
then used `ScRunOne()`, which chooses the first ready task. With another task
ahead in the shared queue, that unrelated task could run under TLS hooks. This
source-confirmed ownership gap was recorded in forum reply 4378 before changes.

The portable state scheduler now provides `SchedTake(handle)`: claim exactly one
READY task when no task is already running. It validates the generation and
state, removes only the chosen task, and preserves the relative order of the
remaining ready queue. It neither wakes waiting tasks nor provides fairness.
The existing serialized-owner requirement still applies. `SchedNext()` uses the
same claim path for its normal first-ready selection.

`ScRunHandle(handle)` adds targeted execution to the existing AArch64 cooperative
backend. It rejects invalid, stale, foreign, waiting, completed and nested
requests without selecting another task. Stack, core and execution-environment
checks remain shared with `ScRunOne()`. An owned task with a failed stack guard
is made terminal without entering its function. This is same-core cooperative
execution, not timer preemption, SMP or support for unqualified execution levels.

The TLS worker now calls `ScRunHandle(tlsw_handle)` while its hooks and selected
connection context are installed. Hooks are cleared again on return. The
selection change is in shared code, not a Pi 4-only branch.

Capture 272 on Anvil 488 passed 58 named-dispatch checks: actual interleaved task
traces, preserved FIFO order for other tasks, local values across yield/wait,
targeted wake/resume, nested and busy refusal, foreign ownership, generation
reuse and stale handles, stack-guard failure, cancellation and cleanup. The
same fixture compiled for Pi 3; no physical Pi 3 execution is claimed.

Capture 273 passed all 31 existing X25519/RSA context and signature-corpus cases
with an unrelated ready task deliberately queued before each TLS worker. The
task stayed untouched through TLS slices and cancellation, then ran explicitly
and observed all TLS hooks cleared. Existing crypto verdicts, private-scratch
wiping and local/caller context checks passed. The maximum observed outer worker
call was 4.172 ms; slice targets remain soft. This fixture uses controlled TLS
work with real crypto and the actual cooperative driver, not a live HTTPS test.
Unused profile-formatting entry points are tripwires that fail the test if called.

Three harness compile refusals are retained: missing diagnostic declarations,
a conservative indirect-clock recursion refusal, and missing string formatting.
The harness now reads the qualified counter directly and explicitly detects
unexpected profile formatting; no compiler restriction was disabled.

Evidence is `docs/evidence/anvil-ipv6-20261030/scheduler-owner488`. Cores, fonts
and Vulkan remained healthy and watchdog was off after both RAM tests. A full
Anvil 489 image compiled with the normal automatic build stamp; it is a candidate
and has NOT replaced installed Anvil 488. The ownership fix is source/RAM-qualified,
not yet deployed in the resident monitor. Live QUIC still needs its production
connection worker and application packet/HTTP/3 processing; the preceding TLS,
IPv6 and HTTP/3 limitations remain open.


### Shared TLS/QUIC cooperative arithmetic owner

`Anvil/Core/tls_worker.pbi` now owns cooperative execution and arithmetic hooks
for both stream TLS and QUIC callers. The existing stream TLS adapter uses it;
the physical QUIC fixture uses the same implementation. This is shared code,
with the existing qualified AArch64 same-core backend and a soft 1 ms slice.
It is not timer preemption or a new per-board implementation.

A caller keeps a `TlsWorkerJob` descriptor and its referenced buffers alive.
`TlsWorkerBegin` admits only one owner and refuses competing work without
changing either descriptor or the current task. `TlsWorkerStep` resumes only
that owner's named context. Hooks are installed only during execution and
cleared on return, while scratch ownership persists across suspension.
Wrong-owner step/cancel requests are refused. Entries return 1 after normal
execution and store their protocol result in caller-owned storage; another
return, bad task state or failed reap latches an execution fault. Cancellation
wipes crypto job scratch, not caller buffers. Normal completion preserves
crypto results. Foreign installed hooks or active crypto jobs prevent admission.

The dispatcher owns fairness, deadlines, connection snapshots and transport
cleanup. Clearing hooks does not make suspended crypto scratch available to
other callers. The worker does not cancel the shared root loader: that belongs
to the stream TLS connection adapter. TLS defers while another protocol owns
the worker. Existing connection selection, handshake deadline and cancellation
remain in that adapter. A production multiplexed QUIC connection adapter still
needs its own TLS snapshots and lifecycle integration.

On installed Anvil 488, capture 276 passed the 31-case TLS/crypto regression,
including RSA/X25519 results, cancellation/wiping, an unrelated queued task,
and new competing-owner checks. A different owner suspended and resumed while
TLS deferred without changing its selected slot, cancelling the owner, or
cancelling root loading. The competing owner also cancelled independently.
The same fixture compiled for Pi 3; no Pi 3 execution is claimed.

Capture 275 completed a fresh certificate-verified QUIC/TLS handshake against
the independent server, which confirmed client Finished and h3 ALPN. All 15
checks passed, including repeated competing begin/step/cancel refusals, unchanged
refused descriptors, scoped hooks and complete worker release. There were 260
worker dispatches. Maximum worker call time was 1.659 ms; maximum foreground
network-service gap was 1.703 ms and maximum service call was 237 us. Total
fixture time was 1.350177 s. The earlier fixture's TLS operation could occupy
its caller for 126.594 ms; now its arithmetic context returns to the foreground
dispatcher between slices. The whole TLS operation still takes multiple slices:
this measures responsiveness, not a 76-fold cryptographic speedup.

Capture 277 rejected the deliberately corrupted certificate signature with
the expected TLS/X509 errors; the independent peer did not complete TLS.
Ownership, foreground dispatch and hook-release checks also passed on that
failure path. Reports, identities, exact source snapshots and peer results are
under `docs/evidence/anvil-ipv6-20261030/shared-worker488`.

Two compile refusals are retained: a missing architectural counter include,
and a conservative indirect-service recursion refusal when the entire fixture
was placed inside a worker. The final fixture keeps all network ABI calls in
the foreground and puts only TLS arithmetic operations in cooperative contexts.
No compiler check was disabled or replaced with an unchecked call trampoline.

The full Anvil 490 image compiled through the normal build-stamp mechanism.
It is retained as an uninstalled candidate; the resident Pi remains Anvil 488.
Cores, fonts and Vulkan were healthy and the watchdog was off after the tests.
This qualifies shared worker integration, not a completed HTTP/3 client:
production connection lifecycle, application packet/ACK processing,
HANDSHAKE_DONE/key retirement, recovery, congestion/flow control, streams/QPACK
and real HTTP/3 requests remain. Earlier TLS/device blocking and public
off-link IPv6/RDNSS limitations also remain open.


### Preserve foreground TLS state around cooperative connection slices

`Anvil/Core/tls_context_worker.pbi` adds an explicit TLS snapshot adapter over
the shared arithmetic worker. `TlsContextWorkerBegin` binds a caller-owned
descriptor to an initialized TLS snapshot without selecting it. Each Step saves
the foreground TLS state, restores the operation's connection, runs one worker
slice, saves the connection and restores the foreground state. Its temporary
foreground snapshot is wiped before return. The same crypto owner remains
exclusive across suspension; saving metadata does not permit competing crypto.

Wrong-owner requests and overlapping descriptor/snapshot storage are refused.
Storage is checked again before Step/Cancel. The descriptor, snapshot and all
referenced buffers must remain alive and exclusive; snapshot storage must not
alias TLS working storage or referenced connection buffers. Cancellation first
stops/reaps the worker, then wipes only that connection's snapshot. The caller
must abandon/close the affected transport after a partially executed operation.
This adapter does not implement connection deadlines, transport rollback, QUIC
stream poisoning or a complete production connection lifecycle.

Capture 279 on Anvil 488 passed all 17 live QUIC checks, and the independent
server confirmed client Finished and h3 negotiation. Before every slice the
fixture selected deliberately different foreground TLS metadata. Complete
2,928-byte snapshots matched after every return, and the temporary foreground
copy was zero. A suspended key-share operation was cancelled; its snapshot was
wiped, the foreground was unchanged, and a fresh operation completed normally.
Overlapping-storage and competing-context begin/step/cancel requests were also
refused without changing the rejected descriptor. This is one live connection
with deliberately distinct foreground metadata, not two simultaneous servers.

There were 258 measured worker calls and 260 complete context checks, including
the preliminary cancellation. Maximum Step time including save/restore was
1.761 ms; maximum network-service gap was 1.911 ms, service time was 244 us and
total fixture time was 1.403775 seconds. These are observations, not hard
real-time guarantees. Capture 280 rejected the corrupted certificate signature;
the peer did not complete TLS, and ownership/context/wiping checks also passed.

Exact sources, payloads, reports and peer results are published under
`docs/evidence/anvil-ipv6-20261030/context-worker488`. The full Anvil 491 build
succeeded and is retained as an uninstalled candidate. The snapshot adapter is
currently exercised by the RAM QUIC integration fixture; no resident QUIC API
is claimed. The Pi remains on Anvil 488 with healthy cores, fonts and Vulkan and
watchdog off. Production operation/lifecycle integration, application packet
processing and the previously listed HTTP/3, IPv6 and TLS gaps remain open.


### QUIC TLS operation deadlines and terminal abandonment

`Anvil/Core/quic_tls_operation.pbi` schedules key-share generation, TLS output
building and authenticated CRYPTO input through the shared context worker.
Begin validates ownership/storage and reserves the worker without executing
crypto. Step runs one cooperative slice, preserving foreground TLS state.
Completion returns 1 with the underlying protocol result in the descriptor;
protocol refusal and transport errors retain their existing meanings. A
completed operation can be followed by another; an abandoned operation is
terminal and cannot be restarted with Begin.

Per-operation deadlines are checked before and after a slice. Cancellation or
timeout stops and reaps suspended execution before wiping its snapshot and
invalidating the associated CRYPTO stream. Failure to stop retains ownership:
the caller must retry/diagnose, never free the buffers. Deadlines are soft;
they do not preempt an atomic step or replace the overall connection deadline.
The dispatcher still owns UDP service, fairness and actual connection close.

Outgoing and incoming stream owners now expose terminal abandonment. A TLS
output job can be abandoned during its building phase, but this alone does not
stop the coroutine or release storage. The builder checks its job/stream state
when it returns and cannot publish output or revive a poisoned stream. The
existing copy-phase Cancel contract is unchanged. Accepted transcript state is
not rolled back: abandon and close the connection instead of reusing it.

On installed Anvil 488, capture 281 passed 19 live QUIC checks and the peer
independently confirmed client Finished and h3. Probes covered deadline expiry
before execution, refusal to restart the terminal operation, cancellation of
a suspended output builder, and input cancellation before execution. Each
preserved foreground TLS state, wiped the cancelled snapshot and released its
worker; cancelled streams refused further work. The output-cancel probe alone
temporarily used a one-counter-tick slice to force a deterministic checkpoint,
then restored the normal setting before live traffic and timing measurements.

The live run measured 259 worker calls and 265 full context checks. Maximum
operation Step was 1.762 ms, maximum foreground service gap 1.912 ms, maximum
service call 237 us and total fixture time 1.404281 seconds. These observations
are not hard timing guarantees. Capture 283 rejected the corrupted certificate
signature; the peer did not complete TLS, and lifecycle/context checks passed.

Capture 282 passed 92 output tests: the existing 79-case independent wire/hash,
capacity, aliasing, retained-output and reentrancy corpus plus 13 abandonment
checks. A builder was deliberately abandoned from its yield callback and then
allowed to return. Its job stayed terminal, its stream stayed poisoned, no
output bytes were exposed or retained, and copy/append were refused. Its TLS
state had advanced, proving the test did not restore the transcript to retry.

Exact source/payload identities, raw reports and peer results are published in
`docs/evidence/anvil-ipv6-20261030/quic-operation488`. Cores, fonts and Vulkan
were healthy and watchdog was off after all three runs. These shared modules
were compiled into the RAM qualification payloads; no resident monitor API or
image changed. Installed Anvil remains 488 and the previous uninstalled full
candidate remains 491. Production connection lifecycle, application packets,
recovery/congestion/flow control, streams/QPACK and real HTTP/3 traffic remain,
as do the earlier IPv6 and TLS compatibility/device-blocking gaps.


### QUIC connection resource ownership and bounded closure

`Anvil/Core/quic_connection.pbi` composes Initial/Handshake packet spaces,
keys, packet/ACK/TLS jobs and mutable connection storage. Begin validates all
20 caller-supplied spans before mutation, rejecting insufficient capacity,
overflow and overlap with each other, the descriptor or the span table. It
adopts the open UDP handle only after successful initialization. Required
span sizes are explicit; additional supplied capacity is not owned or wiped.
Storage and child jobs remain exclusive until CloseStep returns 1. No child
work may start once closure begins, and all crypto users must honor the shared
worker's exclusion across suspension.

The owner also tracks an overall handshake deadline, separate from individual
TLS operation budgets. The serialized dispatcher supplies its monotonic time
and checks the deadline while waiting for packets or crypto. Deadline expiry
begins closure; it does not roll back transcripts or permit reuse. Clearing
that deadline requires the protocol owner to verify handshake confirmation:
TLS Finished alone is not QUIC HANDSHAKE_DONE.

CloseStep defers while another TLS worker owns arithmetic scratch. It stops
its own suspended TLS operation, cancels packet/ACK/key jobs, invalidates both
CRYPTO streams, retires sent histories and wipes connection keys. Stop refusal
retains ownership rather than freeing live storage. Selected TLS working state
is cleared only when both working-buffer pointers identify this connection;
a different selected TLS context remains intact.

Transport closure is explicit: Step returns 2 until the dispatcher closes the
owned socket and acknowledges that exact handle with a successful result.
Wrong-handle and failed-close acknowledgements retain ownership. Storage is
then erased in chunks of at most 4096 bytes per call, plus fixed-size metadata
cleanup. Completion is idempotent and preserves the terminal reason. No hidden
network call, wait loop, or transport-specific binding is introduced.

The live fixture now uses this shared owner rather than scattered resource
initialization and cleanup. On installed Anvil 488, capture 285 passed 25
checks and the independent peer verified client Finished and h3 negotiation.
Tests covered aliased/undersized storage refusal without mutation, deferral
for another suspended worker, exact socket-close acknowledgement, complete
buffer erasure, and repeated close. A separate probe advanced the supplied
clock to the overall deadline while key-share crypto was suspended, confirmed
that execution stopped before erasure, and verified a separate TLS context's
complete snapshot and working-buffer markers survived. Only that probe used
a one-counter-tick slice to force suspension; it restored the normal setting.

The live exchange and first close measured 1.408773 seconds, with 257 worker
calls and 263 full context checks. Maximum operation Step was 1.762 ms,
maximum foreground service gap 1.911 ms, and maximum service call 239 us.
Closure took 43 bounded calls; the slowest was 54 us. These are observations,
not hard deadlines. The subsequent injected lifecycle probe is not included
in those exchange timings. Capture 286 rejected the corrupted certificate
signature; the peer did not complete TLS and the same lifecycle checks passed.

The shared connection fixture also compiled for BCM2837 using shared crypto
owners and the actual Pi 3 timer/RNG adapter. It was not executed on Pi 3.
Exact sources, identities, payloads, reports and peer results are retained in
`docs/evidence/anvil-ipv6-20261030/quic-connection488`. Both physical runs
returned with healthy cores, fonts and Vulkan and watchdog off. No resident
image or API changed: installed Anvil remains 488; full candidate 491 remains
uninstalled. This resource owner does not yet replace the fixture's handshake
event loop with a reusable connection client. Application packet/frame state,
HANDSHAKE_DONE, recovery, congestion/flow control, streams/QPACK and real HTTP/3
traffic remain, as do the previously recorded IPv6 and TLS gaps.


### Cooperative QUIC handshake packet output

`Anvil/Core/quic_connection_send.pbi` moves Initial/Handshake output from
the fixture into a shared state machine. Begin admits one sender. Step
performs one bounded ready-range scan, packet framing phase, or cooperative
encryption slice, then returns control to the dispatcher. The common crypto
worker owns encryption across suspension, just as it owns TLS arithmetic.
Another worker cannot borrow its scratch. Connection closure now recognizes
and stops this owned packet worker before cancelling its packet job.

Step returns 2 when an immutable protected datagram is ready and 3 while
transport completion is pending. The dispatcher performs the actual UDP
send; retries retain the same bytes and packet number. SendAccepted records
history and marks CRYPTO bytes sent only after whole-datagram acceptance.
SendCompleted acknowledges an ACK snapshot and retires Initial keys/history
only after actual Handshake transmission. A negative completion starts
terminal connection closure. The caller must not replace the pending sender
or mutate its buffers/jobs directly. No UDP call or transport wait is hidden
inside the shared module. The fixture's explicit polling loop is not a
production event dispatcher.

The UDP ABI returns a positive acceptance ticket, not a byte count. The
fixture now passes the requested whole-datagram length to SendAccepted after
checking that ticket. An initial trial caught this harness integration error;
its diagnostic artifacts were retained locally. No monitor was updated.

On installed Anvil 488, capture 291 passed 28 checks and the independent peer
verified client Finished and h3. Every outgoing packet was held ready for an
extra dispatch turn: repeated Step kept its exact bytes and packet number,
wrong-length acceptance and premature completion were refused without history
changes, and a second Begin was refused. A further unsent probe suspended
packet encryption, then closed the connection; the owned worker and packet
job stopped, shared GCM became idle, storage was released only after socket
closure, and further send steps were refused. Only this injected probe used
a one-counter-tick slice and restored the normal setting afterwards.

The live exchange and first close measured 1.410282 seconds. Maximum sender
Step was 1.239 ms, maximum TLS operation Step 1.788 ms, maximum foreground
service gap 1.934 ms and service call 238 us. There were 259 TLS worker calls,
265 complete TLS context checks and 22,677 sender Step calls, including idle
transport polls. Closure took 43 calls with a 54 us maximum. Subsequent injected
lifecycle/cancellation probes are excluded from these exchange timings.
These observations are not hard timing guarantees or a throughput claim.

The signature-refusal run also retained the lifecycle and sender checks; the
peer did not complete TLS. The shared fixture compiled for BCM2837 with its
real timer/RNG adapter, but was not executed on Pi 3. Exact sources, payloads,
reports, identities and peer results are retained in
`docs/evidence/anvil-ipv6-20261030/quic-connection-send488`.

The host peer is now checked and stopped at payload return, before potentially
slow diagnostic downloads. An earlier successful exchange was followed by
the peer's idle timeout while report readback retried; that original record
is preserved and the same payload was replayed with the corrected boundary.
Report downloads used smaller bursts on the final runs. The earlier stalled
capture was recovered from retained state without a reboot.

Installed Anvil remains 488 and full candidate 491 remains uninstalled.
Both final physical runs returned with healthy cores, fonts and Vulkan and
watchdog off. This is the outgoing half of a reusable handshake client;
receive/ACK/TLS dispatch still lives in the fixture. Application frames and
HANDSHAKE_DONE, recovery, congestion/flow control, streams/QPACK and actual
HTTP/3 requests remain, along with the previously recorded IPv6 and TLS gaps.


### Bounded connection ACK application

`Anvil/Core/quic_connection_ack.pbi` now owns application of a pending
Initial/Handshake ACK event to the connection's sent history and CRYPTO
stream. Admission requires the receive owner's authentication flag, a pending
ACK event and matching packet space/stream owners. Initial packet protection
is not certificate identity; TLS still validates the peer. Pending output
must finish before ACK admission, and sender admission refuses an active ACK
job, preserving history ordering without overlapping ledger writers.

Step returns after one existing ledger validation/event step, marking at most
256 stream bytes, or reclaiming at most 256 bytes. The existing ledger first
validates the entire wire ACK before applying packet events. Each event's
metadata cookie must point to that packet's exact slot in the connection's
owned metadata array before it is dereferenced. Stream offsets and lengths
are checked, and the receive parser advances only after every history and
stream operation completes. Failure begins terminal connection closure;
already applied effects are not rolled back. Existing close ownership cancels
the underlying ACK lock and invalidates the connection's streams. No I/O,
crypto execution or waiting occurs inside this module.

The live fixture uses the shared ACK driver, yielding to network service
between its steps. Capture 293 on Anvil 488 passed 30 checks and the peer
independently verified client Finished and h3. Admission without the existing
authentication flag was refused without changing driver/history state, then
the original flag was restored. Repeated Begin and a competing send were
refused. The receive event remained pending throughout ACK application; on
completion its parser advanced, the history lock was released, repeated Step
was idempotent and readmission without another pending event was refused.

The live ACK used six dispatcher steps, with a 39 us maximum. The exchange
and first close took 1.409771 seconds; maximum sender Step was 1.242 ms, TLS
operation Step 1.761 ms, foreground service gap 1.948 ms and service call
243 us. There were 258 TLS worker calls and 264 complete context checks.
These are observations, not hard timing or throughput guarantees. Existing
deadline, cancellation, state preservation, output ownership and close checks
remained enabled. The corrupted-certificate run also retained these checks
while refusing the signature; the peer did not complete TLS.

The shared fixture compiled for BCM2837 with its real timer/RNG adapter;
it was not executed on Pi 3. Exact source, raw reports, peer results, payloads,
identities and qualification records are retained in
`docs/evidence/anvil-ipv6-20261030/quic-connection-ack488`. Both physical runs
returned with healthy cores, fonts and Vulkan and watchdog off. Installed
Anvil remains 488; no resident image/API changed and candidate 491 remains
uninstalled. Packet decryption/framing and TLS receive dispatch still live in
the fixture. Application frames/HANDSHAKE_DONE, recovery, congestion/flow,
streams/QPACK and real HTTP/3 requests remain, together with the earlier IPv6
and TLS compatibility/device-blocking work.


### Cooperative connection receive crypto

`Anvil/Core/quic_connection_receive.pbi` supplies shared
`QuicConnectionReceiveBegin/Step` for Initial/Handshake packets. Admission
requires an available packet space, a subspan of the owned input buffer and
no pending sender or ACK application. Decryption runs through the same
exclusive cooperative worker used by TLS and outgoing encryption. Each Step
performs one worker slice or frame-parser step. ACK events remain borrowed
until the ACK driver accepts them. Authenticated packet-number state advances
only after packet processing completes; terminal completion is idempotent.

Connection close recognizes its incoming worker, stops it before cancelling
the underlying packet job and releasing storage, and still defers to foreign
worker ownership. An underlying receive crypto job is also cancelled if a
yield occurred during admission before the outer receive phase was assigned.
Sender admission refuses an active incoming packet. CID selection, peer-ID
learning and TLS feed remain caller responsibilities; this module does not
claim an application-packet receiver or complete client scheduler.

The live Pi 4 fixture now uses this driver and checks repeated admission and
competing sender refusal while crypto is owned, and completion idempotence.
A separate cancellation check retains the first received Initial ciphertext
and its original destination ID, starts decryption in a fresh connection,
forces a one-counter-tick test slice, restores the production slice, then
closes while the worker is suspended. It verifies worker/GCM release, packet
job cancellation, terminal connection state, hook cleanup and refusal to
resume after close. This replay is a local cancellation probe, not new wire
traffic or an application-data exchange.

Capture 296 passed 32 checks under installed Anvil 488; the independent peer
verified client Finished and h3. Receive used 23 calls, maximum 1.270 ms.
The exchange and first close took 1.409660 seconds; sender Step maximum was
1.232 ms, ACK Step 40 us, TLS operation Step 1.760 ms, foreground gap 1.919 ms
and service call 326 us. There were 258 TLS worker calls and 264 full context
checks. These are observed timings, not guarantees. The bad-signature run
also passed its refusal and lifecycle checks without completing peer TLS.

Exact evidence is in
`docs/evidence/anvil-ipv6-20261030/quic-connection-receive488`. The final shared
fixture compiled with the actual Pi 3 timer/RNG adapter, but was not executed
on Pi 3. Both final physical runs returned with cores/fonts/Vulkan healthy and
watchdog off. Anvil 488 remains installed; no resident image changed. A prior
positive trial passed but had a duplicated cancellation-test invocation; only
the corrected fixture is the final archived qualification. TLS feed, CID
policy and the initial protected 1-RTT check still live in the fixture.
HANDSHAKE_DONE, application processing, recovery, congestion/flow control,
streams/QPACK and real HTTP/3 remain open, as do the earlier IPv6 and TLS
compatibility/device-blocking items.


### Connection TLS feed and key-transition dispatch

`Anvil/Core/quic_connection_tls.pbi` now drives CRYPTO input, handshake traffic
keys, peer transport parameters, application read keys and client Finished
output through explicit connection states. Each Step admits or advances one
TLS/key operation, parses a parameter, checks a transition, or copies at most
256 Finished bytes. It performs no network I/O or waiting. Sender and receive
admission refuse an active feed job; close uses the existing operation/key
ownership and resource erasure. Per-operation timeouts supplement the caller's
overall connection deadline. CID selection and UDP remain external.

The TLS context owner provides read-only state, traffic-secret view and buffer
identity queries, keeping snapshot offsets out of connection scheduling code.
The new feed driver reads the connection snapshot rather than whichever TLS
context the foreground currently selects. Callers must initialize and save
the connection's TLS context in its owned storage before admission. Traffic
secret views borrow that storage until the operation completes.

`QuicTlsOperation` kind4 derives QUIC traffic keys through the context worker.
Compose `Anvil/Network/quic_crypto.pbi` before this operation module; the
connection fixture already includes it through the handshake receive owner.
Job, output keys and input secret ranges are checked for invalid overlap;
secret input may be a view inside the retained TLS snapshot. Cancellation
stops the coroutine first, then wipes the snapshot, derivation job and output
keys. The fixture exercises cancellation after a forced one-counter-tick
slice, restores the normal slice and checks complete key/snapshot erasure.
The existing three operation probes remain, making four in total.

The live fixture now polls the shared feed driver instead of implementing its
own TLS/key/parameter/Finished transition loop. Its complete foreground-context
and ownership checks are factored into common before/after-slice probes used
by both the initialization path and the feed driver. The foreground deliberately
selects unrelated TLS metadata between slices; all 271 complete context checks
passed. Repeated feed admission is refused and completed Step is idempotent.

Physical capture 298 under Anvil488 passed 34 checks. The independent peer
verified client Finished and h3. Feed dispatch used 276 calls with a maximum
1.786 ms; exchange plus first close took 1.413970 seconds. Maximum foreground
gap was 1.908 ms, service call537 us, sender1.238 ms, receive1.269 ms and ACK39us.
There were 263 TLS worker calls and six additional context checks from the
operation probes. These are measured observations, not guarantees. The
corrupted-certificate run retained all probes and refused TLS completion.

Exact qualification is archived at
`docs/evidence/anvil-ipv6-20261030/quic-connection-tls488`. The fixture also
compiled for Pi3 with its real timer/RNG adapter; no Pi3 execution is claimed.
Both physical runs returned with cores/fonts/Vulkan healthy and watchdog off.
Installed Anvil488 is unchanged. Connection initialization, CID policy and
the first protected1RTT check remain fixture-owned. Application frames and
packet space, HANDSHAKE_DONE, recovery, congestion/flow, streams/QPACK and real
HTTP/3 remain open, plus earlier IPv6 and TLS compatibility/device blocking.


### Shared handshake connection-ID admission

The shared connection receiver now checks the QUIC version, packet-space kind,
destination ID and peer source ID before admission. Header/CID mismatches
return6 (discard) without changing the pending job or learned identity.
`QuicConnectionReceivePacketBegin` selects Initial or Handshake from the
header, while the existing level-specific Begin also enforces these checks.
Retired Initial packets are discarded. Input remains a validated subspan of
the connection's retained datagram buffer.

The connection stores the peer-ID-known flag and length. A candidate source
ID stays in the owned packet until authenticated packet processing completes;
only then is it copied into the owned peer-ID buffer. Authentication failure
or duplicate discard cannot establish that identity. Subsequent handshake
packets must match it. Initial packet protection is not certificate identity;
TLS peer validation still follows. The supported profile remains an eight-byte
local ID and a nonempty peer source ID of at most20 bytes. Zero-length peer IDs,
Retry, version negotiation, migration and application CID management remain
outside this handshake receiver.

The live fixture delegates long-header CID admission and peer-ID learning to
the shared receiver. Before admission it temporarily changes a destination
byte, and a source byte once known, checking discard without identity changes,
then restores the exact wire bytes. It also verifies that admission alone
does not establish identity. In a separate fresh connection, the retained
Initial packet's authentication tag is corrupted; decryption must discard it
with no learned ID, no peer-buffer writes and largest authenticated PN still
-1. The original ciphertext is then restored for the existing suspended-receive
cancellation probe. These mutations are local tests, not transmitted packets.

Capture300 on Anvil488 passed36 checks, with independent peer verification of
client Finished and h3. Exchange plus first close took1.412657 seconds;
maximum foreground gap1.886ms, service238us, sender1.236ms, receive1.258ms,
TLS feed1.763ms and ACK40us. There were258 TLS worker calls and266 full context
checks. These are observations, not guarantees. The bad-certificate run also
retained all CID/lifecycle checks and did not complete peer TLS.

Evidence is in `docs/evidence/anvil-ipv6-20261030/quic-connection-cid488`.
The same shared fixture compiled for Pi3 with its actual timer/RNG adapter;
no Pi3 execution is claimed. Both final physical runs returned with cores,
fonts and Vulkan healthy, watchdog off, and installed Anvil488 unchanged.
Connection initialization and the first protected1RTT check remain fixture
code. Application packet space/frames, HANDSHAKE_DONE, recovery, congestion/
flow, streams/QPACK and real HTTP/3 remain, along with the earlier IPv6 and
TLS compatibility/device-blocking work.


### Zero-length peer IDs and datagram-tail discard

The receiver now accepts peer source IDs of zero to20 bytes while retaining
the explicit peer-ID-known flag. Sender admission distinguishes an unknown
peer (first Initial uses the original DCID) from a learned empty ID (subsequent
Initial/Handshake packets use a zero-length DCID). Handshake output requires
a known peer, and supplied lengths must match the learned length. TLS feed
admission applies the same binding; transport-parameter checks accept the
authenticated empty source-ID parameter. The local ID remains eight bytes.

The first physical zero-ID trial completed TLS but exposed a fixture error:
it treated an unparseable datagram tail as a connection failure. The peer's
1200-byte datagram contained 135-byte Initial and1046-byte Handshake packets,
plus19 trailing bytes added by its datagram builder. The fixture now discards
the unparseable remainder while retaining authenticated packet effects, then
continues receiving. The packet parser itself still reports malformed input;
no padding is passed off as authenticated frames. The failed trial is not a
passing qualification.

The independent aioquic1.7.0 peer also needed an explicit test-profile change:
its zero-ID configuration automatically replenished IDs and emitted invalid
empty NEW_CONNECTION_ID frames after TLS. The fixture subclass suppresses
additional ID issuance only when configured for zero-length IDs. Nonzero mode
delegates unchanged to aioquic; no TLS/certificate/crypto behavior is replaced.
The local-client self-test now detects pending transport-close errors and runs
for at least250ms after both sides complete, rather than stopping at Finished.
Both zero-ID and eight-byte-ID local checks passed this extended test.

Final physical qualification on installed Anvil488 comprises:
- zero-ID handshake and protected first application packet,36 checks;
- eight-byte-ID regression handshake,36 checks;
- zero-ID bad-certificate signature refusal, plus all extra lifecycle checks.
Independent peers verified Finished/h3 for the positive cases and no TLS
completion for the signature refusal. Raw reports independently confirm peer
ID lengths0,8,0. All previous context, cancellation, ID-rejection and ownership
checks remain enabled. The short packet's frames still are not interpreted;
this does not claim HANDSHAKE_DONE processing or an HTTP/3 exchange.

Exact final source, peer self-tests, reports and payloads are retained in
`docs/evidence/anvil-ipv6-20261030/quic-zero-cid488`. The fixture compiled for
Pi3 with its real timer/RNG adapter; it was not executed there. Final physical
runs returned with cores/fonts/Vulkan healthy and watchdog off. Installed
Anvil488 is unchanged. Retry, version negotiation, migration/application CID
management, shared initialization, application packet processing, recovery,
congestion/flow, streams/QPACK and real HTTP/3 remain, as do the earlier IPv6
and TLS compatibility/device-blocking items.

### Prepared Initial keys under cooperative ownership — 2026-10-31

`QuicTlsOperationBegin` kind 5 adopts a prepared `QuicKeyJob` and its exact
`QuicKeys` output owner. Supply the job as `stream`, keys as `outputJob`, and
zero `output`/`capacity`. The caller first uses `QuicInitialKeysBegin` or
`QuicTrafficKeysBegin`; these prepare storage without doing key arithmetic.
Admission accepts phase 1 or 3, checks matching output ownership and nonoverlap,
and reserves the common context worker before adopting either object. A
refusal leaves the pending job with the caller, who must retain it for retry
or cancel it. The snapshot, job, keys and referenced storage remain exclusive
until completion or cancellation. Kind 4 remains the traffic-secret convenience
path. This change adds no target-specific implementation.

Kind 5 runs key steps through the common cooperative worker and its TLS context
save/restore. Checkpoints separate pending key steps. Cancellation and timeout
stop execution before wiping the job, output keys and connection snapshot.
Per-operation timeouts do not replace the caller's connection deadline, fair
dispatch or network service. No UDP calls or foreground wait loops are added
to the shared operation module.

The live fixture now uses this path for both Initial key directions, including
its packet/receive cancellation setups, instead of calling key arithmetic
directly from the foreground. Its fifth operation probe rejects a mismatched
key owner before admission, forces a suspended Initial-key operation, cancels
it, and checks key/snapshot wipe and unchanged foreground TLS context. Eight
additional context checks now supplement the per-slice and original checks.

Physical evidence: `docs/evidence/anvil-ipv6-20261030/quic-prepared-keys488/`.
The same positive binary passed 36 checks with both zero- and eight-byte peer
IDs; independent peers verified Finished and h3. The bad-signature case still
refused the certificate. Retained reports verify all extra lifecycle/context
checks. Pi 3 compilation uses its actual timer/RNG adapter; it is not an
execution claim. Installed Anvil 488 was unchanged, with healthy cores, fonts
and Vulkan and watchdog off after every returning RAM run.

This closes direct foreground Initial-key arithmetic in the tested startup
path. Complete connection startup composition is still pending: the fixture
still configures TLS, entropy, IDs and parameters and orchestrates key share
and ClientHello output. Application frame processing/HANDSHAKE_DONE, recovery,
streams/QPACK, real HTTP/3, off-link IPv6 and remaining TLS/device work are
also unfinished. These results are not a full networking or latency claim.

### Shared client handshake startup — 2026-10-31

Compose `Anvil/Core/quic_connection_start.pbi` after the connection owner and
its TLS operation dependencies. `QuicConnectionStartBegin(connection,timeout)`
returns 0 on admission or a negative refusal without mutation. The caller first
configures trusted time, anchors, hostname, buffers, ALPN and QUIC parameters,
generates the two eight-byte IDs with the entropy-backed generator, and saves
that initialized TLS context into the owner's snapshot. Immutable TLS inputs
remain borrowed. The driver does not collect entropy or make policy choices.

Admission requires fresh connection work, empty Initial output, no Initial
keys, an unknown peer, an initialized saved TLS context with matching owned
buffers/configuration, and an available common worker. Startup cannot restart
after admission or completion. While it is pending, send, receive, ACK and
TLS-feed admission refuse overlapping work.

`QuicConnectionStartStep` returns 0 pending, 1 complete or a negative failure.
It orchestrates key-share generation, server/client Initial-key preparation
and cooperative derivation, ClientHello construction, and retained CRYPTO
output. One call performs one admission, worker slice, storage preparation or
at most 256 bytes of output copy. A busy worker leaves its current admission
stage pending. Failure starts connection close; existing close processing
stops the owned worker before wiping keys, snapshot and retained output.
The caller still checks the overall connection deadline, services transport
between steps, and drives close to completion. There are no UDP calls or
foreground wait loops in the shared driver. After completion, use the shared
Initial sender to produce and submit the datagram.

The live fixture now configures the connection and drives this shared startup
API. Its former local key-share/Initial-key/ClientHello orchestration is gone.
The existing key-share cancellation, output cancellation and other operation
probes remain; the fixture runs them at the corresponding driver boundaries.
It also checks duplicate admission refusal, send/receive exclusion, stable
completion, both Initial keys ready and nonempty retained ClientHello output.

Evidence is in `docs/evidence/anvil-ipv6-20261030/quic-startup488/`. The same
positive binary passed 36 existing checks and the additional startup checks
with both zero- and eight-byte peer IDs on Anvil 488. Independent peers verified
Finished/h3, and the bad-signature run still refused the certificate. Core,
font and Vulkan health checks passed after every RAM return; watchdog off.
Pi 3 compiled with its actual hardware adapter, but was not executed. The
installed monitor image was unchanged. These are interoperability and
ownership proofs, not a universal latency or HTTP/3 completion claim.

The first application packet is still authenticated without frame processing.
Application packet-space handling/HANDSHAKE_DONE, recovery, streams/QPACK and
actual HTTP/3 requests remain open, along with off-link IPv6 and other remaining
TLS/device work. Connection policy, entropy initialization and transport I/O
remain explicit caller responsibilities.

### Application frame syntax — 2026-10-31

`Anvil/Network/quic_application_frames.pbi` adds
`QuicApplicationFrameRead(source,bytes,view)` for authenticated QUIC v1 1-RTT
plaintext. It returns one frame's consumed byte count or a negative refusal,
leaving the entire output view unchanged on refusal. The view borrows the
packet; keep that storage immutable and alive while consuming it.

`QuicApplicationFrame.base` holds the common handshake-frame fields. Additional
fields are `stream`, `finalSize`, `value`, `sequence`, `retire`, `idBytes`,
`resetToken` and `fin`. Stream payloads use base.data/bytes/offset; FIN records
finalSize. RESET_STREAM uses finalSize and base.error; STOP_SENDING uses
base.error. Flow limits use value, with stream populated when present.
NEW_CONNECTION_ID exposes the CID in base.data/bytes, its sequence/retire
values, idBytes and the borrowed 16-byte resetToken. NEW_TOKEN and path data
use base.data/bytes. Application close uses base.error and its reason view.
HANDSHAKE_DONE has only its type and ACK-eliciting flag.

All base v1 frame types are decoded. Common ACK/CRYPTO/transport-close layouts
reuse the existing decoder, including its local 64-range ACK work bound.
STREAM without LEN consumes the complete remaining packet. Checks cover
integer truncation, minimal frame types, stream offset/end overflow, stream
count limits, nonempty tokens, CID lengths and retirement ordering. Unknown
extension types are refused. Nonminimal field integers remain legal.
Wire facts are independently implemented from
[RFC 9000 sections 12.4 and 19](https://www.rfc-editor.org/rfc/rfc9000.html#section-19).

This layer performs syntax validation only. It does not authenticate packets,
enforce sender roles or stream/CID state, apply flow control or ACK effects,
confirm the handshake or retire keys. In particular, merely decoding
HANDSHAKE_DONE does not apply the connection transition described in
[RFC 9001 section 4.1.2](https://www.rfc-editor.org/rfc/rfc9001.html#section-4.1.2).
It is not a 0-RTT policy API or an HTTP/3 implementation.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-frames488/`.
The physical decoder proof passed 2,309 checks, covering every base frame type,
all STREAM flag combinations, prefixes, following-frame boundaries, limits,
invalid encodings and unchanged output on refusal. Refusal checks inspect
every output byte; this aggregates the verdict without reducing coverage.
The live fixture also decoded the first authenticated application packet:
HANDSHAKE_DONE with a zero-length peer ID, and HANDSHAKE_DONE plus
NEW_CONNECTION_ID with an eight-byte peer ID. Both live runs passed the 36
existing checks and all extra lifecycle/startup assertions. Independent peer
records confirm Finished/h3 and compatible sent frame counts. No packet-number
correlation claim is made for that frame-count comparison.

Pi 3 compilation used its actual hardware adapter; no Pi 3 execution claim.
All three Pi 4 RAM runs returned with healthy cores, fonts and Vulkan and the
watchdog off. Installed Anvil 488 was unchanged. Certificate rejection code did
not change; the prior negative certificate proof was not rerun or counted as
a new result. Application packet ownership, frame effects/ACKs, handshake
confirmation and key retirement, recovery, streams/QPACK and real HTTP/3
remain open, together with remaining IPv6/TLS/device work.

### Cooperative application packet protection — 2026-10-31

`Anvil/Core/quic_application_packet.pbi` exposes
`QuicApplicationPacketBegin(op,keys,packet,bytes,idBytes,number,encrypt)`,
`QuicApplicationPacketStep(op)` and `QuicApplicationPacketCancel(op)`.
Begin returns0 on admission, Step returns0 pending or1 authenticated/encrypted,
and negative results signal refusal/failure. Terminal Step results are stable.
The common worker owns arithmetic scratch across suspension. Descriptor, keys
and packet must remain disjoint, exclusive and alive until terminal return.
Cancellation stops/reaps the worker before abandoning packet crypto; discard
the partially processed packet. Borrowed traffic keys remain caller-owned.
Never consume plaintext before successful authentication. Authentication
failure preserves the original protected wire bytes.

The operation accepts short-header packets only. Its caller binds the correct
connection, keys and destination CID, supplies the largest authenticated
incoming packet number or a unique outgoing packet number, and serializes
protocol state. It does not allocate packet numbers, apply frames, perform UDP
I/O or authorize key-phase changes. Those remain connection-dispatch duties.
Connection close now cancels its owned application operation before wiping
keys/storage. Other connection admissions refuse concurrent application work.
The TLS feed derives both server-read and client-write application keys through
the existing context worker before producing Client Finished.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-packet488/`.
Two final physical Pi4 runs on resident488 passed the36 existing checks and
extra application/startup/lifecycle assertions with zero- and eight-byte peer
IDs. The independent peer verified Client Finished/h3 and decrypted an outgoing
1-RTT PN0/PING. The received application packet number is correlated with the
peer's sent frame record. A locally corrupted authentication tag was rejected
with protected bytes unchanged, followed by successful authentication of the
original packet. A separate forced suspension was cancelled by connection
close, releasing the worker and wiping owned storage.

Application crypto maximum Step time was506/513 us; maximum foreground service
gaps were1,885/1,882 us for zero/eight IDs. These are observed small-packet
measurements, not hard scheduling guarantees or throughput benchmarks.
The first development run's existing36 checks passed, but its new cancellation
assertion failed because the harness invoked the probe twice after wiping its
saved keys. That failed extension is retained separately; final runs use one
invocation and pass. No resident update or reset was required. Cores, fonts and
Vulkan remained healthy, with watchdog off. Pi3 compilation used its real
hardware adapter; no Pi3 execution claim is made.

This establishes bidirectional application packet protection, not a complete
application transport. Packet-number/history management, frame effects and
ACKs, HANDSHAKE_DONE confirmation and Handshake-key retirement, recovery,
congestion/flow control, streams/QPACK and real HTTP/3 remain open. Earlier
negative certificate results remain historical; this change's new negative
test concerns application authentication. Remaining IPv6/TLS/device work is
also unfinished.

### Shared application ACK range encoding — 2026-10-31

`Anvil/Network/quic_packet_ack.pbi` provides `QuicPacketAck` and
`QuicPacketAckInit/Seen/Record/Write/WriteDelay/Sent`. Its level values are0
(Initial),2 (Handshake), and4 (application packet-number space). Range storage
is caller-owned, disjoint from the descriptor, and holds1..64 inclusive
low/high pairs of native integers at16-byte strides. All calls are bounded by
that capacity. There is no pruning: exhaustion returns a resource refusal.

`WriteDelay(state,dst,capacity,token,delay)` writes an ACK type2 with the supplied
encoded delay. Delay is the wire integer, already scaled using the advertised
ACK-delay exponent; this API does not measure time or select an ACK schedule.
The caller measures intentional delay for the largest acknowledged packet,
following [RFC 9000 sections13.2.5 and19.3](https://www.rfc-editor.org/rfc/rfc9000.html#section-13.2.5).
Initial/Handshake spaces reject nonzero delay. `Write` retains the zero-delay
convenience interface. Invalid delay, insufficient output capacity and aliasing
refuse before writing output or the demand token.

`Seen` is a read-only duplicate lookup. `Record` is called only after packet
authentication and successful processing of every frame; it does not itself
authorize receipt or suppress repeated frame effects. Duplicate eliciting
packets request another ACK. Non-eliciting receipt does not create demand.
`Sent` uses the captured demand token so a stale completion cannot clear newer
demand. The caller owns send/retry timing, packet protection and transport I/O.

The old `QuicHandshakeAck` descriptor retains its field layout and public
interface as a thin facade over the common implementation. Its initialization
still accepts only Initial and Handshake. No second range algorithm is copied.

Physical evidence is in
`docs/evidence/anvil-ipv6-20261030/quic-ack-delay488/`. The new application suite
passed5,794 checks against an independent packet-number set and wire encoder,
covering sparse/merged/duplicate ranges, capacity, stale demand completions,
all four integer widths for ACK delay, boundary values, exact bytes, output
guards and invalid-delay immutability. The unchanged legacy cases passed5,535
checks through the compatibility facade. The live encrypted regression passed
the36 existing checks plus lifecycle/startup/application assertions; the
independent peer verified Finished/h3 and client 1-RTT PING after the refactor.
This live regression does not yet send an application ACK.

All three Pi4 runs returned with cores, fonts and Vulkan healthy, watchdog off,
and resident488 unchanged. The shared composition also compiled using the real
Pi3 adapter; no Pi3 execution is claimed. Application ACK transmission still
needs connection-owned receipt tracking and frame effects. Handshake
confirmation/key retirement, recovery, congestion/flow control, streams/QPACK,
real HTTP/3 and remaining IPv6/TLS/device work remain open.

### Connection-owned application packet state — 2026-10-31

`Anvil/Network/quic_application_state.pbi` provides `QuicApplicationState` with
inline storage for64 ACK ranges, independent authenticated/processed largest
packet numbers, the processed largest packet's receipt timestamp, and the next
outgoing number. On the tested AArch64 targets it occupies1,120 bytes.
`QuicConnection` embeds and initializes it, then wipes it during final close.
The existing20 external buffer spans are unchanged. The descriptor is larger;
consumers must compile against the updated definition. Keep the state at its
original address: its ACK descriptor points into its inline storage.

`QuicApplicationStateInit` accepts a fresh zeroed descriptor only. An active
state cannot be reinitialized. `QuicApplicationNumberReserve` returns a fresh
number or negative refusal. Reserve before encryption; abandoned work never
returns a reservation to the pool. The last legal number can be reserved once,
then exhaustion remains a refusal without wrapping. Preserve this state across
key updates; only a genuinely new connection/key lifetime may restart numbering.
This follows the packet-number requirements in
[RFC9000 section12.3](https://www.rfc-editor.org/rfc/rfc9000.html#section-12.3).

`QuicApplicationAuthenticated` is called only after packet authentication. It
updates the reconstruction reference and returns whether that PN was already
fully processed. It does not create an ACK receipt. `QuicApplicationProcessed`
is a separate caller assertion that this packet was authenticated and all its
frames successfully processed. Its PN upper-bound check is not proof of those
conditions. The serialized connection dispatcher must enforce them and prevent
duplicate effects. Range exhaustion refuses without updating processed timing.

`QuicApplicationAckDelay` scales elapsed controlled receipt time using our
advertised exponent0..20. Older or duplicate PNs do not replace the largest
processed PN's timestamp. `QuicApplicationAckWrite` serializes that delay using
the shared ACK writer and rejects output/token overlap with any part of the
state, including packet-number counters. These operations do not schedule ACKs,
authenticate packets, apply frames, enforce max_ack_delay, or transmit packets.

Physical evidence:
`docs/evidence/anvil-ipv6-20261030/quic-application-state488/`.
The standalone Pi4 proof passed2,716 checks, including numbering exhaustion,
refused reinitialization, separate authentication/receipt state, duplicate and
out-of-order timestamps, capacity, stale completions, delay overflow/scaling,
exact ACK bytes/guards and unchanged state on refusal. The live fixture uses
the owner to reserve the outgoing PING's PN, update authenticated reception
only after tag success, and verify every byte of the state is erased on close.
It deliberately leaves ACK receipts empty because application frame effects
are not integrated yet. The final live run passed36 existing checks plus all
additional lifecycle/application/state assertions; the independent peer
verified Finished/h3 and client 1-RTT PING.

The first live run failed a fixture shutdown probe: its callback had crossed
the old hard-coded512KiB scheduler registration. That failed run is retained.
The fixture now registers a linker-derived, aligned code extent, records both
callback and limit, and still closes the owned connection if probe admission
fails. The callback at0x108022c is outside the old0x1080000 limit and within the
new0x10869f8 limit. Its first64 bytes are identical at that address in both
builds. The final registered extent lies within the validated image map.

Both qualifying Pi4 runs returned healthy, with watchdog off and resident488
unchanged. The failed development run also returned with healthy cores, fonts
and Vulkan. The final composition compiled with the actual Pi3 adapter; it was
not executed there. No reset or resident update was needed. Application frame
effects and ACK transmission, handshake confirmation/key retirement, recovery,
congestion/flow control, streams/QPACK/realHTTP3 and remaining IPv6/TLS/device
work remain open.


### Completed-handshake TLS snapshot cleanup (2026-10-31)

`Tls13ContextRetireHandshakeSecrets(snapshot, capacity)` is a shared Crypto
primitive for connection owners that have confirmed their handshake and excluded
concurrent crypto work. It accepts only a complete, connected TLS snapshot,
returns1 on success and0 on unchanged refusal, and is idempotent. It erases
256 bytes of early/derived/handshake secrets, ephemeral DH/private material and
the Finished key. Master/application secrets, application record keys and all
other snapshot bytes survive. It does not select or modify global TLS working
state: an owner must separately restore the cleaned snapshot if its connection
is currently selected. It does not itself confirm a QUIC handshake or discard
QUIC packet keys/recovery state, nor claim erasure of arbitrary older copies.

Physical Anvil488 evidence is retained in
`docs/evidence/anvil-ipv6-20261030/tls-handshake-secrets488/`.
The live certificate-verified QUIC fixture returned x0=0, capture324, passing36
existing checks plus retirement/application/lifecycle assertions. It checks
null/overflow pointers, short capacity and pre-Finished state without mutation;
checks every snapshot byte against the expected erasures/preserved bytes;
checks a different selected TLS context remains unchanged; checks idempotence;
and restores/re-saves the cleaned snapshot before returning to the original
context. The test cleans a separate snapshot: production connection confirmation
and selected-context retirement remain to be integrated. The independent peer
verified Finished/h3 and authenticated client1-RTT PING. The measured exchange
was1,417,956us; maximum service dispatch242us and gap1,882us. These are fixture
observations, not general latency guarantees.

Cores, fonts and Vulkan remained healthy; watchdog was off afterward. Resident488
and the boot image were unchanged. The same composition compiled with the real
Pi3 adapter but was not executed there. Application frame effects/ACK transmission,
confirmation/key retirement, recovery/congestion/flow, streams/QPACK/real HTTP3,
and remaining IPv6/TLS/device work are still open.


### Client handshake confirmation and key retirement (2026-10-31)

`QuicConnectionHandshakeDone` applies the client-side effect of a decoded
HANDSHAKE_DONE frame from the current authenticated application packet. The
caller supplies the validated frame event; this API is not a packet parser.
It additionally requires a successful decrypt with this connection's read
keys, completed TLS startup/feed and no pending send/receive/ACK/crypto work.
It returns1 after confirmation, including duplicates, or a negative unchanged
refusal. It retires Handshake read/write packet keys, the Handshake sent ledger
and CRYPTO streams, cleans the owned TLS snapshot and restores that cleaned
snapshot only if this connection is selected. Application keys/state survive.
The confirmed flag and cleared handshake deadline are committed together.
Old Handshake input is dropped; old-level output and TLS feed cannot restart.
This does not ACK the application packet or claim other frame effects succeeded.

Physical evidence is retained under
`docs/evidence/anvil-ipv6-20261030/quic-handshake-confirm488/`.
One identical PMF ran against independent peers with eight-byte and zero-byte
connection IDs, captures325/326, on resident Anvil488. Both passed36 primary
checks and additional application, retirement, lifecycle and confirmation
assertions. The eight-byte run exercised the selected owner; the zero-byte run
exercised an unrelated selected TLS context. All snapshot bytes and both packet
key structures were checked: previously nonzero handshake material disappeared,
application material was preserved, and the unrelated context did not change.
The tests also exercised bad-tag/pending-decrypt/busy-worker refusal, repeated
confirmation, retired-level refusal/drop, deadline clearing and empty ACK
receipts. Both peers authenticated a subsequent client1-RTT PING and verified
Finished/h3. The peer's zero-CID fixture omits invalid empty NEW_CONNECTION_ID
frames, as documented in its source.

Measured exchange durations were1,419,170us and410,754us; maximum foreground
service gaps were1,882us and1,947us. These are individual fixture measurements,
not performance guarantees. Both runs returned x0=0 with cores/fonts/Vulkan
health checks passing and watchdogoff. Retained screenshots are monitor-return
evidence, not UI/input or rendering correctness tests. The actual Pi3 adapter
compiled; it was not executed. Resident488 and the boot image were unchanged.

Application frame effects beyond HANDSHAKE_DONE and their ACK transmission,
recovery/congestion/flow control, streams/QPACK/real HTTP3, key updates,
Retry/migration and remaining IPv6/TLS/device work remain open.


### Peer connection IDs and retirement obligations (2026-10-31)

`Anvil/Network/quic_peer_ids.pbi` owns a caller-supplied bounded peer-ID table.
Init installs sequence0 from the authenticated handshake, optionally with its
TLS reset token. Add accepts authenticated NEW_CONNECTION_ID fields, detects
conflicting reuse, tolerates duplicates/reordering, applies a monotonic retire
floor and checks the post-retirement active count before mutation. It chooses
a surviving ID if the selected one is retired. Invalid/overlapping inputs,
active-limit excess and storage exhaustion leave state unchanged. These are
separate negative statuses; the connection's close/error policy remains the
caller's responsibility. A zero-length initial ID rejects subsequent new IDs,
but can retain a TLS-supplied reset token.

The56-byte owner uses2..64 caller-provided72-byte records, with an advertised
active limit between2 and capacity. Size storage for active IDs PLUS retirement
obligations; the default Core integration has8 records and the fixture advertises2.
Find returns a borrowed read-only record, not a copy. RetireNext reports an owed
sequence (-1 when empty); it does not clear anything on submission. RetiredAck
requires the caller to have authenticated an ACK for the RETIRE_CONNECTION_ID
frame. Only then is the record/token erased and reusable. A delayed old ID can
recreate a retirement obligation but cannot reactivate below the floor. This is
state handling, not a reliable sender, migration or stateless-reset detector.

Core QuicConnection embeds the table, closes/wipes it with the owner, initializes
it from authenticated parameters, and applies decoded NEW_CONNECTION_ID via
QuicConnectionPeerIdAdd. The caller supplies a validated frame event from the
current successful owned application decrypt and serializes pending transport
output. The selected peer CID is copied into the existing outgoing-ID buffer.
Init's limit must be OUR advertised value, not the peer's advertised limit.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-peer-ids488/`.
The final physical state suite passed710 checks (capture330), including exact
independently generated record images, refusal atomicity, retirement/reclamation,
limits, duplicates, reorder, one/twenty-byte IDs and zero-ID token retention.
The identical final live image passed against eight-byte and zero-byte peer IDs
(captures331/332):36 primary checks each plus application/lifecycle/confirmation/
peer-ID assertions, exact received ID/token comparisons, duplicate Add and full
close erasure. The peers verified Finished/h3 and authenticated subsequent
client1-RTT PING. NEW_CONNECTION_ID effects counted1/0, matching peer traces.
The real Pi3 composition compiled but was not executed. Final resident488
was unchanged, watchdogoff and cores/fonts/Vulkan health checks passed.
Monitor captures are not UI/input/rendering-correctness tests.

One earlier live payload did NOT return: run637 hit the15s deadman and restarted.
The tool observed the restarted resident and its version reply after its90s
observation. The peer received no datagrams. Read-only recovery found healthy
cores and retained report bytes from the prior CPU proof; cached report writes
mean this does not identify an exact stop point. The exact same failing image
later passed (capture329). An instrumented run also passed before the final
zero-ID token correction. This intermittent failure is UNRESOLVED, not fixed by
adding progress marks. Its image, exact sources, failed journal, peer trace,
recovery and exact replay are retained in development1800. Fixture progress at
report0xff00 is now explicitly cache-cleaned, stages1..10; the early services
slot0xff08 is cleared by report initialization at stage8. This diagnostics change
is not a runtime fix. Pi3 compile removes Pi4 cache maintenance as usual.

Application receipts/ACK transmission, reliable RETIRE_CONNECTION_ID sending,
preferred-address IDs, local ID issuance, reset detection, recovery/congestion/
flow, streams/QPACK/real HTTP3, key updates, Retry/migration and remaining IPv6/
TLS/device work remain open. No unprocessed packet is acknowledged by this change.


### Cooperative application ACK output (2026-10-31)

`Anvil/Core/quic_connection_control.pbi` sends an application ACK with an
optional PING using owned output buffer16 and the shared packet worker. Begin
checks the connection/dispatch state, computes ACK delay with OUR advertised
exponent and irreversibly reserves an application packet number. It writes the
ACK and short header, then starts cooperative encryption. Step returns0 while
computing,2 when immutable ciphertext is ready,3 while awaiting actual transport
completion and1 after completion. Accepted is called only after queue acceptance,
never EAGAIN. Completed(result=0) means actual transmission succeeded; only then
is the captured ACK-demand token cleared. Newer demand survives a stale token.
Failures after reservation can consume a packet number and close the owner;
there is no rollback/reuse. Raw application APIs must remain serialized against
this operation, as documented by both interfaces.

The connection owns control phase/length/PN/token. Handshake send, receive and
TLS feed, plus peer-ID mutation, refuse while control ciphertext is outstanding.
Existing CloseStep cancels the shared application operation and closes the
socket before wiping owned storage. Scheduling, congestion/recovery policy and
reliable retirement delivery are not implemented by this sender.

The live dispatcher now commits an application receipt only after all frames
have succeeded. Its current supported set is PADDING, PING, HANDSHAKE_DONE and
NEW_CONNECTION_ID; other frame kinds are refused without receipt/ACK commit.
Receipt time is captured before authentication/processing. The sender transmits
ACK+PING and leaves ACK demand pending through encryption, submission and queue
acceptance. The peer checker requires a decoded authenticated ACK covering an
actual HANDSHAKE_DONE packet, not merely a received UDP datagram.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-ack488/`.
Identical final Pi4 payload, resident488, captures335/336 against eight-byte and
zero-byte peer IDs:36 primary checks each plus all application/confirmation/CID/
control assertions. The independent peers authenticated client PN0PING and ACKs
covering exactly server PN4 and PN3 respectively; unprocessed earlier numbers
were not acknowledged. The fixture checks competing Begin/early completion,
ready/accepted/completed state transitions, immutable ciphertext, demand retained
until actual TX success and duplicate completion refusal. No forced transport
failure, EAGAIN, stale-token or ACK-only integration run is claimed here; the
underlying receipt/token serializer has its earlier independent CPU evidence.

Both runs returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff. Exchange
elapsed1416621/411300us; maximum foreground service gap1947/1882us. These are
individual fixture observations. The actual Pi3 adapter compiled, not executed.
No resident update or reset occurred. Monitor screenshots are return evidence,
not UI/input/rendering tests. The prior run637 watchdog failure remains unresolved;
it did not recur in these tests.

Reliable RETIRE_CONNECTION_ID delivery, application sent-history/recovery and
ACK scheduling, general frame/stream dispatch, preferred-address/local-ID/reset
handling, congestion/flow, QPACK/real HTTP3, key updates, Retry/migration and the
remaining IPv6/TLS/device work remain open.

The first implementation called a private helper across a module boundary. The
layering gate rejected it; the final module owns its bounds helper. Both final
Pi4 runs and the Pi3 compile were repeated on the corrected source. Pre-correction
artifacts and the failed gate are retained in the adjacent
`quic-application-ack-development488` evidence directory.


### Application packet delivery ledger (2026-10-31)

The shared sent ledger in `Anvil/Network/quic_handshake_sent.pbi` now accepts
application number space4 as well as Initial0/Handshake2. Its existing API names
are retained. The same full-frame validation pass precedes delivery events;
wrong-space ACKs and acknowledgments of unsent numbers are refused. Validation
and event processing remain cooperative, at most64 slots per step. This is a
bounded history, not a complete recovery policy or an unbounded connection.

`QuicConnection` owns an application history, ACK job and128 sent slots. The
control sender checks history availability before reserving a PN, keeps history
reservation aligned with `applicationState.nextNumber`, and refuses divergence.
`QuicConnectionControlAccepted(c,now)` now requires the caller's monotonic send
time: after actual queue admission, it commits the packet BEFORE peer ACKs can
be processed. Its eliciting flag controls bytes in flight. Actual transmission
completion still separately clears the outgoing ACK-demand token. Ambiguous or
failed accepted sends close ownership. CloseStep cancels an owned application
ACK job and discards this history before storage release.

The live fixture now waits for a real authenticated peer ACK after sending its
ACK+PING. It decodes ACK/ACK_ECN through the shared application frame view and
runs the shared two-pass acknowledgment job. It verifies exactly one delivery
event, the correct packet length, all of that packet's in-flight bytes removed,
and largestAcked0. The receive packet is committed only after all its supported
frames have succeeded. The current continuation also handles padding/PING,
NEW_CONNECTION_ID and HANDSHAKE_DONE; general streams remain open.

Final evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-delivery488/`.
Identical final Pi4 payload on resident488, eight-byte/zero-byte peer IDs,
captures338/339:36 primary checks plus all extended assertions. Both independent
peer qlogs show their authenticated client PN0ACK+PING and server ACK range[0,0]
in exactly the packet the Pi reported processing (server PN5/PN4). Three refusal
probes also pass per run: wrong packet-number space, an unsent PN, and cancel
after validation but before application. Both refusal/cancel cases preserve
in-flight accounting and produce no delivery event. The real acknowledgment
then succeeds. ACK processing takes3 cooperative steps for this one packet.

Both runs returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff; no
resident update or reset. Exchange elapsed1439773/434225us, max foreground gap
1911/1940us, individual fixture observations. Actual Pi3 adapter compiled only.
Retained monitor screenshots are return evidence, not UI/input/rendering proof.
The earlier run637 watchdog failure remains unresolved and did not recur here.

Limitations: this owner currently has128 lifetime application packet slots;
exhaustion refuses further reservation without reusing a PN. Pruning/storage
policy is required for long-lived web transfers. Loss scheduling, retransmitted
frames, reliable RETIRE_CONNECTION_ID delivery, RTT/congestion/flow policy,
general stream dispatch, QPACK/HTTP3, key updates, Retry/migration, additional CID
handling and remaining IPv6/TLS/device work are not completed by this change.
ACK_ECN is decoded by the common path; a separate on-wire ECN test is not claimed.


### Reclaiming acknowledged sent history (2026-10-31)

The shared sent ledger now uses ring storage while keeping absolute packet
numbers. `first` is the exclusive upper bound of a proven acknowledged prefix;
`issued` remains the next absolute number. Reservation uses issued modulo
capacity and refuses when the unpruned window is full or QUIC numbering is
exhausted. Reclamation never resets numbers, delivery totals or key epochs.

`QuicHandshakeSentPrune(s,budget)` reclaims at most1..64 contiguous sent-and-ACKed
slots, zeroing each slot. It stops at the first unacknowledged, lost-only or
reserved-unsent packet and refuses during an active ACK job. Callers must consume
all delivery events before reclamation. Already-pruned numbers are known to have
been sent and acknowledged: duplicate ACK ranges below first are validated for
syntax but skipped without visiting every old number or touching reused slots.
Commit refuses an old number; Lost on a proven acknowledged old number returns0.
Unsent gaps are never silently forgotten. Retained/new ranges still undergo the
entire ACK validation pass before any event is applied.

Application sender capacity admission now counts the unpruned window, not all
packets ever issued. The handshake sender and ACK handler also use ring indexing
for their separate CRYPTO metadata slots and check absolute-number bounds before
use. The live application dispatcher explicitly prunes after consuming the peer's
delivery event and completing its ACK job. Pruning is an explicit caller action;
it is not an automatic loss policy or permission to discard undelivered metadata.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-sent-prune488/`.
Physical Pi4 capture340 passes1241 independent ledger assertions: existing
Initial/Handshake behavior, level4, full histories, retained slot/guard/event
hashes, repeated four-slot wraparound with monotonically increasing numbers,
partial-budget pruning, old ACKs crossing reclaimed/live ranges, prefix blocked
by an unacknowledged or unsent number, unsent ACK refusal, busy pruning and
invalid budgets. Acknowledged counters and in-flight bytes remain consistent.

Final live captures341/342 under resident488 pass36 primary and all extended
assertions with eight-byte/zero-byte peer IDs. The authenticated peer ACK delivers
client PN0, the fixture reclaims exactly one slot, and first/issued both remain1.
Independent qlogs identify the matching server ACK packets (PN5/PN4). Exchange
elapsed1441690/436622us; maximum foreground gap1881/1917us, individual observations.
Both return x0=0 with healthy cores/fonts/Vulkan and watchdogoff. The real Pi3
adapter compiled, not executed. No resident image change or reset occurred.
Screenshots are retained return evidence, not UI/input/rendering claims.

The application owner still has128 physical slots. A blocking unacknowledged,
lost-only or unsent prefix can still exhaust that window; loss/retransmission and
safe retirement of such metadata remain open. This removes the unconditional
lifetime limit for acknowledged traffic, not all storage/backpressure limits.
Handshake metadata wrap indexing was reviewed and compiled in the live path;
a whole handshake exceeding128 packets was not exercised. Reliable retirement
frames, loss timers, RTT/congestion/flow, streams/QPACK/HTTP3 and remaining
IPv6/TLS/device work remain open. The previous run637 watchdog failure remains
unexplained and did not recur in these tests.


### Cooperative acknowledgment-based loss detection (2026-10-31)

`quic_handshake_sent.pbi` now provides `QuicHandshakeSentLossBegin/Step/Cancel`
for all three number spaces. The caller supplies a monotonic current time,
positive loss delay in the Commit clock's units, and packet threshold of at
least3. The ledger's completed authenticated ACK state supplies largestAcked.
A scan holds the ledger lock and visits at most64 slots per call. Step returns0
for more work,1 for a loss event and2 when done. The event retains number, byte
count, send time, cookie, previous flags and removed in-flight bytes.

Only unacknowledged in-flight packets preceding an acknowledged packet are
eligible. Packet distance or elapsed send time can trigger loss. Sent facts and
frame metadata remain retained; the scan clears in-flight accounting once and
sets the existing lost flag. It does not erase history or manufacture delivery.
Late ACKs still work and do not subtract flight bytes again. Already-lost,
ACKed, unsent and non-flight records are ignored. An unacknowledged tail or a
space without an ACK needs probing/PTO, not this declaration. These conditions
follow [RFC9002 section6.1](https://www.rfc-editor.org/rfc/rfc9002.html#section-6.1).

At DONE, nextTime is the earliest remaining eligible packet's deadline, or0 if
none. Addition saturates at the signed clock maximum instead of wrapping.
The supplied delay must come from the path's RTT/reordering/granularity policy;
this API does not estimate RTT, run a timer or implement PTO. Cancellation
releases ownership and preserves any loss events already emitted. Those frames
must be requeued/consumed or the connection closed; there is no rollback or
permission to free their metadata. A connection using an external loss job
must finish/cancel it before attempting history discard or connection close.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss488/`. Physical Pi4,
resident488, capture343:2121 independent ledger assertions pass, including the
prior ring/ACK regressions plus packet/time thresholds, exact deadline boundary,
no-ACK/newer-tail protection, ACK-only versus padded packets, skipped unsent
numbers, late ACK after loss, repeated scans, exact loss-event metadata/order,
busy admissions, a64-slot cooperative boundary, cancellation before/after an
event, invalid clock/delay/threshold/alias arguments and deadline saturation.
The independent Python state tracks flags, accounting and event hashes; the Pi
executes the compiled routines. Supplied timestamps simulate loss conditions;
this is not a dropped-datagram wire experiment.

The payload returned x0=0, with healthy cores/fonts/Vulkan and watchdogoff.
Image/map/report/screenshot are retained; the screenshot is monitor return
evidence, not UI/input/rendering validation. The actual Pi3 target compiled,
not executed. No resident update or reset occurred. The earlier run637 watchdog
incident remains unresolved and did not recur.

This adds detection and preserved loss events, not retransmission or a complete
recovery controller. Path RTT/PTO timers, frame ownership/requeueing, congestion
responses, retirement-frame delivery and safe release of lost metadata remain
open. Lost records still block prefix pruning until acknowledged. Streams,
QPACK/HTTP3 and the remaining IPv6/TLS/device items also remain open.


### Standalone application probe output (2026-10-31)

The shared control sender now accepts PING without pending ACK demand. It still
includes an ACK when one is pending; an empty request (no ACK and no PING) is
refused before packet-number reservation. Clock and exponent admission is checked
before reservation even for PING-only output. The connection records controlHasAck
for the admitted packet. Successful transmission consumes an ACK token only when
that packet actually carried an ACK; a standalone probe cannot consume ACK demand
that belongs to another packet. Output ownership, unique PN reservation, encryption,
transport-admission history and actual-transmission completion remain separate.

The live fixture completes the initial ACK+PING exchange and consumes/prunes the
peer's acknowledgment of client PN0. With no pending ACK, it then sends fresh PN1
containing only PING. It verifies empty-request and negative-clock refusals do not
consume a number, exact probe lengths30/22 for eight-byte/zero-byte destination
IDs, absent ACK token, immutable ciphertext through actual TX and retained
in-flight accounting. The independent peer requires a decoded authenticated PN1
with exactly one PING frame, not a UDP packet count or a local return code.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-application-probe488/`.
Both physical Pi4 runs under resident488, captures344/345, pass36 primary and all
extended assertions; independent peer checks pass for both destination-ID lengths.
Exchange elapsed441660/440278us and maximum foreground gap1882/1909us in these
individual runs. Both returned x0=0 with healthy cores/fonts/Vulkan and watchdogoff.
The actual Pi3 adapter compiled but was not executed. No resident update/reset;
retained monitor screenshots show return evidence, not UI/input/rendering proof.

This supplies probe output, not PTO scheduling or retransmission policy. The
fixture does not process a peer ACK of PN1 before closing and does not inject loss.
No test of a newly arriving ACK demand during probe transmission is claimed; the
completion branch explicitly leaves it untouched when controlHasAck is false.
RTT/PTO ownership, dropped-packet recovery, reliable frame retransmission, safe
release of lost metadata, congestion/flow/streams/QPACK/HTTP3 and remaining
IPv6/TLS/device work remain open. The earlier run637 watchdog failure remains
unresolved and did not recur here.


### Physical QUIC probe loss detection (2026-10-31)

The live interoperability fixture now supports `--drop-probe`. After the first
application exchange is acknowledged, the independent peer discards the second
short-header datagram before passing it to its QUIC receiver. The discarded
ciphertext's length and SHA-256 are retained. Anvil sends fresh probes with packet
numbers 1 through 4. The peer authenticates 2, 3 and 4 as PING-only packets and
requires that 1 never appeared in its authenticated receive log. There is no TLS
bypass, simulated acknowledgment, packet-number reuse or receiver state injection.

Before consuming the later ACKs, the shared loss scanner reports no loss. After
three delivery events, largestAcked is 4 and only the missing probe remains in
flight. The packet threshold of 3 then reports PN1 exactly once with its original
length and send timestamp, reducing in-flight bytes to zero. The lost record
remains retained: prefix pruning refuses to pass it. A repeated scan emits no
second event. The fixture uses an effectively disabled time threshold to isolate
packet-threshold behavior; it is not an RTT/PTO or time-loss test.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-wire-loss488/`.
Physical Pi4 captures 346/347 under resident 488 pass all 36 primary and extended
checks with eight-byte and zero-byte destination IDs. Discarded probes were
30/22 bytes. Both runs observe three later delivery events and one loss event,
with zero fixture faults. Exchange times were 447028/443206 us and maximum
foreground service gaps 1898/1901 us in these individual runs. The real Pi3 adapter
compiled but was not executed. Hash/map checks, confirmed return, retained monitor
captures, post-run cores/fonts/Vulkan and watchdog-off checks passed. No resident
image update or reset was needed; captures are not rendering/input qualification.

Only the fixture, builder and independent peer changed; the shared loss detector
needed no correction for this experiment. The first compile attempt used an
unsupported default procedure argument in the fixture and failed before producing
a payload. It was corrected to an explicit argument before either physical run.
The prior run637 watchdog incident remains unresolved and did not recur here.

This proves real lost-packet detection and accounting, not recovery of reliable
application data. RTT/PTO scheduling, owned recovery job cleanup, retransmitted
frame ownership and safe lost-prefix release remain next, followed by outstanding
congestion/flow, streams/QPACK/HTTP3 and IPv6/TLS/device work. ACK/PING alone do not
prove retransmission of a reliable frame. Existing non-loss mode remains the
builder default; the loss mode explicitly requires its matching peer configuration.


### Shared RTT and recovery duration arithmetic (2026-10-31)

`Anvil/Network/quic_handshake_sent.pbi` now provides `QuicRttInit`,
`QuicRttSample`, `QuicRttLossDelay`, `QuicRttPto` and `QuicRttDeadline`.
The path estimator is separate from packet-number spaces and accepts caller clock
units. Its recommended microsecond initialization is 333000 with granularity 1000.
ACK-delay decoding and sample eligibility remain caller responsibilities: only a
fully validated ACK with a newly acknowledged largest PN and at least one newly
acknowledged eliciting packet may supply a sample. Use receive time, not the time
when deferred processing finishes. Positive elapsed samples are required.

The implementation maintains raw minimum/latest RTT and adjusted smoothed RTT and
variation. Initial/Handshake ACK delay is ignored; application delay is capped
only after confirmation and cannot lower a sample below the observed minimum.
Weighted means use quotient/remainder arithmetic to avoid intermediate overflow.
The loss duration rounds upward; PTO duration and absolute deadlines saturate at
signed maximum. Application PTO is refused before confirmation. Backoff is an
explicit caller input, not a hidden counter or timer.

Protocol facts: [RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html), including
[verified erratum 7539](https://www.rfc-editor.org/errata/rfc9002). Variation is updated
from the previous smoothed estimate, as corrected by that erratum. The code is an
independent integer implementation; no appendix code is incorporated.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-rtt488/`.
The physical Pi4 under resident 488 passed 3,389 assertions (2,121 existing sent/loss
checks plus 1,268 timing checks), capture 348. An independent arbitrary-precision
Python oracle evaluates weighted sums directly, while the target uses overflow-safe
quotient/remainder decomposition. Cases cover first sample, delay clamping and
rejection, different packet spaces, confirmation, deterministic varied samples,
integer rounding, maximum signed values, saturated backoff/deadlines and refusal
without state mutation. The real Pi3 adapter compiled only. Image hash, map,
15-second deadman, confirmed return, viewed monitor capture, post-run cores/fonts/Vulkan
and watchdog-off checks passed. No resident update/reset or live latency claim.
A Python quoting error in the test generator was corrected before compilation;
no failed payload was run. The earlier run 637 watchdog incident remains unresolved
and did not recur.

These are timing primitives, not an automatic recovery controller. They do not
consume raw ACKs, select packet-number spaces, arm timers, manage PTO count or
retransmit frames. Next integrate eligible authenticated samples, retained send
timestamps and owned timer/loss-job cleanup, then exercise actual deadline-driven
probes. Reliable frame requeue/release, congestion/flow, streams/QPACK/HTTP3 and
remaining IPv6/TLS/device networking remain open. The live dropped-packet fixture
was not rerun for this additive math API; its previous evidence remains scoped to
its recorded source image.


### RTT sampling from completed ACK evidence (2026-10-31)

The shared sent-history ACK job now retains whether its largest packet was newly
acknowledged, that packet's send timestamp, whether any new delivery elicited an
ACK, the raw delay field, and whether its timing evidence was consumed.
`QuicRttAck` requires successful completion and consumes eligible evidence once.
It refuses incomplete/cancelled jobs, invalid clocks/exponents and owner aliases.
A newly acknowledged largest packet need not itself elicit ACKs if another newly
acknowledged packet did. A duplicate largest packet never supplies a new sample.
The ACK-delay shift saturates before overflowing. This adapter uses microseconds;
initialize its path estimator and supply receive timestamps/caps in those units.
The caller still authenticates the packet and preserves the job owner's lifetime.

The live fixture now calls this adapter after validated application ACK completion,
using the timestamp captured when the UDP datagram was dequeued, before crypto and
frame processing. It reads the authenticated peer's delay exponent/cap parameters.
It retains up to four sample traces (largest PN, receive/send timestamps, raw delay,
exponent, cap, level and confirmation). A separate host checker matches their ACK
numbers and quantized delays to the independent peer log and recomputes statistics
using arbitrary-precision arithmetic. The timestamps include local transport
queuing; they are not hardware wire timestamps or a general latency benchmark.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-rtt-ack488/`.
Physical Pi4 CPU capture 349 passed 3,513 assertions, including 124 new eligibility
checks. Cases include a non-eliciting largest with another eliciting delivery,
old largest with fresh lower packets, non-eliciting-only delivery, repeated calls,
partial/cancelled ACKs, invalid clocks, alias refusal and saturated delay decoding.
Live captures 350/351 passed all 36 primary and extended checks for eight-byte and
zero-byte destination IDs. Both took two samples: PN0 and PN4, whose ACK covered
three later probes. The discarded PN1 still produced exactly one loss event.
The derived PTO durations were 123622/112377 us; maximum foreground service gaps
were 1888/1897 us. These are individual-run measurements, not comparative claims.
The real Pi3 live adapter compiled only. All hashes/maps, deadman guards, returns,
viewed monitor captures and post-run core/font/Vulkan/watchdog-off checks passed.
No resident update/reset. The earlier run637 watchdog incident remains unresolved
and did not recur.

The production helper now enforces sample eligibility, and the live fixture uses
it, but production connection scheduling still needs integration. Derived PTO
values were checked, not armed. The loss fixture still sends probes explicitly
and disables its time threshold to isolate packet-threshold loss. Owned timer and
loss-job lifecycle, deadline-driven probes, reliable frame retransmission/release,
congestion/flow, streams/QPACK/HTTP3 and remaining IPv6/TLS/device work remain open.


### Shared probe timer and physical deadline-driven output (2026-10-31)

`QuicProbeTimer` provides Init, Arm, Poll, Acknowledged and Discard in the shared
sent/recovery module. Arm computes the earliest eligible Initial/Handshake/
Application deadline from RTT and the latest eliciting send times, using -1 for
an unavailable space. It excludes application data before confirmation. Poll
emits one expiry, disarms and increments bounded backoff; expiry does not change
packet delivery/loss state. A fresh authenticated ACK resets backoff only when
the caller also certifies address validation. The caller must rearm after ACKs,
sends and key discard; the ACK method alone does not recompute the deadline.
Discard prevents further polling or arming until explicit reinitialization.
No asynchronous callback or borrowed packet storage is hidden in the timer.

The live builder's new `--pto-probe` mode implies deliberate peer loss of PN1.
After receiving the first authenticated ACK, the Pi arms from its measured RTT
and PN1 send time, then keeps servicing foreground work while polling. Only after
expiry does it send fresh PN2. The peer authenticates PN2 and acknowledges it.
Before that ACK, the loss scanner reports no loss even though the PTO elapsed.
Afterward, the RTT-derived time threshold identifies PN1 once; the PN distance is
only one, so the packet threshold cannot explain this result. Backoff is reset,
the idle timer disarmed and timer ownership discarded during fixture cleanup.
The earlier explicit three-probe loss mode remains available separately.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-pto488/`.
Physical Pi4 capture 352 passed 3,916 CPU assertions, adding 403 timer checks.
These cover space selection/ties, application confirmation, deadline boundaries,
single firing, no eligible space, invalid admission preserving state, validated
ACK reset, cancellation and 65 repeated expiries through saturated backoff.
Live captures 353/354 passed all primary/extended checks for eight-byte and
zero-byte IDs. The peer received PN0 and PN2; PN1 was discarded before decryption.
The host checker matched ACK traces and recomputed RTT and the armed deadline.
PTO intervals were 116284/125092 us; Poll observed expiry 10/32 us after those
deadlines. Probe queue admission followed expiry; those figures are not physical
transmit timestamps. Maximum foreground service gaps were 1884/1913 us.
The real Pi3 adapter compiled only. All hashes/maps/deadman/returns, viewed monitor
captures and post-run cores/fonts/Vulkan/watchdog-off checks passed. No resident
update or reset. The older run637 watchdog incident remains unresolved and did
not recur. A lost deadman-arm reply in the CPU run was recovered by reading its
actual status, without rearming or restarting the program.

This verifies one timer-driven probe and subsequent time-based loss in the live
fixture. It does not yet prove repeated wire loss recovery, reliable frame
retransmission or production Core scheduling. The caller still determines keys,
outstanding eliciting spaces and address-validation/no-flight probe policy.
Integrating timer and loss-job ownership into connection dispatch/close, rearming
on all events, reliable frame requeue/release, congestion/flow, streams/QPACK/
HTTP3 and remaining IPv6/TLS/device networking remain open.


### Connection-owned recovery lifetime (2026-10-31)

`QuicConnection` now owns the RTT estimator, probe timer and bounded loss job. Begin initializes the estimator and timer. Recovery polling and loss stepping refuse a closing connection. Loss admission selects an owned packet-number space and refuses pending control/output work. Close disarms the timer immediately, even while shared TLS resources are held by another task; CloseStep cancels an active owned loss scan before discarding its ledger. Descriptor cleanup wipes the recovery state.

The live fixture uses these owned objects for the measured-deadline probe exchange. It then deliberately arms a timer and leaves an owned loss scan pending while a foreign TLS worker holds shared resources. Both Pi 4 cases verified immediate disarming, refusal of further poll/step calls, preservation of the foreign worker, and cancellation/release of the loss job before normal wipe and socket cleanup. This final timer arm is a lifecycle test, not an extra wire transmission.

Physical resident-488 tests used eight-byte and zero-byte peer IDs, captures 355/356, with independent peer authentication, ACK/loss and RTT/deadline trace checks. Both returned successfully; cores, font and Vulkan checks remained healthy and the deadman was disabled. BCM2837 compiled with its real adapter; it was not executed. No resident image changed. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-recovery-owner488/`.

This integrates ownership and teardown, not a complete recovery scheduler. The fixture still supplies send/ACK timing policy and explicitly arms the timer. Automatic rearming across sends, ACKs and key discard, repeated-loss recovery, reliable frame requeue, congestion/flow control, streams/QPACK/HTTP/3, off-link IPv6 and remaining TLS/device blocking are still open.


### ACK-eliciting flight and probe eligibility (2026-10-31)

Sent history now maintains an outstanding ACK-eliciting packet count and the latest accepted ACK-eliciting send time. ACK-only and padding-only sends do not advance that time. ACK application, explicit loss and bounded loss scanning remove a packet from the count exactly once; a late ACK of a lost packet does not subtract it again. Discard clears both fields. Pruning does not erase the latest send anchor while older packets remain outstanding.

`QuicHandshakeSentProbeTime` returns that time when eligible packets remain, -1 when none remain, or an error below -1. It refuses a locked ledger rather than reading a partially applied ACK/loss transaction. It does not implement address-validation anti-deadlock probes or loss-time priority. The live PTO fixture now queries this state when arming its application probe and when checking idle disarm, replacing the generic last-send timestamp and hardcoded empty-flight argument.

Physical Pi 4 resident488 passed 4,379 CPU assertions (including 463 additional checks) and both live eight-byte/zero-byte CID cases. These retain independent peer authentication and RTT/deadline/loss oracles plus recovery-close checks. Captures357/358/359 were retained and viewed; current returns are recorded separately from the previous LASTRUN visible in the capture. Core/font/Vulkan health and watchdog-off checks passed. The real BCM2837 adapter compiled, not executed. No resident image changed. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-probe-eligibility488/`.

These are shared recovery inputs, not a complete scheduler. Automatic send/ACK/key-discard rearming, repeated-loss recovery, reliable frame retransmission, congestion/flow control and HTTP/3 request streams remain open. Remaining IPv6 and TLS/device blocking work is also unfinished. Protocol facts follow RFC9002 sections6.2/6.4; implementation and test oracle are independent.


### Connection probe rearming (2026-10-31)

`QuicConnectionRecoveryRearm(c,resetBackoff)` now selects eligible owned packet-number spaces with usable write keys. Confirmed application traffic uses the validated peer max_ack_delay, converted from milliseconds to microseconds; absent values default to 25ms. It computes into a temporary timer and publishes only after successful admission. Locked ledgers and closing connections refuse rearming. The reset argument is a dispatcher policy input for fresh validated ACKs or packet-space retirement, not proof of an authenticated packet by itself.

Shared Initial/Handshake and application control send acceptance rearm the timer automatically. Completed handshake ACK processing rearms it, resetting backoff for fresh Handshake ACKs (or confirmation). Initial and Handshake key retirement reset and reselect the timer. Completion of an owned loss scan rearms/disarms it from remaining eligible flight. The live application ACK dispatcher explicitly calls the same helper after RTT sampling, with freshness computed from the ledger ACK count. The fixture no longer manually arms the timer before its missing-packet wait or after completing loss processing.

Physical resident488 Pi 4 cases with eight-byte and zero-byte peer IDs passed, captures360/361. Independent trace checking verifies that accepting probe PN2 rearms at its send time plus twice the previous PTO, then ACK2 resets/recomputes the deadline from the updated RTT. Idle loss completion disarms; a pending owned loss scan refuses rearming, and close cancellation remains verified. Both cases also passed primary/extended/peer authentication, loss, ownership and healthy core/font/Vulkan/watchdog-off checks. BCM2837 compiled with its real adapter, not executed. No resident image update or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-rearm488/`.

This is normal PTO integration, not a complete recovery controller. Application ACK dispatch and RTT sampling remain caller-driven; handshake RTT integration, time-threshold loss timer priority, no-flight client address-validation probes, repeated wire-loss handling, reliable frame requeue/reclamation, congestion/flow control and HTTP/3 request streams remain open. Off-link IPv6 and remaining TLS/device blocking are also unfinished. Captures show monitor launch state; record.json establishes the current return, not the older LASTRUN text in screenshots.


### Consecutive probe loss on the physical Pi (2026-10-31)

The live builder now supports `--repeat-probe`, which enables the PTO fixture and makes the peer discard client PN1 and PN2 ciphertext before QUIC processing. The fixture polls the owned timer twice, sends fresh PN2 and PN3 only after the respective expiries, and relies on the shared automatic rearming path. It checks that timer expiry itself neither acknowledges packets nor removes bytes in flight. After authenticated ACK3, both missing packets are reported lost exactly once through the time threshold (their packet distances are below three), then idle recovery disarms.

Independent checking uses the Pi timestamps and peer authentication log: the second deadline is based on PN2's send time and twice the first PTO; PN3's armed deadline uses four times the first PTO; ACK3 resets to the newly measured RTT-derived PTO. Both dropped ciphertext digests are retained and distinct. The peer authenticated only PN0 and PN3 among these application packets. These are real encrypted UDP drops, not injected ACKs or synthetic clock advances.

Both physical resident488 Pi 4 cases passed, with eight-byte and zero-byte peer IDs and captures362/363. Primary/extended assertions, RTT/deadline oracles, safe close, core/font/Vulkan health and watchdog-off checks passed. BCM2837 compiled with its real adapter, not executed. No resident update or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-repeat488/`. The viewed screenshots retain launch/monitor state; record.json proves the current return rather than the older LASTRUN visible in the image.

This establishes two consecutive missing-probe recovery cycles, not unlimited recovery or reliable application data retransmission. The fixture still drives a bounded packet schedule and receive loop. Time-loss timer priority, client no-flight/address-validation policy, handshake RTT integration, reliable frame ownership/requeue/reclamation, congestion/flow control, streams/QPACK/HTTP/3 and remaining IPv6/TLS/device networking are unfinished. Existing single-drop and legacy packet-threshold modes remain available.


### Recovery polling and partially applied ledger jobs (2026-10-31)

`QuicConnectionRecoveryPoll` now refuses with `QUIC_SENT_BUSY` while any Initial, Handshake or application sent ledger is locked. Bounded ACK/loss jobs can yield after only part of their event stream has been applied. Consuming a probe expiry during that interval would advance backoff and clear the armed timer against an intermediate state. The new refusal leaves the timer intact; the dispatcher must finish or cancel the ledger job and perform the required rearming before resuming recovery polling. This is a cooperative refusal, with no internal wait.

The live fixture requests an otherwise-due poll using a maximum timestamp while real ACK and loss jobs hold their locks. It compares every timer byte and all three lock owners before/after the refused call. These are lifecycle injection checks, separate from the real-clock two-consecutive-drop exchange, which still verifies actual timer expiries, fresh probes, peer ACKs, loss accounting, backoff reset and idle disarming.

Both physical resident488 Pi 4 peer-ID variants passed, captures364/365, including primary/extended assertions, independent peer/deadline/RTT checks and safe close. The first case exercised 14 locked ACK polls and five locked loss polls; observed lock spaces were Initial and application (mask5). Handshake-space refusal is implemented by the same guard but is not claimed as newly exercised wire coverage. Core/font/Vulkan health and watchdog-off checks passed. BCM2837 compiled, not executed; no resident change or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-poll-guard488/`. Viewed screenshots show launch state; record.json proves the current return.

Full recovery policy remains unfinished: time-loss timer priority, client no-flight/address-validation probes, handshake RTT integration, reliable data retransmission/ownership/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining off-link IPv6/TLS/device blocking. This guard protects a transaction boundary; it does not complete those policies.


### Validated loss-deadline state (2026-10-31)

Sent history now retains the next deadline and policy from a completed bounded loss scan. `QuicHandshakeSentLossTime(s,delay,threshold)` returns a positive deadline, zero when no loss timer is needed, -1 when a fresh scan is required, or an error below -1. A locked ledger refuses the query. The result is published only at scan completion, not after a partial event stream.

Fresh ACK application, explicit loss and admission of a new scan invalidate the stored result. Cancelling a rescan leaves it unknown. A changed delay or packet threshold requests a new scan without destroying the previous policy result. Duplicate ACKs and newer tail sends preserve a still-valid deadline; the tail cannot precede the largest acknowledged packet. Pruning acknowledged prefixes preserves the result, while discard clears it. No-flight and no-eligible-prefix cases are known idle without a scan.

Physical Pi 4 resident488 passed 4,647 assertions, including 268 additional checks covering completed/partial/cancelled scans, policy changes, fresh versus duplicate ACKs, late ACKs after loss, tail sends and explicit invalidation. Both live peer-ID variants also passed the existing consecutive-drop and locked-poll tests, captures366/367/368 across CPU and live runs. Independent peer/RTT/deadline checks, safe close, core/font/Vulkan health and watchdog-off passed. BCM2837 compiled with its real adapter, not executed. No resident update or reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-deadline488/`; viewed screenshots show monitor launch state, while record.json proves the current return.

The connection dispatcher does not yet consume this query to give time-based loss priority over PTO. That integration remains next; this change supplies validated, bounded-scan state rather than assuming an old deadline is current. Client no-flight/address-validation, handshake RTT, reliable retransmission/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining IPv6/TLS/device work are still open.


### Time-loss priority in connection polling (2026-10-31)

`QuicConnectionRecoveryPoll` now checks eligible owned packet-number spaces using the current RTT loss delay and packet threshold three before considering PTO. Return zero means no action now; `QUIC_RECOVERY_PROBE` (one) requests a probe; `QUIC_RECOVERY_LOSS` (two) requests a bounded loss scan. `recoveryLevel` is valid only on returns one/two. Negative values remain refusal/error results. A caller receiving two must run the selected space's scan with current policy, consume its events and poll again. Poll itself does not mark packets lost.

An unknown/stale scan requests work immediately. With valid scan results, the earliest loss deadline wins; any future loss deadline suppresses PTO dispatch even when the stored PTO candidate is earlier. The candidate is retained without advancing backoff. These are poll-driven candidates, not asynchronous timer callbacks. No loss work means normal one-shot PTO behavior resumes. Discarded/keyless spaces are excluded and locked ledgers still refuse polling. Negative timestamps are refused.

The physical Pi fixture adds 104 isolated scheduler assertions with synthetic timestamps and separate storage: stale scans in all three spaces, earliest-deadline selection, future/due loss priority over an artificially early PTO candidate, byte-for-byte preservation of that candidate, repeated scan requests, no premature loss marking, key/discard exclusion, idle behavior, one-shot application PTO and RTT-policy invalidation. They do not authenticate packets, own a socket or alter the live connection and are not wire-latency evidence.

Both resident488 Pi 4 peer-ID variants passed these assertions plus the separate real-clock two-drop exchange, locked-poll checks, independent peer/RTT/deadline/loss checks and safe close; captures369/370 were viewed and retained. Core/font/Vulkan health and watchdog-off passed. BCM2837 compiled, not executed. No resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-priority488/`. Current returns are proven by record.json, not older LASTRUN text in launch screenshots. Protocol priority follows RFC9002 sections6.1.2/6.2.1; implementation is independent.

Remaining work includes live dispatch of loss-scan requests in general traffic, client no-flight/address-validation policy, handshake RTT, reliable data ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP/3 and remaining off-link IPv6/TLS/device blocking. This polling policy does not complete the connection controller or networking.


### Authenticated traffic drives loss dispatch (2026-10-31)

The live QUIC fixture now consumes `QuicConnectionRecoveryPoll` loss requests after the authenticated application ACK and RTT update. It verifies return `QUIC_RECOVERY_LOSS` and the selected application space, preserves in-flight accounting/backoff until the scan begins, then starts the bounded scan at the recorded real clock using the selected space. Scan events are consumed with foreground service between steps. Polling after completion must return idle. Legacy packet-threshold-only fixture mode retains its explicit scan policy.

Both physical Pi 4 connection-ID cases passed the two-dropped-datagram exchange, scheduler dispatch, independent peer/RTT/deadline checks, 104 separate synthetic scheduler assertions and safe close. The peer authenticated only the surviving probe; two missing packets produced two loss events. New report fields 5C8/5D0/5D8 record dispatch checked/start/completion; the independent oracle verifies ordering after ACK receipt. Captures371/372 were viewed and retained; record.json proves the current return, not older LASTRUN text. Core/font/Vulkan checks and watchdog-off passed. BCM2837 compiled only; no resident update/reset.

Evidence: `docs/evidence/anvil-ipv6-20261030/quic-loss-dispatch488/`. This proves live integration in the connection fixture, not a complete web client dispatcher. Client no-flight/address-validation policy, handshake RTT, reliable frame ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP3 and remaining off-link IPv6/TLS/device blocking remain open.


### Retained handshake receive timestamps and RTT (2026-10-31)

Shared receive APIs now offer `QuicConnectionReceiveBeginAt` and `QuicConnectionReceivePacketBeginAt`, taking the datagram dequeue timestamp in the same clock units as sent history/recovery. Values below -1 are refused before admission; -1 omits sampling. Existing Begin APIs remain wrappers supplying -1. Admitted receive storage retains the timestamp through cooperative decryption and ACK processing. After the ACK ledger reaches DONE, Core updates RTT before rearming PTO; `acknowledge.rttSample` records whether a sample was accepted. Initial/Handshake ACK delay is ignored. Eligibility and one-shot sampling stay in QuicRttAck. Timing errors fail the owned connection rather than silently fabricating a sample.

The live fixture captures time once per UDP dequeue and reuses it for coalesced packets. It records up to16 handshake samples separately from application samples. Both physical Pi cases passed the independent oracle replaying handshake then application RTT arithmetic and derived PTO/loss deadlines, the two-dropped-probe exchange, 104 isolated scheduler assertions, live loss dispatch and cleanup. The observed handshake sample was Initial PN0; no live Handshake-space sample is claimed. The first case's roughly one-second observation increases subsequent probe waits; it is retained rather than reset for faster tests. These are software dequeue observations, not hardware arrival timestamps.

Captures373/374 were viewed and retained; record.json proves each current return. Core/font/Vulkan and watchdog-off passed. BCM2837 compiled only; no resident update/reset. Evidence: `docs/evidence/anvil-ipv6-20261030/quic-handshake-rtt488/`. Protocol facts: RFC9002 sections5.1-5.3, https://www.rfc-editor.org/rfc/rfc9002.html#section-5.1; implementation is independent.

Client no-flight/address-validation policy, reliable frame ownership/retransmission/reclamation, congestion/flow, streams/QPACK/HTTP3 and off-link IPv6/TLS/device blocking remain open. This does not complete networking.
