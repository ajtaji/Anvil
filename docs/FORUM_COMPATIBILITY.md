# Native forum compatibility and migration contract

Status: discovery/design, 2026-09-11. This is an independent PureMetal application
for Anvil, with PureBasic host tooling. Node.js, NodeBB and Redis do not thereby
run on Anvil. Pi 3 boot, storage and networking still require their own proof.
No production data was exported or changed during this inventory.

## Observed installation

Read-only package metadata and bounded Redis type/cardinality queries found:

| Item | Observed |
|---|---|
| NodeBB | 4.14.9 |
| Database | Redis; 53,890 keys in its selected database |
| Active theme | Harmony |
| Indexed users/topics/posts/categories | 9 / 747 / 2,070 / 119 |
| Upload directory | Approximately 30 MiB allocated (`du -sh`) |

Counts are index cardinalities at one instant, not a consistent export. They
do not certify deleted, remote/federated, orphaned or private-record totals.
No usernames, addresses, passwords, tokens or private messages were printed.

Active packages: composer-default, Harmony, markdown, mentions,
widget-essentials, rewards-essentials, emoji, dbsearch, traditional-categories,
spam-be-gone and the local automatic-watch plugin. Installed-but-not-active
packages include 2factor, local emailer, link-preview, ntfy, web-push and other
themes. Installation alone is not evidence a feature is enabled.

## Compatibility inventory

Every row requires implementation and acceptance; this is not a parity claim.

| Surface | Required treatment |
|---|---|
| Categories | Preserve IDs, parent hierarchy, order, descriptions and per-group access; traditional nested navigation. |
| Topics/posts | Preserve IDs, authorship references, raw Markdown, chronology, replies, edits, tags, pinned/locked/deleted state and moderation visibility. |
| Links/uploads | Preserve `/topic/<id>/<slug>`, `/post/<id>` resolution, anchors and registered attachment paths; checksum actual files and refuse missing/traversing references. |
| Composition | Markdown, fenced code, quoting, safe links, mentions and emoji; sanitize rendered output independently. Never trust imported HTML. |
| Identity | Profiles, groups, bans, roles and permissions; no accidental public access to private categories, messages or deleted material. |
| Discovery | Search, pagination, unread state, bookmarks, watched categories/topics and notifications. Rebuild search indexes rather than importing engine internals. |
| Moderation/admin | Editing, moving, locking, deleting, tags, audit trail, anti-spam and rate limits; admin authorizations checked server-side. |
| Notifications | Reproduce automatic watching for the configured administrator without hardcoding an identity; require an explicit imported setting. Email delivery is a separate service. |
| Additional features | Chat, federation, polls, widgets, rewards, reactions, OAuth, 2FA and push need field/plugin census before claiming parity. Preserve unsupported records in the private archive and refuse a lossy migration silently. |

## Email before account creation

Pending email challenges are a separate bounded, expiring store, not user rows.
They have no UID, profile, membership, session or user-list appearance. Only
after a one-use challenge proves mailbox possession may a transaction allocate
the account and its unique identity. Token replay, expired tokens, concurrent
redemption and resend flooding must be tested. Use cryptographic random tokens,
store token digests, avoid account enumeration, and require TLS for delivery
flows and browser sessions. Do not save plaintext passwords in pending records.

Import does not grandfather unverified identities into active accounts.
Preserve authorship through inactive historical-principal references; require
verified-email evidence or a fresh verification before login activation. Do not
infer verification from a nonempty email field. Existing bans remain enforced.
Password-hash compatibility is unproven; do not discard hashes or force resets
without a migration decision. Sessions, reset tokens and API credentials should
not become valid credentials in the new service by copying them.

## Proposed interchange package (not implemented yet)

Use a versioned manifest plus streaming UTF-8 JSON Lines by entity type, and
separate attachment blobs addressed by digest. The manifest records source
version, export format version, snapshot boundary, counts, byte lengths and
SHA-256 for each file. IDs are decimal strings, timestamps explicitly Unix
milliseconds, text retains Unicode/newlines, and missing differs from null.
Each record retains its source ID and type; cross-references are validated in a
second pass. Preserve source ordering and flags, not Redis cache structures.

Private entities and credentials require a separately encrypted, access-limited
channel/package; never commit real exports, upload them publicly or include
them in diagnostic logs. Parser limits must bound nesting, record length,
integer range, archive expansion and attachments. Unknown mandatory fields,
duplicate IDs, dangling authors/categories and failed checksums abort staging.
Keep a migration report of counts and rejected record IDs without PII.

NodeBB's built-in per-user exports are not a complete migration format. The
profile job exports private profile/history/session/chat information and removes
the password; the post job generates per-user CSV. Neither replaces a whole-site
snapshot with permissions, settings and uploads. These jobs were read, not run.
[Profile exporter](https://github.com/NodeBB/NodeBB/blob/v4.14.9/src/user/jobs/export-profile.js),
[post exporter](https://github.com/NodeBB/NodeBB/blob/v4.14.9/src/user/jobs/export-posts.js).

## Target storage prerequisites

Do not load the entire database into Pi 3 RAM. Use bounded caches, paginated
indexes and streaming attachments. Anvil exposes storage services, but an API
name or successful write does not prove durable transactional commits. Before
accepting forum writes, prove append/write completion, flush-to-media ordering,
torn-write detection, recovery and atomic publication on the actual medium.
Use a journal with sequence numbers, lengths, checksums and commit records;
rebuildable indexes and generation-based snapshots. Only acknowledge a durable
post/account transaction after its data and required identity indexes commit.
Failed capacity estimates must refuse admission with an actionable message.

Need measurements: Redis dataset bytes, logical export size, largest record,
upload logical size, expected growth/concurrency and actual Pi 3 storage/RAM
budget. A 30 MiB upload tree does not mean a 30 MiB total migration. Reserve
space for old and new generations, journal, staging, recovery and growth.

## Reversible migration procedure (not performed)

1. Inventory exact NodeBB/plugin versions and configured Redis persistence
   mode; identify RDB/AOF files without publishing configuration secrets.
2. Obtain a consistent snapshot during an approved write-free boundary. Preserve
   the database, uploads, private configuration and custom plugin code together.
   Redis AOF/multipart persistence must not be mistaken for a standalone RDB.
   Verify checksums and restore to an isolated host with outgoing email, push
   and federation disabled before trusting the backup.
3. Run the PureBasic converter against the isolated restored database, never a
   guessed raw-RDB parser on production. An independently implemented Redis
   protocol client may stream authorized records. Freeze a version-specific
   key/schema mapping after actual record-type census; indexes alone miss data.
4. Import into a fresh, non-public target generation. Validate counts, every
   reference, permissions, timestamps, attachments and representative rendered
   threads. Compare public/private views and test verification before account
   creation. Prove cold restart and interrupted-write recovery.
5. Schedule a final freeze/snapshot/import and cutover only after acceptance.
   Retain the old site offline/read-only and the verified backup unchanged.
   Prevent two writable authorities. Do not switch DNS or stop the old service
   as part of desk discovery.
6. Roll back by disabling the new writer and restoring routing to the preserved
   old service. If the new service accepted writes, reconcile/export that delta
   before reopening the old writer; otherwise rollback would lose posts.

[NodeBB backup guidance](https://docs.nodebb.org/configuring/upgrade/) identifies
database and upload backups; deployment-specific persistence still needs checking.

## Licensing and API boundaries

NodeBB declares GPL-3.0. Do not copy or translate its implementation, Harmony
templates, plugin code or bundled assets into an MIT-labelled implementation.
Independently implement documented behavior and data interoperability; retain
each third-party asset's actual license if later selected. Content ownership is
separate from software licensing. Seek appropriate review before distributing
derived code. No upstream code was copied into this repository in this lane.
[NodeBB license](https://github.com/NodeBB/NodeBB#license).

The [official API reference](https://docs.nodebb.org/api/) is useful for route
behavior, but public API responses omit private data and are not a backup.
The [database abstraction documentation](https://docs.nodebb.org/configuring/databases/)
does not promise a stable raw Redis schema. Pin conversion to observed 4.14.9
and fail explicitly for unrecognized source versions until tested.
