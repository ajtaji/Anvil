# RaspberryPi4/Reference - published documents the gates read

Every file here is read by a gate or generator under `tools/`. Each one is a
published standard, a government test-vector file, or sample test data, kept
unmodified so the gates parse their expected values from the document itself.
No third-party source code is kept here; where a gate cites source code it
names the upstream, version and line instead.

Terms: NIST CAVP and FIPS files are works of the United States Government
(17 U.S.C. 105). RFCs are reproduced unmodified under the IETF Trust Legal
Provisions or their stated unlimited distribution. The certificates are
BearSSL sample data under the MIT licence; the notice is
`licenses/BearSSL-LICENSE.txt`.

| File | Upstream | Read by |
|---|---|---|
| `cavp_SHA1ShortMsg.rsp`, `cavp_SHA1LongMsg.rsp` | NIST CAVP `shabytetestvectors.zip` | `tools/a64/a64_sha1_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `cavp_HMAC.rsp` | NIST CAVP `hmactestvectors.zip` | `tools/a64/a64_hmacsha1_check.py` |
| `cavp_ECB{GFSbox,KeySbox,VarKey,VarTxt}{128,192,256}.rsp` | NIST CAVP `KAT_AES.zip` (AESAVS) | `tools/a64/a64_aes_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `fips197.txt` | NIST FIPS 197-upd1 (2023), text extraction | `tools/a64/a64_aes_check.py` |
| `fips197-2001.txt` | NIST FIPS 197 (2001), text extraction | `tools/a64/a64_aes_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `rfc3174.txt` | RFC 3174, US Secure Hash Algorithm 1 | `tools/a64/a64_sha1_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `rfc2202.txt` | RFC 2202, Test Cases for HMAC-MD5 and HMAC-SHA-1 | `tools/a64/a64_hmacsha1_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `rfc6070.txt` | RFC 6070, PKCS #5 PBKDF2 Test Vectors | `tools/a64/a64_pbkdf2_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `rfc3394.txt` | RFC 3394, AES Key Wrap Algorithm | `tools/a64/a64_keywrap_check.py`, `tools/gen_pi4_crypto_selftest.py` |
| `rfc1350.txt` | RFC 1350, The TFTP Protocol (Revision 2) | `tools/a64/a64_tftp_check.py` |
| `rfc1123.txt` | RFC 1123, Requirements for Internet Hosts | `tools/a64/a64_tftp_check.py` |
| `rfc2347.txt` | RFC 2347, TFTP Option Extension | `tools/a64/a64_tftp_check.py` |
| `rfc9293-tcp.txt` | RFC 9293, Transmission Control Protocol | `tools/a64/a64_net_check.py` |
| `cert-{ee,ica,root}-{ec,rsa}.pem.txt` | BearSSL `samples/cert-*.pem` (commit 7bea48e5), stored with a `.txt` suffix because this repository refuses `.pem` files | `tools/x509_proof_gen.py`, `tools/t0_pemproof_gen.py` (through `a64_x509_check.py` and `a64_t0vm_check.py`) |
| `bearssl_test_x509_root.crt` | BearSSL `test/x509/root.crt` (commit 7bea48e5) | `tools/gen_rsa_vectors.py` |
