; ======================================================================
;  tls13_hs.pi4 - the TLS 1.3 CLIENT: key schedule, transcript and
;                 handshake state machine (RFC 8446), ON THE RASPBERRY
;                 PI 4 (BCM2711, AArch64)
; ======================================================================
;
;  Ported from RP2350/Lib/tls13_hs.pico2 (own-written against RFC 8446
;  and gated against the RFC 8448 section 3 trace; BearSSL has no TLS
;  1.3 to translate). The security posture, the state machine, the
;  refusal table and the public API are the Pico core's. Every place the
;  port had to differ is listed under "WHAT THE PORT CHANGED" below.
;
;  THE FULL ORDERED INCLUDE LIST the MAIN file must carry (a library
;  never includes a library). #X509_SIG_LINKED = 1 must be defined
;  BEFORE x509 so its stubs compile out and certificate signatures are
;  really checked:
;
;     #X509_SIG_LINKED = 1
;     XIncludeFile "Anvil/Core/sha256.pbi"
;     XIncludeFile "Anvil/Crypto/sha512.pbi"
;     XIncludeFile "RaspberryPi4/Lib/hmac.pi4"
;     XIncludeFile "RaspberryPi4/Lib/hkdf.pi4"
;     XIncludeFile "RaspberryPi4/Lib/entropy.pi4"
;     XIncludeFile "RaspberryPi4/Lib/drbg.pi4"
;     XIncludeFile "Anvil/Crypto/aes.pbi"
;     XIncludeFile "RaspberryPi4/Lib/gcm.pi4"
;     XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
;     XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
;     XIncludeFile "RaspberryPi4/Lib/x25519.pi4"
;     XIncludeFile "RaspberryPi4/Lib/ecp.pi4"
;     XIncludeFile "RaspberryPi4/Lib/ecdsa.pi4"
;     XIncludeFile "RaspberryPi4/Lib/rsa.pi4"
;     XIncludeFile "RaspberryPi4/Lib/t0vm.pi4"
;     XIncludeFile "RaspberryPi4/Lib/x509_blob.pi4"
;     XIncludeFile "RaspberryPi4/Lib/x509.pi4"
;     XIncludeFile "RaspberryPi4/Lib/tls13_record.pi4"
;     XIncludeFile "RaspberryPi4/Lib/tls13_hs.pi4"
;
;  entropy.pi4 is on the list because drbg.pi4 requires it (DrbgAutoSeed
;  reads the BCM2711 RNG200). Nothing in entropy.pi4 touches the hardware
;  unless DrbgAutoSeed/DrbgAutoReseed is called. Any file missing is a
;  loud compile-time undefined-procedure error naming the gap.
;
; ======================================================================
;  SECURITY POSTURE - read this before changing anything below.
; ----------------------------------------------------------------------
;  A VERIFY THAT CAN BE SKIPPED IS WORSE THAN NO TLS AT ALL, BECAUSE IT
;  LIES. Therefore:
;   * There is NO path where a bad certificate, a bad signature, a bad
;     Finished, an unsupported extension or an unknown message leaves
;     Tls13State reachable by Tls13Connected(). Every one of them sets
;     Tls13State = #TLS13_ST_FAILED, and FAILED is terminal until a fresh
;     Tls13Init.
;   * Every refusal has a NAME (#TLS13_REFUSE_*) and an alert to send.
;   * The default is CLOSED: unrecognised, unoffered or out-of-scope
;     extensions, schemes and features all refuse.
;   * Tls13Init REFUSES WITHOUT A CLOCK and REFUSES WITHOUT A TRUST
;     ANCHOR.
;
;  SCOPE. TLS_AES_128_GCM_SHA256 only; key exchange x25519 (default) or
;  secp256r1; CertificateVerify ecdsa_secp256r1_sha256,
;  ecdsa_secp384r1_sha384, ecdsa_secp521r1_sha512 (2026-10-14) or
;  rsa_pss_rsae_sha256 (rsa_pkcs1_sha256/384/512 are offered for
;  CERTIFICATE signatures only and refused in CertificateVerify). NOT implemented,
;  each refused by name: PSK / resumption, 0-RTT, HelloRetryRequest (so a
;  server that will not use x25519 or secp256r1 cannot be reached), client
;  certificates, a synthetic message_hash on the wire. A post-handshake
;  NewSessionTicket is counted in Tls13TicketsDiscarded and dropped - no
;  ticket is stored and no PSK is ever offered. KeyUpdate IS implemented.
;
; ======================================================================
;  THE PUBLIC API - and WHAT A CALLER MUST SUPPLY
; ----------------------------------------------------------------------
;    A TRUST ANCHOR, registered with x509 BEFORE Tls13Init:
;        X509ResetAnchors()
;        X509AddAnchorRSA(isCA, dnAddr, dnLen, nAddr, nLen, eAddr, eLen)
;        X509AddAnchorEC (isCA, dnAddr, dnLen, 23, qAddr, qLen)
;      dn is the DER of the anchor's subject Name (the whole SEQUENCE); n
;      and e are the big-endian RSA modulus and exponent; q is the 65-byte
;      uncompressed P-256 point. isCA = 1 for a root/intermediate CA that
;      signs the chain; isCA = 0 pins an end-entity key directly. x509
;      KEEPS THE ANCHOR BY ADDRESS - the bytes must outlive the connection.
;    A CLOCK: Tls13Init's unixTime, seconds since 1970, from a source the
;      board trusts (SNTP, the RTC). 0 or negative is refused.
;    A SEEDED DRBG: DrbgAutoSeed() (the RNG200) or DrbgInit(seed, len)
;      BEFORE Tls13NewKeyShare. An unseeded DRBG is refused by name.
;    TWO BUFFERS: Tls13SetHsBuffer(addr, size) (>= 512, sized for the
;      largest certificate chain to accept; required by Tls13Init) and
;      Tls13SetRecvBuffer(addr, size) (5 + 16640 for full RFC 8446
;      compliance; required by Tls13FeedBytes).
;    A TRANSPORT: this file never touches a socket. The caller sends the
;      records the Build procedures return and hands every received byte
;      to Tls13FeedBytes.
;
;    Tls13SetGroup(group) -> 1/0   #TLS_GROUP_X25519 or #TLS_GROUP_SECP256R1
;    Tls13Init(nameAddr, nameLen, unixTime) -> 1/0
;        nameLen < 0 means NO NAME CHECK - say so out loud if you use it.
;        Runs EcdsaInit/X25519Init, which move the program-wide Read
;        cursor - call it before any Restore/Read loop of your own.
;    Tls13NewKeyShare() -> 1/0     client random, session id and private
;                                  key from the DRBG, then the public share
;    Tls13DeriveKeySharePublic() -> 1/0
;    Tls13BuildClientHello(dst, dstmax) -> record length, or 0
;    Tls13FeedBytes(src, len) -> bytes consumed, or -1
;    Tls13FeedRecord(rec, reclen) -> 1/0
;    Tls13Connected() -> 1 once the handshake completed
;    Tls13BuildClientFinished(dst, dstmax) -> record length (call once,
;                                  when Tls13State = #TLS13_ST_SEND_FINISHED)
;    Tls13BuildAppRecord(dst, dstmax, payload, len) -> record length
;    Tls13BuildAlert(dst, dstmax, level, desc) -> record length
;    Tls13BuildKeyUpdate(dst, dstmax, requestPeerUpdate) -> record length
;    Tls13AppAddr / Tls13AppLen    plaintext of the last application record
;    Tls13State / Tls13Err / Tls13Alert / Tls13X509Err / Tls13PeerAlert
;    Tls13TicketsDiscarded / Tls13KeyUpdatePending
;
;  THE KEY SCHEDULE, THE TRANSCRIPT AND THE CERTIFICATEVERIFY CONTEXT are
;  exactly the Pico core's (RFC 8446 7.1, 4.4.1, 4.4.3): the "derived"
;  context is SHA-256("") computed at init, the running transcript lives
;  in a 104-byte sha256 snapshot (Anvil/Core/sha256.pbi keeps the same
;  104-byte layout), and the CertificateVerify digest is SHA-256 over 64
;  spaces, "TLS 1.3, server CertificateVerify", 0x00 and
;  Transcript-Hash(ClientHello..Certificate).
;
;  CONSTANT TIME, where there is a secret: secrets carry a sec prefix and
;  flow only through HKDF/HMAC/AES-GCM/X25519/P-256. The Finished compare
;  is hmac.pi4's CtEqual. Parsing is driven by public lengths only.
;
; ======================================================================
;  WHAT THE PORT CHANGED, AND WHY
; ======================================================================
;
;  1. RSA-PSS TAKES ITS KEY THROUGH RsaSetPubKey. The Pico call is the
;     nine-argument RsaPssVrfy(sig, slen, hash, 32, 32, n, nlen, e, elen).
;     This backend passes EIGHT arguments and refuses a ninth with a
;     frontend fatal error, so rsa.pi4 splits it: RsaSetPubKey(n, nlen,
;     e, elen) then RsaPssVrfy(sig, slen, hash, 32, 32). The
;     CertificateVerify handler installs the END-ENTITY key immediately
;     before the verify - x509's chain walk installs issuer keys through
;     the same RsaSetPubKey, so the key must be set here, never assumed.
;
;  2. THE DRBG VERDICT IS CHECKED. drbg.pi4's DrbgGenerate returns the
;     length, or #DRBG_ERR_UNSEEDED having written NOTHING. The Pico core
;     ignores the return, which on this library would send a ClientHello
;     whose random, session id and PRIVATE KEY are whatever the buffers
;     last held - zeros on a fresh boot: a key anyone can compute.
;     Tls13NewKeyShare now refuses with #TLS13_REFUSE_KEYGEN_FAILED unless
;     every draw returned its full length, and clears the share so
;     Tls13BuildClientHello refuses too.
;
;  3. THE KDF VERDICT IS CHECKED. hkdf.pi4's HkdfExpandLabel (and so
;     DeriveSecret) returns the length, or a negative #HKDF_ERR_* when
;     the HkdfLabel will not encode - a refusal the 32-bit copies do not
;     have. Every call here goes through TlsExpandLabel/TlsDeriveSecret,
;     which latch TlsKdfFault on any short answer; each state transition
;     that installed key material tests it and refuses with
;     #TLS13_REFUSE_KDF_FAILED (new, = 9) rather than run on an
;     unwritten secret. With the fixed labels in this file it cannot
;     fire; it is here so a future edit that breaks a label is loud.
;
;  4. #TLS13_MAX_SIG IS rsa.pi4's #RsaMaxBytes (512, RSA-4096), not the
;     Pico's 544, so a signature longer than this part's RSA can take is
;     refused as #TLS13_REFUSE_SIG_TOO_LONG - its real reason - instead of
;     surfacing as a bad signature.
;
;  5. THE P-256 REDRAW LOOP IS A While, not Repeat/Until, and refuses BY
;     NAME (#TLS13_REFUSE_KEYGEN_FAILED) after eight out-of-range draws,
;     where the Pico copy returned a bare 0.
;
;  6. ARRAY ADDRESSES ARE WRITTEN @Arr[0], the Pi 4 libraries' spelling.
;     The certificate tables TlsCertAddr/TlsCertLen stay `.i`: x509.pi4
;     walks them with an eight-byte cell stride and PeekI, and `.i` is
;     eight bytes here, so the contract holds by declaration.
;
;  7. Tls13Init no longer calls Sha256Begin() to "warm the K table":
;     Anvil/Core/sha256.pbi reaches its constants with ?Sha256KTable and
;     never moves the Read cursor, so there is nothing to warm.
;
;  NOTHING ELSE MOVED. No 32-bit word arithmetic lives in this file: every
;  value is a byte (PeekA & 255), a public length, a 16/24-bit wire field
;  built from bytes, or a small state/code number, so .i being 64 bits
;  changes no result. Right shifts here are only ever of non-negative
;  wire values.
;
;  PROOF STATUS - STATED PLAINLY. DESK-PROVEN ONLY. NOTHING IN THIS FILE
;  HAS RUN ON SILICON, AND NO HANDSHAKE WITH A LIVE SERVER HAS BEEN
;  ATTEMPTED FROM A PI 4. It builds for -t pi4 and passes
;  tools/tls13_rfc8448_check.py under the AArch64 model: the complete
;  RFC 8448 section 3 handshake replayed through this state machine with
;  every published secret, key, iv and record matched byte for byte, the
;  trace's real RSA-PSS CertificateVerify verified, and the refusal table
;  walked case by case. First green run 2026-10-14: 307 checks, 0 failed,
;  about 2.5 billion model instructions across 13 jobs (one X25519 is about
;  135 million of them; an RSA-2048 CertificateVerify plus its x509 walk
;  is under 50 million). --mutate: 18 of 18 mutants behave as expected
;  (17 killed, and the one control - gcm regressed to the 32-bit verdict
;  spelling with this record layer unchanged - stays green).
;  NOT proven anywhere on this part: a CA-signed
;  chain through this file (the trace's certificate is a directly
;  trusted self-signed leaf), the ECDSA branch of CertificateVerify, and
;  any real network transport. The DRBG must be seeded from the RNG200
;  (DrbgAutoSeed) before real use; the gate seeds it with fixed bytes on
;  purpose.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====

; ----------------------------------------------------------------------
;  Sizes. Both are hard refusal limits, never truncation points. The two
;  large buffers are NOT here - they belong to the caller (see the header).
; ----------------------------------------------------------------------
#TLS13_MAX_CERTS  = 6        ; certificates in a chain
#TLS13_MAX_SIG    = #RsaMaxBytes   ; largest signature rsa.pi4 accepts (512, RSA-4096)

; ----------------------------------------------------------------------
;  Protocol constants (RFC 8446 appendix B).
; ----------------------------------------------------------------------
#TLS13_VERSION         = $0304
#TLS13_LEGACY_VERSION  = $0303
#TLS13_SUITE_AES128GCM = $1301   ; TLS_AES_128_GCM_SHA256

#TLS_GROUP_SECP256R1 = $0017
#TLS_GROUP_X25519    = $001D

#TLS_SIG_ECDSA_P256_SHA256   = $0403
#TLS_SIG_ECDSA_P384_SHA384   = $0503
#TLS_SIG_ECDSA_P521_SHA512   = $0603
#TLS_SIG_RSA_PKCS1_SHA256    = $0401   ; certificates only - never in CV
#TLS_SIG_RSA_PKCS1_SHA384    = $0501   ; certificates only - never in CV
#TLS_SIG_RSA_PKCS1_SHA512    = $0601   ; certificates only - never in CV
#TLS_SIG_RSA_PSS_RSAE_SHA256 = $0804

#TLS_HS_CLIENT_HELLO         = 1
#TLS_HS_SERVER_HELLO         = 2
#TLS_HS_NEW_SESSION_TICKET   = 4
#TLS_HS_END_OF_EARLY_DATA    = 5
#TLS_HS_ENCRYPTED_EXTENSIONS = 8
#TLS_HS_CERTIFICATE          = 11
#TLS_HS_CERTIFICATE_REQUEST  = 13
#TLS_HS_CERTIFICATE_VERIFY   = 15
#TLS_HS_FINISHED             = 20
#TLS_HS_KEY_UPDATE           = 24
#TLS_HS_MESSAGE_HASH         = 254

#TLS_EXT_SERVER_NAME            = 0
#TLS_EXT_SUPPORTED_GROUPS       = 10
#TLS_EXT_SIGNATURE_ALGORITHMS   = 13
#TLS_EXT_ALPN                   = 16
#TLS_EXT_PRE_SHARED_KEY         = 41
#TLS_EXT_EARLY_DATA             = 42
#TLS_EXT_SUPPORTED_VERSIONS     = 43
#TLS_EXT_PSK_KEY_EXCHANGE_MODES = 45
#TLS_EXT_KEY_SHARE              = 51

; Alerts (RFC 8446 appendix B.2) - the ones this client can send.
#TLS_ALERT_LEVEL_WARNING  = 1
#TLS_ALERT_LEVEL_FATAL    = 2
#TLS_ALERT_CLOSE_NOTIFY          = 0
#TLS_ALERT_UNEXPECTED_MESSAGE    = 10
#TLS_ALERT_BAD_RECORD_MAC        = 20
#TLS_ALERT_RECORD_OVERFLOW       = 22
#TLS_ALERT_HANDSHAKE_FAILURE     = 40
#TLS_ALERT_BAD_CERTIFICATE       = 42
#TLS_ALERT_UNSUPPORTED_CERT      = 43
#TLS_ALERT_CERTIFICATE_EXPIRED   = 45
#TLS_ALERT_CERTIFICATE_UNKNOWN   = 46
#TLS_ALERT_ILLEGAL_PARAMETER     = 47
#TLS_ALERT_UNKNOWN_CA            = 48
#TLS_ALERT_DECODE_ERROR          = 50
#TLS_ALERT_DECRYPT_ERROR         = 51
#TLS_ALERT_PROTOCOL_VERSION      = 70
#TLS_ALERT_INTERNAL_ERROR        = 80
#TLS_ALERT_INSUFFICIENT_SECURITY = 71
#TLS_ALERT_MISSING_EXTENSION     = 109
#TLS_ALERT_UNSUPPORTED_EXTENSION = 110

; ----------------------------------------------------------------------
;  States. There is no path from FAILED to anywhere.
; ----------------------------------------------------------------------
#TLS13_ST_IDLE          = 0    ; before Tls13Init
#TLS13_ST_START         = 1    ; initialised, ClientHello not yet built
#TLS13_ST_WAIT_SH       = 2
#TLS13_ST_WAIT_EE       = 3
#TLS13_ST_WAIT_CERT     = 4
#TLS13_ST_WAIT_CV       = 5
#TLS13_ST_WAIT_FINISHED = 6
#TLS13_ST_SEND_FINISHED = 7    ; server flight verified; send ours
#TLS13_ST_CONNECTED     = 8
#TLS13_ST_CLOSED        = 9    ; peer sent close_notify
#TLS13_ST_FAILED        = 10   ; terminal; Tls13Err names why

; ----------------------------------------------------------------------
;  THE REFUSAL TABLE. Every way this client can refuse a handshake, with
;  a name. Nothing below returns a generic failure.
; ----------------------------------------------------------------------
#TLS13_OK                                = 0
; --- setup and caller misuse ---
#TLS13_REFUSE_NO_TIME                    = 1
#TLS13_REFUSE_NO_ANCHORS                 = 2
#TLS13_REFUSE_BAD_GROUP                  = 3
#TLS13_REFUSE_BUF_TOO_SMALL              = 4
#TLS13_REFUSE_WRONG_STATE                = 5
#TLS13_REFUSE_NO_RECV_BUFFER             = 6
#TLS13_REFUSE_KEYGEN_FAILED              = 7
#TLS13_REFUSE_NO_HS_BUFFER               = 8
#TLS13_REFUSE_KDF_FAILED                 = 9    ; hkdf refused a label (Pi 4)
; --- record layer ---
#TLS13_REFUSE_RECORD_TOO_LONG            = 10
#TLS13_REFUSE_RECORD_SHORT               = 11
#TLS13_REFUSE_BAD_RECORD_MAC             = 12
#TLS13_REFUSE_ALL_ZERO_INNER             = 13
#TLS13_REFUSE_SEQ_OVERFLOW               = 14
#TLS13_REFUSE_PLAINTEXT_AFTER_KEYS       = 15
#TLS13_REFUSE_UNEXPECTED_CCS             = 16
#TLS13_REFUSE_BAD_CCS_VALUE              = 17
#TLS13_REFUSE_UNKNOWN_CONTENT_TYPE       = 18
#TLS13_REFUSE_RECORD_LEN_MISMATCH        = 19
; --- handshake framing ---
#TLS13_REFUSE_HS_MSG_TOO_LONG            = 20
#TLS13_REFUSE_HS_TRUNCATED               = 21
#TLS13_REFUSE_UNEXPECTED_MESSAGE         = 22
#TLS13_REFUSE_TRAILING_DATA              = 23
#TLS13_REFUSE_EMPTY_HANDSHAKE_RECORD     = 24
#TLS13_REFUSE_MESSAGE_HASH_SYNTHETIC     = 25
#TLS13_REFUSE_COOPERATIVE_STOP           = 26
#TLS13_REFUSE_TRANSCRIPT_INPUT           = 27
; --- ServerHello ---
#TLS13_REFUSE_SH_LEGACY_VERSION          = 30
#TLS13_REFUSE_HELLO_RETRY_REQUEST        = 31
#TLS13_REFUSE_DOWNGRADE_SENTINEL         = 32
#TLS13_REFUSE_SESSION_ID_ECHO            = 33
#TLS13_REFUSE_CIPHER_SUITE               = 34
#TLS13_REFUSE_COMPRESSION_METHOD         = 35
#TLS13_REFUSE_NO_SUPPORTED_VERSIONS      = 36
#TLS13_REFUSE_NOT_TLS13                  = 37
#TLS13_REFUSE_NO_KEY_SHARE               = 38
#TLS13_REFUSE_KEY_SHARE_GROUP            = 39
#TLS13_REFUSE_KEY_SHARE_LENGTH           = 40
#TLS13_REFUSE_PSK_OFFERED                = 41
#TLS13_REFUSE_SH_UNKNOWN_EXTENSION       = 42
#TLS13_REFUSE_ECDHE_FAILED               = 43
; --- EncryptedExtensions ---
#TLS13_REFUSE_EARLY_DATA_ACCEPTED        = 50
#TLS13_REFUSE_UNOFFERED_EXTENSION        = 51
#TLS13_REFUSE_EXT_NOT_ALLOWED_HERE       = 52
#TLS13_REFUSE_PSK_KEY_EXCHANGE_MODES     = 53
#TLS13_REFUSE_ALPN_FORMAT                = 54
#TLS13_REFUSE_ALPN_SELECTION             = 55
#TLS13_REFUSE_ALPN_DUPLICATE             = 56
#TLS13_REFUSE_QUIC_CONFIG                = 57
#TLS13_REFUSE_QUIC_PARAMETERS            = 58
#TLS13_REFUSE_QUIC_LEVEL                 = 59
#TLS13_QUIC_CONFIG_SIZE                  = 48
#TLS_EXT_QUIC_PARAMETERS                 = 57
; --- Certificate ---
#TLS13_REFUSE_CERT_CONTEXT_NOT_EMPTY     = 60
#TLS13_REFUSE_EMPTY_CERT_LIST            = 61
#TLS13_REFUSE_TOO_MANY_CERTS             = 62
#TLS13_REFUSE_CERT_EXTENSION_UNSOLICITED = 63
#TLS13_REFUSE_CHAIN_INVALID              = 64   ; see Tls13X509Err
#TLS13_REFUSE_NO_EE_KEY                  = 65
; --- CertificateVerify ---
#TLS13_REFUSE_SIGALG_NOT_OFFERED         = 70
#TLS13_REFUSE_SIGALG_PKCS1_IN_CV         = 71
#TLS13_REFUSE_SIGALG_KEY_MISMATCH        = 72
#TLS13_REFUSE_SIGNATURE_INVALID          = 73
#TLS13_REFUSE_SIG_TOO_LONG               = 74
; --- Finished ---
#TLS13_REFUSE_FINISHED_LENGTH            = 80
#TLS13_REFUSE_FINISHED_MISMATCH          = 81
; --- out of scope, refused by name ---
#TLS13_REFUSE_CLIENT_AUTH_REQUESTED      = 90
#TLS13_REFUSE_END_OF_EARLY_DATA          = 91
#TLS13_REFUSE_KEY_UPDATE_BAD_REQUEST     = 92
#TLS13_REFUSE_KEY_UPDATE_LENGTH          = 93
#TLS13_REFUSE_POST_HS_UNKNOWN            = 94
#TLS13_REFUSE_PEER_ALERT                 = 95
#TLS13_REFUSE_ALERT_LENGTH               = 96

; ----------------------------------------------------------------------
;  STATE. Secret-carrying buffers carry a sec prefix so a reviewer can
;  grep the taint; everything else here is public wire data.
; ----------------------------------------------------------------------
Global Tls13State.i
Global Tls13Err.i                    ; a #TLS13_REFUSE_* name
Global Tls13Alert.i                  ; the alert that refusal would send
Global Tls13X509Err.i                ; the x509 verdict, on a chain refusal
Global Tls13PeerAlert.i              ; the description the peer sent
Global Tls13TicketsDiscarded.i
Global Tls13KeyUpdatePending.i
Global Tls13AppAddr.i
Global Tls13AppLen.i

Global TlsGroup.i                    ; the group offered in key_share
Global TlsUnixTime.i
Global TlsNameAddr.i
Global TlsNameLen.i

; --- key schedule (all secret) ---
Global Dim secTlsEarly.a[32]
Global Dim secTlsDerived.a[32]
Global Dim secTlsHsSec.a[32]
Global Dim secTlsMaster.a[32]
Global Dim secTlsCHs.a[32]           ; client_handshake_traffic_secret
Global Dim secTlsSHs.a[32]           ; server_handshake_traffic_secret
Global Dim secTlsCAp.a[32]           ; client_application_traffic_secret_N
Global Dim secTlsSAp.a[32]           ; server_application_traffic_secret_N
Global Dim secTlsEcdhe.a[32]         ; the (EC)DHE shared secret
Global Dim secTlsPriv.a[32]          ; our ephemeral private key
Global Dim secTlsFinKey.a[32]        ; a Finished key, transiently
Global Dim secTlsKeyBuf.a[16]        ; a traffic key, transiently
Global Dim secTlsIvBuf.a[12]         ; a traffic iv, transiently
Global Dim secTlsZeros.a[32]         ; 32 zero bytes: the absent PSK

; --- our ClientHello, as sent ---
Global Dim TlsClientRandom.a[32]
Global Dim TlsSessionId.a[32]
Global TlsSessionIdLen.i
Global Dim TlsKeyShare.a[65]         ; our public share (32 or 65 bytes)
Global TlsKeyShareLen.i
Global Dim TlsPeerShare.a[65]        ; the server's share, as received
Global TlsPeerShareLen.i

; --- the extensions we offered, for the RFC 8446 4.2 "did I ask for
;     this?" test on every server extension ---
#TLS13_MAX_OFFERED = 8
Global Dim TlsOfferedExt.i[#TLS13_MAX_OFFERED]
Global TlsOfferedCount.i

; --- transcript ---
Global Dim TlsTrSnap.a[104]          ; the running transcript hash state
Global Dim TlsThBuf.a[32]            ; a computed transcript hash
Global Dim TlsThCert.a[32]           ; Transcript-Hash(CH..Certificate)
Global Dim TlsThSf.a[32]             ; Transcript-Hash(CH..server Finished)
Global Dim TlsEmptyHash.a[32]        ; SHA-256("") - the "derived" context

; --- handshake reassembly, in the CALLER's buffer ---
Global TlsHsAddr.i
Global TlsHsSize.i
Global TlsHsLen.i

; --- receive framing, on the CALLER's buffer ---
Global TlsRecvAddr.i
Global TlsRecvSize.i
Global TlsRecvLen.i

; --- certificate chain, pointing into the handshake buffer ---
Global Dim TlsCertAddr.i[#TLS13_MAX_CERTS]
Global Dim TlsCertLen.i[#TLS13_MAX_CERTS]
Global TlsCertCount.i

; --- scratch ---
Global Dim TlsScratch.a[72]          ; basepoint / P-256 point / small message work
Global Dim TlsMsgHash.a[64]          ; the CertificateVerify message hash
                                     ; (32, 48 or 64 bytes by scheme)
Global Dim TlsVerifyData.a[32]
Global Dim TlsHrrRandom.a[32]        ; the RFC 8446 4.1.3 HRR sentinel
Global Dim TlsP256Order.a[32]        ; the P-256 group order n
Global Dim TlsLbl.a[80]              ; the HKDF label texts, back to back
Global Dim TlsCvCtx.a[98]            ; 64 spaces + the context string + NUL
Global TlsLabelsReady.i
Global TlsKdfFault.i                 ; 1 once an hkdf call came back short
Global TlsAlpnOfferLen.i
Global TlsAlpnSelectedLen.i
; Caller-owned configuration: offer ptr/bytes, receive ptr/capacity, received
; bytes, received flag (six native integers). Lifetime spans the connection.
Global TlsQuicConfig.i
Global Dim TlsAlpnOffer.a[256]
Global Dim TlsAlpnSelected.a[256]
; label offsets inside TlsLbl
#TLS_L_DERIVED   = 0            ; "derived"
#TLS_L_DERIVED_N = 7
#TLS_L_CHS       = 7            ; "c hs traffic"
#TLS_L_CHS_N     = 12
#TLS_L_SHS       = 19           ; "s hs traffic"
#TLS_L_SHS_N     = 12
#TLS_L_CAP       = 31           ; "c ap traffic"
#TLS_L_CAP_N     = 12
#TLS_L_SAP       = 43           ; "s ap traffic"
#TLS_L_SAP_N     = 12
#TLS_L_KEY       = 55           ; "key"
#TLS_L_KEY_N     = 3
#TLS_L_IV        = 58           ; "iv"
#TLS_L_IV_N      = 2
#TLS_L_FIN       = 60           ; "finished"
#TLS_L_FIN_N     = 8
#TLS_L_UPD       = 68           ; "traffic upd"
#TLS_L_UPD_N     = 11

; ----------------------------------------------------------------------
;  TlsFail(err, alert) - the ONE way this file refuses. It is terminal:
;  Tls13State becomes FAILED and nothing moves it again short of a fresh
;  Tls13Init. Returns 0 so callers can write "ProcedureReturn TlsFail(..)".
; ----------------------------------------------------------------------
Procedure.i TlsFail(err.i, alert.i)
  If Tls13Err = #TLS13_OK
    Tls13Err = err
    Tls13Alert = alert
  EndIf
  Tls13State = #TLS13_ST_FAILED
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  Big-endian readers and writers. Every length on the wire is public.
; ----------------------------------------------------------------------
Procedure.i TlsRd8(p.i)
  ProcedureReturn PeekA(p) & 255
EndProcedure

; Returns the 16-bit value at p, most significant byte first.
Procedure.i TlsRd16(p.i)
  ProcedureReturn ((PeekA(p) & 255) << 8) | (PeekA(p + 1) & 255)
EndProcedure

; Returns the 24-bit value at p, most significant byte first.
Procedure.i TlsRd24(p.i)
  ProcedureReturn ((PeekA(p) & 255) << 16) | ((PeekA(p + 1) & 255) << 8) | (PeekA(p + 2) & 255)
EndProcedure

; Stores the low byte of v at p.
Procedure TlsWr8(p.i, v.i)
  PokeB(p, v & 255)
EndProcedure

; Stores the low 16 bits of v at p, most significant byte first.
Procedure TlsWr16(p.i, v.i)
  PokeB(p,     (v >> 8) & 255)
  PokeB(p + 1, v & 255)
EndProcedure

; Stores the low 24 bits of v at p, most significant byte first.
Procedure TlsWr24(p.i, v.i)
  PokeB(p,     (v >> 16) & 255)
  PokeB(p + 1, (v >> 8) & 255)
  PokeB(p + 2, v & 255)
EndProcedure

; Copies n bytes from src to dst, lowest address first.
Procedure TlsCopy(dst.i, src.i, n.i)
  Protected i.i
  i = 0
  While i < n
    PokeB(dst + i, PeekA(src + i) & 255)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  TlsInitTables() - the HKDF label texts, the CertificateVerify context,
;  the HelloRetryRequest sentinel random and the P-256 group order.
;
;  Written as direct assignments rather than a DataSection ON PURPOSE:
;  Restore/Read walk one PROGRAM-WIDE cursor, and a library that quietly
;  moved it would break any caller in the middle of its own read loop.
;  The ASCII is in the comment beside each row.
; ----------------------------------------------------------------------
Procedure TlsInitTables()
  Protected i.i
  If TlsLabelsReady <> 0
    ProcedureReturn
  EndIf

  ; "derived"
  TlsLbl[0] = $64 : TlsLbl[1] = $65 : TlsLbl[2] = $72 : TlsLbl[3] = $69
  TlsLbl[4] = $76 : TlsLbl[5] = $65 : TlsLbl[6] = $64
  ; "c hs traffic"
  TlsLbl[7] = $63 : TlsLbl[8] = $20 : TlsLbl[9] = $68 : TlsLbl[10] = $73
  TlsLbl[11] = $20 : TlsLbl[12] = $74 : TlsLbl[13] = $72 : TlsLbl[14] = $61
  TlsLbl[15] = $66 : TlsLbl[16] = $66 : TlsLbl[17] = $69 : TlsLbl[18] = $63
  ; "s hs traffic"
  TlsLbl[19] = $73 : TlsLbl[20] = $20 : TlsLbl[21] = $68 : TlsLbl[22] = $73
  TlsLbl[23] = $20 : TlsLbl[24] = $74 : TlsLbl[25] = $72 : TlsLbl[26] = $61
  TlsLbl[27] = $66 : TlsLbl[28] = $66 : TlsLbl[29] = $69 : TlsLbl[30] = $63
  ; "c ap traffic"
  TlsLbl[31] = $63 : TlsLbl[32] = $20 : TlsLbl[33] = $61 : TlsLbl[34] = $70
  TlsLbl[35] = $20 : TlsLbl[36] = $74 : TlsLbl[37] = $72 : TlsLbl[38] = $61
  TlsLbl[39] = $66 : TlsLbl[40] = $66 : TlsLbl[41] = $69 : TlsLbl[42] = $63
  ; "s ap traffic"
  TlsLbl[43] = $73 : TlsLbl[44] = $20 : TlsLbl[45] = $61 : TlsLbl[46] = $70
  TlsLbl[47] = $20 : TlsLbl[48] = $74 : TlsLbl[49] = $72 : TlsLbl[50] = $61
  TlsLbl[51] = $66 : TlsLbl[52] = $66 : TlsLbl[53] = $69 : TlsLbl[54] = $63
  ; "key"
  TlsLbl[55] = $6B : TlsLbl[56] = $65 : TlsLbl[57] = $79
  ; "iv"
  TlsLbl[58] = $69 : TlsLbl[59] = $76
  ; "finished"
  TlsLbl[60] = $66 : TlsLbl[61] = $69 : TlsLbl[62] = $6E : TlsLbl[63] = $69
  TlsLbl[64] = $73 : TlsLbl[65] = $68 : TlsLbl[66] = $65 : TlsLbl[67] = $64
  ; "traffic upd"
  TlsLbl[68] = $74 : TlsLbl[69] = $72 : TlsLbl[70] = $61 : TlsLbl[71] = $66
  TlsLbl[72] = $66 : TlsLbl[73] = $69 : TlsLbl[74] = $63 : TlsLbl[75] = $20
  TlsLbl[76] = $75 : TlsLbl[77] = $70 : TlsLbl[78] = $64

  ; RFC 8446 4.4.3: sixty-four spaces, then the context string, then 0x00
  i = 0
  While i < 64
    TlsCvCtx[i] = $20
    i = i + 1
  Wend
  ; "TLS 1.3, server CertificateVerify"
  TlsCvCtx[64] = $54 : TlsCvCtx[65] = $4C : TlsCvCtx[66] = $53 : TlsCvCtx[67] = $20
  TlsCvCtx[68] = $31 : TlsCvCtx[69] = $2E : TlsCvCtx[70] = $33 : TlsCvCtx[71] = $2C
  TlsCvCtx[72] = $20 : TlsCvCtx[73] = $73 : TlsCvCtx[74] = $65 : TlsCvCtx[75] = $72
  TlsCvCtx[76] = $76 : TlsCvCtx[77] = $65 : TlsCvCtx[78] = $72 : TlsCvCtx[79] = $20
  TlsCvCtx[80] = $43 : TlsCvCtx[81] = $65 : TlsCvCtx[82] = $72 : TlsCvCtx[83] = $74
  TlsCvCtx[84] = $69 : TlsCvCtx[85] = $66 : TlsCvCtx[86] = $69 : TlsCvCtx[87] = $63
  TlsCvCtx[88] = $61 : TlsCvCtx[89] = $74 : TlsCvCtx[90] = $65 : TlsCvCtx[91] = $56
  TlsCvCtx[92] = $65 : TlsCvCtx[93] = $72 : TlsCvCtx[94] = $69 : TlsCvCtx[95] = $66
  TlsCvCtx[96] = $79
  TlsCvCtx[97] = $00                   ; the separator

  ; RFC 8446 4.1.3 HelloRetryRequest sentinel Random
  TlsHrrRandom[0] = $CF : TlsHrrRandom[1] = $21 : TlsHrrRandom[2] = $AD : TlsHrrRandom[3] = $74
  TlsHrrRandom[4] = $E5 : TlsHrrRandom[5] = $9A : TlsHrrRandom[6] = $61 : TlsHrrRandom[7] = $11
  TlsHrrRandom[8] = $BE : TlsHrrRandom[9] = $1D : TlsHrrRandom[10] = $8C : TlsHrrRandom[11] = $02
  TlsHrrRandom[12] = $1E : TlsHrrRandom[13] = $65 : TlsHrrRandom[14] = $B8 : TlsHrrRandom[15] = $91
  TlsHrrRandom[16] = $C2 : TlsHrrRandom[17] = $A2 : TlsHrrRandom[18] = $11 : TlsHrrRandom[19] = $16
  TlsHrrRandom[20] = $7A : TlsHrrRandom[21] = $BB : TlsHrrRandom[22] = $8C : TlsHrrRandom[23] = $5E
  TlsHrrRandom[24] = $07 : TlsHrrRandom[25] = $9E : TlsHrrRandom[26] = $09 : TlsHrrRandom[27] = $E2
  TlsHrrRandom[28] = $C8 : TlsHrrRandom[29] = $A8 : TlsHrrRandom[30] = $33 : TlsHrrRandom[31] = $9C

  ; the secp256r1 group order n, big-endian - the private scalar must be
  ; in [1, n-1], and a draw outside it is redrawn rather than reduced
  TlsP256Order[0] = $FF : TlsP256Order[1] = $FF : TlsP256Order[2] = $FF : TlsP256Order[3] = $FF
  TlsP256Order[4] = $00 : TlsP256Order[5] = $00 : TlsP256Order[6] = $00 : TlsP256Order[7] = $00
  TlsP256Order[8] = $FF : TlsP256Order[9] = $FF : TlsP256Order[10] = $FF : TlsP256Order[11] = $FF
  TlsP256Order[12] = $FF : TlsP256Order[13] = $FF : TlsP256Order[14] = $FF : TlsP256Order[15] = $FF
  TlsP256Order[16] = $BC : TlsP256Order[17] = $E6 : TlsP256Order[18] = $FA : TlsP256Order[19] = $AD
  TlsP256Order[20] = $A7 : TlsP256Order[21] = $17 : TlsP256Order[22] = $9E : TlsP256Order[23] = $84
  TlsP256Order[24] = $F3 : TlsP256Order[25] = $B9 : TlsP256Order[26] = $CA : TlsP256Order[27] = $C2
  TlsP256Order[28] = $FC : TlsP256Order[29] = $63 : TlsP256Order[30] = $25 : TlsP256Order[31] = $51

  i = 0
  While i < 32
    secTlsZeros[i] = 0
    i = i + 1
  Wend

  TlsLabelsReady = 1
EndProcedure

; ======================================================================
;  THE TRANSCRIPT HASH
;
;  hkdf, hmac, x509 and the CertificateVerify context all drive the ONE
;  global SHA-256 context, so the running transcript cannot simply live
;  in it. It lives as a 104-byte snapshot and every operation is
;  Restore -> work -> Snapshot. Sha256End runs on a copy of the state, so
;  taking a hash does not disturb the running transcript.
; ======================================================================
Procedure Tls13TranscriptReset()
  Sha256Begin()
  Sha256Snapshot(@TlsTrSnap[0])
EndProcedure

; Adds len bytes at addr to the running hash of the handshake messages.
Procedure Tls13TranscriptAbsorb(addr.i, len.i)
  Sha256Restore(@TlsTrSnap[0])
  Sha256Update(addr, len)
  Sha256Snapshot(@TlsTrSnap[0])
EndProcedure

; Optional scheduler seam. A paused chunk owns no live SHA context: each
; chunk restores and snapshots the connection's transcript before yielding.
Global *Tls13PauseHook
Procedure.i Tls13TranscriptAppend(addr.i,bytes.i)
  Define off.i,n.i
  If Tls13State=#TLS13_ST_FAILED : ProcedureReturn 0 : EndIf
  If bytes<0 Or (bytes>0 And addr=0)
    ProcedureReturn TlsFail(#TLS13_REFUSE_TRANSCRIPT_INPUT,#TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If Tls13PauseHook=0
    Tls13TranscriptAbsorb(addr,bytes) : ProcedureReturn 1
  EndIf
  off=0
  While off<bytes
    If Tls13PauseHook<>0
      If Tls13PauseHook()=0 : ProcedureReturn TlsFail(#TLS13_REFUSE_COOPERATIVE_STOP,#TLS_ALERT_INTERNAL_ERROR) : EndIf
    EndIf
    n=bytes-off : If n>512 : n=512 : EndIf
    Sha256Restore(@TlsTrSnap[0])
    Sha256Update(addr+off,n)
    Sha256Snapshot(@TlsTrSnap[0])
    off=off+n
  Wend
  If Tls13PauseHook<>0
    If Tls13PauseHook()=0 : ProcedureReturn TlsFail(#TLS13_REFUSE_COOPERATIVE_STOP,#TLS_ALERT_INTERNAL_ERROR) : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

; Writes the hash of the handshake messages so far (32 bytes) to dst; the
; running hash carries on unchanged.
Procedure Tls13TranscriptHash(dst.i)
  Sha256Restore(@TlsTrSnap[0])
  Sha256End(dst)
EndProcedure

; ======================================================================
;  THE KEY SCHEDULE (RFC 8446 7.1)
; ======================================================================

; ----------------------------------------------------------------------
;  TlsExpandLabel / TlsDeriveSecret - hkdf.pi4's HkdfExpandLabel and
;  DeriveSecret with their verdict kept. Each returns the byte count, or
;  a negative #HKDF_ERR_* having written nothing; anything but the full
;  length latches TlsKdfFault, which every state transition that
;  installs key material tests (port change 3 in the header).
; ----------------------------------------------------------------------
Procedure TlsExpandLabel(secret.i, label.i, labellen.i, context.i, ctxlen.i, dst.i, outlen.i)
  If HkdfExpandLabel(secret, 32, label, labellen, context, ctxlen, dst, outlen) <> outlen
    TlsKdfFault = 1
  EndIf
EndProcedure

; Derive-Secret(secret, label, transcript hash) into 32 bytes at dst, with
; the hkdf verdict latched in TlsKdfFault.
Procedure TlsDeriveSecret(secret.i, label.i, labellen.i, thash.i, dst.i)
  If DeriveSecret(secret, 32, label, labellen, thash, 32, dst) <> 32
    TlsKdfFault = 1
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  TlsKeyIvFrom(secret, keyDst, ivDst) - RFC 8446 7.3 traffic key
;  calculation: key = HKDF-Expand-Label(secret, "key", "", 16) and
;  iv = HKDF-Expand-Label(secret, "iv", "", 12).
; ----------------------------------------------------------------------
Procedure TlsKeyIvFrom(secret.i, keyDst.i, ivDst.i)
  TlsExpandLabel(secret, @TlsLbl[#TLS_L_KEY], #TLS_L_KEY_N, 0, 0, keyDst, 16)
  TlsExpandLabel(secret, @TlsLbl[#TLS_L_IV], #TLS_L_IV_N, 0, 0, ivDst, 12)
EndProcedure

; ----------------------------------------------------------------------
;  TlsScheduleEarly() - the top of the schedule, which needs no inputs at
;  all in a full handshake: the PSK is 32 zero bytes and the salt is
;  absent, so the early secret is a constant. Then the first "derived"
;  step, whose context is SHA-256("") - NOT an empty context.
; ----------------------------------------------------------------------
Procedure TlsScheduleEarly()
  HkdfExtract(0, 0, @secTlsZeros[0], 32, @secTlsEarly[0])
  TlsDeriveSecret(@secTlsEarly[0], @TlsLbl[#TLS_L_DERIVED], #TLS_L_DERIVED_N, @TlsEmptyHash[0], @secTlsDerived[0])
EndProcedure

; ----------------------------------------------------------------------
;  TlsScheduleHandshake(th) - the handshake secret from the (EC)DHE
;  shared secret, then the two handshake traffic secrets over the
;  transcript through ServerHello, then the SECOND "derived" step and the
;  master secret (which needs no more transcript, so it is computed here
;  and used later with a different transcript hash).
; ----------------------------------------------------------------------
Procedure TlsScheduleHandshake(th.i)
  HkdfExtract(@secTlsDerived[0], 32, @secTlsEcdhe[0], 32, @secTlsHsSec[0])
  TlsDeriveSecret(@secTlsHsSec[0], @TlsLbl[#TLS_L_CHS], #TLS_L_CHS_N, th, @secTlsCHs[0])
  TlsDeriveSecret(@secTlsHsSec[0], @TlsLbl[#TLS_L_SHS], #TLS_L_SHS_N, th, @secTlsSHs[0])
  TlsDeriveSecret(@secTlsHsSec[0], @TlsLbl[#TLS_L_DERIVED], #TLS_L_DERIVED_N, @TlsEmptyHash[0], @secTlsDerived[0])
  HkdfExtract(@secTlsDerived[0], 32, @secTlsZeros[0], 32, @secTlsMaster[0])
EndProcedure

; ----------------------------------------------------------------------
;  TlsScheduleApplication(th) - the two application traffic secrets, over
;  the transcript through the SERVER's Finished (not the client's).
; ----------------------------------------------------------------------
Procedure TlsScheduleApplication(th.i)
  TlsDeriveSecret(@secTlsMaster[0], @TlsLbl[#TLS_L_CAP], #TLS_L_CAP_N, th, @secTlsCAp[0])
  TlsDeriveSecret(@secTlsMaster[0], @TlsLbl[#TLS_L_SAP], #TLS_L_SAP_N, th, @secTlsSAp[0])
EndProcedure

; ----------------------------------------------------------------------
;  TlsFinishedVerify(secret, th, dst) - RFC 8446 4.4.4:
;      finished_key = HKDF-Expand-Label(secret, "finished", "", 32)
;      verify_data  = HMAC(finished_key, Transcript-Hash(...))
; ----------------------------------------------------------------------
Procedure TlsFinishedVerify(secret.i, th.i, dst.i)
  TlsExpandLabel(secret, @TlsLbl[#TLS_L_FIN], #TLS_L_FIN_N, 0, 0, @secTlsFinKey[0], 32)
  HmacOf(@secTlsFinKey[0], 32, th, 32, dst)
EndProcedure

; ======================================================================
;  KEY EXCHANGE
; ======================================================================

; ----------------------------------------------------------------------
;  TlsAllZero(p, n) - is this buffer entirely zero? Used for the RFC 8446
;  7.4.2 / RFC 7748 6.1 check that an X25519 shared secret is not the
;  all-zero value, which is what a small-order peer point produces. The
;  scan is over a SECRET, so it accumulates with OR and tests once rather
;  than branching per byte.
; ----------------------------------------------------------------------
Procedure.i TlsAllZero(p.i, n.i)
  Protected i.i
  Protected acc.i
  acc = 0
  i = 0
  While i < n
    acc = acc | (PeekA(p + i) & 255)
    i = i + 1
  Wend
  If acc = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  TlsScalarBelowOrder() - is secTlsPriv, read big-endian, in [1, n-1]
;  for P-256? A draw outside that range is REDRAWN, never reduced:
;  reducing biases the private key, and bias in an ECDH private key is
;  the shape that has broken real deployments.
; ----------------------------------------------------------------------
Procedure.i TlsScalarBelowOrder()
  Protected i.i
  Protected a.i
  Protected b.i
  If TlsAllZero(@secTlsPriv[0], 32) <> 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < 32
    a = secTlsPriv[i] & 255
    b = TlsP256Order[i] & 255
    If a < b
      ProcedureReturn 1
    EndIf
    If a > b
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0                    ; exactly n - out of range
EndProcedure

; ----------------------------------------------------------------------
;  Tls13DeriveKeySharePublic() - the public key share for whatever
;  private key is currently held in secTlsPriv. Split out from
;  Tls13NewKeyShare because deriving a public key from a private one is a
;  step in its own right; there is NO entry point anywhere in this file
;  that accepts a private key from a caller.
; ----------------------------------------------------------------------
Procedure.i Tls13DeriveKeySharePublic()
  Protected i.i
  If TlsGroup = #TLS_GROUP_X25519
    ; the RFC 7748 base point u = 9, little-endian
    i = 0
    While i < 32
      TlsScratch[i] = 0
      i = i + 1
    Wend
    TlsScratch[0] = 9
    X25519(@TlsKeyShare[0], @secTlsPriv[0], @TlsScratch[0])
    TlsKeyShareLen = 32
    ProcedureReturn 1
  EndIf
  If TlsGroup = #TLS_GROUP_SECP256R1
    If TlsScalarBelowOrder() = 0
      ProcedureReturn 0
    EndIf
    If EcP256Mulgen(@TlsKeyShare[0], @secTlsPriv[0], 32) <> 65
      ProcedureReturn 0
    EndIf
    TlsKeyShareLen = 65
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  Tls13NewKeyShare() - draw the ephemeral private key, the 32-byte
;  client random and the 32-byte legacy session id from the DRBG, then
;  derive the public share. The DRBG must already be seeded by the
;  board's entropy glue; this file never touches a raw entropy source.
;
;  For P-256 the private scalar is redrawn until it lands in [1, n-1].
;  The redraw probability is about 2^-32, so the loop is a formality -
;  and a bounded one: eight failures is a broken DRBG, and it refuses.
;
;  EVERY DRAW MUST RETURN ITS FULL LENGTH (port change 2). drbg.pi4
;  answers an unseeded call with #DRBG_ERR_UNSEEDED and writes nothing,
;  which would leave the private key as whatever the buffer held. Any
;  short draw refuses with #TLS13_REFUSE_KEYGEN_FAILED and clears the
;  share, so Tls13BuildClientHello cannot send it either.
; ----------------------------------------------------------------------
; Setup checkpoints occur between complete DRBG requests, never inside
; its mutable HMAC state. Other consumers may draw randomness while paused.
Global *Tls13SetupPauseHook
Procedure.i Tls13SetupCheckpoint()
  If Tls13State=#TLS13_ST_FAILED : ProcedureReturn 0 : EndIf
  If Tls13SetupPauseHook<>0
    If Tls13SetupPauseHook()=0 : ProcedureReturn TlsFail(#TLS13_REFUSE_COOPERATIVE_STOP,#TLS_ALERT_INTERNAL_ERROR) : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Tls13NewKeyShare()
  Protected tries.i
  TlsKeyShareLen = 0
  TlsSessionIdLen = 0
  If Tls13SetupCheckpoint()=0 : ProcedureReturn 0 : EndIf
  If DrbgGenerate(@TlsClientRandom[0], 32) <> 32
    ProcedureReturn TlsFail(#TLS13_REFUSE_KEYGEN_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If Tls13SetupCheckpoint()=0 : ProcedureReturn 0 : EndIf
  If DrbgGenerate(@TlsSessionId[0], 32) <> 32
    ProcedureReturn TlsFail(#TLS13_REFUSE_KEYGEN_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  TlsSessionIdLen = 32
  tries = 0
  While tries < 8
    If Tls13SetupCheckpoint()=0 : ProcedureReturn 0 : EndIf
    If DrbgGenerate(@secTlsPriv[0], 32) <> 32
      TlsKeyShareLen = 0
      ProcedureReturn TlsFail(#TLS13_REFUSE_KEYGEN_FAILED, #TLS_ALERT_INTERNAL_ERROR)
    EndIf
    If Tls13SetupCheckpoint()=0 : ProcedureReturn 0 : EndIf
    If Tls13DeriveKeySharePublic() <> 0
      ProcedureReturn 1
    EndIf
    tries = tries + 1
  Wend
  TlsKeyShareLen = 0
  ProcedureReturn TlsFail(#TLS13_REFUSE_KEYGEN_FAILED, #TLS_ALERT_INTERNAL_ERROR)
EndProcedure

; ----------------------------------------------------------------------
;  TlsComputeEcdhe() - the shared secret from our private key and the
;  server's key share. Refuses on anything the peer could have chosen to
;  make it degenerate: an off-curve or malformed P-256 point, or an
;  all-zero X25519 result (a small-order peer point).
; ----------------------------------------------------------------------
Procedure.i TlsComputeEcdhe()
  Protected i.i
  If TlsGroup = #TLS_GROUP_X25519
    If TlsPeerShareLen <> 32
      ProcedureReturn 0
    EndIf
    X25519(@secTlsEcdhe[0], @secTlsPriv[0], @TlsPeerShare[0])
    If TlsAllZero(@secTlsEcdhe[0], 32) <> 0
      ProcedureReturn 0
    EndIf
    ProcedureReturn 1
  EndIf
  If TlsGroup = #TLS_GROUP_SECP256R1
    If TlsPeerShareLen <> 65
      ProcedureReturn 0
    EndIf
    ; EcP256Mul works in place and validates the incoming point
    TlsCopy(@TlsScratch[0], @TlsPeerShare[0], 65)
    If EcP256Mul(@TlsScratch[0], 65, @secTlsPriv[0], 32) <> 1
      ProcedureReturn 0
    EndIf
    ; the shared secret is the X coordinate
    i = 0
    While i < 32
      secTlsEcdhe[i] = TlsScratch[1 + i] & 255
      i = i + 1
    Wend
    If TlsAllZero(@secTlsEcdhe[0], 32) <> 0
      ProcedureReturn 0
    EndIf
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  SET-UP
; ======================================================================

; ----------------------------------------------------------------------
;  Tls13SetGroup(group) -> 1 accepted, 0 refused.
;
;  A group this client cannot do is refused HERE, at the setter, with
;  Tls13Err naming why - not accepted now and discovered mid-handshake.
;  The state is left alone: this runs before Tls13Init, so there is no
;  handshake to fail yet, and Tls13Init clears the error itself.
; ----------------------------------------------------------------------
Procedure.i Tls13SetGroup(group.i)
  If group = #TLS_GROUP_X25519 Or group = #TLS_GROUP_SECP256R1
    TlsGroup = group
    ProcedureReturn 1
  EndIf
  Tls13Err = #TLS13_REFUSE_BAD_GROUP
  ProcedureReturn 0
EndProcedure

; Gives the handshake the buffer it collects received bytes in (addr, size
; bytes) and empties it.
Procedure Tls13SetRecvBuffer(addr.i, size.i)
  TlsRecvAddr = addr
  TlsRecvSize = size
  TlsRecvLen = 0
EndProcedure

; ----------------------------------------------------------------------
;  Tls13SetHsBuffer(addr, size) - the handshake-message reassembly
;  buffer. Must be set BEFORE Tls13Init, which refuses without it. Size
;  it for the largest certificate chain the board must accept: a message
;  that does not fit is refused, loudly, and the connection ends.
; ----------------------------------------------------------------------
Procedure Tls13SetHsBuffer(addr.i, size.i)
  TlsHsAddr = addr
  TlsHsSize = size
  TlsHsLen = 0
EndProcedure

; ----------------------------------------------------------------------
;  Tls13Init(nameAddr, nameLen, unixTime) -> 1 ok / 0 refused.
;
;  The two refusals here are the ones that matter most, because both
;  failure modes look like success: a handshake with no clock validates
;  every expired certificate, and a handshake with no trust anchor
;  validates every certificate full stop.
; ----------------------------------------------------------------------
Procedure.i Tls13Init(nameAddr.i, nameLen.i, unixTime.i)
  Define i.i
  TlsQuicConfig=0
  TlsAlpnOfferLen=0 : TlsAlpnSelectedLen=0
  For i=0 To 255 : TlsAlpnOffer[i]=0 : TlsAlpnSelected[i]=0 : Next
  Tls13State = #TLS13_ST_IDLE
  Tls13Err = #TLS13_OK
  Tls13Alert = 0
  Tls13X509Err = 0
  Tls13PeerAlert = -1
  Tls13TicketsDiscarded = 0
  Tls13KeyUpdatePending = 0
  Tls13AppAddr = 0
  Tls13AppLen = 0
  TlsHsLen = 0
  TlsRecvLen = 0
  TlsCertCount = 0
  TlsPeerShareLen = 0
  TlsKeyShareLen = 0
  TlsSessionIdLen = 0
  TlsOfferedCount = 0
  TlsKdfFault = 0

  TlsInitTables()

  If unixTime <= 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_TIME, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If xNumAnchors <= 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_ANCHORS, #TLS_ALERT_UNKNOWN_CA)
  EndIf
  If TlsHsAddr = 0 Or TlsHsSize < 512
    ; No room to reassemble a handshake message is not a small problem:
    ; it is a client that cannot read a Certificate. Refused here, where
    ; it is a caller error, rather than mid-flight where it looks like a
    ; server fault.
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_HS_BUFFER, #TLS_ALERT_INTERNAL_ERROR)
  EndIf

  TlsUnixTime = unixTime
  TlsNameAddr = nameAddr
  TlsNameLen = nameLen
  If TlsGroup <> #TLS_GROUP_SECP256R1
    TlsGroup = #TLS_GROUP_X25519
  EndIf

  ; one-time constant loads; these walk the program-wide Read cursor, so
  ; the header says to call Tls13Init before any read loop of your own.
  ; (sha256.pbi needs no warm-up here - port change 7.)
  EcdsaInit()
  X25519Init()

  ; SHA-256("") - the context of both "derived" steps, computed, never
  ; typed in as a literal
  Sha256Of(@TlsScratch[0], 0, @TlsEmptyHash[0])

  Tls13RecReset()
  Tls13TranscriptReset()
  TlsScheduleEarly()
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf

  Tls13State = #TLS13_ST_START
  ProcedureReturn 1
EndProcedure

; Returns 1 once the handshake has finished and the connection is up, else
; 0.
Procedure.i Tls13Connected()
  If Tls13State = #TLS13_ST_CONNECTED
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  TlsNoteOffered(ext) - remember an extension we sent, so that every
;  server extension can be tested against RFC 8446 4.2: "Implementations
;  MUST NOT send extension responses if the remote endpoint did not send
;  the corresponding extension requests ... Upon receiving such an
;  extension, an endpoint MUST abort the handshake."
; ----------------------------------------------------------------------
Procedure TlsNoteOffered(ext.i)
  If TlsOfferedCount < #TLS13_MAX_OFFERED
    TlsOfferedExt[TlsOfferedCount] = ext
    TlsOfferedCount = TlsOfferedCount + 1
  EndIf
EndProcedure

; Returns 1 if extension number ext was in the list this client offered,
; else 0.
Procedure.i TlsWasOffered(ext.i)
  Protected i.i
  i = 0
  While i < TlsOfferedCount
    If TlsOfferedExt[i] = ext
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  CLIENTHELLO (RFC 8446 4.1.2)
; ======================================================================
; Optional RFC 7301 protocol list: one length byte then 1..255 opaque bytes
; per name, at most 256 total bytes. Call after Init, before ClientHello.
; Empty input disables ALPN. Copy before commit, including aliased input.
Procedure.i Tls13SetAlpn(protocols.i,bytes.i)
 Define p.i,n.i,i.i
 Define Dim copy.a[256]
 If Tls13State<>#TLS13_ST_START : ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 If bytes<0 Or bytes>256 Or (bytes>0 And protocols=0) : ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_FORMAT,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 For i=0 To bytes-1 : copy[i]=PeekA(protocols+i) : Next
 p=0
 While p<bytes
  n=copy[p]&255 : p=p+1
  If n=0 Or n>bytes-p : ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_FORMAT,#TLS_ALERT_INTERNAL_ERROR) : EndIf
  p=p+n
 Wend
 For i=0 To 255
  If i<bytes : TlsAlpnOffer[i]=copy[i] : Else : TlsAlpnOffer[i]=0 : EndIf
  TlsAlpnSelected[i]=0
 Next
 TlsAlpnOfferLen=bytes : TlsAlpnSelectedLen=0
 ProcedureReturn 1
EndProcedure

; Selection is visible to the application only after the verified handshake.
; Returns selected byte count, zero when absent, -1 for state/buffer refusal.
Procedure.i Tls13Alpn(destination.i,capacity.i)
 Define i.i
 If Tls13State<>#TLS13_ST_CONNECTED : ProcedureReturn -1 : EndIf
 If TlsAlpnSelectedLen=0 : ProcedureReturn 0 : EndIf
 If destination=0 Or capacity<TlsAlpnSelectedLen : ProcedureReturn -1 : EndIf
 For i=0 To TlsAlpnSelectedLen-1 : PokeA(destination+i,TlsAlpnSelected[i]) : Next
 ProcedureReturn TlsAlpnSelectedLen
EndProcedure

Procedure.i TlsAlpnReadSelection(body.i,bytes.i)
 Define p.i,n.i,offered.i,i.i,equal.i
 If TlsAlpnOfferLen=0 : ProcedureReturn TlsFail(#TLS13_REFUSE_UNOFFERED_EXTENSION,#TLS_ALERT_UNSUPPORTED_EXTENSION) : EndIf
 If bytes<4 : ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_FORMAT,#TLS_ALERT_DECODE_ERROR) : EndIf
 n=TlsRd8(body+2)
 If TlsRd16(body)<>bytes-2 Or n=0 Or n+3<>bytes : ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_FORMAT,#TLS_ALERT_DECODE_ERROR) : EndIf
 p=0
 While p<TlsAlpnOfferLen
  offered=TlsAlpnOffer[p]&255 : p=p+1 : equal=0
  If offered=n
   equal=1
   For i=0 To n-1 : If TlsAlpnOffer[p+i]<>TlsRd8(body+3+i) : equal=0 : EndIf : Next
  EndIf
  If equal<>0
   For i=0 To n-1 : TlsAlpnSelected[i]=TlsRd8(body+3+i) : Next
   TlsAlpnSelectedLen=n : ProcedureReturn 1
  EndIf
  p=p+offered
 Wend
 ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_SELECTION,#TLS_ALERT_ILLEGAL_PARAMETER)
EndProcedure

; Configure after Init, before ClientHello. Buffers remain separate, immutable
; where applicable, and alive through the connection. Parameters are opaque to
; TLS: the QUIC owner validates their semantics and connection-ID binding.
Procedure.i Tls13SetQuicParameters(config.i,offer.i,bytes.i,peer.i,capacity.i)
 Define i.i
 If Tls13State<>#TLS13_ST_START : ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 If config<=0 Or offer<=0 Or peer<=0 Or bytes<0 Or bytes>16384 Or capacity<1 Or capacity>16384 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 If config>$7FFFFFFFFFFFFFFF-48 Or offer>$7FFFFFFFFFFFFFFF-bytes Or peer>$7FFFFFFFFFFFFFFF-capacity : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 If (config<offer+bytes And offer<config+48) Or (config<peer+capacity And peer<config+48) Or (offer<peer+capacity And peer<offer+bytes) : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : EndIf
 PokeI(config,offer) : PokeI(config+8,bytes) : PokeI(config+16,peer) : PokeI(config+24,capacity) : PokeI(config+32,0) : PokeI(config+40,0)
 TlsQuicConfig=config : ProcedureReturn 1
EndProcedure

; Read-only conservative destination bound, shared by admission and builder.
Procedure.i Tls13ClientHelloCapacity()
 Define nlen.i,extra.i
 nlen=TlsNameLen : If nlen<0 : nlen=0 : EndIf
 extra=0 : If TlsQuicConfig<>0 : extra=4+PeekI(TlsQuicConfig+8) : EndIf
 ProcedureReturn 256+nlen+TlsAlpnOfferLen+Bool(TlsAlpnOfferLen>0)*6+extra
EndProcedure
; Zero when QUIC has no ready output. Does not advance TLS or set an error.
Procedure.i Tls13QuicOutputCapacity()
 If TlsQuicConfig=0 : ProcedureReturn 0 : EndIf
 If Tls13State=#TLS13_ST_START And TlsKeyShareLen>0 : ProcedureReturn Tls13ClientHelloCapacity() : EndIf
 If Tls13State=#TLS13_ST_SEND_FINISHED : ProcedureReturn 36 : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i Tls13BuildClientHello(dst.i, dstmax.i)
  Protected p.i
  Protected extStart.i
  Protected q.i
  Protected bodyStart.i
  Protected msgLen.i
  Protected i.i
  Protected g2.i
  Protected nlen.i
  Protected start.i,extra.i

  If Tls13State <> #TLS13_ST_START
    ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If TlsKeyShareLen = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KEYGEN_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  ; A negative name length means "no name known", which also means no SNI
  ; and no certificate name check. It is kept as the sentinel it is; the
  ; builder works off a local zero instead of overwriting it.
  nlen = TlsNameLen
  If nlen < 0
    nlen = 0
  EndIf
  ; Without ALPN the largest ClientHello is 197 bytes plus the
  ; server name; reserve the optional ALPN bytes too before any write -
  ; a bound checked afterwards is a bound that already overflowed.
  start=dst+5 : extra=0
  If TlsQuicConfig<>0
    If TlsAlpnOfferLen=0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : EndIf
    start=dst : extra=4+PeekI(TlsQuicConfig+8) : TlsSessionIdLen=0
  EndIf
  If dstmax < Tls13ClientHelloCapacity()
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf

  TlsOfferedCount = 0
  bodyStart = start + 4
  p = bodyStart

  TlsWr16(p, #TLS13_LEGACY_VERSION) : p = p + 2
  TlsCopy(p, @TlsClientRandom[0], 32) : p = p + 32
  TlsWr8(p, TlsSessionIdLen) : p = p + 1
  TlsCopy(p, @TlsSessionId[0], TlsSessionIdLen) : p = p + TlsSessionIdLen
  ; exactly one cipher suite: TLS_AES_128_GCM_SHA256. Offering only what
  ; we implement means a suite we cannot do can never be negotiated.
  TlsWr16(p, 2) : p = p + 2
  TlsWr16(p, #TLS13_SUITE_AES128GCM) : p = p + 2
  ; legacy_compression_methods: exactly one, null
  TlsWr8(p, 1) : p = p + 1
  TlsWr8(p, 0) : p = p + 1

  extStart = p
  p = p + 2                            ; extensions length, filled at the end
  If TlsQuicConfig<>0
    TlsWr16(p,#TLS_EXT_QUIC_PARAMETERS) : TlsWr16(p+2,PeekI(TlsQuicConfig+8))
    TlsCopy(p+4,PeekI(TlsQuicConfig),PeekI(TlsQuicConfig+8)) : p=p+extra
    TlsNoteOffered(#TLS_EXT_QUIC_PARAMETERS)
  EndIf

  ; ---- server_name (RFC 6066), only when we know the name ----
  If nlen > 0
    TlsWr16(p, #TLS_EXT_SERVER_NAME) : p = p + 2
    TlsWr16(p, 5 + nlen) : p = p + 2
    TlsWr16(p, 3 + nlen) : p = p + 2
    TlsWr8(p, 0) : p = p + 1           ; name_type host_name
    TlsWr16(p, nlen) : p = p + 2
    TlsCopy(p, TlsNameAddr, nlen) : p = p + nlen
    TlsNoteOffered(#TLS_EXT_SERVER_NAME)
  EndIf

  ; RFC 7301 section 3.1; TLS 1.3 selects this in EncryptedExtensions.
  If TlsAlpnOfferLen>0
    TlsWr16(p,#TLS_EXT_ALPN) : TlsWr16(p+2,TlsAlpnOfferLen+2)
    TlsWr16(p+4,TlsAlpnOfferLen)
    TlsCopy(p+6,@TlsAlpnOffer[0],TlsAlpnOfferLen) : p=p+6+TlsAlpnOfferLen
    TlsNoteOffered(#TLS_EXT_ALPN)
  EndIf

  ; ---- supported_groups. RFC 8446 9.2 makes this mandatory alongside
  ;      key_share; the chosen group goes first. ----
  If TlsGroup = #TLS_GROUP_X25519
    g2 = #TLS_GROUP_SECP256R1
  Else
    g2 = #TLS_GROUP_X25519
  EndIf
  TlsWr16(p, #TLS_EXT_SUPPORTED_GROUPS) : p = p + 2
  TlsWr16(p, 6) : p = p + 2
  TlsWr16(p, 4) : p = p + 2
  TlsWr16(p, TlsGroup) : p = p + 2
  TlsWr16(p, g2) : p = p + 2
  TlsNoteOffered(#TLS_EXT_SUPPORTED_GROUPS)

  ; ---- signature_algorithms. With no signature_algorithms_cert sent,
  ;      RFC 8446 4.2.3 makes this ONE list govern both the
  ;      CertificateVerify and the certificate signatures, so it names
  ;      everything x509 can verify: ECDSA on P-256, P-384 and P-521 with
  ;      their own hashes, RSA-PSS with SHA-256, and PKCS#1 v1.5 with
  ;      SHA-256/384/512 - the last three because chains are still signed
  ;      with them; RFC 8446 4.4.3 forbids PKCS#1 in CertificateVerify,
  ;      and this client refuses it there by name. rsa_pss_rsae_sha384 /
  ;      sha512 are NOT offered: rsa.pi4's PSS is SHA-256 only, and every
  ;      RSA server must accept rsa_pss_rsae_sha256 (RFC 8446 9.1). ----
  TlsWr16(p, #TLS_EXT_SIGNATURE_ALGORITHMS) : p = p + 2
  TlsWr16(p, 16) : p = p + 2
  TlsWr16(p, 14) : p = p + 2
  TlsWr16(p, #TLS_SIG_ECDSA_P256_SHA256) : p = p + 2
  TlsWr16(p, #TLS_SIG_ECDSA_P384_SHA384) : p = p + 2
  TlsWr16(p, #TLS_SIG_ECDSA_P521_SHA512) : p = p + 2
  TlsWr16(p, #TLS_SIG_RSA_PSS_RSAE_SHA256) : p = p + 2
  TlsWr16(p, #TLS_SIG_RSA_PKCS1_SHA256) : p = p + 2
  TlsWr16(p, #TLS_SIG_RSA_PKCS1_SHA384) : p = p + 2
  TlsWr16(p, #TLS_SIG_RSA_PKCS1_SHA512) : p = p + 2
  TlsNoteOffered(#TLS_EXT_SIGNATURE_ALGORITHMS)

  ; ---- supported_versions: 1.3 and nothing else. There is no version
  ;      negotiation in this client and therefore no version to downgrade
  ;      to. ----
  TlsWr16(p, #TLS_EXT_SUPPORTED_VERSIONS) : p = p + 2
  TlsWr16(p, 3) : p = p + 2
  TlsWr8(p, 2) : p = p + 1
  TlsWr16(p, #TLS13_VERSION) : p = p + 2
  TlsNoteOffered(#TLS_EXT_SUPPORTED_VERSIONS)

  ; ---- key_share: one share, for the chosen group ----
  TlsWr16(p, #TLS_EXT_KEY_SHARE) : p = p + 2
  TlsWr16(p, 6 + TlsKeyShareLen) : p = p + 2
  TlsWr16(p, 4 + TlsKeyShareLen) : p = p + 2
  TlsWr16(p, TlsGroup) : p = p + 2
  TlsWr16(p, TlsKeyShareLen) : p = p + 2
  TlsCopy(p, @TlsKeyShare[0], TlsKeyShareLen) : p = p + TlsKeyShareLen
  TlsNoteOffered(#TLS_EXT_KEY_SHARE)

  TlsWr16(extStart, p - extStart - 2)

  msgLen = p - bodyStart
  If 5 + 4 + msgLen > dstmax
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  TlsWr8(start, #TLS_HS_CLIENT_HELLO)
  TlsWr24(start+1, msgLen)
  ; RFC 8446 5.1: the initial ClientHello carries legacy_record_version
  ; 0x0301 for middlebox compatibility
  If TlsQuicConfig=0 : Tls13RecBuildPlainHeader(dst, #TLS_CT_HANDSHAKE, 4 + msgLen, $01) : EndIf

  If Tls13TranscriptAppend(start, 4 + msgLen)=0 : ProcedureReturn 0 : EndIf
  Tls13State = #TLS13_ST_WAIT_SH
  ProcedureReturn start-dst + 4 + msgLen
EndProcedure

; ======================================================================
;  SERVERHELLO (RFC 8446 4.1.3)
; ======================================================================
Procedure.i TlsHandleServerHello(msg.i, mlen.i)
  Protected p.i
  Protected endp.i
  Protected sidLen.i
  Protected extLen.i
  Protected extEnd.i
  Protected et.i
  Protected el.i
  Protected sawVersions.i
  Protected sawKeyShare.i
  Protected ksGroup.i
  Protected ksLen.i
  Protected i.i
  Protected same.i

  p = msg + 4
  endp = msg + mlen

  If mlen < 4 + 2 + 32 + 1
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf

  ; legacy_version MUST be 0x0303 (RFC 8446 4.1.3)
  If TlsRd16(p) <> #TLS13_LEGACY_VERSION
    ProcedureReturn TlsFail(#TLS13_REFUSE_SH_LEGACY_VERSION, #TLS_ALERT_PROTOCOL_VERSION)
  EndIf
  p = p + 2

  ; Random. Two things live in here and both are refusals.
  same = 1
  i = 0
  While i < 32
    If (PeekA(p + i) & 255) <> (TlsHrrRandom[i] & 255)
      same = 0
      Break
    EndIf
    i = i + 1
  Wend
  If same <> 0
    ; A HelloRetryRequest. Not implemented, and named as such rather than
    ; mis-parsed as a ServerHello - which is what happens if the sentinel
    ; is not checked, because an HRR IS a ServerHello structurally.
    ProcedureReturn TlsFail(#TLS13_REFUSE_HELLO_RETRY_REQUEST, #TLS_ALERT_HANDSHAKE_FAILURE)
  EndIf
  ; RFC 8446 4.1.3: the last 8 bytes "DOWNGRD" || 0x01 or 0x00 are a
  ; server telling us it negotiated 1.2 or below. We offered only 1.3, so
  ; seeing this at all means something is rewriting the handshake.
  If (PeekA(p + 24) & 255) = $44 And (PeekA(p + 25) & 255) = $4F
    If (PeekA(p + 26) & 255) = $57 And (PeekA(p + 27) & 255) = $4E
      If (PeekA(p + 28) & 255) = $47 And (PeekA(p + 29) & 255) = $52
        If (PeekA(p + 30) & 255) = $44 And (PeekA(p + 31) & 255) <= 1
          ProcedureReturn TlsFail(#TLS13_REFUSE_DOWNGRADE_SENTINEL, #TLS_ALERT_ILLEGAL_PARAMETER)
        EndIf
      EndIf
    EndIf
  EndIf
  p = p + 32

  ; legacy_session_id_echo MUST equal what we sent (RFC 8446 4.1.3)
  sidLen = TlsRd8(p) : p = p + 1
  If p + sidLen > endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  If sidLen <> TlsSessionIdLen
    ProcedureReturn TlsFail(#TLS13_REFUSE_SESSION_ID_ECHO, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf
  i = 0
  While i < sidLen
    If (PeekA(p + i) & 255) <> (TlsSessionId[i] & 255)
      ProcedureReturn TlsFail(#TLS13_REFUSE_SESSION_ID_ECHO, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    i = i + 1
  Wend
  p = p + sidLen

  If p + 3 > endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  If TlsRd16(p) <> #TLS13_SUITE_AES128GCM
    ; we offered exactly one suite; anything else is the server picking a
    ; suite that was not on the table
    ProcedureReturn TlsFail(#TLS13_REFUSE_CIPHER_SUITE, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf
  p = p + 2
  If TlsRd8(p) <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_COMPRESSION_METHOD, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf
  p = p + 1

  If p + 2 > endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  extLen = TlsRd16(p) : p = p + 2
  extEnd = p + extLen
  If extEnd <> endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_TRAILING_DATA, #TLS_ALERT_DECODE_ERROR)
  EndIf

  sawVersions = 0
  sawKeyShare = 0
  While p < extEnd
    If p + 4 > extEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    et = TlsRd16(p)
    el = TlsRd16(p + 2)
    p = p + 4
    If p + el > extEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    If et = #TLS_EXT_SUPPORTED_VERSIONS
      If el <> 2
        ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
      EndIf
      If TlsRd16(p) <> #TLS13_VERSION
        ProcedureReturn TlsFail(#TLS13_REFUSE_NOT_TLS13, #TLS_ALERT_PROTOCOL_VERSION)
      EndIf
      sawVersions = 1
    ElseIf et = #TLS_EXT_KEY_SHARE
      If el < 4
        ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
      EndIf
      ksGroup = TlsRd16(p)
      ksLen = TlsRd16(p + 2)
      If ksGroup <> TlsGroup
        ; the server picked a group we did not send a share for. Without
        ; HelloRetryRequest there is nothing to do but refuse, by name.
        ProcedureReturn TlsFail(#TLS13_REFUSE_KEY_SHARE_GROUP, #TLS_ALERT_ILLEGAL_PARAMETER)
      EndIf
      If ksLen <> el - 4
        ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
      EndIf
      If ksLen > 65
        ProcedureReturn TlsFail(#TLS13_REFUSE_KEY_SHARE_LENGTH, #TLS_ALERT_ILLEGAL_PARAMETER)
      EndIf
      TlsCopy(@TlsPeerShare[0], p + 4, ksLen)
      TlsPeerShareLen = ksLen
      sawKeyShare = 1
    ElseIf et = #TLS_EXT_PRE_SHARED_KEY
      ; We never offered a PSK. A server answering with one is either
      ; broken or attacking; either way this is refused BY NAME, never
      ; skipped as "an extension we do not handle".
      ProcedureReturn TlsFail(#TLS13_REFUSE_PSK_OFFERED, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    Else
      ; RFC 8446 4.1.3 allows exactly supported_versions, key_share and
      ; pre_shared_key in a ServerHello. Anything else is refused.
      ProcedureReturn TlsFail(#TLS13_REFUSE_SH_UNKNOWN_EXTENSION, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    p = p + el
  Wend

  If sawVersions = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_SUPPORTED_VERSIONS, #TLS_ALERT_MISSING_EXTENSION)
  EndIf
  If sawKeyShare = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_KEY_SHARE, #TLS_ALERT_MISSING_EXTENSION)
  EndIf

  ; ---- the transcript is now CH..SH; everything below hangs off it ----
  If TlsComputeEcdhe() = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_ECDHE_FAILED, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf
  Tls13TranscriptHash(@TlsThBuf[0])
  TlsScheduleHandshake(@TlsThBuf[0])

  ; every key is checked BEFORE it is installed (port change 3)
  TlsKeyIvFrom(@secTlsSHs[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  Tls13RecSetReadKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])
  TlsKeyIvFrom(@secTlsCHs[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  Tls13RecSetWriteKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])

  Tls13State = #TLS13_ST_WAIT_EE
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  ENCRYPTEDEXTENSIONS (RFC 8446 4.3.1)
; ======================================================================
Procedure.i TlsHandleEncryptedExtensions(msg.i, mlen.i)
  Protected p.i
  Protected endp.i
  Protected extLen.i
  Protected et.i
  Protected el.i
  Protected sawAlpn.i
  Protected sawQuic.i,dest.i
  sawAlpn=0

  If mlen < 6
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  p = msg + 4
  endp = msg + mlen
  extLen = TlsRd16(p) : p = p + 2
  If p + extLen <> endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_TRAILING_DATA, #TLS_ALERT_DECODE_ERROR)
  EndIf

  While p < endp
    If p + 4 > endp
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    et = TlsRd16(p)
    el = TlsRd16(p + 2)
    p = p + 4
    If p + el > endp
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf

    If et = #TLS_EXT_EARLY_DATA
      ; We never sent early data. A server accepting it is out of scope
      ; AND out of order, and it is refused by name.
      ProcedureReturn TlsFail(#TLS13_REFUSE_EARLY_DATA_ACCEPTED, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    If et = #TLS_EXT_PRE_SHARED_KEY
      ProcedureReturn TlsFail(#TLS13_REFUSE_PSK_OFFERED, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    If et = #TLS_EXT_PSK_KEY_EXCHANGE_MODES
      ProcedureReturn TlsFail(#TLS13_REFUSE_PSK_KEY_EXCHANGE_MODES, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    If et = #TLS_EXT_KEY_SHARE Or et = #TLS_EXT_SUPPORTED_VERSIONS
      ; RFC 8446 4.2 table: these belong in ServerHello, never here.
      ProcedureReturn TlsFail(#TLS13_REFUSE_EXT_NOT_ALLOWED_HERE, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    If et = #TLS_EXT_SIGNATURE_ALGORITHMS
      ProcedureReturn TlsFail(#TLS13_REFUSE_EXT_NOT_ALLOWED_HERE, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    If TlsWasOffered(et) = 0
      ; RFC 8446 4.2: an answer to a question we did not ask.
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNOFFERED_EXTENSION, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    If et=#TLS_EXT_ALPN
      If sawAlpn<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_ALPN_DUPLICATE,#TLS_ALERT_ILLEGAL_PARAMETER) : EndIf
      sawAlpn=1
      If TlsAlpnReadSelection(p,el)=0 : ProcedureReturn 0 : EndIf
    EndIf
    If et=#TLS_EXT_QUIC_PARAMETERS
      If TlsQuicConfig=0 Or sawQuic<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_PARAMETERS,#TLS_ALERT_ILLEGAL_PARAMETER) : EndIf
      sawQuic=1 : dest=PeekI(TlsQuicConfig+16)
      If el>PeekI(TlsQuicConfig+24) Or (dest<endp And msg<dest+el) : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : EndIf
      TlsCopy(dest,p,el) : PokeI(TlsQuicConfig+32,el) : PokeI(TlsQuicConfig+40,1)
    EndIf
    ; The remaining offered server_name and supported_groups values
    ; do not change client behavior. ALPN was checked and retained above.
    p = p + el
  Wend

  If TlsQuicConfig<>0 And (sawQuic=0 Or sawAlpn=0) : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_PARAMETERS,#TLS_ALERT_MISSING_EXTENSION) : EndIf
  Tls13State = #TLS13_ST_WAIT_CERT
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  CERTIFICATE (RFC 8446 4.4.2) and the chain walk through x509
; ======================================================================
Procedure.i TlsHandleCertificate(msg.i, mlen.i)
  Protected p.i
  Protected endp.i
  Protected ctxLen.i
  Protected listLen.i
  Protected listEnd.i
  Protected clen.i
  Protected extLen.i
  Protected v.i

  If mlen < 5
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  p = msg + 4
  endp = msg + mlen

  ; RFC 8446 4.4.2: in a server Certificate sent in response to a
  ; ClientHello, certificate_request_context MUST be zero length.
  ctxLen = TlsRd8(p) : p = p + 1
  If ctxLen <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_CERT_CONTEXT_NOT_EMPTY, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf

  If p + 3 > endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  listLen = TlsRd24(p) : p = p + 3
  listEnd = p + listLen
  If listEnd <> endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_TRAILING_DATA, #TLS_ALERT_DECODE_ERROR)
  EndIf

  TlsCertCount = 0
  While p < listEnd
    If p + 3 > listEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    clen = TlsRd24(p) : p = p + 3
    If clen <= 0 Or p + clen > listEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    If TlsCertCount >= #TLS13_MAX_CERTS
      ProcedureReturn TlsFail(#TLS13_REFUSE_TOO_MANY_CERTS, #TLS_ALERT_UNSUPPORTED_CERT)
    EndIf
    TlsCertAddr[TlsCertCount] = p
    TlsCertLen[TlsCertCount] = clen
    TlsCertCount = TlsCertCount + 1
    p = p + clen

    If p + 2 > listEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    extLen = TlsRd16(p) : p = p + 2
    If p + extLen > listEnd
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
    EndIf
    If extLen <> 0
      ; This client offers no certificate-level extension (no OCSP
      ; stapling, no SCT), so any extension here is unsolicited and is
      ; refused rather than skipped.
      ProcedureReturn TlsFail(#TLS13_REFUSE_CERT_EXTENSION_UNSOLICITED, #TLS_ALERT_UNSUPPORTED_EXTENSION)
    EndIf
    p = p + extLen
  Wend

  If TlsCertCount = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_EMPTY_CERT_LIST, #TLS_ALERT_CERTIFICATE_UNKNOWN)
  EndIf

  ; ---- the chain walk. x509 drives the same one global SHA-256 context
  ;      the transcript uses, which is exactly why the transcript lives in
  ;      a snapshot. Nothing to restore afterwards - the snapshot is
  ;      untouched by anything x509 does. ----
  v = X509ValidateChain(@TlsCertAddr[0], @TlsCertLen[0], TlsCertCount, TlsNameAddr, TlsNameLen, TlsUnixTime)
  Tls13X509Err = v
  If v <> #X509ERR_OK
    ; Every x509 verdict lands here: expired, not yet valid, wrong server
    ; name, broken chain, untrusted root, bad signature, unsupported hash
    ; - and the seam-not-linked verdict too. Tls13X509Err carries exactly
    ; which, and the ALERT is picked to match, because "bad certificate"
    ; told a server nothing it could act on and RFC 8446 6.2 has the
    ; specific names.
    If v = #X509ERR_EXPIRED
      ProcedureReturn TlsFail(#TLS13_REFUSE_CHAIN_INVALID, #TLS_ALERT_CERTIFICATE_EXPIRED)
    EndIf
    If v = #X509ERR_NOT_TRUSTED
      ProcedureReturn TlsFail(#TLS13_REFUSE_CHAIN_INVALID, #TLS_ALERT_UNKNOWN_CA)
    EndIf
    If v = #X509ERR_UNSUPPORTED Or v = #X509ERR_WRONG_KEY_TYPE
      ProcedureReturn TlsFail(#TLS13_REFUSE_CHAIN_INVALID, #TLS_ALERT_UNSUPPORTED_CERT)
    EndIf
    If v = #X509ERR_WEAK_PUBLIC_KEY
      ProcedureReturn TlsFail(#TLS13_REFUSE_CHAIN_INVALID, #TLS_ALERT_INSUFFICIENT_SECURITY)
    EndIf
    ProcedureReturn TlsFail(#TLS13_REFUSE_CHAIN_INVALID, #TLS_ALERT_BAD_CERTIFICATE)
  EndIf
  If X509EePkeyType = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_EE_KEY, #TLS_ALERT_UNSUPPORTED_CERT)
  EndIf

  ; the CertificateVerify signs the transcript through THIS message, so
  ; freeze it now, before the next one is absorbed
  Tls13TranscriptHash(@TlsThCert[0])

  Tls13State = #TLS13_ST_WAIT_CV
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  CERTIFICATEVERIFY (RFC 8446 4.4.3)
; ======================================================================
Procedure.i TlsHandleCertificateVerify(msg.i, mlen.i)
  Protected p.i
  Protected endp.i
  Protected alg.i
  Protected slen.i
  Protected sig.i
  Protected ok.i

  If mlen < 8
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_TRUNCATED, #TLS_ALERT_DECODE_ERROR)
  EndIf
  p = msg + 4
  endp = msg + mlen
  alg = TlsRd16(p) : p = p + 2
  slen = TlsRd16(p) : p = p + 2
  If p + slen <> endp
    ProcedureReturn TlsFail(#TLS13_REFUSE_TRAILING_DATA, #TLS_ALERT_DECODE_ERROR)
  EndIf
  If slen > #TLS13_MAX_SIG
    ProcedureReturn TlsFail(#TLS13_REFUSE_SIG_TOO_LONG, #TLS_ALERT_DECODE_ERROR)
  EndIf
  sig = p

  ; ---- the RFC 8446 4.4.3 signed content: 64 spaces, the context
  ;      string, a 0x00 separator, then Transcript-Hash(CH..Certificate).
  ;      Hashed here, streamed rather than buffered, with the SCHEME's
  ;      hash - SHA-256 for 0403/0804, SHA-384 for 0503, SHA-512 for 0603
  ;      (the transcript hash inside it is the suite's SHA-256 either
  ;      way). The running transcript is a snapshot, so this is free to
  ;      use the hashers. ----
  Sha256Begin()
  Sha256Update(@TlsCvCtx[0], 98)
  Sha256Update(@TlsThCert[0], 32)
  Sha256End(@TlsMsgHash[0])

  ok = 0
  If alg = #TLS_SIG_ECDSA_P384_SHA384 Or alg = #TLS_SIG_ECDSA_P521_SHA512
    ; RFC 8446 4.2.3: in TLS 1.3 an ECDSA scheme names its CURVE as well
    ; as its hash, so the end-entity key must be on exactly that curve.
    If X509EePkeyType <> 2
      ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    If alg = #TLS_SIG_ECDSA_P384_SHA384
      If X509EeCurve <> 24
        ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
      EndIf
      Sha384Begin()
      Sha384Update(@TlsCvCtx[0], 98)
      Sha384Update(@TlsThCert[0], 32)
      Sha384End(@TlsMsgHash[0])
      ok = EcdsaVrfy(24, @TlsMsgHash[0], 48, X509EeQAddr, X509EeQLen, sig, slen)
    Else
      If X509EeCurve <> 25
        ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
      EndIf
      Sha512Begin()
      Sha512Update(@TlsCvCtx[0], 98)
      Sha512Update(@TlsThCert[0], 32)
      Sha512End(@TlsMsgHash[0])
      ok = EcdsaVrfy(25, @TlsMsgHash[0], 64, X509EeQAddr, X509EeQLen, sig, slen)
    EndIf
    If ok < 0
      ok = 0
    EndIf
  ElseIf alg = #TLS_SIG_RSA_PSS_RSAE_SHA256
    If X509EePkeyType <> 1
      ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    ; port change 1: the key goes in through RsaSetPubKey. x509's chain
    ; walk installed ISSUER keys through the same call, so the end-entity
    ; key is installed here, immediately before the verify, every time.
    RsaSetPubKey(X509EeNAddr, X509EeNLen, X509EeEAddr, X509EeELen)
    ok = RsaPssVrfy(sig, slen, @TlsMsgHash[0], 32, 32)
  ElseIf alg = #TLS_SIG_ECDSA_P256_SHA256
    If X509EePkeyType <> 2
      ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    If X509EeCurve <> 23
      ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_KEY_MISMATCH, #TLS_ALERT_ILLEGAL_PARAMETER)
    EndIf
    ok = EcdsaVrfy(23, @TlsMsgHash[0], 32, X509EeQAddr, X509EeQLen, sig, slen)
    If ok < 0
      ok = 0
    EndIf
  ElseIf alg = #TLS_SIG_RSA_PKCS1_SHA256 Or alg = #TLS_SIG_RSA_PKCS1_SHA384 Or alg = #TLS_SIG_RSA_PKCS1_SHA512
    ; RFC 8446 4.4.3: "RSASSA-PKCS1-v1_5 algorithms ... MUST NOT be used
    ; in CertificateVerify". They are offered for CERTIFICATES only. This
    ; is its own refusal so the log says what actually happened.
    ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_PKCS1_IN_CV, #TLS_ALERT_ILLEGAL_PARAMETER)
  Else
    ProcedureReturn TlsFail(#TLS13_REFUSE_SIGALG_NOT_OFFERED, #TLS_ALERT_ILLEGAL_PARAMETER)
  EndIf

  If ok <> 1
    ProcedureReturn TlsFail(#TLS13_REFUSE_SIGNATURE_INVALID, #TLS_ALERT_DECRYPT_ERROR)
  EndIf

  Tls13State = #TLS13_ST_WAIT_FINISHED
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  THE SERVER'S FINISHED (RFC 8446 4.4.4)
; ======================================================================
Procedure.i TlsHandleServerFinished(msg.i, mlen.i)
  If mlen <> 4 + 32
    ProcedureReturn TlsFail(#TLS13_REFUSE_FINISHED_LENGTH, #TLS_ALERT_DECODE_ERROR)
  EndIf

  ; verify_data covers the transcript through CertificateVerify - i.e.
  ; everything absorbed so far, this message NOT included
  Tls13TranscriptHash(@TlsThBuf[0])
  TlsFinishedVerify(@secTlsSHs[0], @TlsThBuf[0], @TlsVerifyData[0])
  If TlsKdfFault <> 0
    ; no finished_key was written - comparing against whatever the buffer
    ; held would be comparing against nothing (port change 3)
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If CtEqual(@TlsVerifyData[0], msg + 4, 32) <> 1
    ProcedureReturn TlsFail(#TLS13_REFUSE_FINISHED_MISMATCH, #TLS_ALERT_DECRYPT_ERROR)
  EndIf

  ; now the Finished joins the transcript, and CH..server-Finished is the
  ; context for both application traffic secrets AND for our own Finished
  If Tls13TranscriptAppend(msg, mlen)=0 : ProcedureReturn 0 : EndIf
  Tls13TranscriptHash(@TlsThSf[0])
  TlsScheduleApplication(@TlsThSf[0])

  ; the server switched to application keys the moment it sent that
  ; Finished, so our READ side switches now. The write side stays on the
  ; handshake key until our own Finished has been sent.
  TlsKeyIvFrom(@secTlsSAp[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  Tls13RecSetReadKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])

  Tls13State = #TLS13_ST_SEND_FINISHED
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  THE CLIENT'S FINISHED
; ======================================================================
Procedure.i Tls13BuildClientFinished(dst.i, dstmax.i)
  Protected n.i
  If Tls13State <> #TLS13_ST_SEND_FINISHED
    ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If (TlsQuicConfig=0 And dstmax<5+36+1+16) Or (TlsQuicConfig<>0 And dstmax<36)
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf

  TlsFinishedVerify(@secTlsCHs[0], @TlsThSf[0], @TlsVerifyData[0])
  TlsKeyIvFrom(@secTlsCAp[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  ; assembled in TlsScratch, NOT in the reassembly buffer: the server may
  ; already have pipelined the first bytes of a post-handshake message in
  ; there, and overwriting them would lose them
  TlsWr8(@TlsScratch[0], #TLS_HS_FINISHED)
  TlsWr24(@TlsScratch[1], 32)
  TlsCopy(@TlsScratch[4], @TlsVerifyData[0], 32)

  ; protected under the CLIENT HANDSHAKE traffic key, which is still the
  ; installed write key
  If TlsQuicConfig<>0
    TlsCopy(dst,@TlsScratch[0],36) : n=36
  Else
    n = Tls13RecProtect(#TLS_CT_HANDSHAKE, @TlsScratch[0], 36, 0, dst, dstmax)
  EndIf
  If n = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf

  ; keep the transcript honest even though nothing in scope consumes it
  ; past this point (the resumption master secret is out of scope)
  If Tls13TranscriptAppend(@TlsScratch[0], 36)=0 : ProcedureReturn 0 : EndIf

  ; and now the write side moves to application keys (derived and checked
  ; above, before anything was sent)
  Tls13RecSetWriteKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])

  Tls13State = #TLS13_ST_CONNECTED
  ProcedureReturn n
EndProcedure

; ======================================================================
;  KEY UPDATE (RFC 8446 4.6.3)
; ======================================================================
; Moves the receiving side to its next key. Returns 1, or 0 (refused by
; name) if hkdf did not produce every byte - checked before the install.
Procedure.i TlsApplyReadKeyUpdate()
  TlsExpandLabel(@secTlsSAp[0], @TlsLbl[#TLS_L_UPD], #TLS_L_UPD_N, 0, 0, @TlsThBuf[0], 32)
  TlsCopy(@secTlsSAp[0], @TlsThBuf[0], 32)
  TlsKeyIvFrom(@secTlsSAp[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  Tls13RecSetReadKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])
  ProcedureReturn 1
EndProcedure

; Moves the sending side to its next key: derives the next client traffic
; secret from the current one and installs the key and IV made from it.
; Returns 1, or 0 (refused by name) on an hkdf fault.
Procedure.i TlsApplyWriteKeyUpdate()
  TlsExpandLabel(@secTlsCAp[0], @TlsLbl[#TLS_L_UPD], #TLS_L_UPD_N, 0, 0, @TlsThBuf[0], 32)
  TlsCopy(@secTlsCAp[0], @TlsThBuf[0], 32)
  TlsKeyIvFrom(@secTlsCAp[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  If TlsKdfFault <> 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_KDF_FAILED, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  Tls13RecSetWriteKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  Tls13BuildKeyUpdate(dst, dstmax, requestPeerUpdate) -> record length.
;  The message is protected under the OLD write key and the new key is
;  installed AFTERWARDS, which is the order RFC 8446 4.6.3 requires.
; ----------------------------------------------------------------------
Procedure.i Tls13BuildKeyUpdate(dst.i, dstmax.i, requestPeerUpdate.i)
  If TlsQuicConfig<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : EndIf
  Protected n.i
  Protected m.i
  If Tls13State <> #TLS13_ST_CONNECTED
    ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  m = @TlsScratch[0]
  TlsWr8(m, #TLS_HS_KEY_UPDATE)
  TlsWr24(m + 1, 1)
  If requestPeerUpdate <> 0
    TlsWr8(m + 4, 1)
  Else
    TlsWr8(m + 4, 0)
  EndIf
  n = Tls13RecProtect(#TLS_CT_HANDSHAKE, m, 5, 0, dst, dstmax)
  If n = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If TlsApplyWriteKeyUpdate() = 0
    ProcedureReturn 0
  EndIf
  Tls13KeyUpdatePending = 0
  ProcedureReturn n
EndProcedure

; ======================================================================
;  APPLICATION DATA AND ALERTS
; ======================================================================
Procedure.i Tls13BuildAppRecord(dst.i, dstmax.i, payload.i, len.i)
  If TlsQuicConfig<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : EndIf
  Protected n.i
  If Tls13State <> #TLS13_ST_CONNECTED
    ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  n = Tls13RecProtect(#TLS_CT_APPDATA, payload, len, 0, dst, dstmax)
  If n = 0
    If Tls13RecErr = #TLSREC_ERR_SEQ_OVERFLOW
      ProcedureReturn TlsFail(#TLS13_REFUSE_SEQ_OVERFLOW, #TLS_ALERT_INTERNAL_ERROR)
    EndIf
    ProcedureReturn TlsFail(#TLS13_REFUSE_BUF_TOO_SMALL, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  Tls13BuildAlert(dst, dstmax, level, desc) -> record length, or 0.
;
;  Two shapes, and which one comes out is not a choice: RFC 8446 5 says an
;  alert is protected once a key exists and plaintext before that. A
;  handshake refused at ServerHello time - which is most of the refusal
;  table - happens BEFORE any key exists, and a client that could only
;  send protected alerts would simply drop the connection silently there.
;  Telling the peer why is the polite half of failing closed; the
;  connection ends either way.
;
;  Tls13Alert holds the alert the last refusal wants sent, and every
;  refusal in this file sets it.
; ----------------------------------------------------------------------
Procedure.i Tls13BuildAlert(dst.i, dstmax.i, level.i, desc.i)
  If TlsQuicConfig<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : EndIf
  Protected m.i
  m = @TlsScratch[0]
  TlsWr8(m, level)
  TlsWr8(m + 1, desc)
  If TlsWKeyed = 0
    If dstmax < #TLS_REC_HDR + 2
      ProcedureReturn 0
    EndIf
    Tls13RecBuildPlainHeader(dst, #TLS_CT_ALERT, 2, $03)
    PokeB(dst + #TLS_REC_HDR, level & 255)
    PokeB(dst + #TLS_REC_HDR + 1, desc & 255)
    ProcedureReturn #TLS_REC_HDR + 2
  EndIf
  ProcedureReturn Tls13RecProtect(#TLS_CT_ALERT, m, 2, 0, dst, dstmax)
EndProcedure

; ======================================================================
;  HANDSHAKE MESSAGE DISPATCH
; ======================================================================

; ----------------------------------------------------------------------
;  TlsHandleMessage(msg, mlen) - one COMPLETE handshake message, header
;  included. Absorption order is not cosmetic:
;    * ServerHello, EncryptedExtensions and Certificate are absorbed
;      BEFORE they are handled, because the secrets and the signature
;      that follow them are computed over a transcript that includes them.
;    * CertificateVerify and Finished are absorbed AFTER, because each is
;      verified against the transcript that does NOT include itself.
;  Getting this backwards produces a client that talks only to itself.
; ----------------------------------------------------------------------
Procedure.i TlsHandleMessage(msg.i, mlen.i)
  Protected t.i
  Protected r.i

  t = TlsRd8(msg)

  If t = #TLS_HS_MESSAGE_HASH
    ; RFC 8446 4.4.1's synthetic message_hash exists only to rewrite the
    ; transcript around a HelloRetryRequest. HRR is not implemented here,
    ; so this can only be an attempt to rewrite our transcript.
    ProcedureReturn TlsFail(#TLS13_REFUSE_MESSAGE_HASH_SYNTHETIC, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf
  If t = #TLS_HS_END_OF_EARLY_DATA
    ProcedureReturn TlsFail(#TLS13_REFUSE_END_OF_EARLY_DATA, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf
  If t = #TLS_HS_CERTIFICATE_REQUEST
    ProcedureReturn TlsFail(#TLS13_REFUSE_CLIENT_AUTH_REQUESTED, #TLS_ALERT_HANDSHAKE_FAILURE)
  EndIf

  If Tls13State = #TLS13_ST_WAIT_SH
    If t <> #TLS_HS_SERVER_HELLO
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If Tls13TranscriptAppend(msg, mlen)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn TlsHandleServerHello(msg, mlen)
  EndIf

  If Tls13State = #TLS13_ST_WAIT_EE
    If t <> #TLS_HS_ENCRYPTED_EXTENSIONS
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If Tls13TranscriptAppend(msg, mlen)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn TlsHandleEncryptedExtensions(msg, mlen)
  EndIf

  If Tls13State = #TLS13_ST_WAIT_CERT
    If t <> #TLS_HS_CERTIFICATE
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If Tls13TranscriptAppend(msg, mlen)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn TlsHandleCertificate(msg, mlen)
  EndIf

  If Tls13State = #TLS13_ST_WAIT_CV
    If t <> #TLS_HS_CERTIFICATE_VERIFY
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    r = TlsHandleCertificateVerify(msg, mlen)
    If r = 0
      ProcedureReturn 0
    EndIf
    If Tls13TranscriptAppend(msg, mlen)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn 1
  EndIf

  If Tls13State = #TLS13_ST_WAIT_FINISHED
    If t <> #TLS_HS_FINISHED
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    ; absorbs its own message internally, at the right moment
    ProcedureReturn TlsHandleServerFinished(msg, mlen)
  EndIf

  ; ---- post-handshake ----
  If Tls13State = #TLS13_ST_CONNECTED
    If t = #TLS_HS_NEW_SESSION_TICKET
      ; Counted and thrown away. See the header: this is the one
      ; out-of-scope thing that is not a refusal, and the reason is that
      ; it cannot change what this connection does - no ticket is stored
      ; and no PSK is ever offered.
      Tls13TicketsDiscarded = Tls13TicketsDiscarded + 1
      ProcedureReturn 1
    EndIf
    If t = #TLS_HS_KEY_UPDATE
      If TlsQuicConfig<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : EndIf
      If mlen <> 5
        ProcedureReturn TlsFail(#TLS13_REFUSE_KEY_UPDATE_LENGTH, #TLS_ALERT_DECODE_ERROR)
      EndIf
      If TlsRd8(msg + 4) > 1
        ProcedureReturn TlsFail(#TLS13_REFUSE_KEY_UPDATE_BAD_REQUEST, #TLS_ALERT_ILLEGAL_PARAMETER)
      EndIf
      If TlsApplyReadKeyUpdate() = 0
        ProcedureReturn 0
      EndIf
      If TlsRd8(msg + 4) = 1
        Tls13KeyUpdatePending = 1
      EndIf
      ProcedureReturn 1
    EndIf
    ProcedureReturn TlsFail(#TLS13_REFUSE_POST_HS_UNKNOWN, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf

  ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
EndProcedure

; ----------------------------------------------------------------------
;  TlsHsFeed(p, n) - append a handshake fragment and run every COMPLETE
;  message it completes. A handshake message may span records, so this
;  reassembles; a message longer than the buffer is refused by name, not
;  truncated.
; ----------------------------------------------------------------------
Procedure.i TlsHsFeed(p.i, n.i)
  Protected mlen.i
  Protected total.i
  Protected i.i

  If n = 0
    ; RFC 8446 5.1: zero-length handshake fragments are not permitted -
    ; and a stream of them is a free denial of service.
    ProcedureReturn TlsFail(#TLS13_REFUSE_EMPTY_HANDSHAKE_RECORD, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf
  If TlsHsAddr = 0
    ProcedureReturn TlsFail(#TLS13_REFUSE_NO_HS_BUFFER, #TLS_ALERT_INTERNAL_ERROR)
  EndIf
  If TlsHsLen + n > TlsHsSize
    ProcedureReturn TlsFail(#TLS13_REFUSE_HS_MSG_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
  EndIf
  TlsCopy(TlsHsAddr + TlsHsLen, p, n)
  TlsHsLen = TlsHsLen + n

  While TlsHsLen >= 4
    mlen = TlsRd24(TlsHsAddr + 1)
    total = 4 + mlen
    If total > TlsHsSize
      ProcedureReturn TlsFail(#TLS13_REFUSE_HS_MSG_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
    EndIf
    If TlsHsLen < total
      ProcedureReturn 1                ; incomplete; wait for more records
    EndIf
    If TlsHandleMessage(TlsHsAddr, total) = 0
      ProcedureReturn 0
    EndIf
    ; shift whatever followed down to the front
    i = 0
    While i < TlsHsLen - total
      PokeB(TlsHsAddr + i, PeekA(TlsHsAddr + total + i) & 255)
      i = i + 1
    Wend
    TlsHsLen = TlsHsLen - total
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
; QUIC owner supplies authenticated, ordered CRYPTO bytes. Encryption levels:
; 0 Initial, 2 Handshake, 3 application. Consume at most 256 bytes and never
; cross a handshake-message boundary, so the next call rechecks the level.
; Returns bytes consumed, 0 for empty input, -1 on terminal TLS failure.
Procedure.i Tls13FeedQuic(level.i,src.i,bytes.i)
 Define expected.i,want.i,total.i
 If TlsQuicConfig=0 Or bytes<0 Or (bytes>0 And src<=0)
  TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : ProcedureReturn -1
 EndIf
 expected=-1
 Select Tls13State
  Case #TLS13_ST_WAIT_SH : expected=0
  Case #TLS13_ST_WAIT_EE : expected=2
  Case #TLS13_ST_WAIT_CERT : expected=2
  Case #TLS13_ST_WAIT_CV : expected=2
  Case #TLS13_ST_WAIT_FINISHED : expected=2
  Case #TLS13_ST_CONNECTED : expected=3
 EndSelect
 If expected<0 Or level<>expected
  TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : ProcedureReturn -1
 EndIf
 If bytes=0 : ProcedureReturn 0 : EndIf
 If TlsHsAddr=0 Or TlsHsSize<4 Or TlsHsLen<0 Or TlsHsLen>TlsHsSize
  TlsFail(#TLS13_REFUSE_NO_HS_BUFFER,#TLS_ALERT_INTERNAL_ERROR) : ProcedureReturn -1
 EndIf
 If TlsHsLen<4
  want=4-TlsHsLen
 Else
  total=4+TlsRd24(TlsHsAddr+1)
  If total>TlsHsSize Or total<=TlsHsLen
   TlsFail(#TLS13_REFUSE_HS_MSG_TOO_LONG,#TLS_ALERT_RECORD_OVERFLOW) : ProcedureReturn -1
  EndIf
  want=total-TlsHsLen
 EndIf
 If want>bytes : want=bytes : EndIf
 If want>256 : want=256 : EndIf
 If src>$7FFFFFFFFFFFFFFF-want
  TlsFail(#TLS13_REFUSE_QUIC_CONFIG,#TLS_ALERT_INTERNAL_ERROR) : ProcedureReturn -1
 EndIf
 If TlsHsFeed(src,want)=0 : ProcedureReturn -1 : EndIf
 ProcedureReturn want
EndProcedure

;  TlsHandleAlert(p, n) - RFC 8446 6. close_notify closes; everything
;  else is fatal here. The level byte is deliberately not trusted: 1.3
;  says all alerts other than close_notify and user_canceled are fatal
;  regardless of what the level byte claims.
; ----------------------------------------------------------------------
Procedure.i TlsHandleAlert(p.i, n.i)
  If n <> 2
    ProcedureReturn TlsFail(#TLS13_REFUSE_ALERT_LENGTH, #TLS_ALERT_DECODE_ERROR)
  EndIf
  Tls13PeerAlert = TlsRd8(p + 1)
  If Tls13PeerAlert = #TLS_ALERT_CLOSE_NOTIFY
    Tls13State = #TLS13_ST_CLOSED
    ProcedureReturn 1
  EndIf
  ProcedureReturn TlsFail(#TLS13_REFUSE_PEER_ALERT, #TLS_ALERT_CLOSE_NOTIFY)
EndProcedure

; ======================================================================
;  RECORD DISPATCH
; ======================================================================

; ----------------------------------------------------------------------
;  Tls13FeedRecord(rec, reclen) -> 1 ok, 0 refused.
;
;  rec must be a COMPLETE record, 5-byte header included, in a writable
;  buffer: a protected record is opened in place.
; ----------------------------------------------------------------------
Procedure.i Tls13FeedRecord(rec.i, reclen.i)
  If TlsQuicConfig<>0 : ProcedureReturn TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : EndIf
  Protected t.i
  Protected flen.i
  Protected n.i
  Protected inner.i

  If Tls13State = #TLS13_ST_FAILED
    ProcedureReturn 0
  EndIf
  If Tls13State = #TLS13_ST_CLOSED
    ProcedureReturn TlsFail(#TLS13_REFUSE_WRONG_STATE, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf
  If reclen < #TLS_REC_HDR
    ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_SHORT, #TLS_ALERT_DECODE_ERROR)
  EndIf

  Tls13AppAddr = 0
  Tls13AppLen = 0

  t = TlsRd8(rec)
  flen = TlsRd16(rec + 3)
  If flen <> reclen - #TLS_REC_HDR
    ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_LEN_MISMATCH, #TLS_ALERT_DECODE_ERROR)
  EndIf
  If flen > #TLS_MAX_CIPHERTEXT
    ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
  EndIf

  ; ---- change_cipher_spec: RFC 8446 5 and appendix D.4. A 1.3 endpoint
  ;      in middlebox-compatibility mode may send one; it MUST be dropped
  ;      without processing, and it MUST NOT be part of the transcript.
  ;      After the handshake it has no meaning at all. ----
  If t = #TLS_CT_CHANGE_CIPHER_SPEC
    If Tls13State = #TLS13_ST_CONNECTED
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_CCS, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If flen <> 1
      ProcedureReturn TlsFail(#TLS13_REFUSE_BAD_CCS_VALUE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If TlsRd8(rec + #TLS_REC_HDR) <> 1
      ProcedureReturn TlsFail(#TLS13_REFUSE_BAD_CCS_VALUE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    ProcedureReturn 1
  EndIf

  ; ---- before any read key exists, records are plaintext ----
  If TlsRKeyed = 0
    If flen > #TLS_MAX_PLAINTEXT
      ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
    EndIf
    If t = #TLS_CT_HANDSHAKE
      ProcedureReturn TlsHsFeed(rec + #TLS_REC_HDR, flen)
    EndIf
    If t = #TLS_CT_ALERT
      ProcedureReturn TlsHandleAlert(rec + #TLS_REC_HDR, flen)
    EndIf
    ProcedureReturn TlsFail(#TLS13_REFUSE_UNKNOWN_CONTENT_TYPE, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf

  ; ---- once a read key exists, EVERYTHING is protected. A plaintext
  ;      handshake or data record arriving here is an attempt to inject
  ;      unauthenticated bytes and is refused by name. ----
  If t <> #TLS_CT_APPDATA
    ProcedureReturn TlsFail(#TLS13_REFUSE_PLAINTEXT_AFTER_KEYS, #TLS_ALERT_UNEXPECTED_MESSAGE)
  EndIf

  n = Tls13RecUnprotect(rec, reclen)
  If n < 0
    If Tls13RecErr = #TLSREC_ERR_BAD_TAG
      ProcedureReturn TlsFail(#TLS13_REFUSE_BAD_RECORD_MAC, #TLS_ALERT_BAD_RECORD_MAC)
    EndIf
    If Tls13RecErr = #TLSREC_ERR_ALL_ZERO_INNER
      ProcedureReturn TlsFail(#TLS13_REFUSE_ALL_ZERO_INNER, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    If Tls13RecErr = #TLSREC_ERR_SEQ_OVERFLOW
      ProcedureReturn TlsFail(#TLS13_REFUSE_SEQ_OVERFLOW, #TLS_ALERT_INTERNAL_ERROR)
    EndIf
    If Tls13RecErr = #TLSREC_ERR_TOO_LONG
      ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
    EndIf
    ProcedureReturn TlsFail(#TLS13_REFUSE_RECORD_SHORT, #TLS_ALERT_DECODE_ERROR)
  EndIf

  inner = TlsRecInnerType
  If inner = #TLS_CT_HANDSHAKE
    ProcedureReturn TlsHsFeed(rec + #TLS_REC_HDR, n)
  EndIf
  If inner = #TLS_CT_ALERT
    ProcedureReturn TlsHandleAlert(rec + #TLS_REC_HDR, n)
  EndIf
  If inner = #TLS_CT_APPDATA
    If Tls13State <> #TLS13_ST_CONNECTED
      ; application data before the handshake finished would be data this
      ; client cannot yet attribute to an authenticated server
      ProcedureReturn TlsFail(#TLS13_REFUSE_UNEXPECTED_MESSAGE, #TLS_ALERT_UNEXPECTED_MESSAGE)
    EndIf
    Tls13AppAddr = rec + #TLS_REC_HDR
    Tls13AppLen = n
    ProcedureReturn 1
  EndIf
  ; a change_cipher_spec INSIDE a protected record is not a thing
  ProcedureReturn TlsFail(#TLS13_REFUSE_UNKNOWN_CONTENT_TYPE, #TLS_ALERT_UNEXPECTED_MESSAGE)
EndProcedure

; ----------------------------------------------------------------------
;  Tls13FeedBytes(src, len) -> bytes consumed, or -1 on refusal.
;
;  The transport pump: hand over whatever TCP produced and this frames
;  records out of it, dispatching each complete one. Uses the buffer
;  given to Tls13SetRecvBuffer - see the header for why that buffer
;  belongs to the caller. Returns how many bytes were taken; call again
;  with the rest if it took fewer than offered (which happens when a
;  record completed and the caller should look at Tls13AppLen first).
; ----------------------------------------------------------------------
Procedure.i Tls13FeedBytesLimited(src.i, len.i, records.i)
  If TlsQuicConfig<>0
    TlsFail(#TLS13_REFUSE_QUIC_LEVEL,#TLS_ALERT_UNEXPECTED_MESSAGE) : ProcedureReturn -1
  EndIf
  Protected took.i
  Protected want.i
  Protected flen.i
  Protected total.i

  If TlsRecvAddr = 0
    TlsFail(#TLS13_REFUSE_NO_RECV_BUFFER, #TLS_ALERT_INTERNAL_ERROR)
    ProcedureReturn -1
  EndIf
  If TlsRecvSize < #TLS_REC_HDR + 1
    TlsFail(#TLS13_REFUSE_NO_RECV_BUFFER, #TLS_ALERT_INTERNAL_ERROR)
    ProcedureReturn -1
  EndIf

  ; A zero budget performs no work and consumes no bytes.
  If records <= 0 : ProcedureReturn 0 : EndIf
  took = 0
  While took < len
    ; first fill the 5-byte header
    If TlsRecvLen < #TLS_REC_HDR
      want = #TLS_REC_HDR - TlsRecvLen
      If want > len - took
        want = len - took
      EndIf
      TlsCopy(TlsRecvAddr + TlsRecvLen, src + took, want)
      TlsRecvLen = TlsRecvLen + want
      took = took + want
      If TlsRecvLen < #TLS_REC_HDR
        ProcedureReturn took
      EndIf
    EndIf

    flen = TlsRd16(TlsRecvAddr + 3)
    total = #TLS_REC_HDR + flen
    If flen > #TLS_MAX_CIPHERTEXT
      TlsFail(#TLS13_REFUSE_RECORD_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
      ProcedureReturn -1
    EndIf
    If total > TlsRecvSize
      ; the caller's buffer cannot hold a legal record the server sent.
      ; Refused loudly - never silently truncated into a parser.
      TlsFail(#TLS13_REFUSE_RECORD_TOO_LONG, #TLS_ALERT_RECORD_OVERFLOW)
      ProcedureReturn -1
    EndIf

    want = total - TlsRecvLen
    If want > len - took
      want = len - took
    EndIf
    TlsCopy(TlsRecvAddr + TlsRecvLen, src + took, want)
    TlsRecvLen = TlsRecvLen + want
    took = took + want
    If TlsRecvLen < total
      ProcedureReturn took
    EndIf

    TlsRecvLen = 0
    If Tls13FeedRecord(TlsRecvAddr, total) = 0
      ProcedureReturn -1
    EndIf
    records = records - 1
    If Tls13AppLen > 0 Or records = 0
      ; the plaintext lives in the caller's buffer and the next record
      ; would overwrite it, so hand control back now
      ProcedureReturn took
    EndIf
  Wend
  ProcedureReturn took
EndProcedure

; Compatibility entry: legacy callers may still consume a complete batch.
; Cooperative callers use Tls13FeedBytesLimited with a positive record budget.
Procedure.i Tls13FeedBytes(src.i, len.i)
  ProcedureReturn Tls13FeedBytesLimited(src, len, $7FFFFFFF)
EndProcedure

; ==== PORTABLE CORE A64 END ====
