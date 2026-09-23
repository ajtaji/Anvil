# Native HTTP connection server

`Anvil/Services/Http/server.pbi` is a portable native HTTP connection engine:
it accepts connections, incrementally receives and admits requests, routes
them, builds responses, handles partial writes and closes connections. It is
more than a parser, but **is not yet a deployed Pi web server**. The transport
and polling owner must be supplied by target composition. The included
`transport_tcp.pbi` supplies a native adapter for the existing selected-socket
TCP library; it is not enabled merely by including the connection engine.

Include `Anvil/Applications/Forum/http_head.pbi` and the named transport
services before the engine. The request admission parser follows its existing
documented restricted HTTP/1.1 grammar. No external server code is imported.
Persistence, ordered pipelining and close handling were cross-checked against
[RFC 9112 sections 9.3 and 9.6](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3).

## Using the monitor service

The Pi 4 monitor explicitly includes the parser, native transport and engine.
The prompt's network-service pass polls them even after a listener is lost,
so existing children and queued output still receive service. No listener opens
at boot: start it deliberately from the console (the default port is 8080):

```text
http serve
http status
http stop
http serve 8081
```

Visit `http://<board-ip>:8080/` (or your selected port) and
`/health`. Use the address reported by Anvil, not a fixed assumed address.
`http get <url>` remains the separate HTTP client command.

This is a cooperative prompt service, not yet a preemptively scheduled process.
A long-running command or payload that does not poll these services can delay
the server. The general scheduler remains a separate implementation requirement.
There are no account or private-data routes, and no TLS; do not expose this as
the production forum. The live forum is unchanged. Pi 3 still needs its real
boot/network drivers before the same service can run there.

Desk-build and command checks (neither deploys or connects to a board):

```text
python tools/http_monitor_build_check.py --compiler <PureMetalForge.exe> --output <new-scratch-image-path>
python tools/http_monitor_command_check.py --purebasic <pbcompiler.exe>
```

The build helper pins `PMF_ROOT` and stages this repository's compiler data,
then records every successful monitor build through the build-count mechanism.
It refuses an existing output path to preserve prior candidates.

## Supported browser surface

- `GET /`: original responsive HTML landing page with a health link.
- `GET /health`: plain-text service status.
- `HEAD` on those resources or missing resources: same content length and
  headers as GET, without response body.
- Missing paths return 404; unsupported methods return 405 with Allow.
- Malformed requests, oversized headers/bodies and unsupported transfer coding
  produce explicit error responses followed by close. No request is dispatched
  until its admitted Content-Length body is completely received.

Responses carry Content-Length, explicit content type and nosniff. HTTP/1.1
connections are reusable for at most 16 requests. `Connection: close` wins
case-insensitively across comma-separated tokens and repeated fields; the
last permitted response and every parser rejection explicitly close. Complete
requests are consumed with their exact Content-Length body, and any already-read
next request bytes are retained, including partial headers. Pipelined responses
remain ordered: only after one response is accepted by transport is the next
routed. No bytes following an explicit close are dispatched. Reuse lowers close
pressure but does not replace transport-side correct TIME-WAIT handling.
This component does not implement chunked bodies, upgrades, HTTP/2, file serving or
100-continue; Expect is rejected with 417 before waiting for a body. There is no disk-path construction or user content reflected
in the current static responses. It accepts syntactically valid Host values
for these public fixed resources; configured authority validation is required
before account links, redirects or private forum routing are added.

The page explicitly says that the forum is under construction and registration
and sign-in are unavailable. HTTP health is not a claim that database, email,
authentication or Pi board support is ready.

## Transport ownership contract

| Service | Contract |
| --- | --- |
| `HtAccept()` | Nonblocking. Positive unique connection handle transfers to engine, 0 means none, negative means listener error. Never return one live handle twice. |
| `HtRead(handle,pointer,count)` | Nonblocking. Positive bytes no greater than count, 0 means would-block, negative means EOF/error. Never retain/write beyond supplied memory. |
| `HtWrite(handle,pointer,count)` | Nonblocking. Positive bytes accepted no greater than count, 0 would-block, negative fatal. Copy accepted data before returning; the engine may reuse its output after close. |
| `HtClose(handle)` | Called once to return ownership to transport. On normal response completion, drain previously accepted output and send FIN, with a bounded close timeout. Do not discard pending send-ring bytes. The engine never accesses that handle again. |

`HsPoll(nowMilliseconds)` performs one accept attempt when a slot is available
and at most one 512-byte read or write per occupied slot per pass. Up to four
engine slots have independent receive, response and partial-write state.
`HsStop()` releases all engine-owned connections. Calls must be serialized by
one service owner; never call the engine or existing TCP selection routines
from an IRQ or concurrently from application callbacks.

`TcpListenQueued(port)` reserves a persistent listener; incoming SYNs allocate
independent child TCBs. `TcpAccept(listener)` returns one established pending
child, or -1, preserving the selected socket. Pending children are bounded by
the shared pool and accepted in slot order. Exact connection tuples are matched
before wildcard listeners. Legacy `TcpListen` retains its original converting,
rearming behavior for existing callers. Reopening a queued reservation is refused
until explicitly unlistened; unlisten/close/abort cancel its unaccepted children,
but accepted children remain owned by their service.

The Pi-family TCP pool now has 16 slots (approximately 420 KiB). One HTTP
listener leaves at most 15 aggregate child/other connections, including closing
and TIME-WAIT TCBs. HTTP serves up to four active connections, each at most 16
requests. Pending connections and other services also consume this finite pool.
When exhausted, new SYNs are not accepted until slots become available; the
240-second TIME-WAIT is never shortened to manufacture capacity. This is not
an unlimited-throughput or public-Internet readiness claim.

Native adapter startup is `HtStart(port)`, which reserves a free TCP slot and
listens without calling TcpInit or resetting other sockets. Call
`HtService(nowMilliseconds)` before `HsPoll` to advance TCP/drain ownership.
It restores the previously selected socket on every operation. `TcpGeneration`
is a per-slot lifecycle counter advanced by TcpWipe, never reset by TcpInit;
generation saturation refuses identity rather than wrapping. Each accepted
HTTP handle also has a separate nonreused serial. Old handles cannot address
a reset/reused TCP connection. `TcpListenerGeneration` is a separate stable
listener lease advanced on successful Listen, unchanged by connection rearm.
Together with `TcpListeningPort` it distinguishes continued listener ownership
from a slot repurposed even onto the same port by another service. Lease
exhaustion refuses a new Listen instead of wrapping.

Normal `HtClose` queues FIN through TcpClose and retains transport drain state.
After ten seconds without completing close, the same-generation connection
may be aborted; TIME-WAIT remains governed by TCP's own timer. `HtStop` is an
explicit service shutdown, not normal response completion: it unlistens and
aborts only still-owned non-TIME-WAIT children, while preserving TCP TIME-WAIT.
It cannot abort a foreign same-port lease or a reused child generation. A lost
listener does not stop servicing existing child/drain ownership. Call HsStop before HtStop. No driver
or monitor startup is silently wired by these files.

## Bounds and failure behavior

Each slot reserves 4096 header bytes plus 1024 body bytes, and 4096 response
bytes. Four slots reserve 36 KiB of byte buffers plus small integer tables.
Request receive has an absolute ten-second deadline from acceptance or prior
response completion (also the keepalive idle deadline); each response gets ten
seconds from construction. Dribbling bytes does not extend
either deadline. EOF, provider failures, invalid byte counts and deadline
expiry release the connection. No response is promised after transport loss.

The caller supplies nonnegative monotonic milliseconds, not wall clock.
Backward time is refused without servicing. Timeouts compare elapsed time,
without adding a deadline that could overflow. The clock must fit the target's
native integer: AArch64 has a 64-bit domain; a 32-bit port still needs a proven
long-uptime clock representation before deployment. Ignoring a backward/wrapped
clock refusal would stop progress. There is no silent wrapping arithmetic.

Parsing work is bounded by the header cap per poll; repeated partial headers
are reparsed. This initial implementation is bounded, not a throughput claim.
Response literals are fixed and fit the output cap; adding dynamic rendering
requires checked length construction and explicit output-overflow handling.

## Test boundary and deployment requirements

```text
python tools/http_server_check.py --compiler <PureMetalForge executable>
python tools/http_server_transport_check.py --compiler <PureMetalForge executable>
python tools/http_server_queued_check.py --compiler <PureMetalForge executable>
```

The test builds an isolated fixture and executes the actual emitted native
server and parser. Test-only transport hooks provide fragmented input,
short/would-block output and a localhost socket bridge. The localhost browser
request is answered by the emitted engine; the host adapter is an instrument,
**not a Python production server or a Pi network-driver test**.

The native adapter gate executes the real adapter against explicit fake TCP
services, including queued-output preservation, TIME-WAIT, draining timeout,
selection restoration, reset/rearm and foreign slot reuse. A second fixture
executes the real lifecycle-counter prefix of TcpWipe, listener-lease block of
TcpListen and getters, including saturation.

The queued wire gate executes the real net/link/TCP/adapter/HTTP stack using
scripted checksum-correct Ethernet frames: 15 independent HTTP connections with
TIME-WAIT retained, full-pool refusal, two simultaneously accepted HTTP clients,
queued relisten refusal and pending-child cancellation. These are native emitted
instruction tests, not physical-peer delivery or board-throughput proof. The
legacy TCP multi-interface and receiver gate remains a separate regression.

Before deployment: physical transport acceptance/drain/reset tests, several
simultaneous physical clients within backend capacity, memory quota exhaustion,
long-uptime timing and scheduler/service latency under load. Pi 3 still needs
its executable board and networking drivers. HTTPS server identity, secure
sessions, CSRF, authorization, persistence and registration dependencies must
be live before any private data or account-write endpoints are exposed.
