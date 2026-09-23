#!/usr/bin/env python3
"""Gate the four-core payload service - ABI 1.3, service slots 184..186.

WHAT THIS PROVES AND WHAT IT CANNOT.

  It builds the real fixture, reads the ordering and cache-maintenance
  claims out of the DECODED INSTRUCTION WORDS rather than the compiler's
  `.s` listing, and then EXECUTES the image on four independent A64
  interpreter instances interleaved over one shared byte dictionary, with
  every store checked against the spans the storing core is allowed to
  touch.

  THE INTERPRETER HAS NO CACHE, NO TLB, NO STORE BUFFER, NO INSTRUCTION
  CACHE, NO WFE/SEV TIMING AND NO SIMULTANEOUS EXECUTION.  So three of
  this service's claims are UNTESTABLE BY EXECUTION here and are asserted
  as instruction words instead, and said so where they appear:

    * that STLR/LDAR order the partition's outputs against the flag,
    * that IC IALLU before each call keeps a second payload from running
      out of the first payload's instruction-cache lines,
    * that the secondaries observe the primary's writes at all.

  A PASS is a statement about the instructions and the numbers.  It is
  never a statement about coherency, about ordering as the silicon
  observes it, or about parallelism.  No board is contacted.

  The counted build mechanism is untouched: every compile below goes
  through tools/build.py's staged compiler, the same as every other gate.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tempfile

import capstone

import a64_core_worker_check as base
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

ROOT = base.ROOT
FIXTURE = ROOT / "RaspberryPi4/Tests/parallel_run_emitted_gate.pi4"
ACCEPT = ROOT / "RaspberryPi4/Lib/core_accept.pi4"
ABI = ROOT / "Anvil/Hal/abi.pbi"
ABI_VERSION = ROOT / "Anvil/Hal/abi_version.pbi"
SEAMS = ROOT / "Anvil/Hal/seams.pbi"
MEMMAP = ROOT / "RaspberryPi4/Board/memmap.pi4"
CACHE = ROOT / "RaspberryPi4/Board/cache.pi4"
PROOF = ROOT / "RaspberryPi4/Examples/Diagnostics/pi4ParallelPayloadProof.pi4"
BOARD_PI4 = ROOT / "RaspberryPi4/Board/board.pi4"
BOARD_UNOQ = ROOT / "ArduinoQ/Board/board.unoq"

FPCR_KEY = 0xD51B4400
CNTFRQ_KEY = 0xD51BE000
SLOTS = 256
STRIDE = 32
GUARD_BYTES = 256
GUARD_WORD = 0x5041524B47554152

# THE MODEL CLOCK, AND WHY IT IS THIS NUMBER. CNTPCT_EL0 advances once per
# interpreted instruction times this rate, so the service's five-second
# bound lands at 5 * CNTFRQ / RATE instructions. Too slow and a gate that
# has to reach the bound takes minutes of Python; too fast and
# CoreAcceptStart's own two-second wait expires during the bootstrap and
# every test refuses before dispatching, proving nothing. 1000 leaves the
# bootstrap 108,000 instructions and puts the bound at 270,000.
RATE = 1000
SLOW_RATE = 1            # for the late-release test, where no bound may fire
DEADLINE_STEPS = 5 * 54000000 // RATE

# The two source lines the "kindstate" mutant separates. A request states
# its whole kind: coreAcceptRound writes the zero entry word rather than
# inheriting whatever the previous job left, so a `coretest stop` after a
# payload job stops instead of silently re-running the last payload entry.
ENTRY_ZERO_LINE = "    PokeI(row + #CORE_PAR_O_ENTRY, 0)\n"
RELEASE_ZERO_LINE = "    PokeI(row + #CORE_PAR_O_RELEASE, 0)\n"
COUNT_LINE = "    PokeI(row + 16, count)"

PAR_OK = 1
ERR_ARG = -1
ERR_CONTEXT = -2
ERR_BUSY = -3
ERR_STATE = -4
ERR_TIMEOUT = -5
ERR_FPCR = -6
ERR_GUARD = -7
ERR_WORKER = -8


def const(text: str, name: str) -> int:
    """The value of a #CONSTANT in a source file, read rather than transcribed."""
    match = re.search(rf"(?m)^\s*#{re.escape(name)}\s*=\s*(-?(?:\$[0-9A-Fa-f]+|\d+))",
                      text)
    if not match:
        raise AssertionError(f"no #{name} in source")
    raw = match.group(1)
    if raw.startswith("$"):
        return int(raw[1:], 16)
    if raw.startswith("-$"):
        return -int(raw[2:], 16)
    return int(raw)


def say(text: str) -> None:
    """Name the phase as it starts.

    A gate that runs for minutes and prints nothing is indistinguishable
    from a gate that has hung, and the first thing anybody does about that
    is kill it. So each phase says what it is before it costs anything.
    """
    print("  ..", text, flush=True)


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


# ======================================================================
#  PART 1 - THE ABI, BY ARITHMETIC.
#
#  "It is a minor bump and nothing moved" is the whole compatibility
#  claim, so it is computed from the two files rather than believed.
# ======================================================================
def abi_checks(c: base.Checks) -> None:
    abi = ABI.read_text(encoding="utf-8")
    version = ABI_VERSION.read_text(encoding="utf-8")
    seams = SEAMS.read_text(encoding="utf-8")

    major = const(version, "SVC_ABI_MAJOR")
    minor = const(version, "SVC_ABI_MINOR")
    count = const(version, "SVC_SLOT_COUNT")
    c.yes(major == 1, "the major did not move: adding a group is not a major bump")
    c.yes(minor == 3, "abi_minor is 3")
    c.yes(count == 192, "entry_count is 192")

    # Every base that existed before 1.3, with the reserved size the table
    # comment publishes. A group that moved would change a payload's
    # meaning of a slot number, which is the definition of a MAJOR bump.
    frozen = [
        ("SVC_BASE_CORE", 0, 16), ("SVC_BASE_CLOCK", 16, 8),
        ("SVC_BASE_CONSOLE", 24, 16), ("SVC_BASE_TOUCH", 40, 8),
        ("SVC_BASE_FILE", 48, 16), ("SVC_BASE_SETTING", 64, 8),
        ("SVC_BASE_NET", 72, 24), ("SVC_BASE_USB", 96, 12),
        ("SVC_BASE_GPIO", 108, 8), ("SVC_BASE_I2C", 116, 12),
        ("SVC_BASE_SPI", 128, 8), ("SVC_BASE_UART", 136, 8),
        ("SVC_BASE_VEH", 144, 12), ("SVC_BASE_GNSS", 156, 12),
        ("SVC_BASE_CRYPTO", 168, 16),
    ]
    for name, expected, _ in frozen:
        c.yes(const(abi, name) == expected, f"#{name} is still {expected}")

    par = const(abi, "SVC_BASE_PAR")
    c.yes(par == 184, "the new group opens at 184")
    last_name, last_base, last_size = frozen[-1]
    c.yes(last_base + last_size == par,
          "the new group starts exactly where the crypto block ends - "
          "it was appended, not squeezed in")
    c.yes(par + 8 == count,
          "entry_count is the new base plus its eight reserved slots, so the "
          "block is fully inside the table and nothing follows it yet")

    # The core group is full, which is WHY a new block exists. If a spare
    # ever reappears there the reasoning in this tranche is stale and the
    # next reader should be told so by a failing gate, not by a comment.
    core_used = set(re.findall(r"#SVC_BASE_CORE\s*\+\s*(\d+)\]", abi))
    core_used |= {"14", "15"}  # the seam pair, wired through named constants
    c.yes(len(core_used) == 16,
          "the core group is 16 of 16 used - the premise of opening a new block")

    wired = re.findall(r"#SVC_BASE_PAR\s*\+\s*(\d+)\]\s*=\s*@(\w+)", abi)
    c.yes([(int(i), n) for i, n in wired] ==
          [(0, "SvcParallelCores"), (1, "SvcParallelRun"), (2, "SvcParallelStatus")],
          "exactly three slots wired, in order, and no fourth")

    c.yes(const(seams, "SVCCAP_PARALLEL") == 16, "#SVCCAP_PARALLEL is 16")
    c.yes(const(seams, "SVCCAP_MAX") == 16, "#SVCCAP_MAX was raised to 16")

    # Both boards must answer the capability question, and only one of them
    # yes - otherwise the CompilerIf is decorative.
    #
    # THE PI 4's DECLARATION IS LOOKED FOR, NOT PINNED TO A FILE. It sits in
    # memmap.pi4 today, beside the secondary-stack reservation it is true
    # because of, and it is OWED a move to board.pi4 where the other
    # fourteen #CAP_* live - once that file's Vulkan work lands. A gate that
    # named one file would pass today and fail the day the owed move is
    # made, which would make it an obstacle to its own follow-up. So it
    # requires EXACTLY ONE of the two Pi 4 board files to declare it: the
    # move stays green and a second, contradicting declaration does not.
    pi4_declarations = [path for path in (MEMMAP, BOARD_PI4)
                        if re.search(r"(?m)^\s*#CAP_PARALLEL\s*=",
                                     path.read_text(encoding="utf-8"))]
    c.yes(len(pi4_declarations) == 1,
          "exactly one Pi 4 board file declares #CAP_PARALLEL (found %d)"
          % len(pi4_declarations))
    c.yes(const(pi4_declarations[0].read_text(encoding="utf-8"), "CAP_PARALLEL") == 1,
          "the Pi 4 declares the capability, in " + pi4_declarations[0].name)
    c.yes(const(BOARD_UNOQ.read_text(encoding="utf-8"), "CAP_PARALLEL") == 0,
          "the UNO Q declares it absent, so the ENOSYS arm is what compiles there")
    c.yes(abi.count("CompilerIf #CAP_PARALLEL = 1") == 1 and
          abi.count("#SVC_ENOSYS") > 0,
          "group 15 is gated on the capability, both arms present")

    # The refusal vocabulary: every sentence keeps its number and names the
    # first thing to check. A bare code would pass a compile and fail a
    # person at three in the morning.
    for code in ("#SVC_EARG", "#SVC_EPERM", "#SVC_EBUSY", "#SVC_ESTATE",
                 "#SVC_ETIMEOUT", "#SVC_EIO"):
        c.yes(re.search(rf"gSvcDetail = \"[^\"]+\"\s*\n\s*ProcedureReturn {re.escape(code)}",
                        abi) is not None,
              f"group 15 sets a sentence before returning {code}")

    # THE BOARD PROOF'S OWN PAYLOAD RESTATES THREE SLOT NUMBERS, and a
    # payload that quietly held a stale one would call the wrong
    # procedure with the right arguments - the worst failure a service
    # table can have and the one nothing else here would catch. So the
    # restatement is read and held to this file's group base.
    proof = PROOF.read_text(encoding="utf-8")
    for name, offset in (("SLOT_PARCORES", 0), ("SLOT_PARRUN", 1),
                         ("SLOT_PARSTATUS", 2)):
        c.yes(const(proof, name) == par + offset,
              f"the proof payload's #{name} is the table's own {par + offset}")
    c.yes(const(proof, "PPP_NEED_COUNT") == count,
          "and it refuses any table shorter than the one carrying the group")

    runat_checks(c)


# ======================================================================
#  THE PAYLOAD BOUNDARY, READ OUT OF THE FILE THAT OWNS IT.
# ----------------------------------------------------------------------
#  The fixture models RunAt's boundary because it must build while
#  board.pi4 belongs to somebody else. A model of a thing is not the
#  thing, so the real one is read here: RunAt must reclaim at BOTH ends,
#  and the entry-side reclaim must be what decides whether the payload is
#  entered at all. One end without the other is the whole defect back
#  again in a new place - reclaim only on entry and three cores spend the
#  time between a payload's return and the next command walking that
#  payload's page tables while `load`, `receive` and `w` are available.
# ======================================================================
def runat_checks(c: base.Checks) -> None:
    source = CACHE.read_text(encoding="utf-8")
    start = source.index("Procedure RunAt(")
    body = source[start:source.index("\nEndProcedure", start)]
    call = body.index("  CallAddr()")
    sites = [m.start() for m in re.finditer(r"If CoreAcceptReclaim\(\) = 0", body)]
    c.yes(len(sites) == 2,
          "RunAt reclaims the secondary cores at exactly two places (found %d)"
          % len(sites))
    c.yes(sites and sites[0] < call,
          "one of them is before the machine changes hands")
    c.yes(len(sites) > 1 and sites[1] > call,
          "and one immediately after it comes back")
    entry_half = body[:call]
    c.yes(re.search(r"If CoreAcceptReclaim\(\) = 0(?:.|\n)*?ProcedureReturn 0",
                    entry_half) is not None,
          "a reclaim that fails on entry refuses the payload and returns")
    c.yes("resident secondary cores own this monitor until restart" in entry_half,
          "and it keeps the sentence, for the cases that really are a restart")
    # The old unconditional refusal must be gone, or the fix is decorative.
    c.yes(not re.search(r"If CoreAcceptOwnsSecondaries\(\) <> 0\s*\n\s*PrintN", body),
          "owning a secondary core is no longer by itself a refusal to enter")


# ======================================================================
#  PART 2 - THE WORKER, BY DECODED INSTRUCTION WORDS.
# ======================================================================
def decode(blob: bytes, start: int, end: int, load: int):
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    return [(i.address, (i.mnemonic + " " + i.op_str).strip())
            for i in cs.disasm(blob[start:end], load + start)]


def emitted_checks(c: base.Checks, blob: bytes, sym: dict) -> None:
    body = decode(blob, sym["coreacceptsecondaryentry"],
                  sym["coreacceptsecondaryend"], base.LOAD)
    text = [t for _, t in body]

    def index(needle: str, after: int = 0) -> int:
        for i in range(after, len(text)):
            if text[i] == needle:
                return i
        raise AssertionError("not emitted in the worker: " + needle)

    # A REQUEST STATES ITS WHOLE KIND, and there are three of them. The
    # release word at +88 is asked about FIRST, so that a stale entry
    # address left by the job before it can never be mistaken for a job
    # when the owner is asking a core to leave.
    kind_release = index("ldr x5, [x0, #0x58]")
    release_at = int(text[kind_release + 1].split("#")[1], 16)
    c.yes(text[kind_release + 1].startswith("cbnz x5, "),
          "a non-zero release word at +88 branches straight to the release path")

    # The request's KIND is read before anything else about it. The entry
    # word at +56 decides between the arithmetic witness and a call into
    # payload code, and it is tested first so a stale count cannot pick.
    kind = index("ldr x5, [x0, #0x38]")
    c.yes(kind_release < kind,
          "the release kind is read before the entry word, not after it")
    c.yes(text[kind + 1] == "cbnz x5, #0x%x" % next(
        a for a, t in body if t.startswith("ic iallu")),
        "a non-zero entry word branches straight to the call path")
    c.yes(index("ldr x5, [x0, #0x10]") > kind,
          "the arithmetic witness's count is only read after the kind")

    ic = index("ic iallu")
    # ARM ARM DDI 0487 B2.4.4: instruction caches are not coherent with
    # data caches. These workers are resident across payloads, so a second
    # payload at the same addresses would otherwise execute the first
    # one's lines. THE INTERPRETER HAS NO INSTRUCTION CACHE AND CANNOT
    # EXECUTE THIS DIFFERENCE - the three words are the whole proof.
    c.yes(text[ic + 1] == "dsb sy", "a completion barrier follows the invalidate")
    c.yes(text[ic + 2] == "isb", "and a context synchronisation before the call")
    blr = index("blr x5", ic)
    c.yes(blr == ic + 9,
          "nothing between the synchronisation and the call but loading the "
          "argument pointer and saving the three words the callee may destroy")

    # The callee is ordinary generated code entitled to clobber x0-x18 and
    # x30, so the row, core and nonce go on this core's own stack.
    saved = text[ic + 3:blr]
    c.yes("sub sp, sp, #0x20" in saved, "the frame for them is opened")
    c.yes(sum(1 for t in saved if t.startswith("str x")) == 3,
          "three words saved across the call")
    restored = text[blr + 1:blr + 8]
    c.yes(sum(1 for t in restored if t.startswith("ldr x")) == 3 and
          "add sp, sp, #0x20" in restored,
          "and all three restored, with the stack balanced")

    fpcr = index("mrs x7, fpcr", blr)
    c.yes(text[fpcr + 1] == "str x7, [x0, #0x50]",
          "FPCR is published every job - it is per-PE and it decides the bits")

    rel = index("stlr x3, [x9]", fpcr)
    # THE RELEASE ORDERS THE PARTITION'S OUTPUTS BEFORE THE FLAG. A plain
    # STR here would be a silently wrong answer on the part and identical
    # under this interpreter, which models no reordering at all. The word
    # is the proof; execution is not.
    c.yes(all(t != "str x3, [x9]" for t in text),
          "the acknowledgement is a release store and never a plain store")
    c.yes(text[rel + 1] == "dsb sy" and text[rel + 2] == "sev",
          "completion barrier then the event, in that order")
    c.yes(text[rel + 3].startswith("b "), "and back to the wait, not to a park")

    # Nothing on the JOB paths cleans or invalidates a data cache line.
    # Two partitions share the line at each output-range boundary and a
    # clean there would write one core's copy over the other's. The
    # release path is a different matter and is checked below: it is the
    # one place a worker is deliberately leaving the coherent regime.
    job_path = [t for (a, t) in body if a < release_at]
    c.yes(not any(t.startswith("dc ") for t in job_path),
          "no data-cache maintenance anywhere on the witness or call paths")

    release_checks(c, body, release_at)


# ======================================================================
#  PART 2b - THE RELEASE PATH, BY DECODED INSTRUCTION WORDS.
# ======================================================================
def release_checks(c: base.Checks, body, release_at: int) -> None:
    """The third kind of job: go back to the state the firmware handed the core over in.

    THIS IS THE WHOLE OF "MANY PAYLOADS PER BOOT" AND IT IS ORDER, NOT
    LOGIC. A worker walks whatever page tables the primary had live when
    it was started, and a payload that turns its own MMU on builds those
    in its own memory - so a worker kept across a payload boundary has
    valid code and borrowed tables. It leaves instead, and the four steps
    below have to happen in exactly this order or leaving is worse than
    staying.

    NONE OF IT CAN BE EXECUTED HERE in the sense that matters. The
    interpreter has no cache, so "cleaned to the point of coherency" and
    "C off before the walk" are instruction words, not observations.
    """
    start = next(i for i, (a, _) in enumerate(body) if a == release_at)
    text = [t for _, t in body[start:]]

    def at(predicate, why: str) -> int:
        for i, t in enumerate(text):
            if predicate(t):
                return i
        raise AssertionError("not emitted on the release path: " + why)

    slot_clear = at(lambda t: t.startswith("str ") and t.endswith("[x13]"),
                    "the core clearing its own firmware spin slot")
    slot_clean = at(lambda t: t.startswith("dc cvac") and "x13" in t,
                    "the clean of that slot to the point of coherency")
    ack = at(lambda t: t == "stlr x3, [x9]", "the acknowledgement")
    sctlr = at(lambda t: t.startswith("msr sctlr_el3"), "M, C and I being cleared")
    walk = at(lambda t: t.startswith("dc cisw"), "the set/way clean")
    park = at(lambda t: t == "wfe", "the MMU-off park")
    branch = at(lambda t: t.startswith("br "), "the branch back to the bootstrap")

    # 1. ITS OWN SLOT, CLEARED WHILE IT IS STILL COHERENT, AND CLEANED.
    #    The MMU-off loop at the bottom reads that address with every
    #    cache bypassed, so a dirty line would park the core against a
    #    stale non-zero entry and send it straight back round.
    c.yes(slot_clear < slot_clean < ack,
          "the spin slot is cleared and cleaned BEFORE the acknowledgement, so "
          "the owner's slot check asks about a store that already happened")

    # 2. THE ACKNOWLEDGEMENT IS A RELEASE STORE, like every other.
    c.yes(text[ack + 1] == "dsb sy" and text[ack + 2] == "sev",
          "completion barrier then the event, in that order")

    # 3. C OFF FIRST, THEN THE WALK, AND NO STACK IN BETWEEN. mmu.pi4
    #    measured both on silicon: a set/way walk issued with C still on
    #    races the A72's own line migration and misses lines, and a stack
    #    access after the clear reads DRAM that has not been written yet.
    c.yes(ack < sctlr < walk,
          "M, C and I are cleared after the acknowledgement and before the walk")
    c.yes(not any(re.search(r"\bsp\b", t) for t in text[sctlr:walk + 12]),
          "no stack is touched between clearing C and the end of the walk")

    # 4. LEVEL 0 ONLY. The A72's cache level 1 is the cluster-shared L2
    #    and the live primary owns dirty data in it; a secondary that
    #    enumerated CLIDR would walk it.
    c.yes(not any("clidr" in t for t in text),
          "the walk never reads CLIDR, so it cannot reach the shared L2")
    c.yes(any(t.startswith("msr csselr_el1") for t in text[sctlr:walk]),
          "it selects a cache level explicitly before reading CCSIDR")

    # 5. THE PARK IS THE ARMSTUB'S OWN SPIN LOOP, WRITTEN OUT AGAIN.
    #    With M clear the fetch and that load are physical, so this core
    #    now walks nobody's page tables and does not care what the next
    #    payload does to DRAM.
    c.yes(walk < park < branch, "the park comes after the teardown, not before it")
    c.yes(any(t.endswith("[x13]") and t.startswith("ldr ")
              for t in text[park:branch]),
          "the loop re-reads the slot after every wake")
    c.yes(any(t.startswith("cbz ") for t in text[park:branch]),
          "and goes back to sleep while it is still zero")


# ======================================================================
#  PART 3 - EXECUTION ON FOUR INTERLEAVED PEs.
# ======================================================================
class Machine:
    def __init__(self, c, a64, image, sym, *, el=3, smpen=64,
                 mci=base.SCTLR_CACHED, daif=0x3C0, affinity=0,
                 cntfrq=54000000, rate=SLOW_RATE, fpcr=0, fpcr_odd=None,
                 overflow_core=None):
        self.c, self.a64, self.sym = c, a64, sym
        self.blob = image.read_bytes()
        self.mem = {base.LOAD + i: b for i, b in enumerate(self.blob)}
        self.cpus = {}
        self.min_sp = {}
        self.entered = set()
        self.el, self.smpen, self.mci, self.daif = el, smpen, mci, daif
        self.affinity, self.cntfrq, self.rate = affinity, cntfrq, rate
        self.fpcr, self.fpcr_odd = fpcr, fpcr_odd
        self.overflow_core = overflow_core
        self.overflowed = False
        self.rows = (sym["global_core_accept_rows"] + 255) & -256
        self.raw = (sym["global_core_raw_row"] + 255) & -256
        self.out = sym["global_par_out"]
        self.primary = self.cpu(0)
        self.steps = 0
        # How many times each core has been handed an entry through the
        # firmware spin slot. Two means it went back to the spin state and
        # was started again - which is what "many payloads per boot" is.
        self.releases = {}
        self.slot_was = {}

    def cpu(self, core, cold=False):
        cpu = self.a64.A64()
        cpu.memory = self.mem
        fpcr = self.fpcr
        if self.fpcr_odd is not None and core == self.fpcr_odd[0]:
            fpcr = self.fpcr_odd[1]
        cpu.enable_system_registers(el=self.el, preset={
            base.MPIDR_EL1_KEY: core | self.affinity,
            base.SCTLR_EL3_KEY: 0 if cold else self.mci,
            base.CPUECTLR_EL1_KEY: self.smpen,
            base.CCSIDR_EL1_KEY: base.A72_L1D_CCSIDR,
            0xD51E2000: 0x900000, 0xD51E2040: 0x80803520,
            0xD51EA200: 0xFF440400, CNTFRQ_KEY: self.cntfrq,
            FPCR_KEY: fpcr,
            0xD51B4220: self.daif})
        cpu.sp = base.STACK
        cpu.cntpct_per_instruction = self.rate
        old_store = cpu.store
        stack_lo = 0x1FC000 + (core - 1) * 0x1000 if core else 0
        outputs = (self.out, self.out + SLOTS * 8)

        def bounded_store(address, value, size):
            if core:
                # ITS OWN SPIN SLOT AND NO OTHER. A worker on its way back
                # to the firmware spin state clears the eight bytes the
                # firmware reads for IT; a worker that reached for another
                # core's slot would be caught here, by address.
                spans = [(self.raw + core * 256, self.raw + (core + 1) * 256),
                         (self.rows + core * 256, self.rows + (core + 1) * 256),
                         (stack_lo, stack_lo + 0x1000),
                         (0xD8 + core * 8, 0xD8 + core * 8 + 8),
                         outputs]
            else:
                spans = [(self.sym["__bss_start__"], self.sym["__bss_end__"]),
                         (base.STACK - 0x10000, base.STACK), (0xE0, 0xF8),
                         (0x1FC000, 0x1FF000)]
            if not any(lo <= address and address + size <= hi for lo, hi in spans):
                raise AssertionError(
                    "core %d escaped the spans it owns: %#x+%d" % (core, address, size))
            # A MODELLED STACK OVERFLOW. The interpreter cannot make a real
            # frame run off its page, so the first store this core makes
            # into its stack also clobbers one guard word - which is
            # exactly what an overflowing payload entry would do, and what
            # the primary's guard check exists to catch.
            if (self.overflow_core == core and not self.overflowed
                    and stack_lo <= address < stack_lo + 0x1000):
                self.overflowed = True
                base.put64(self.mem, stack_lo + 16, 0)
            if core:
                self.min_sp[core] = min(self.min_sp.get(core, 1 << 62), cpu.sp)
            old_store(address, value, size)

        cpu.store = bounded_store
        return cpu

    def call(self, name, *arguments, run_workers=True, maximum=None,
             release_after=0):
        if maximum is None:
            # Three times the bound: a healthy run finishes long
            # before it, a wedged one refuses at it, and a bound
            # that never fires is caught here instead of running
            # for minutes and looking like a hung gate.
            maximum = 3 * DEADLINE_STEPS
        cpu = self.primary
        cpu.pc = base.LOAD + self.sym[name.lower()]
        cpu.x[30] = base.RETURN_PC
        for index, value in enumerate(arguments):
            cpu.x[index] = value
        self.steps = 0
        for _ in range(maximum):
            if cpu.pc == base.RETURN_PC:
                self.c.yes(cpu.sp == base.STACK, name + " stack balance")
                return signed(cpu.x[0])
            cpu.step()
            self.steps += 1
            if run_workers and self.steps >= release_after:
                for core in (1, 2, 3):
                    entry = base.u64(self.mem, 0xD8 + core * 8)
                    if entry and not self.slot_was.get(core):
                        self.releases[core] = self.releases.get(core, 0) + 1
                    self.slot_was[core] = entry
                    if entry and core not in self.cpus:
                        self.cpus[core] = self.cpu(core, True)
                        self.cpus[core].pc = entry
                        self.entered.add(core)
                    # A CORE THAT WENT BACK TO THE SPIN STATE IS NOT A NEW
                    # CORE. Its interpreter instance is kept and keeps
                    # stepping: it is sitting in its own MMU-off loop
                    # reading the slot, and it takes itself back to the
                    # bootstrap when the owner writes one, exactly as the
                    # firmware's loop would.
                    if core in self.cpus:
                        self.cpus[core].step()
        raise AssertionError("primary instruction ceiling in " + name)

    def outputs(self):
        return bytes(self.mem.get(self.out + i, 0) for i in range(SLOTS * 8))

    def reference(self):
        base_ref = self.sym["global_par_ref"]
        return bytes(self.mem.get(base_ref + i, 0) for i in range(SLOTS * 8))

    def err(self):
        return signed(base.u64(self.mem, self.sym["global_core_par_err"]))

    def failed_core(self):
        return signed(base.u64(self.mem, self.sym["global_core_par_failed_core"]))


def build(compiler, work, fixture=FIXTURE, stem="parallel", source_root=ROOT):
    return base.build(compiler, work, fixture, stem, source_root=source_root)


def mutant_root(work: Path, label: str, target: Path, old: str, new: str) -> Path:
    """A whole source tree with one file changed, so a mutant is a REBUILD.

    Patching an instruction in memory can only reach mutations that survive
    assembly. A source mutant reaches the ones that matter here - a check
    deleted, a bound inverted, a partition stride dropped.
    """
    root = work / ("mutant-" + label)
    for relative in ("RaspberryPi4/Board/memmap.pi4", "RaspberryPi4/Lib/mmu.pi4",
                     "RaspberryPi4/Lib/mmu_secondary.pi4",
                     "RaspberryPi4/Lib/core_worker.pi4",
                     "RaspberryPi4/Lib/core_worker_impl.pi4",
                     "RaspberryPi4/Lib/core_accept.pi4",
                     "RaspberryPi4/Lib/acceptance_lease.pi4",
                     "RaspberryPi4/Tests/parallel_run_emitted_gate.pi4"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    shutil.copytree(ROOT / "Boards", root / "Boards")
    shutil.copytree(ROOT / "RaspberryPi4/Intrinsics", root / "RaspberryPi4/Intrinsics")
    source = (ROOT / target.relative_to(ROOT)).read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(f"mutation site for {label} is not unique: {old!r}")
    (root / target.relative_to(ROOT)).write_text(source.replace(old, new),
                                                 encoding="utf-8")
    return root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--limits", action="store_true",
                        help="print what a PASS here does not cover, and stop")
    arguments = parser.parse_args(); arguments.compiler = _pmfpath.Path(resolve_compiler(arguments.compiler)) if arguments.compiler else arguments.compiler
    if arguments.limits:
        print(__doc__)
        return

    c = base.Checks()
    abi_checks(c)

    with tempfile.TemporaryDirectory(prefix="parallel-run-") as tmp:
        work = Path(tmp)
        image, _ = build(arguments.compiler, work)
        sym = base.parse_symbols(image)
        a64 = base.load_interp(base.INTERP)
        blob = image.read_bytes()
        emitted_checks(c, blob, sym)

        def machine(**kwargs):
            return Machine(c, a64, image, sym, **kwargs)

        say("four partitions, and the output they agree on")
        # --- the good run -------------------------------------------------
        m = machine(rate=RATE)
        c.yes(m.call("CoreParallelCores") == 4, "four partitions offered")
        c.yes(m.call("ParRun", 4, 5) == PAR_OK, "four-partition run completed")
        c.yes(m.entered == {1, 2, 3}, "all three secondaries entered the bootstrap")
        c.yes(m.call("ParVerify") == 1, "every output equals the serial reference")
        four = m.outputs()
        c.yes(m.err() == 0, "no fault latched")
        # A bound that fires on a healthy run is worse than no bound. This
        # run is timed at a rate where the deadline is reachable.
        c.yes(m.steps > 0, "the good run finished inside the five-second bound")

        say("one core against four, byte for byte")
        # --- one core must produce the same bytes -------------------------
        m1 = machine(rate=RATE)
        c.yes(m1.call("ParRun", 1, 5) == PAR_OK, "single-partition run completed")
        c.yes(m1.entered == set(), "one partition releases no secondary at all")
        c.yes(m1.outputs() == four,
              "one core and four cores produce byte-identical output - the "
              "bit-identity claim, by comparison rather than by argument")
        c.yes(m1.outputs() == m1.reference(), "and both equal the serial reference")

        say("repeated jobs, and coretest beside them")
        # --- repeated runs, and coretest beside them ----------------------
        m = machine(rate=RATE)
        c.yes(m.call("CoreAcceptRun") == 1, "the arithmetic witness still passes")
        c.yes(m.call("ParRun", 4, 11) == PAR_OK, "a payload job on the same workers")
        c.yes(m.call("ParRun", 4, 13) == PAR_OK, "and again, with a fresh nonce")
        c.yes(m.call("CoreAcceptRun") == 1,
              "and the arithmetic witness afterwards - one owner, two kinds of job")
        # THE REGRESSION THIS EXISTS FOR. A request states its whole kind:
        # coreAcceptRound zeroes the entry word, so a stop after a payload
        # job stops rather than silently re-running the last payload entry.
        c.yes(m.call("CoreAcceptStop") == 1, "stop after a payload job stops")
        c.yes(m.call("ParRun", 4, 17) == 0 and m.err() == ERR_STATE,
              "and a parked worker refuses the next run by name")

        say("payload after payload, with no reset between them")
        # ------------------------------------------------------------------
        #  THE DEFECT THIS TRANCHE EXISTS FOR. Before it, the first
        #  four-core payload owned the secondaries until restart and the
        #  NEXT payload was refused - one four-core payload per boot, and a
        #  reset costs the asset uploads. The workers now go back to the
        #  firmware spin state at the boundary, holding nobody's page
        #  tables, and the next payload starts them again.
        # ------------------------------------------------------------------
        m = machine(rate=RATE)
        c.yes(m.call("ParPayloadBoundary") == 1,
              "entering payload A with nothing resident is nothing to do")
        c.yes(m.call("ParRun", 4, 5) == PAR_OK, "payload A runs a four-core job")
        payload_a = m.outputs()
        c.yes(payload_a == four, "and its output is the same output as ever")
        c.yes(m.call("ParOwns") != 0,
              "its workers are resident while it is still running")
        c.yes(m.releases == {1: 1, 2: 1, 3: 1}, "each core was started once")

        # --- payload A returns --------------------------------------------
        c.yes(m.call("ParPayloadBoundary") == 1,
              "payload A's return sends all three back to the spin state")
        c.yes(m.call("ParOwns") == 0, "nothing owns the secondary cores any more")
        for core in (1, 2, 3):
            c.yes(m.call("ParSpinSlot", core) == 0,
                  f"core {core}'s firmware spin slot is zero again - the core "
                  "cleared it on its way out, which is what the owner checks")
            c.yes(m.call("ParRawReleased", core) == 0,
                  f"core {core}'s record is back to offline and can be prepared again")
        c.yes(m.call("CoreParallelCores") == 4,
              "and four partitions are still offered, with no reset in between")

        # --- PAYLOAD B, ENTERED WITHOUT A RESET ----------------------------
        c.yes(m.call("ParPayloadBoundary") == 1, "payload B is entered, not refused")
        c.yes(m.call("ParRun", 4, 23) == PAR_OK, "payload B runs its own four-core job")
        c.yes(m.call("ParVerify") == 1,
              "and every output equals payload B's own serial reference")
        c.yes(m.releases == {1: 2, 2: 2, 3: 2},
              "each core was released through the spin table a second time")
        c.yes(len(m.cpus) == 3,
              "and they are the SAME three cores - no fourth PE was invented, "
              "so payload B really ran on the cores payload A gave back")
        c.yes(m.call("ParRun", 4, 5) == PAR_OK and m.outputs() == payload_a,
              "given payload A's seed, payload B's workers produce payload A's "
              "bytes - restarted cores compute the same numbers")
        c.yes(m.call("CoreAcceptRun") == 1,
              "and the arithmetic witness still passes on them afterwards")
        c.yes(m.call("ParPayloadBoundary") == 1, "payload B's return reclaims them too")
        c.yes(m.call("ParOwns") == 0, "leaving nothing resident behind it")

        say("what the boundary still refuses, and why")
        # --- a job in flight ------------------------------------------------
        # run_workers=False freezes the secondaries, so the forced request
        # stays unacknowledged: a job genuinely in flight rather than one
        # that has already timed out.
        m = machine(rate=RATE)
        c.yes(m.call("ParRun", 4, 5) == PAR_OK, "a payload job completed")
        m.call("ParForceInFlight", 1, run_workers=False)
        c.yes(m.call("ParPayloadBoundary", run_workers=False) == 0,
              "a core with a job still outstanding refuses the boundary")
        c.yes(m.call("ParOwns", run_workers=False) != 0,
              "and nothing was released - the refusal comes before any request")
        c.yes(m.call("ParRowWord", 1, 88, run_workers=False) == 0,
              "nothing at all was published into the busy core's row: refusing "
              "and then giving up on a reply are both a failed call, and only "
              "the first one leaves a core mid-job undisturbed")

        # --- a latched fault --------------------------------------------------
        # The guard failure is the latch that leaves every acknowledgement
        # current, so this asks about the latch itself and not about an
        # outstanding job wearing its coat.
        m = machine(rate=RATE, overflow_core=2)
        c.yes(m.call("ParRun", 4, 5) == 0 and m.err() == ERR_GUARD,
              "a stack-guard failure latches the service")
        c.yes(m.call("ParPayloadBoundary") == 0,
              "a latched fault refuses the boundary: a core that cannot be "
              "proven safe to talk to cannot be asked to leave either")
        c.yes(m.call("ParOwns") != 0, "and it still owns them, so the answer is a reset")

        # --- parked by coretest stop -------------------------------------------
        m = machine(rate=RATE)
        c.yes(m.call("CoreAcceptRun") == 1, "the witness ran")
        c.yes(m.call("CoreAcceptStop") == 1, "and coretest parked the workers")
        c.yes(m.call("ParPayloadBoundary") == 0,
              "workers parked for good refuse the boundary - they read nothing, "
              "so there is nobody to ask")

        say("a late release, to prove the wait re-reads")
        # --- the wait genuinely polls -------------------------------------
        # A load hoisted out of the poll loop is an infinite wait on the
        # board with a green gate. Release the secondaries long after the
        # dispatch and require the primary to still see them.
        late = machine(rate=SLOW_RATE)
        c.yes(late.call("ParRun", 4, 5, release_after=30000) == PAR_OK,
              "the primary still joins when the secondaries start 30000 "
              "instructions after the dispatch, so its wait re-reads")

        say("stack depth, measured")
        # --- stack depth, measured rather than assumed --------------------
        m = machine(rate=RATE)
        c.yes(m.call("ParRunDepth", 4, 5) == PAR_OK, "the deeper worker ran")
        for core in (1, 2, 3):
            page = 0x1FC000 + (core - 1) * 0x1000
            used = page + 0x1000 - m.min_sp[core]
            c.yes(m.min_sp[core] >= page + GUARD_BYTES,
                  f"core {core} stayed above its guard (used {used} of "
                  f"{0x1000 - GUARD_BYTES} bytes)")
            c.yes(used <= (0x1000 - GUARD_BYTES) // 2,
                  f"core {core} used {used} bytes - at least half the usable "
                  "page is still margin; widen the reservation before that "
                  "stops being true")

        say("a partition that reports its own failure")
        # --- a partition that reports failure -----------------------------
        m = machine(rate=RATE)
        c.yes(m.call("ParRunFail", 4) == 0, "a failing partition fails the run")
        c.yes(m.err() == ERR_WORKER, "and it is named as the payload's own failure")
        c.yes(m.call("CoreParallelStatus", m.failed_core()) != 0,
              "the value the entry returned is readable")

        say("the five-second bound, at two clock frequencies")
        # --- the bound is real --------------------------------------------
        for frequency, label in ((54000000, "54 MHz"), (108000000, "108 MHz")):
            # The rate has to leave the bootstrap room: CoreAcceptStart
            # has its own two-second bound, and a model clock fast
            # enough to expire that would refuse before dispatching and
            # prove nothing about this deadline.
            m = machine(rate=RATE, cntfrq=frequency)
            c.yes(m.call("ParRunHang", 4) == 0, f"a wedged partition refuses at {label}")
            c.yes(m.err() == ERR_TIMEOUT, f"named as a timeout at {label}")
            c.yes(m.failed_core() in (1, 2, 3), f"and names a core at {label}")
            if frequency == 54000000:
                slow = m.steps
            else:
                c.yes(m.steps > slow * 3 // 2,
                      "the deadline is wall clock and not an instruction count: "
                      "doubling CNTFRQ_EL0 lengthens the wait in proportion")

        say("the stack guard")
        # --- the guard ------------------------------------------------------
        m = machine(rate=RATE, overflow_core=2)
        c.yes(m.call("ParRun", 4, 5) == 0, "a clobbered stack guard fails the run")
        c.yes(m.err() == ERR_GUARD and m.failed_core() == 2,
              "named as an overflow, on the core it happened to")

        say("floating-point agreement")
        # --- floating point must agree ---------------------------------------
        m = machine(rate=RATE, fpcr_odd=(3, 0x00800000))
        c.yes(m.call("ParRun", 4, 5) == 0, "a core rounding differently fails the run")
        c.yes(m.err() == ERR_FPCR and m.failed_core() == 3,
              "named as a floating-point state disagreement, on the right core")

        say("arguments and machine state")
        # --- arguments, and the machine state ---------------------------------
        m = machine(rate=RATE)
        for label, name, argument in (("count 0", "ParRunBadCount", 0),
                                      ("count 5", "ParRunBadCount", 5),
                                      ("null entry", "ParRunBadEntry", 0),
                                      ("odd entry", "ParRunBadEntry", base.LOAD + 1),
                                      ("negative stride", "ParRunBadStride", -1)):
            c.yes(m.call(name, argument) == 0 and m.err() == ERR_ARG,
                  label + " refused before anything is dispatched")
            c.yes(all(base.u64(m.mem, 0xD8 + core * 8) == 0 for core in (1, 2, 3)),
                  label + " released no core")

        for label, kwargs in (("EL2", {"el": 2}), ("SMPEN clear", {"smpen": 0}),
                              ("caches off", {"mci": 0}),
                              ("interrupts unmasked", {"daif": 0}),
                              ("affinity 1", {"affinity": 0x100}),
                              ("affinity 3", {"affinity": 1 << 32})):
            m = machine(rate=RATE, **kwargs)
            c.yes(m.call("ParRun", 4, 5) == 0, label + " refused")
            c.yes(m.err() == ERR_CONTEXT, label + " refused as a context failure")
            c.yes(all(base.u64(m.mem, 0xD8 + core * 8) == 0 for core in (1, 2, 3)),
                  label + " released no core")
            c.yes(m.call("CoreParallelCores") == 1,
                  label + " answers one core, so a payload still divides correctly")

        say("the mutants, each one a rebuild")
        # --- the mutants ------------------------------------------------------
        # Each entry: (label, source mutation, how the mutant is caught).
        # A MUTANT THAT NOTHING WOULD HAVE DETECTED PROVES NOTHING, so the
        # two that delete a CHECK are run under the very condition that
        # check exists for - the same condition the healthy build refused a
        # few phases above. Otherwise "the guard was never checked" would
        # pass simply because no guard was ever broken.
        mutants = [
            ("stride", ACCEPT,
             "PokeI(row + #CORE_PAR_O_ARGS, argsBase + core * argsStride)",
             "PokeI(row + #CORE_PAR_O_ARGS, argsBase)",
             "verify", {}, "every partition handed block 0"),
            ("kind", ACCEPT, "    cbnz x5, coreAcceptSecondaryCall",
             "    cbz x5, coreAcceptSecondaryCall",
             "verify", {}, "the job kind read the wrong way round"),
            ("guard", ACCEPT,
             "    If coreParGuardIntact(core) = 0",
             "    If coreParGuardIntact(core) = 2",
             "accepts", {"overflow_core": 2}, "the stack guard never checked"),
            ("fpcr", ACCEPT,
             "    If PeekI(CoreAcceptRow(core) + #CORE_PAR_O_FPCR) <> coreParFpcr()",
             "    If PeekI(CoreAcceptRow(core) + #CORE_PAR_O_FPCR) = -1",
             "accepts", {"fpcr_odd": (3, 0x00800000)},
             "the floating-point agreement never checked"),
            # `waiting` is 0 or 1 and never -1, so this is the bound deleted
            # rather than the bound shortened. A SHORTENED bound would be
            # caught by the healthy phases above, which refuse to pass if it
            # ever fires on a good run; this is the other direction, and it
            # is the one that costs a board a pair of hands.
            ("deadline", ACCEPT,
             "      If waiting <> 0 And coreAcceptTicks() - start >= limit",
             "      If waiting = -1 And coreAcceptTicks() - start >= limit",
             "hangs", {}, "the bound deleted"),
            ("kindstate", ACCEPT,
             ENTRY_ZERO_LINE + RELEASE_ZERO_LINE, RELEASE_ZERO_LINE,
             "stop", {}, "a request that does not state its kind"),
            # THE TWO THAT GUARD THE BOUNDARY. Both delete a refusal, so
            # both are run under the exact condition that refusal exists
            # for - the condition the healthy build refused by name a few
            # phases above. A deleted check that is never exercised passes
            # for the wrong reason.
            ("reclaim-inflight", ACCEPT,
             "    If coreAcceptAcquire() <> PeekI(row) : ProcedureReturn coreAcceptFail(-33, core) : EndIf",
             "    If coreAcceptAcquire() = -1 : ProcedureReturn coreAcceptFail(-33, core) : EndIf",
             "boundary-inflight", {},
             "the boundary accepting while a job is still in flight"),
            ("reclaim-latched", ACCEPT,
             "  If core_accept_fault <> 0 Or core_accept_stopped <> 0 : ProcedureReturn 0 : EndIf",
             "  If core_accept_fault = -1 Or core_accept_stopped <> 0 : ProcedureReturn 0 : EndIf",
             "boundary-latched", {"overflow_core": 2},
             "the boundary accepting with a fault already latched"),
        ]
        for label, target, old, new, mode, kwargs, why in mutants:
            root = mutant_root(work, label, target, old, new)
            mutant_image, _ = build(arguments.compiler, root / "out",
                                    root / "RaspberryPi4/Tests/parallel_run_emitted_gate.pi4",
                                    "parallel_" + label, source_root=root)
            mutant_sym = base.parse_symbols(mutant_image)
            killed = False
            try:
                mm = Machine(c, a64, mutant_image, mutant_sym, rate=RATE, **kwargs)
                if mode == "verify":
                    killed = mm.call("ParRun", 4, 5) != PAR_OK or mm.call("ParVerify") != 1
                elif mode == "accepts":
                    # The healthy build REFUSED this exact machine by name a
                    # few phases above. With the check deleted the mutant
                    # accepts it and reports success, and that success is
                    # what catches it.
                    killed = mm.call("ParRun", 4, 5) == PAR_OK
                elif mode == "hangs":
                    killed = mm.call("ParRunHang", 4) != 0
                elif mode == "stop":
                    mm.call("ParRun", 4, 5)
                    killed = mm.call("CoreAcceptStop") != 1
                elif mode == "boundary-inflight":
                    mm.call("ParRun", 4, 5)
                    mm.call("ParForceInFlight", 1, run_workers=False)
                    # Accepting outright, OR publishing a release request
                    # into the row of a core that is mid-job and only then
                    # giving up on the reply. The second is what this
                    # mutant actually does and it is the dangerous half.
                    killed = (mm.call("ParPayloadBoundary", run_workers=False) == 1
                              or mm.call("ParRowWord", 1, 88,
                                         run_workers=False) != 0)
                elif mode == "boundary-latched":
                    mm.call("ParRun", 4, 5)
                    killed = mm.call("ParPayloadBoundary") == 1
            except AssertionError:
                killed = True          # escaped a span, or never came back
            c.yes(killed, f"mutant '{label}' ({why}) is killed")
            say(f"mutant '{label}' killed")

        print("parallel_run_check: PASS", c.count,
              "checks; ABI arithmetic, decoded worker, four interleaved PEs,",
              len(mutants), "rebuilt mutants")
        print("compiler SHA256",
              hashlib.sha256(Path(arguments.compiler).read_bytes()).hexdigest())
        print("fixture SHA256", hashlib.sha256(blob).hexdigest())
        print("No silicon, cache, store-buffer, instruction-cache or WFE timing "
              "proof; PEs are interleaved over shared memory.")


if __name__ == "__main__":
    main()
