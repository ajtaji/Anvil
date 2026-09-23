#!/usr/bin/env python3
"""The Pi 4 crypto image-size ladder.

Nine cumulative images, each one adding one module to the one above it,
so a module's code size is a DIFFERENCE that was measured rather than a
line count that was guessed.  Every image is built by the same compiler
with the same load/stack addresses the gates use, and every Main() calls
enough of the module to keep dead-code stripping from removing it - the
part-one note records that stripping is real on this target ("+112 for
CTR is not a mistake").

Single builds, one core, no pool: this is deliberately safe to run while
a gate sweep owns the machine.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "_work"
PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LOAD = 0x00400000
STACK = 0x03000000

UART = 'XIncludeFile "RaspberryPi4/Lib/uart.pi4"'
SHA = 'XIncludeFile "Anvil/Core/sha256.pbi"'
BN = 'XIncludeFile "RaspberryPi4/Lib/bignum.pi4"'
EC = 'XIncludeFile "RaspberryPi4/Lib/ec256.pi4"'
X255 = 'XIncludeFile "RaspberryPi4/Lib/x25519.pi4"'
ECDSA = 'XIncludeFile "RaspberryPi4/Lib/ecdsa.pi4"'
RSA = 'XIncludeFile "RaspberryPi4/Lib/rsa.pi4"'
T0 = 'XIncludeFile "RaspberryPi4/Lib/t0vm.pi4"'
BLOB = 'XIncludeFile "RaspberryPi4/Lib/x509_blob.pi4"'
X509 = 'XIncludeFile "RaspberryPi4/Lib/x509.pi4"'

BUFS = """
Global Dim sz.u[600]
Global Dim szb.a[512]
Global Dim gC.i[4]
Global Dim gL.i[4]
"""

# x509.pi4 declares its OWN stubs when #X509_SIG_LINKED = 0, so the
# unlinked image needs nothing but the constant - exactly the shape the
# gate's mode-A harness builds.

CALL_UART = '  UartWriteStr("s")'
CALL_BN = """  BnZero(@sz[0], 256)
  r = r + BnIsZero(@sz[0]) + BnModpow2(@sz[0], @szb[0], 4, @sz[0], 1, @sz[0], 16)"""
CALL_EC = """  EcInit()
  r = r + EcP256Mulgen(@szb[0], @szb[0], 32) + EcP256Mul(@szb[0], 65, @szb[0], 32)"""
CALL_X255 = """  X25519Init()
  r = r + X25519(@szb[0], @szb[0], @szb[0])"""
CALL_SHA = """  Sha256Begin()
  Sha256Update(@szb[0], 32)
  Sha256End(@szb[0])
  Sha256Of(@szb[0], 32, @szb[0])"""
CALL_ECDSA = """  EcdsaInit()
  r = r + EcdsaVrfyRaw(@szb[0], 32, @szb[0], 65, @szb[0], 64)
  r = r + EcdsaVrfyAsn1(@szb[0], 32, @szb[0], 65, @szb[0], 70)
  r = r + EcdsaAsn1ToRaw(@szb[0], 70)
  r = r + EcdsaVrfy(23, @szb[0], 32, @szb[0], 65, @szb[0], 70)"""
CALL_RSA = """  RsaSetPubKey(@szb[0], 256, @szb[0], 3)
  r = r + RsaVrfy(@szb[0], 256, RsaOidSha256(), 32, @szb[0])
  r = r + RsaPkcs1Vrfy(@szb[0], 256, RsaOidSha256(), 32, @szb[0])
  r = r + RsaPssVrfy(@szb[0], 256, @szb[0], 32, 32)"""
CALL_T0 = """  T0Start()
  r = r + T0Run() + T0Norm(1) + T0RamGet(0)
  T0RamPut(0, 0)"""
CALL_X509 = """  T0LoadX509()
  X509ResetAnchors()
  X509AddAnchorRSA(1, @szb[0], 8, @szb[0], 256, @szb[0], 3)
  X509AddAnchorEC(1, @szb[0], 8, 23, @szb[0], 65)
  gC[0] = @szb[0] : gL[0] = 16
  r = r + X509ValidateChain(@gC[0], @gL[0], 1, @szb[0], 4, 1700000000)"""

LADDER = [
    ("L0  uart only (the baseline)",
     [UART], [CALL_UART], 0),
    ("L1  + bignum",
     [UART, BN], [CALL_BN, CALL_UART], 0),
    ("L2  + ec256",
     [UART, BN, EC], [CALL_BN, CALL_EC, CALL_UART], 0),
    ("L3  + x25519",
     [UART, BN, EC, X255], [CALL_BN, CALL_EC, CALL_X255, CALL_UART], 0),
    ("L4  + sha256",
     [UART, SHA, BN, EC, X255],
     [CALL_SHA, CALL_BN, CALL_EC, CALL_X255, CALL_UART], 0),
    ("L5  + ecdsa",
     [UART, SHA, BN, EC, X255, ECDSA],
     [CALL_SHA, CALL_BN, CALL_EC, CALL_X255, CALL_ECDSA, CALL_UART], 0),
    ("L6  + rsa",
     [UART, SHA, BN, EC, X255, ECDSA, RSA],
     [CALL_SHA, CALL_BN, CALL_EC, CALL_X255, CALL_ECDSA, CALL_RSA,
      CALL_UART], 0),
    ("L7  + t0vm",
     [UART, T0, SHA, BN, EC, X255, ECDSA, RSA],
     [CALL_T0, CALL_SHA, CALL_BN, CALL_EC, CALL_X255, CALL_ECDSA, CALL_RSA,
      CALL_UART], 0),
    ("L8  + x509_blob + x509, WHOLE SEAM LINKED (mode C)",
     [UART, T0, SHA, BN, EC, X255, ECDSA, RSA, BLOB, X509],
     [CALL_T0, CALL_SHA, CALL_BN, CALL_EC, CALL_X255, CALL_ECDSA, CALL_RSA,
      CALL_X509, CALL_UART], 1),
]

# One extra image, off the ladder: the stub build, so the cost of
# LINKING the seam is a measurement and not an inference.
STUB_IMAGE = ("S   uart + t0vm + sha256 + x509_blob + x509, "
              "SEAM UNLINKED (mode A)",
              [UART, T0, SHA, BLOB, X509],
              [CALL_T0, CALL_SHA, CALL_X509, CALL_UART], 0)


def build(name, includes, calls, linked, tag):
    src = ["EnableExplicit"]
    if X509 in includes:
        src.append("#X509_SIG_LINKED = %d" % (1 if linked else 0))
    for inc in includes:
        src.append(inc)
    src.append(BUFS)
    src.append("Procedure.i Main()")
    src.append("  Define r.i")
    src.append("  r = 0")
    src.extend(calls)
    src.append("  ProcedureReturn r")
    src.append("EndProcedure")
    text = "\n".join(src) + "\n"

    harness = WORK / ("sz_%s.pi4" % tag)
    img = WORK / ("sz_%s.img" % tag)
    harness.write_text(text, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        print("BUILD FAILED  %s\n%s" % (name, r.stdout))
        return None
    return img.stat().st_size


def resolve_compiler(requested):
    """Resolve the PureMetal compiler. A named compiler (explicit or
    PMF_COMPILER) is routed through the shared, validating resolver
    (tools/pmf_compiler.py): refuses a missing, retired, or
    untracked/stale executable (forum 977). With nothing named, this
    falls back to tools/build.py's bare-PATH search, unchanged."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    if requested or os.environ.get("PMF_COMPILER"):
        from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402
        return _pmf_resolve_compiler(requested)
    return anvil_build.find_compiler(requested)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)
    WORK.mkdir(exist_ok=True)
    print("image size ladder, tree %s" % ROOT)
    print("%-58s %10s %10s" % ("image", "bytes", "delta"))
    prev = None
    rows = []
    for i, (name, inc, calls, linked) in enumerate(LADDER):
        n = build(name, inc, calls, linked, "l%d" % i)
        if n is None:
            return 1
        d = "" if prev is None else "%+d" % (n - prev)
        print("%-58s %10d %10s" % (name, n, d))
        rows.append((name, n, d))
        prev = n
    name, inc, calls, linked = STUB_IMAGE
    n = build(name, inc, calls, linked, "stub")
    if n is None:
        return 1
    print("%-58s %10d %10s" % (name, n, ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
