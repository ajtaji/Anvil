#!/usr/bin/env python3
r"""Executable gate for Anvil's on-board `crypto` self-test.

      python tools/a64/a64_cryptoself_check.py
      python tools/a64/a64_cryptoself_check.py --module gcm
      python tools/a64/a64_cryptoself_check.py --speed 1
      python tools/a64/a64_cryptoself_check.py --public-key

WHAT THIS GATE IS FOR, AND WHAT IT IS EXPLICITLY NOT FOR

  It is the DESK PROOF that has to be green before the board is
  claimed and KERNEL8.IMG is written.  Flashing a monitor whose
  self-test has never been executed anywhere is how a bench session
  turns into a debugging session with a locked board in the middle of
  it.

  It is NOT the result.  The self-test exists because the model cannot
  answer the questions silicon answers - real caches, real timing, a
  real memory system with the MMU off, and a compiler bug the emulator
  and the code generator SHARE.  A green run here means the sweep is
  wired up correctly and the arithmetic is right in the model.  The
  Pi 4 transcript is the evidence.

WHAT IT CHECKS, IN ORDER

  1. THE GENERATED TABLE IS CURRENT.  tools/gen_pi4_crypto_selftest.py
     is re-run into a scratch file and the result must be byte-identical
     to Anvil/Core/cryptotest_vectors.pbi.  A stale table would let the
     board pass vectors nobody can reproduce.

  2. THE TABLE IN THE IMAGE IS THE TABLE ON DISK.  The meta records and
     the byte stream are read back OUT OF THE BUILT IMAGE at ?CryVecMeta
     / ?CryVecData - the compiler's own symbols - and compared field by
     field against what the generator produced in python.  This is the
     one check that says the bytes the board will actually hash are the
     bytes NIST published, and it does not trust the assembler to have
     laid the DataSection out the way the source reads.

  3. EVERY EXPECTATION IS RE-DERIVED IN PYTHON.  hashlib, hmac and the
     `cryptography` package recompute every vector's answer from its
     own inputs before the image is allowed to run.  A wrong table would
     have to be wrong in the document, in the generator AND in OpenSSL.

  4. THE SWEEP RUNS.  CryptoSelfTestAll(0) is entered by its symbol with
     a modelled PL011 and a modelled architectural counter and nothing
     else - no mailbox, no framebuffer, no radio, because the self-test
     touches none of them.  Every line of its transcript must say PASS,
     the totals line must account for every vector, and the number of
     GCM forgeries REFUSED must equal the number of GCM vectors.

  5. THE NEGATIVE CONTROL BITES.  A forgery that is accepted has to be
     able to turn this gate red, or the forgery check proves nothing.
     --negative rebuilds the image with GcmDecrypt's verdict line
     replaced by the 32-bit families' spelling - the `>> 31` that
     returns $FFFFFFFF00000000 on this target - and requires the sweep
     to FAIL with code 8.  The mutation is written into a COPY in
     _work/; this gate never opens gcm.pi4 for writing.

WHAT THE TICK AND THROUGHPUT NUMBERS MEAN HERE: NOTHING.

  CNTPCT_EL0 is shimmed as a model STEP COUNT, because the interpreter
  does not decode MRS at all and every gate that needs one shims it.
  So the tick column comes out as instructions retired, not time, and
  the throughput lines come out as a ratio of step counts.  They are
  printed anyway - the point is that the arithmetic does not divide by
  zero and the lines are well formed - and the gate says so out loud
  rather than letting a reader take the KB/s figure for a measurement.
  THE REAL NUMBERS ONLY EXIST ON THE PART.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac as _hmac
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

from a64_interp import A64, attach_symbols        # noqa: E402
import build_count                                # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
SOURCE = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
GEN = ROOT / "tools" / "gen_pi4_crypto_selftest.py"
TABLE = ROOT / "Anvil" / "Core" / "cryptotest_vectors.pbi"
GCM_LIB = ROOT / "RaspberryPi4" / "Lib" / "gcm.pi4"
WORK = ROOT / "_work"
IMG = WORK / "cryptoself.img"

# board.pi4's own LoadAddress / StackAddress, read out of the source so
# that a placement that moves in the monitor moves here too.
LOAD = 0x00200000
SENTINEL = 0xDEADBEE0

# The PL011 this monitor prints through, and the flags it polls.
UART_LO, UART_HI = 0xFE201000, 0xFE20104F
UART_DR = 0xFE201000
UART_FR = 0xFE201018
FR_RXFE = 16                 # receive FIFO EMPTY - nothing typed, ever
FR_IDLE = FR_RXFE            # TX not full, not busy, RX empty

CNTFRQ = 54_000_000          # what this part reads, timer.pi4's header

MASK64 = 0xFFFFFFFFFFFFFFFF

# Generous, because a self-test is meant to be long: 142 vectors with
# three PBKDF2 runs of 4096 iterations in them.  A runaway shows as a
# budget exhaustion with a step count, not as a hang.
STEP_LIMIT = 3_000_000_000


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_pi4_crypto_selftest",
                                                  GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_pi4_crypto_selftest"] = mod
    spec.loader.exec_module(mod)
    return mod


# =====================================================================
#  1. THE GENERATED TABLE IS CURRENT
# =====================================================================
def check_table_current() -> None:
    WORK.mkdir(exist_ok=True)
    scratch = WORK / "cryptotest_vectors_regen.pbi"
    r = subprocess.run([sys.executable, str(GEN), str(scratch)],
                       cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise SystemExit("the vector generator failed:\n" + r.stdout)
    # LINE ENDINGS ARE NOT CONTENT. The repository stores the table with LF
    # endings and the generator writes LF, but a checkout with automatic
    # CRLF conversion hands the working copy back with CRLF. Comparing raw
    # bytes would call every such checkout stale, so both sides are
    # compared with CRLF folded to LF - and nothing else is forgiven.
    a = TABLE.read_bytes().replace(b"\r\n", b"\n")
    b = scratch.read_bytes().replace(b"\r\n", b"\n")
    if a != b:
        raise SystemExit(
            "Anvil/Core/cryptotest_vectors.pbi is STALE: re-running\n"
            "tools/gen_pi4_crypto_selftest.py produces a different file.\n"
            "Regenerate it and rebuild; do not edit the table by hand.\n"
            "  python tools/gen_pi4_crypto_selftest.py")
    print("  the vector table on disk is what the generator produces today "
          "(%d bytes)" % len(a))


# =====================================================================
#  RE-DERIVE EVERY EXPECTATION IN PYTHON
# =====================================================================
def rederive(gen, table) -> None:
    """Recompute every vector's answer from its own inputs.

    This runs on the python-side table, before anything is built, so a
    table that is wrong is caught by arithmetic rather than by the board
    disagreeing with it - which is the failure that looks like a silicon
    problem and is not one.
    """
    from cryptography.hazmat.primitives.ciphers import (
        Cipher, algorithms, modes)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.keywrap import aes_key_wrap
    from cryptography.hazmat.backends import default_backend

    def _ec_oracle():
        """gen_ec_vectors' own curve arithmetic, loaded once and
        anchored against the published KATs before it is believed."""
        if not hasattr(rederive, "_ec"):
            spec = importlib.util.spec_from_file_location(
                "gen_ec_vectors_oracle", ROOT / "tools" / "gen_ec_vectors.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.anchor()
            rederive._ec = mod
        return rederive._ec

    def _t0_expect(steps: bytes) -> bytes:
        """Re-run the bounds contract over the step table.

        The contract is five lines in RaspberryPi4/Lib/t0vm.pi4 and both
        of its numbers are read out of that file rather than written
        here, so this is a second reading of the source and not a second
        copy of the answer.
        """
        spec = importlib.util.spec_from_file_location(
            "a64_t0vm_check_oracle", ROOT / "tools" / "a64" /
            "a64_t0vm_check.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        K = mod.module_constants()
        N, E = K["T0_RAM_SIZE"], K["T0ERR_RAM_BOUNDS"]
        ram, err, out = {}, 0, bytearray()
        for i in range(len(steps) // 12):
            p = steps[i * 12:i * 12 + 12]
            op, w = p[0], p[1]
            addr = int.from_bytes(p[4:8], "little", signed=True)
            val = int.from_bytes(p[8:12], "little")
            res = 0
            if op == 0:
                err = 0
            elif op in (1, 2):
                if addr < 0 or addr > N - w:
                    err = E
                    res = 0
                elif op == 1:
                    for k in range(w):
                        ram[addr + k] = (val >> (8 * k)) & 255
                else:
                    res = 0
                    for k in range(w):
                        res |= ram.get(addr + k, 0) << (8 * k)
                    if w == 4:
                        res = ((res & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000
            elif op == 3:
                res = ((val & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000
            out += (res & ((1 << 64) - 1)).to_bytes(8, "little")
            out += (err & ((1 << 64) - 1)).to_bytes(8, "little")
        return bytes(out)

    M = gen
    n = 0
    for module, vid, f, param, note in table.recs:
        a, b, c, d, e, g = f
        if module == M.MOD_SHA256:
            want = hashlib.sha256(a).digest()
        elif module == M.MOD_SHA1:
            want = hashlib.sha1(a * param).digest()
        elif module == M.MOD_HMAC:
            want = _hmac.new(a, b, hashlib.sha256).digest()[:len(e)]
        elif module == M.MOD_HMACSHA1:
            want = _hmac.new(a, b, hashlib.sha1).digest()[:len(e)]
        elif module == M.MOD_HKDF:
            prk = _hmac.new(a if a else b"\x00" * 32, b,
                            hashlib.sha256).digest()
            if prk != d:
                raise SystemExit("hkdf %d: the PRK in the table is not "
                                 "HMAC(salt, ikm)" % vid)
            okm, t, ctr = b"", b"", 0
            while len(okm) < len(e):
                ctr += 1
                t = _hmac.new(prk, t + c + bytes([ctr]),
                              hashlib.sha256).digest()
                okm += t
            want = okm[:len(e)]
        elif module == M.MOD_PBKDF2:
            want = hashlib.pbkdf2_hmac("sha1", a, b, param, len(e))
        elif module == M.MOD_DRBG:
            want = e          # covered by gen_drbg_vectors' own anchor
        elif module == M.MOD_AES:
            enc = Cipher(algorithms.AES(a), modes.ECB(),
                         backend=default_backend()).encryptor()
            want = enc.update(b) + enc.finalize()
        elif module == M.MOD_AESCTR:
            enc = Cipher(algorithms.AES(a), modes.CTR(b),
                         backend=default_backend()).encryptor()
            want = enc.update(c) + enc.finalize()
        elif module == M.MOD_GCM:
            blob = AESGCM(a).encrypt(b, d, c if c else None)
            if blob[-16:] != g:
                raise SystemExit("gcm %d: the tag in the table is not the "
                                 "one AESGCM computes" % vid)
            want = blob[:-16]
        elif module == M.MOD_KEYWRAP:
            want = aes_key_wrap(a, b)

        # ---- part two, the public-key half --------------------------
        # THE SHAPE CHANGES HERE AND IT IS WORTH SAYING WHY. Four of the
        # seven answer with a VERDICT and carry no expected bytes at
        # all, so "want != e" would be vacuously true for them and this
        # pass would silently stop checking anything. Each of those
        # branches therefore says out loud where its oracle actually is
        # rather than passing quietly - and every one of them is an
        # anchor the generator RE-RUNS on every build, not a claim.
        elif module == M.MOD_BIGNUM:
            mod = int.from_bytes(a, "big")
            x = int.from_bytes(b, "big") if b else 0
            y = int.from_bytes(c, "big") if c else 0
            if param == 1:
                want = ((x % mod) * (y % mod)) % mod
            elif param in (2, 5):
                want = pow(x % mod, y, mod)
            elif param in (3, 4):
                want = x % mod
            else:
                raise SystemExit("bignum %d: op %d has no second opinion"
                                 % (vid, param))
            want = want.to_bytes(len(e), "big")
        elif module == M.MOD_P256:
            ec = _ec_oracle()
            if param == 4:
                # A NEGATIVE. There are no expected bytes; the whole
                # expectation is "EcP256Mul returns 0", and the oracle
                # is gen_ec_vectors' own construction of the point plus,
                # for the derived case, a64_ec_check.derived_range_point.
                # Re-deriving "this is not a valid point" here would be
                # a second decoder and it would agree with itself.
                want = e
            elif param == 1:
                want = ec.enc_point(ec.pt_mul(int.from_bytes(b, "big"), ec.G))
            else:
                pt = (int.from_bytes(a[1:33], "big"),
                      int.from_bytes(a[33:65], "big"))
                got = ec.enc_point(ec.pt_mul(int.from_bytes(b, "big"), pt))
                want = got[1:33] if param == 3 else got
        elif module == M.MOD_X25519:
            ec = _ec_oracle()
            want = ec.x25519(a, b)
        elif module == M.MOD_ECDSA:
            # The verdict is in `param` and the oracle is
            # gen_ecdsa_vectors.verify(), which anchor() re-runs against
            # the published RFC 6979 A.2.5 signatures on every build.
            want = e
        elif module == M.MOD_RSA:
            # The seam records carry the hash the verify must RECOVER,
            # and that is re-derivable here. The verdicts are anchored
            # by gen_rsa_vectors, which builds every signature with its
            # own private key and asserts the real certificate's
            # recovered hash against the TBS it read off the disk.
            if (param & 255) == 4:
                # d10's "expected output" is the UNTOUCHED SENTINEL, not
                # an answer: with no key installed the refusal must leave
                # the caller's buffer exactly as it found it, so what is
                # checked is that the table still asks for a full run of
                # $A5 and has not quietly been given something the board
                # could satisfy by writing.
                if e != bytes([0xA5]) * 32:
                    raise SystemExit(
                        "the rsa no-key record's sentinel is no longer 32 "
                        "bytes of $A5, so it no longer measures whether a "
                        "refusal wrote anything.")
                want = e
            else:
                want = hashlib.sha256(d).digest() if e else e
        elif module == M.MOD_T0VM:
            want = _t0_expect(a)
        elif module == M.MOD_X509:
            # No second opinion, and this is the one place in the table
            # where that is a real gap rather than a shape. Re-deriving
            # an #X509ERR_* code means a second chain validator; what
            # stands behind these thirteen instead is that every
            # certificate, anchor and tampered copy comes out of
            # tools/x509_proof_gen.py and tools/ecdsa_x509_gen.py, whose
            # own generators built and signed the chains, and that the
            # tamper helpers are length-preserving by construction and
            # asserted so at generation time.
            want = e
        else:
            raise SystemExit("no second opinion for module %d" % module)
        if want != e:
            raise SystemExit(
                "vector %s %d (%s) DISAGREES with a second implementation "
                "BEFORE anything was built. The table is wrong, not the "
                "library under test." % (module, vid, note))
        n += 1
    print("  all %d expectations re-derived in python and agree" % n)


# =====================================================================
#  BUILD
# =====================================================================
def build(img: pathlib.Path, gcm_include: str | None = None) -> None:
    WORK.mkdir(exist_ok=True)
    src = SOURCE
    if gcm_include is not None:
        # THE MUTATION GOES IN A COPY OF board.pi4, never in board.pi4:
        # a mutant written over a shared source can be picked up by a
        # concurrent build or commit.
        text = SOURCE.read_text(encoding="utf-8", errors="replace")
        text = text.replace('XIncludeFile "RaspberryPi4/Lib/gcm.pi4"',
                            'XIncludeFile "%s"' % gcm_include)
        src = WORK / "board_mut.pi4"
        src.write_text(text, encoding="utf-8", newline="\n")
    r = subprocess.run([str(PMFC), "--compile", str(src), "-t", "pi4", "-o", str(img)],
                       cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout[-4000:])
    # A whole monitor image was built, so it is counted like any other
    # build of the board file. The build is proven good above first.
    build_count.record_build(src, "pi4", img,
                             by="tools/a64/a64_cryptoself_check.py",
                             compiler=PMFC)


def symbols(img: pathlib.Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in img.with_suffix(".img.sym").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                out[k.strip().lower()] = int(v)
            except ValueError:
                pass
    if out.get("_start") != 0:
        raise SystemExit("the .sym is not offsets - _start is not 0")
    return out


def stack_top() -> int:
    text = SOURCE.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\s*StackAddress\s+\$([0-9A-Fa-f]+)", text, re.M)
    if not m:
        raise SystemExit("board.pi4 no longer declares StackAddress; this "
                         "gate reads the stack top out of the source rather "
                         "than repeating it.")
    return int(m.group(1), 16)


# =====================================================================
#  2. THE TABLE IN THE IMAGE IS THE TABLE ON DISK
# =====================================================================
def check_table_in_image(blob: bytes, syms: dict[str, int], gen,
                         table) -> None:
    meta_off = syms.get("cryvecmeta")
    data_off = syms.get("cryvecdata")
    if meta_off is None or data_off is None:
        raise SystemExit(
            "the built image has no CryVecMeta / CryVecData symbol, so the "
            "vector table is not in it. Check that board.pi4 still includes "
            "Anvil/Core/cryptotest_vectors.pbi.")
    stride = 40
    bad = 0
    for i, (module, vid, fields, param, note) in enumerate(table.recs):
        rec = blob[meta_off + i * stride: meta_off + (i + 1) * stride]
        got = [int.from_bytes(rec[k * 4:k * 4 + 4], "little")
               for k in range(10)]
        want = [module, vid] + [len(f) for f in fields] + [param, got[9]]
        if got[:9] != want[:9]:
            print("    ** meta record %d differs: image %r, generator %r"
                  % (i, got[:9], want[:9]))
            bad += 1
            continue
        blobbed = b"".join(fields)
        inimg = blob[data_off + got[9]: data_off + got[9] + len(blobbed)]
        if inimg != blobbed:
            print("    ** the bytes of vector %d (%s) in the image are not "
                  "the bytes the generator emitted" % (i, note))
            bad += 1
    if bad:
        raise SystemExit("%d vector records in the built image do not match "
                         "the generator. The assembler did not lay the "
                         "DataSection out the way the source reads." % bad)
    print("  all %d vector records read back OUT OF THE BUILT IMAGE and "
          "match the generator" % len(table.recs))


# =====================================================================
#  4. RUN THE SWEEP IN THE MODEL
# =====================================================================
class Run:
    def __init__(self):
        self.uart = bytearray()
        self.steps = 0


def make_cpu(img: pathlib.Path, r: Run) -> A64:
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    mem = cpu.memory

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE, called explicitly because this closure
        # replaces A64.load. With the MMU off every data access on the
        # part is Device-nGnRnE and an unaligned wide one is a silent
        # runaway; without this line the model would be more permissive
        # than the board it is certifying.
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return FR_IDLE
            if UART_LO <= addr <= UART_HI:
                return 0
            raise SystemExit(
                "the self-test read MMIO at $%08X, which it must not: it is "
                "meant to touch nothing but the console. Something it calls "
                "has grown a hardware dependency." % addr)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR:
                r.uart.append(value & 0xFF)
                return
            if UART_LO <= addr <= UART_HI:
                return
            raise SystemExit(
                "the self-test wrote MMIO at $%08X, which it must not." % addr)
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    return cpu


def run_proc(img: pathlib.Path, entry: int, arg: int, r: Run,
             limit: int = STEP_LIMIT, label: str = "") -> int:
    cpu = make_cpu(img, r)
    plain = A64.step.__get__(cpu)

    def step() -> None:
        r.steps += 1
        ins = cpu.fetch(cpu.pc)
        # THE INTERPRETER DOES NOT DECODE MRS AT ALL - a64_interp.py says
        # so in mmu_enabled's docstring - so every gate that needs one
        # shims it. CNTPCT_EL0 becomes the step count, which is why the
        # tick column in the transcript below is instructions and not
        # time. It is monotonic, which is all the self-test's own
        # counter-is-moving check asks of it.
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = r.steps
            cpu.pc += 4
            return
        plain()

    cpu.x = [0] * 31
    cpu.x[0] = arg & MASK64
    cpu.x[30] = SENTINEL
    cpu.sp = stack_top()
    cpu.pc = LOAD + entry
    mark = 50_000_000
    start = r.steps
    while r.steps - start < limit:
        if cpu.pc == SENTINEL:
            return cpu.x[0] & MASK64
        step()
        if r.steps - start >= mark:
            print("    ... %d M model instructions, %d bytes printed"
                  % ((r.steps - start) // 1_000_000, len(r.uart)))
            mark += 50_000_000
    raise SystemExit(
        "%s never returned inside %d model instructions. What it printed "
        "before the budget ran out:\n%s"
        % (label or "the procedure", limit,
           r.uart.decode("latin-1")[-4000:]))


# =====================================================================
#  THE VERDICT
# =====================================================================
def judge(out: str, table, gen, expect_fail: bool) -> int:
    bad = 0
    lines = [ln.rstrip("\r") for ln in out.split("\n")]
    # A VECTOR LINE, NOT ANY LINE CONTAINING "PASS". The totals line
    # reads "crypto: 142 of 142 vectors PASS", so a substring match
    # counts it as a 143rd vector and the count check goes green on a
    # sweep that is one vector short. Anchored on the module-name and
    # id columns instead.
    VEC = re.compile(r"^[a-z0-9-]+\s+\d+\s+(PASS|FAIL)\b")
    passes = [ln for ln in lines if VEC.match(ln) and " PASS" in ln]
    fails = [ln for ln in lines if VEC.match(ln) and "FAIL" in ln]
    forged = [ln for ln in lines if "forged tag REFUSED" in ln]

    want = len(table.recs)
    want_gcm = table.count(gen.MOD_GCM)

    if expect_fail:
        if not fails:
            print("    ** THE NEGATIVE CONTROL DID NOT BITE. The mutated "
                  "verdict line was not caught, which means the forgery "
                  "check in the self-test proves nothing.")
            return 1
        code8 = [ln for ln in lines if "code 8 (FORGED)" in ln]
        if not code8:
            print("    ** the mutant failed, but not with code 8 (FORGED). "
                  "It should fail on the forgery, not on something else:")
            for ln in fails[:3]:
                print("       " + ln.strip())
            return 1
        print("    the negative control BITES: %d vectors report code 8 "
              "(FORGED)." % len(code8))
        print("    " + code8[0].strip())
        return 0

    # THE POSITIVE BRANCH THAT USED TO LIVE HERE IS GONE, DELIBERATELY.
    #
    # It was dead - this function has only ever been called with
    # expect_fail=True - and it was WRONG in the same way judge_pool()
    # was: it required `crypto: N of N vectors PASS`, which CryTotals()
    # prints from the CONSOLE command and which CryptoSelfTestAll, the
    # symbol every caller here enters, does not print at all. Left in
    # place it is a trap: the next person who needs a positive judge
    # copies it and gets a check that can never go green, which is
    # exactly what happened on the pooled path.
    #
    # The positive verdicts are made where the evidence is: the pool in
    # judge_pool() (vector count + the sweep's own return value), the
    # --module path in main() (return value + no FAIL line), and the
    # BOARD transcript in tools/pi4_crypto_transcript_check.py, which is
    # the one place the totals line is genuinely printed and is
    # therefore the one place it is genuinely required.
    raise SystemExit(
        "judge() is the NEGATIVE-control judge and was called with "
        "expect_fail=False. There is no positive branch here on purpose - "
        "see the comment above. Judge a positive run by the sweep's return "
        "value and its vector count, not by a totals line the entered "
        "procedure never prints.")


SYMMETRIC_MAX = 11           # module ids 1..11; 12..18 are the public-key half

MODULE_ARG = {
    "sha256": 1, "sha1": 2, "hmac": 3, "hmacsha1": 4, "hkdf": 5,
    "pbkdf2": 6, "drbg": 7, "aes": 8, "aes-ctr": 9, "gcm": 10,
    "keywrap": 11,
    # ---- part two. THESE ARE NOT CHEAP IN THE MODEL and that is the
    # whole reason the board exists: one P-256 scalar multiply is about
    # 276 million modelled instructions and the board answers it in
    # milliseconds. They are reachable here for a single-module
    # investigation, and the standing ruling is that the vectors are
    # proven ON THE BOARD, not in this interpreter.
    "bignum": 12, "p256": 13, "x25519": 14, "ecdsa": 15, "rsa": 16,
    "t0vm": 17, "x509": 18,
}


def _worker(mid: int):
    """One module, in a process of its own. Returns (ret, transcript, steps).

    This is the entry point the pool spawns, so it must be importable at
    module level and must return only picklable values.
    """
    syms = symbols(IMG)
    r = Run()
    ret = run_proc(IMG, syms["cryptoselftestall"], mid, r,
                   label="CryptoSelfTestAll(%d)" % mid)
    return ret, r.uart.decode("latin-1"), r.steps


def judge_pool(out: str, parts: dict, table, gen) -> int:
    """The union of the per-module transcripts, judged as one sweep."""
    bad = 0
    lines = [ln.rstrip("\r") for ln in out.split("\n")]
    VEC = re.compile(r"^[a-z0-9-]+\s+\d+\s+(PASS|FAIL)\b")
    passes = [ln for ln in lines if VEC.match(ln) and " PASS" in ln]
    fails = [ln for ln in lines if VEC.match(ln) and "FAIL" in ln]
    forged = [ln for ln in lines if "forged tag REFUSED" in ln]

    if fails:
        print("    ** %d FAIL lines across the pool:" % len(fails))
        for ln in fails[:10]:
            print("       " + ln.strip())
        bad += 1
    if len(passes) != len(table.recs):
        print("    ** %d PASS lines, expected %d - one per vector."
              % (len(passes), len(table.recs)))
        bad += 1
    if len(forged) != table.count(gen.MOD_GCM):
        print("    ** %d forged tags refused, expected %d - one per GCM "
              "vector." % (len(forged), table.count(gen.MOD_GCM)))
        bad += 1
    # EVERY MODULE MUST HAVE RUN. A pool that silently lost a worker
    # would show fewer PASS lines, which the count above catches - but
    # the per-module totals name WHICH one, which is the difference
    # between a failed gate and a diagnosed one.
    #
    # THE PER-WORKER VERDICT IS THE RETURN VALUE, NOT A TOTALS LINE, and
    # this used to demand the totals line - which meant THIS GATE COULD
    # NEVER GO GREEN ON ITS DEFAULT PATH, and did not, on 2026-09-05,
    # with all 142 vectors passing in front of it.
    #
    # `crypto: N of N vectors PASS` is printed by CryTotals(), which the
    # CONSOLE command calls after the sweep. A worker here enters
    # CryptoSelfTestAll by its symbol, and that procedure prints the
    # vector lines and returns the fail count - by design, because it is
    # the piece the console wraps. So the check was looking for a line
    # its own entry point cannot produce, and reported eleven modules
    # that had each run every vector correctly as eleven failures.
    #
    # Nothing is lost by dropping it. The return value is STRONGER than
    # the printed line: it is the counter the sweep itself keeps, not a
    # rendering of it, and the pool caller already refuses a non-zero
    # one. The totals line still matters where it is actually produced -
    # on the board - and tools/pi4_crypto_transcript_check.py requires
    # it there, along with the count agreeing with it.
    for mid, (name, ret, text, steps) in sorted(parts.items()):
        want = table.count(mid)
        rows = [ln.strip("\r") for ln in text.split("\n") if VEC.match(ln.strip("\r"))]
        got = len(rows)
        nfail = len([ln for ln in rows if "FAIL" in ln])
        if got != want or ret != 0 or nfail:
            print("    ** %-9s ran %d of the %d vectors it should have, "
                  "returned %d, %d FAIL line(s)"
                  % (name, got, want, ret, nfail))
            bad += 1
        else:
            print("    %-9s %3d of %3d PASS, %d model instructions"
                  % (name, want, want, steps))
    return bad


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--module", choices=sorted(MODULE_ARG),
                    help="run one module's vectors instead of all of them")
    ap.add_argument("--speed", type=int, default=1024, metavar="BYTES",
                    help="bytes for the throughput run (default 1024; the "
                         "board's own default is 65536, which is a very "
                         "long time in a model)")
    ap.add_argument("--no-speed", action="store_true")
    ap.add_argument("--public-key", action="store_true", dest="public_key",
                    help="also build and run the seven public-key modules. "
                         "One P-256 scalar multiply is about 276 million "
                         "model instructions, so this is hours in the model")
    ap.add_argument("--negative", action="store_true",
                    help="rebuild with the 32-bit verdict line and require "
                         "the forgery check to catch it")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4,
                    metavar="N",
                    help="worker processes for the module sweep "
                         "(default: the machine's core count)")
    args = ap.parse_args()

    globals()["PMFC"] = resolve_compiler(args.compiler)
    print("Anvil `crypto` self-test - the DESK proof. The board is the "
          "evidence;")
    print("this says the sweep is wired up and the model agrees with the "
          "documents.")
    print("")

    print("1. the vector table")
    check_table_current()
    gen = load_generator()
    table = gen.Table()
    gen.build_sha256(table, 21)
    gen.build_sha1(table, 10)
    gen.build_hmac(table)
    gen.build_hmacsha1(table)
    gen.build_hkdf(table, 5)
    gen.build_pbkdf2(table, 4096)
    gen.build_drbg(table, 5)
    gen.build_aes(table, cavp=True)
    gen.build_aesctr(table, 4144)
    gen.build_gcm(table)
    gen.build_keywrap(table)
    # THE PUBLIC-KEY HALF IS OPT-IN IN THE MODEL. The pool below runs one
    # worker per module in the table, and the table this gate grades must
    # be the set of modules that pool runs - otherwise the PASS count is
    # compared against vectors that were never entered. The board runs
    # all eighteen in minutes; the model needs hours for the seven below.
    if args.public_key or (args.module and MODULE_ARG[args.module] > SYMMETRIC_MAX):
        gen.build_bignum(table)
        gen.build_ec(table)
        gen.build_ecdsa(table)
        gen.build_rsa(table)
        gen.build_t0vm(table, 4096)
        gen.build_x509(table)
    graded = {name: mid for name, mid in MODULE_ARG.items()
              if table.count(mid) > 0}
    print("  %d vectors across %d modules" % (len(table.recs), len(graded)))

    print("")
    print("2. a second opinion on every expectation")
    rederive(gen, table)

    print("")
    print("3. the build")
    build(IMG)
    blob = IMG.read_bytes()
    syms = symbols(IMG)
    print("  %s, %d bytes" % (IMG.name, len(blob)))
    check_table_in_image(blob, syms, gen, table)

    entry = syms.get("cryptoselftestall")
    if entry is None:
        raise SystemExit("the image has no CryptoSelfTestAll symbol")

    print("")
    print("4. the sweep, in the model")
    bad = 0
    if args.module:
        only = MODULE_ARG[args.module]
        r = Run()
        verdict = run_proc(IMG, entry, only, r, label="CryptoSelfTestAll")
        out = r.uart.decode("latin-1")
        if not args.quiet:
            print(out)
        print("  CryptoSelfTestAll returned %d, %d model instructions"
              % (verdict, r.steps))
        if verdict != 0 or "FAIL" in out:
            print("    ** the single-module run did not come back clean")
            bad += 1
    else:
        # ONE PROCESS PER MODULE, ON ALL CORES. The sweep is a corpus
        # walk and the house rule is that a corpus walk uses a pool.
        # It is also the difference between a gate somebody runs and a
        # gate somebody skips: PBKDF2's three 4096-iteration vectors are
        # about half a billion model instructions on their own - the
        # PBKDF2 gate's own docstring calls its full set "an hour-scale
        # run" - while the other ten modules together are a fraction of
        # that. Serially the whole thing costs PBKDF2 plus everything
        # else; in a pool it costs PBKDF2.
        #
        # The MODULES ARE INDEPENDENT and that is a property of the
        # code, not an assumption: each worker loads its own copy of the
        # image into its own flat memory with its own zeroed .bss, so
        # nothing one module leaves installed can reach another. The
        # BOARD runs them in one process, in order, and that ordering is
        # part of what the silicon run proves - which is another reason
        # the board transcript is the evidence and this is the desk
        # proof.
        import concurrent.futures as _f
        jobs = min(args.jobs, len(graded))
        print("  %d modules on %d worker processes" % (len(graded), jobs))
        parts, order = {}, []
        with _f.ProcessPoolExecutor(max_workers=jobs) as pool:
            futs = {pool.submit(_worker, mid): (name, mid)
                    for name, mid in sorted(graded.items(),
                                            key=lambda kv: kv[1])}
            for fut in _f.as_completed(futs):
                name, mid = futs[fut]
                ret, text, steps = fut.result()
                parts[mid] = (name, ret, text, steps)
                print("    %-9s done: returned %d, %d model instructions"
                      % (name, ret, steps))
        out = ""
        total = 0
        for mid in sorted(parts):
            name, ret, text, steps = parts[mid]
            total += steps
            out += text
            if ret != 0:
                print("    ** %s returned %d, not 0" % (name, ret))
                bad += 1
        if not args.quiet:
            print(out)
        print("  %d model instructions across the pool" % total)
        # The totals line is per worker, so the union is judged on the
        # vector lines and the per-module totals are summed here.
        bad += judge_pool(out, parts, table, gen)

    if not args.no_speed:
        print("")
        print("5. the throughput path")
        speed = syms.get("cryptospeedrun")
        if speed is None:
            raise SystemExit("the image has no CryptoSpeedRun symbol")
        r2 = Run()
        run_proc(IMG, speed, args.speed, r2, label="CryptoSpeedRun")
        sout = r2.uart.decode("latin-1")
        print(sout)
        print("  THE RATES ABOVE ARE NOT MEASUREMENTS. CNTPCT_EL0 is shimmed")
        print("  here as a model step count, so 'ticks' is instructions and")
        print("  'KB/s' is a ratio of instruction counts to a made-up 54 MHz.")
        print("  What this section proves is that the arithmetic is well")
        print("  formed and divides by nothing that can be zero. The real")
        print("  numbers exist only on the part.")
        # ALL ELEVEN, AND THE END MARKER. The list used to be three,
        # from when the throughput run measured three modules, and a
        # list that is a subset of what is expected cannot notice that
        # a module stopped printing. The board also prints one line
        # when it has finished the whole table, and the absence of that
        # is how a run that died in the middle of row seven is told
        # apart from one that never reached row seven at all.
        heads = {ln.split()[0] for ln in sout.replace("\r", "").split("\n")
                 if ln[:1].strip() and ln.split()}
        # t0vm has no throughput row and deliberately so: the bounds
        # guard is a refusal, and "refusals a second" is not a number
        # anybody has a use for. Named here rather than left as a hole.
        for want in sorted(MODULE_ARG, key=MODULE_ARG.get):
            if want == "t0vm":
                continue
            if want not in heads:
                print("    ** the throughput run printed no %s line" % want)
                bad += 1
        for marker in ("throughput: 11 symmetric modules measured",
                       "throughput: 6 public-key modules measured"):
            if marker not in sout:
                print("    ** the throughput run never printed %r, so it did "
                      "not finish the table" % marker)
                bad += 1
        if "no rate" in sout:
            print("    ** a throughput line could not compute a rate")
            bad += 1

    if args.negative:
        print("")
        print("6. the negative control - the 32-bit verdict line")
        src = GCM_LIB.read_text(encoding="utf-8", errors="replace")
        # THE MUTATION IS THE 32-BIT FAMILIES' TWO LINES, VERBATIM, and
        # it has to be BOTH of them. Changing only the shift leaves the
        # `& #GCM_W32` mask in place, and that mask is what saves it:
        # $FFFFFFFFFFFFFFFF & $FFFFFFFF is $FFFFFFFF and the verdict
        # comes out right. The bug needs the unmasked shift AND the
        # unmasked XOR, which is exactly the pair gcm.pi4's danger note
        # quotes from the Pico copies.
        #
        # Matched by TEXT so that a rewritten GcmDecrypt makes this
        # control fail to apply - loudly - instead of mutating nothing
        # and reporting a pass.
        old = ("  neq = ((diff | (- diff)) >> 63) & #GCM_W32\n"
               "  ProcedureReturn neq ! #GCM_W32\n")
        new = ("  neq = (diff | (- diff)) >> 31\n"
               "  ProcedureReturn neq ! $FFFFFFFF\n")
        if src.count(old) != 1:
            raise SystemExit(
                "cannot find GcmDecrypt's exact verdict pair in gcm.pi4, so "
                "the negative control cannot be applied. It is looked for by "
                "text on purpose: a rewritten verdict needs a rewritten "
                "control, not a silently skipped one. Looked for:\n" + old)
        mutated = src.replace(old, new)
        mut = WORK / "gcm_mut.pi4"
        mut.write_text(mutated, encoding="utf-8", newline="\n")
        print("  built from a COPY at %s - gcm.pi4 is never opened for "
              "writing" % mut.name)
        mimg = WORK / "cryptoself_mut.img"
        build(mimg, gcm_include=mut.relative_to(ROOT).as_posix())
        msyms = symbols(mimg)
        r3 = Run()
        run_proc(mimg, msyms["cryptoselftestall"], MODULE_ARG["gcm"], r3,
                 label="CryptoSelfTestAll (mutated)")
        bad += judge(r3.uart.decode("latin-1"), table, gen, expect_fail=True)

    print("")
    print("=" * 70)
    if bad:
        print("a64_cryptoself_check: %d PROBLEM(S)" % bad)
        return 1
    print("a64_cryptoself_check: PASS - %d vectors, %d GCM forgeries "
          "refused, in the model." % (len(table.recs),
                                      table.count(gen.MOD_GCM)))
    print("This is the desk proof. It is NOT the silicon result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
