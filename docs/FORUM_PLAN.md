# Native forum on Anvil

Status: implementation started; **not a running forum or a deployable Pi 3 image**.
This is an independent native application, not a Node.js compatibility layer.
The runtime is PureMetal source; host migration/build utilities use PureBasic.
Python is used only for development gates. The initial target is Raspberry Pi
3 Model B v1.2; application, scheduler policy and storage formats remain portable.

## Definition of finished

A browser can use the familiar forum workflows against the Pi while other
Anvil applications continue to run. An offline copy of the existing NodeBB
site imports without losing IDs, content, permissions or files. Backup and
restore work after restart, not just while objects remain in RAM. No account,
UID, membership or public user entry exists before mailbox possession is proved.
Production cutover occurs only after parity, security, crash-recovery and Pi 3
hardware acceptance, with the original site preserved for rollback.

"Like NodeBB" includes the installation's actual workflows, not just a topic
list that looks similar. JavaScript plugins are not native plugins and cannot
be marked supported merely because their records were copied. Every observed
feature must have an implementation/proof or an explicit unresolved entry.

## Work ownership and contracts

| Area | Current source or specification | Current delivery |
| --- | --- | --- |
| Compatibility and migration | [FORUM_COMPATIBILITY.md](FORUM_COMPATIBILITY.md) | Read-only installation census, feature inventory and proposed interchange/restore contract. No exporter/importer yet. |
| Verified registration | `Anvil/Applications/Forum/registration.pbi`, [FORUM_REGISTRATION.md](FORUM_REGISTRATION.md) | Domain sequencing plus fake-provider tests. Crypto, transactional persistence, mail and secure transport are not supplied by the domain. |
| Scheduling | `Anvil/Kernel/Scheduler/`, [SCHEDULER_PLAN.md](SCHEDULER_PLAN.md) | Tested logical task lifecycle/queues; no context switch or timer preemption yet. |
| HTTP admission | `Anvil/Applications/Forum/http_head.pbi` | Bounded request-head grammar/framing admission with caller-owned state; not a socket server. |
| Pi 3 | `RaspberryPi3/Board/platform.pbi`, [NEW_BOARD_PORTS.md](NEW_BOARD_PORTS.md) | Identity stub only. No executable board entry, storage/network drivers or hardware proof. |

The scheduler is a kernel service, not code private to the forum. Applications
have separate lifecycle, cancellation, resource accounting and contexts.
Existing drivers with shared scratch state are serviced by one owner through
bounded request/completion queues; adding a timer does not make them reentrant.
Initially one CPU is enough to demonstrate scheduling. SMP is a separate
extension, not a prerequisite for more than one application making progress.

## Architecture

Browser requests enter the network/TLS service, then a bounded HTTP parser and
router, then authentication/authorization, then forum commands/queries. Only
the storage service commits persistent changes. Notifications/mail/search use
durable jobs and scheduler completions rather than blocking the request task.

The application owns categories, principals, groups, topics, posts, attachments,
subscriptions, unread state, notifications and moderation history. A historical
principal can preserve authorship without being an active login account.
Authorization is applied before returning any entity or search result. Imported
HTML, Markdown, filenames and URLs are untrusted data, never executable input.

The browser UI must preserve category hierarchy, readable topic/post pages,
code boxes, editing/preview, navigation, search and moderation controls. Use
original responsive HTML/CSS and browser-side interaction where needed, served
by the native application. Do not copy theme code or promise JavaScript-plugin
binary compatibility. The compatibility inventory owns the detailed parity list.

## Storage and import

Use disk-backed records/indexes with bounded caches; never require the entire
database to fit RAM. Transactions need write-ahead/recovery ordering, atomic
publication, checksums and a tested storage flush contract. A filesystem write
returning success is not, by itself, power-loss durability.

The proposed interchange is a versioned manifest, streamed typed JSON Lines and
checksummed attachment blobs. The PureBasic importer first validates everything
into a staging generation. It checks schema/version, counts, bounds, duplicate
IDs, relationships, private permissions, attachments and email-proof provenance.
Only a complete validated generation may become active; failure cannot overwrite
the current database. Unsupported records remain in a private archival section
with a visible migration exception, not silently discarded.

Password hashes require an actual compatibility/KDF decision; no plaintext
password export and no silent reset. Old sessions, API keys and reset tokens
are not activated by import. Unverified source users remain inactive historical
records and must prove an email before acquiring an active account. Source bans
and private-group restrictions survive migration.

A final consistent source snapshot requires a planned write barrier or a proven
snapshot mechanism across database and uploads. This does not authorize stopping
the live site now. Keep one authoritative writer during cutover and retain the
original backup. The round-trip proof includes restart/restore, attachment hashes,
public/private visibility, old links and imported counts by entity/state.

## Security and resource gates

- HTTPS server identity, reviewed TLS and certificate renewal/provisioning.
  No native TLS server is claimed by the existing outbound HTTP client.
- Cryptographic entropy and digest/KDF services fail closed. The configured
  mail service sends challenge links; failed mail never creates accounts.
- CSRF defenses, origin checks, secure/HttpOnly/SameSite session cookies,
  session rotation/revocation, constant-time secret comparisons, password
  recovery, administrative authorization and audit records.
- Sanitized Markdown/HTML, output escaping, safe attachment content types,
  filename traversal refusal and no execution of uploaded files.
- Per-connection deadlines, bounded headers/body/chunks, request and login
  limits, KDF concurrency quotas, global memory/socket/storage quotas and
  cancellation of disconnected requests. No unbounded thread-per-client model.
- A CPU-bound application that never yields must not starve the forum, input
  or storage. Prove timer-driven progress and bounded service latency before
  accepting multi-application hosting. Same-address-space privileged tasks
  are not isolated processes; process isolation needs separate design/proof.

Current TCP has a four-socket pool and selected-socket/shared packet state.
Neither changing that constant nor calling it from several tasks supplies a
web-server connection model. Implement listeners/accepted-connection ownership,
fair servicing and backpressure at the network service layer.

## HTTP admission boundary

`ForumHttpHead` returns incomplete, admitted-head, or an HTTP rejection status.
It reads only the advertised input span and writes five native integers to
caller-owned output: header bytes, body bytes, target offset/length and method
length. No input/output allocation or process-global parse state is used.
The caller must provide valid nonoverlapping memory spans, a receive deadline,
an exact allowed-host policy, method/route authorization and body handling.

The current subset admits origin-form HTTP/1.1, one nonempty Host and at most
one decimal Content-Length. Bare LF, folded headers, whitespace before a colon,
conflicting/duplicate framing and oversized lengths are rejected. Transfer
coding returns 501 unless combined with Content-Length, which returns 400.
Close after every rejection; never reuse a rejected connection's remaining
bytes. No chunked decoder, upload stream, websocket, TLS, cookie parser,
complete URI validator or HTTP server is implied by this foundation.

Framing rules were checked against [RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html),
sections 2, 3, 5 and 6. Chunked decoding and the remaining server requirements
must be implemented and tested before claiming HTTP/1.1 server completeness.

## Delivery sequence and acceptance

1. **Foundation started:** inventory, domain registration, bounded HTTP head
   admission and logical task lifecycle. Independent desk gates are required.
2. **Kernel and Pi 3:** real task contexts/private stacks, exit cleanup, timer
   preemption and reentrancy/service ownership; actual Pi 3 boot, counter,
   interrupt backend, storage, USB/Ethernet and recovery. No Pi 4 address aliases.
3. **Runtime services:** durable transaction store, connection-owned TCP server,
   TLS, secure time/entropy, mail/outbox, HTTP body/chunk decoding and safe router.
4. **First vertical slice:** imported read-only categories/topics/posts in a
   browser, preserved links/files/private visibility; verified-first signup,
   login, posting and reboot-persistent replies alongside a second application.
5. **Parity:** remaining installed forum workflows and administrative functions
   in the compatibility matrix; import all supported records with explicit
   exceptions instead of hidden drops. Browser functional/accessibility tests.
6. **Release/cutover:** repeated crash recovery, backup/restore, adversarial
   input/security review, resource pressure and real Pi 3 multitasking tests.
   Rehearse the complete source backup/import/restore offline before moving
   the live service or its DNS. No production cutover has been scheduled.

There is no defensible completion date or capacity claim yet: measure on the
intended board and retained dataset. Test high memory/storage pressure and
concurrent clients; report measured limits instead of promising unlimited use.

## Current desk commands

```text
python tools/scheduler_lifecycle_check.py --compiler COMPILER
python tools/forum_http_head_check.py --compiler COMPILER
```

Registration reference and fail-closed fixture commands are recorded beside
their tests. None of these small fixtures builds or deploys an Anvil monitor.
Production data, certificates, credentials and real backup packages must never
be committed to this source tree or printed in diagnostic output.
