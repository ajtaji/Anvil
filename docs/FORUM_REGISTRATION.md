# Verified-first registration domain

Status: domain component and deterministic reference-store tests only. Not a
production authentication service, database, mailer or deployed forum.

## State and public contract

`ForumRegBegin(emailHandle, trustedOriginHandle)` creates only a pending email
challenge and sealed transactional mail outbox item. It accepts no password and
must not allocate a user/account ID, membership, profile or public-user entry.
Pending records belong to a separate namespace with bounded retention.

`ForumRegRedeem(tokenHandle, passwordHandle, trustedOriginHandle)` derives an
opaque password verifier using the injected KDF and attempts one atomic storage
operation. The transaction verifies the token digest, current challenge, issuance,
expiry, single-use state and email uniqueness, then consumes proof and creates
the verified account together. No intermediate account may be observable.

Results distinguish pending, verified, denied, unavailable, bad clock/input,
crypto failure and storage failure for trusted server diagnostics. Public replies
always acknowledge receipt without asserting that an account exists or was
created. UI wording: "If this request is eligible, follow the email instructions.
After verification, sign in." Never expose internal result codes, tokens,
addresses or password material in public messages. Uniform response text alone
does not prove resistance to timing, size or email-side enumeration.

## Injected dependencies

All named services must be supplied by trusted server composition before the
domain include. `ForumRegServicesReady()` must return exactly 1 only when all
required dependencies and their policies are operational. No default provider
silently substitutes weak random numbers, plaintext passwords or volatile users.

| Service | Required contract |
| --- | --- |
| ForumRegNow | Reliable nondecreasing server epoch; refuse unknown/rollback state. |
| ForumRegCanonicalEmail | Bounded validated canonical identity handle; provider-specific aliases must not be guessed. |
| ForumRegRandomToken | At least 256 bits from a cryptographic entropy source; 0 on failure. |
| ForumRegTokenDigest | Reviewed cryptographic token digest; opaque handle, 0 on failure. |
| ForumRegPasswordVerifier | Approved salted memory-hard password KDF with versioned parameters and bounded input; never plaintext storage. |
| ForumRegStoreChallenge | One transaction for pending challenge and sealed mail outbox. Enforce canonical-identity uniqueness, existing-account suppression, 60-second resend cooldown, five identity requests and twenty trusted-origin requests per 3600-second window; bounded global capacity. Suppression cannot rotate or extend the current challenge. Return 1 queued, 0 suppressed, negative failure. |
| ForumRegAdmitRedeem | Rate/resource limit before expensive KDF, with trusted transport-derived origin. |
| ForumRegConsumeAndCreate | Atomic proof-consume/account-insert transaction with unique canonical email. Require issued <= now < expiry, unused current proof, verifier record. Return 1 committed, 0 denied, negative failure. |
| ForumRegRelease | Destroy temporary owned handles and wipe secret storage where applicable. Caller owns input password/token handles and must release them too. |

The mail worker delivers from the transactional outbox with bounded retries;
failure never activates an account. Clear token material must not enter ordinary
logs or the pending table. Transport must supply HTTPS, CSRF protection, bounded
request parsing, secure sessions and replay-safe endpoint semantics. These are
not implemented by this domain file.

## Import and bypass policy

`ForumRegImportDisposition` classifies trusted importer results; it is not a
public endpoint or an authorization check on arbitrary client booleans. Verified
imports require authenticated snapshot provenance and source-version-specific
email-verification metadata tied to the canonical email. A nonempty address,
administrator status, social-provider label or existing UID is not proof.
Unknown/unverified records retain legacy IDs and content in quarantine, outside
active user/login/member indexes. Nothing deletes existing source users.
Duplicate identity conflicts stop for reconciliation; importing must never
overwrite another verified identity. Every account-creation route, including
administrative and social routes, must use equivalent proof requirements.

## Evidence and remaining acceptance

`Anvil/Applications/Forum/Tests/registration_reference_test.pb` includes the real
domain and explicit fake crypto handles/reference storage. Host tests cover no
account before proof, unavailable services, invalid clock, crypto/storage failure,
resend suppression and rotation, wrong/expired/replayed tokens, existing email,
identity/origin limits, pre-KDF throttling, uniform replies and import disposition.
Two serialized contenders produce one account. This is NOT proof of concurrent
database safety: the real storage adapter still owes competing-thread/process
redemption, rollback, crash/restart, uniqueness and durable mail-outbox tests.
The reference store models one canonical identity, not a complete account database.
Rate-limit threshold and cooldown checks do not prove the 3600-second window
rollover/reset behavior; that remains a real-provider acceptance requirement.
The host reference run passed 49 checks. The separate fail-closed binding fixture
also compiled through the unified IDE's headless entry and executed 198 emitted
AArch64 instructions, returning success with both registration operations refused
while dependencies were unavailable. No Anvil monitor image was built.

The native reference-state gate passed 14 witnesses over 3438 emitted AArch64
instructions: no account before any proof, pending without an account, incorrect
proof rejection, one verified commit, replay rejection and exact-expiry rejection.
Its deterministic service handles and serialized store are explicitly fixtures,
not production entropy, password hashing, transport or concurrent persistence.

## Reproduce locally

From the repository root, replace the compiler placeholders with local installed
compiler paths. Put host artifacts in a local scratch directory, not a release.

```text
python tools/forum_registration_check.py --compiler PUREMETAL_FORGE_EXECUTABLE
PUREBASIC_COMPILER Anvil/Applications/Forum/Tests/registration_reference_test.pb /CONSOLE /EXE SCRATCH_DIRECTORY/registration_reference_test.exe
SCRATCH_DIRECTORY/registration_reference_test.exe
```

The second command is the Windows PureBasic host-test build; it is not the
PureMetal production build. The Python runner uses the unified IDE application's
`--compile` entry, creates disposable fixture artifacts and removes them afterward.
