#!/usr/bin/env python3
"""End-to-end desk gate: a USB stick on the Pi 5 (RP1 xHCI) mounted through the
shared storage seam - FAT32 and exFAT - as the Pi 4 mounts one.

WHAT RUNS, built -t pi5 so every #PMF_CHIP = 2712 branch is the one that
runs: the monitor's own UsbEnumerate() cut from cursor_input.pi4 (the 2712
guard removed, exactly as a64_usb_kbd_pi5_check.py does - this proves the
path the #CAP_USB flip enables), the real pcie.pi4, gpio_rp1.pi4, xhci.pi4,
hid.pi4 and usbmsc.pi4 (the walk hands the stick's slot to MscSetupCurrent:
SET_CONFIGURATION, Configure Endpoint for the bulk pair, TEST UNIT READY,
INQUIRY, READ CAPACITY), then the storage seam exactly as storage.pi4's USB
branch drives it - FsSetRangeReader(@MscReadBlocks), FsSetRangeWriter(@MscWriteBlocks),
FsSetBlockFlusher(@MscFlush), FsSelectPartition(1) - over the shared
Anvil/Storage/fat32.pbi, exfat.pbi and filesystem.pbi.

THE MACHINE: a64_usb_kbd_pi5_check's RP1 + HID bus model, extended here with
what a mass-storage device needs and that model never had: bulk endpoints
(Configure Endpoint reads their dequeue pointers from the input context;
their doorbells walk Normal TRBs with CHAIN/ISP/IOC, No-Ops and Link TRBs,
and post transfer events with residuals) and a SuperSpeed Bulk-Only
Transport stick (CBW/data/CSW; TEST UNIT READY, REQUEST SENSE, INQUIRY,
READ CAPACITY(10), READ(10), WRITE(10), SYNCHRONIZE CACHE(10); anything else
CHECK CONDITION / ILLEGAL REQUEST). Every bulk buffer must arrive as an RP1
bus address (CPU + $10_0000_0000). The volumes are built here with
tools/fs_reference.py (an independent FAT32/exFAT implementation), and the
written file is found and the volume checked with it afterwards.

SCENARIOS: fat32 and exfat - mount partition 1, read HELLO.TXT, create
NEW.TXT, write and flush it; the disk image must then hold NEW.TXT with the
bytes written and fs_reference must find no damage. nostick - nothing on
the bus: the walk completes, XhciBulkReady() is 0, MscReadBlocks refuses,
and nothing hangs (storage would try the next medium).

Desk proof only. Silicon owed.

  py -3 -B tools/a64/a64_usb_msc_pi5_check.py --compiler <PureMetalForge.exe> [--no-breaks]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_hid_check as H              # noqa: E402
import a64_usb_kbd_pi5_check as K      # noqa: E402  RP1 + HID bus, the cut
import fs_reference as FS              # noqa: E402  independent FAT32/exFAT
from a64_interp import A64, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler   # noqa: E402

LOAD = 0x200000
REL_CURSOR = K.REL_CURSOR
LIBS = ("RaspberryPi4/Lib/timer.pi4", "RaspberryPi4/Lib/pcie.pi4",
        "RaspberryPi4/Lib/gpio_rp1.pi4", "RaspberryPi4/Lib/xhci.pi4",
        "Anvil/Bus/usb_core.pbi",
        "RaspberryPi4/Lib/usbmsc.pi4", "RaspberryPi4/Lib/hid.pi4",
        "Anvil/Storage/fat32.pbi", "Anvil/Storage/exfat.pbi",
        "Anvil/Storage/filesystem.pbi")

PART_LBA = 2048
PART_SECTORS = 70000                    # > 65525 one-sector clusters: FAT32
DISK_SECTORS = PART_LBA + PART_SECTORS + 64
HELLO = b"Hello from a Pi 5 USB stick, read through RP1.\r\n"
NEW = bytes((i * 7 + 3) & 0x7F | 0x20 for i in range(64))


# ======================================================================
#  THE STICK - USB 3.0, Bulk-Only Transport (USB MSC BOT 1.0), SCSI SBC.
# ======================================================================
def scsi_be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class BotStick(H.Dev):
    name = "stick"
    speed = H.SPEED_SS

    def __init__(self, disk: bytearray):
        super().__init__()
        self.disk = disk
        self.blocks = len(disk) // 512
        self.state = "cbw"
        self.pending_in = b""
        self.cmd = None
        self.csw = None
        self.writes = 0
        self.flushes = 0
        self.log = []

    def descriptor(self, dtype, index):
        if dtype == 1:
            d = bytearray(H.devdesc(0, 0, 0, 0x1D6B, 0x5A5A, 9))
            d[2:4] = b"\x00\x03"                          # bcdUSB 3.00
            return bytes(d)
        if dtype == 2:
            comp = [6, 0x30, 0, 0, 0, 0]                  # SS endpoint companion
            return H.config(1, [H.iface(0, 2, 8, 6, 0x50),
                                H.epdesc(0x81, 1024, 0, xfer=2), comp,
                                H.epdesc(0x02, 1024, 0, xfer=2), comp])
        return None

    def class_control(self, ctl, rt, req, val, idx, length, buf):
        if rt == 0xA1 and req == 0xFE:                   # GET MAX LUN
            return 1, b"\x00"
        if rt == 0x21 and req == 0xFF:                   # Bulk-Only reset
            self.state, self.pending_in, self.csw = "cbw", b"", None
            return 1, b""
        if rt == 0x02 and req == 0x01:                   # CLEAR_FEATURE(HALT)
            return 1, b""
        return 6, b""

    # ---- the three BOT phases ------------------------------------------
    def bulk_out(self, ctl, data: bytes) -> int:
        if self.state == "cbw":
            if len(data) != 31 or struct.unpack_from("<I", data, 0)[0] != 0x43425355:
                ctl.bad(f"stick: expected a 31-byte CBW, got {len(data)} bytes")
                return 6
            tag, dlen = struct.unpack_from("<II", data, 4)
            flags = data[12]
            cdb = data[15:15 + (data[14] & 0x1F)]
            self.cmd = (tag, dlen, flags, cdb)
            self.execute_in_or_status()
            return 1
        if self.state == "data-out":
            tag, dlen, flags, cdb = self.cmd
            if cdb[0] == 0x2A:
                lba, n = scsi_be32(cdb, 2), struct.unpack_from(">H", cdb, 7)[0]
                if len(data) != n * 512 or lba + n > self.blocks:
                    ctl.bad(f"stick: WRITE(10) lba {lba} n {n} got {len(data)} bytes")
                    self.set_csw(1, dlen)
                else:
                    self.disk[lba * 512:(lba + n) * 512] = data
                    self.writes += 1
                    self.set_csw(0, 0)
            self.state = "csw"
            return 1
        ctl.bad(f"stick: bulk OUT in state {self.state}")
        return 6

    def bulk_in(self, ctl, want: int):
        if self.state == "data-in":
            d, self.pending_in = self.pending_in[:want], self.pending_in[want:]
            if not self.pending_in:
                self.state = "csw"
            return 1, d
        if self.state == "csw":
            self.state = "cbw"
            return 1, self.csw
        ctl.bad(f"stick: bulk IN in state {self.state}")
        return 6, b""

    def set_csw(self, status, residue):
        tag = self.cmd[0]
        self.csw = struct.pack("<IIIB", 0x53425355, tag, residue, status)

    def execute_in_or_status(self):
        tag, dlen, flags, cdb = self.cmd
        op = cdb[0]
        data = None
        status = 0
        if op == 0x00:                                   # TEST UNIT READY
            data = b""
        elif op == 0x03:                                 # REQUEST SENSE
            data = bytes([0x70, 0, 0, 0, 0, 0, 0, 10] + [0] * 10)
        elif op == 0x12:                                 # INQUIRY
            data = bytes([0, 0x80, 4, 2, 31, 0, 0, 0]) + b"ANVIL   " + b"DESK STICK      " + b"1.00"
        elif op == 0x25:                                 # READ CAPACITY(10)
            data = struct.pack(">II", self.blocks - 1, 512)
        elif op == 0x28:                                 # READ(10)
            lba, n = scsi_be32(cdb, 2), struct.unpack_from(">H", cdb, 7)[0]
            if lba + n > self.blocks:
                data, status = b"", 1
            else:
                data = bytes(self.disk[lba * 512:(lba + n) * 512])
        elif op == 0x2A:                                 # WRITE(10)
            self.state = "data-out"
            return
        elif op == 0x35:                                 # SYNCHRONIZE CACHE(10)
            self.flushes += 1
            data = b""
        else:
            data, status = b"", 1
        self.log.append(op)
        data = data[:dlen]
        self.set_csw(status, dlen - len(data))
        if flags & 0x80 and dlen:
            self.pending_in = data
            self.state = "data-in" if data else "csw"
        else:
            self.state = "csw"


class Rp1MscCtl(K.Rp1HidCtl):
    """RP1 + HID bus, plus bulk endpoints."""

    def configure_endpoint(self, slot, in_ctx):
        comp = super().configure_endpoint(slot, in_ctx)
        if comp != 1:
            return comp
        add = self.rd(in_ctx + 4, 4)
        rec = self.slots[slot]
        eps = rec.setdefault("eps", {})
        for dci in range(2, 32):
            if add & (1 << dci):
                ectx = in_ctx + H.CTX_SIZE * (dci + 1)
                deq = self.rd(ectx + 8, 8)
                if (deq & ~0xF) & 63:
                    self.bad(f"bulk ring for DCI {dci} is not 64-byte aligned")
                eps[dci] = {"ring": deq & ~0xF, "deq": 0, "ccs": deq & 1}
                self.wr(rec["out"] + H.CTX_SIZE * dci, 1, 4)     # EP state Running
                self.log.append(f"bulk-ep slot={slot} dci={dci}")
        return comp

    def handle_command(self, at, ty, param, slot, ep: int = 0):
        if ty == 15:                                     # Stop Endpoint
            self.post_event(at & 0xFFFFFFFF, (at >> 32) & 0xFFFFFFFF, 1 << 24,
                            (33 << 10) | (slot << 24))
            return
        super().handle_command(at, ty, param, slot, ep)

    def doorbell(self, index, value):
        rec = self.slots.get(index)
        if index and rec is not None and value in rec.get("eps", {}):
            if not (self.cfg[0x04] & 0x04):
                self.bad("a bulk doorbell with RP1 bus mastering off")
            self.run_bulk(index, value)
            return
        super().doorbell(index, value)

    def run_bulk(self, slot, dci):
        rec = self.slots[slot]
        ep = rec["eps"][dci]
        dev = rec["dev"]
        dir_in = bool(dci & 1)
        for _ in range(64):                              # TDs queued behind one doorbell
            segs, last, ioc = [], None, False
            for _ in range(400):
                at = ep["ring"] + ep["deq"] * 16
                ctl = self.rd(at + 12, 4)
                if (ctl & 1) != ep["ccs"]:
                    break
                ty = (ctl >> 10) & 0x3F
                if ty == 6:
                    if not (ctl & 2):
                        self.bad("a bulk ring's Link TRB has no Toggle Cycle bit")
                    ep["deq"], ep["ccs"] = 0, ep["ccs"] ^ 1
                    continue
                ep["deq"] += 1
                if ty == 8:
                    continue
                if ty != 1:
                    self.bad(f"TRB type {ty} on a bulk ring")
                    return
                segs.append((self.rd(at, 8), self.rd(at + 8, 4) & 0x1FFFF))
                last = at
                if not (ctl & 0x10):                     # no CHAIN: the TD ends
                    ioc = bool(ctl & 0x20)
                    break
            if last is None:
                return
            if not ioc:
                self.bad("a bulk TD ends without TRB_IOC - no event would be posted")
            total = sum(n for _, n in segs)
            if dir_in:
                comp, data = dev.bulk_in(self, total)
                data = data or b""
                pos = 0
                for buf, n in segs:
                    chunk = data[pos:pos + n]
                    for i, b in enumerate(chunk):
                        self.cpu.memory[buf + i] = b     # through the DMA view
                    pos += len(chunk)
                moved = min(len(data), total)
                if comp == 1 and moved < total:
                    comp = 13
            else:
                blob = bytearray()
                for buf, n in segs:
                    blob += bytes(self.cpu.memory.get(buf + i, 0) for i in range(n))
                comp = dev.bulk_out(self, bytes(blob))
                moved = total if comp == 1 else 0
            self.post_event(last & 0xFFFFFFFF, (last >> 32) & 0xFFFFFFFF,
                            (comp << 24) | ((total - moved) & 0xFFFFFF),
                            (32 << 10) | (dci << 16) | (slot << 24))


CORE_BIND = """Procedure.i gate_CtrlIn(rt.i, req.i, val.i, idx.i, *dst, len.i)
  Define n.i
  n = XhciControlIn(rt, req, val, idx, len)
  If n < 0
    ProcedureReturn -1
  EndIf
  If n > 0 And *dst <> 0
    If XhciCopyIn(*dst, n) <= 0
      ProcedureReturn -1
    EndIf
  EndIf
  ProcedureReturn n
EndProcedure
Procedure.i gate_CtrlOut(rt.i, req.i, val.i, idx.i, *src, len.i)
  ProcedureReturn XhciControlOut(rt, req, val, idx, *src, len)
EndProcedure
Procedure HwUsbBindCore()
  UsbCoreSetHost(@gate_CtrlIn, @gate_CtrlOut)
  XhciSetVbusHook(@GateVbus)
EndProcedure
"""

PROGRAM_EXTRA_INCLUDES = '''XIncludeFile "RaspberryPi4/Lib/timer.pi4"
XIncludeFile "RaspberryPi4/Lib/pcie.pi4"
XIncludeFile "RaspberryPi4/Lib/gpio_rp1.pi4"
XIncludeFile "RaspberryPi4/Lib/xhci.pi4"
XIncludeFile "Anvil/Bus/usb_core.pbi"
XIncludeFile "RaspberryPi4/Lib/usbmsc.pi4"
XIncludeFile "RaspberryPi4/Lib/hid.pi4"
XIncludeFile "Anvil/Storage/fat32.pbi"
XIncludeFile "Anvil/Storage/exfat.pbi"
XIncludeFile "Anvil/Storage/filesystem.pbi"
'''

MAIN = r'''
Global Dim gName.a[16]
Global Dim gNew.a[16]
Global Dim gBuf.a[1024]

Procedure PutName(*dst, *src)
  Define i.i
  i = 0
  Repeat
    PokeA(*dst + i, PeekA(*src + i))
    i = i + 1
  Until PeekA(*src + i - 1) = 0
EndProcedure

Procedure Main()
  Define t0.i
  Define n.i
  Define i.i
  t0 = xh_Ticks()
  Chk(UsbEnumerate())
  Chk((xh_Ticks() - t0) / (xh_TickHz() / 1000))
  Chk(Bool(XhciBulkReady() <> 0))
  Chk(MscReady())
  Chk(MscBlockCount())
  If XhciBulkReady() = 0
    Chk(MscReadBlocks(0, 1, @gBuf[0]))
    Chk(nres)
    ProcedureReturn
  EndIf
  ; storage.pi4's USB branch, in its order
  FsSetRangeReader(@MscReadBlocks)
  FsSetRangeWriter(@MscWriteBlocks)
  FsSetBlockFlusher(@MscFlush)
  Chk(FsSelectPartition(1))
  PutName(@gName[0], ?nm_hello)
  Chk(FsOpen(@gName[0]))
  Chk(FsSize())
  n = FsRead(@gBuf[0], 512)
  Chk(n)
  FsClose()
  i = 0
  While i < 48
    Chk(PeekA(@gBuf[0] + i))
    i = i + 1
  Wend
  i = 0
  While i < 64
    PokeA(@gBuf[512] + i, ((i * 7 + 3) & $7F) | $20)
    i = i + 1
  Wend
  PutName(@gNew[0], ?nm_new)
  Chk(Bool(FsCreate(@gNew[0]) <> 0))
  Chk(FsWrite(@gBuf[512], 64))
  FsClose()
  Chk(Bool(FsFlush() <> 0))
  Chk(FsLastError())
  Chk(nres)
EndProcedure

Main()

DataSection
nm_hello:
  Data.a 72, 69, 76, 76, 79, 46, 84, 88, 84, 0
nm_new:
  Data.a 78, 69, 87, 46, 84, 88, 84, 0
EndDataSection
'''


def make_disk(kind: str) -> bytearray:
    img = bytearray(DISK_SECTORS * 512)
    if kind == "fat32":
        FS.mbr(img, [(0x0C, PART_LBA, PART_SECTORS)])
        v = FS.format_fat32(img, PART_LBA, PART_SECTORS)
        first = 3
        v.alloc_contiguous(first, 1)
        o = v.clus_off(first)
        img[o:o + len(HELLO)] = HELLO
        v.add_root_entry(b"HELLO   TXT", 0x20, first, len(HELLO))
        v.set_fsinfo(v.free_count(), first + 1)
    else:
        FS.mbr(img, [(0x07, PART_LBA, PART_SECTORS)])
        v = FS.format_exfat(img, PART_LBA, PART_SECTORS)
        first = v.root + 1
        v.add_root_file("HELLO.TXT", HELLO, first)
        v.fix_boot_checksums()
    return img


def find_new(img: bytes, kind: str):
    """NEW.TXT's bytes, read back by fs_reference's own parse."""
    rep = FS.check_fat32(img, PART_LBA) if kind == "fat32" else FS.check_exfat(img, PART_LBA)
    for path, e in rep.tree.items():
        if path.upper().rstrip("/").split("/")[-1] == "NEW.TXT":
            return rep, e
    return rep, None


def build(compiler, work, root, cursor_text):
    text = K.PROGRAM
    # the kbd gate's program minus its Main, plus usbmsc/timer/filesystem
    head = text.split("Procedure Main()")[0]
    head = head.replace('XIncludeFile "RaspberryPi4/Lib/pcie.pi4"\nXIncludeFile "RaspberryPi4/Lib/gpio_rp1.pi4"\n'
                        'XIncludeFile "RaspberryPi4/Lib/xhci.pi4"\nXIncludeFile "RaspberryPi4/Lib/hid.pi4"\n',
                        PROGRAM_EXTRA_INCLUDES)
    head = head.replace("Procedure.i MscSetupCurrent()\n  ProcedureReturn 0\nEndProcedure\n", "")
    # HwUsbBindCore, whole: the VBUS hook AND the shared USB core bound to
    # the xHCI control pipe, exactly as hw_usb.pi4's (its hwusb_CtrlIn/Out
    # bodies, repeated here because that file cannot be built alone).
    bind = "Procedure HwUsbBindCore()\n  XhciSetVbusHook(@GateVbus)\nEndProcedure\n"
    if head.count(bind) != 1:
        raise SystemExit("the kbd gate's HwUsbBindCore changed - re-aim")
    head = head.replace(bind, CORE_BIND)
    if "usbmsc.pi4" not in head or "MscSetupCurrent()\n  ProcedureReturn 0" in head:
        raise SystemExit("could not adapt the kbd gate's program - re-aim")
    cut = K.without_guard(K.cut(cursor_text, "Procedure.i UsbEnumerate()"))
    text = head.replace("%(CUT)s", cut) + MAIN
    src = work / "usbmsc5.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "usbmsc5.img"
    r = subprocess.run([compiler, "--compile", str(src), "-t", "pi5", "--load-addr",
                        hex(LOAD), "-s", "-o", str(img)], cwd=root,
                       env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode or "pmfc: OK" not in r.stdout or "target BCM2712" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout[-3000:])
    return img


SCENARIOS = ("fat32", "exfat", "nostick")
BOUND_MS = 3000


def run(img, scenario, budget=200_000_000):
    sym = H.load_syms(img)
    cpu = A64(pc=LOAD)
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    disk = make_disk(scenario) if scenario != "nostick" else None
    stick = BotStick(disk) if disk is not None else None
    topo = {3: stick} if stick else {}
    ctl = Rp1MscCtl(cpu, topo, "healthy")
    K.install(cpu, ctl)
    trap = LOAD + sym["_a64_end_trap"]
    done = False
    for _ in range(budget):
        if cpu.pc == trap:
            done = True
            break
        cpu.step()
    nres = cpu.load(sym["global_nres"], 8)
    got = [cpu.load(sym["global_res"] + 8 * i, 8) for i in range(min(nres, 64))]
    got = [v - (1 << 64) if v >= 1 << 63 else v for v in got]
    fails = []
    if not done:
        return [f"the program never reached its end trap in {budget} steps - IT HUNG"]
    want_n = 7 if scenario == "nostick" else 62
    if len(got) < want_n:
        return [f"{scenario}: the program recorded {len(got)} results, want {want_n} "
                f"(it stopped early: enumerate/bulk/ready = {got[:5]})"] + \
               ["model refused: " + v for v in ctl.violations]
    enum_ok, ms, bulk, ready, blocks = got[:5]
    if ms > BOUND_MS:
        fails.append(f"UsbEnumerate took {ms} ms of modelled time (bound {BOUND_MS})")
    if scenario == "nostick":
        if [enum_ok, bulk, ready] != [1, 0, 0] or got[5] != 0:
            fails.append(f"nostick: enumerate {enum_ok} bulk {bulk} ready {ready} "
                         f"MscReadBlocks {got[5]} - want 1, 0, 0, 0")
    else:
        if [enum_ok, bulk, ready, blocks] != [1, 1, 1, DISK_SECTORS]:
            fails.append(f"{scenario}: enumerate/bulk/ready/blocks = {[enum_ok, bulk, ready, blocks]}, "
                         f"want [1, 1, 1, {DISK_SECTORS}]")
        sel, opened, size, nread = got[5:9]
        text = bytes(got[9:9 + 48])
        created, wrote, flushed, fserr = got[57:61]
        if sel == 0 or opened == 0:
            fails.append(f"{scenario}: FsSelectPartition {sel}, FsOpen(HELLO.TXT) {opened}")
        if size != len(HELLO) or nread != len(HELLO) or text != HELLO[:48]:
            fails.append(f"{scenario}: HELLO.TXT size {size} read {nread} bytes {text!r}")
        if created != 1 or wrote != 64 or flushed != 1 or fserr != 0:
            fails.append(f"{scenario}: create {created} write {wrote} flush {flushed} error {fserr}")
        if stick.flushes < 1:
            fails.append(f"{scenario}: no SYNCHRONIZE CACHE reached the stick")
        rep, e = find_new(bytes(disk), scenario)
        if e is None:
            fails.append(f"{scenario}: fs_reference finds no NEW.TXT on the stick")
        elif getattr(e, "data", None) is not None and bytes(e.data)[:64] != NEW:
            fails.append(f"{scenario}: NEW.TXT on the stick holds {bytes(e.data)[:16]!r}...")
        if rep.errors:
            fails.append(f"{scenario}: fs_reference finds damage: {rep.errors[:3]}")
    fails += ["model refused: " + v for v in ctl.violations]
    return fails


MUTANTS = {
    "bulk-buffer-untranslated": ("RaspberryPi4/Lib/xhci.pi4",
        "    at = xh_QueueTrbCy(ring, xh_Dma(addr + done) & $FFFFFFFF, (xh_Dma(addr + done) >> 32) & $FFFFFFFF, f2, f3, cyc)",
        "    at = xh_QueueTrbCy(ring, (addr + done) & $FFFFFFFF, ((addr + done) >> 32) & $FFFFFFFF, f2, f3, cyc)"),
    "stick-never-offered-to-msc": (REL_CURSOR,
        "    If XhciUseSlot(HidOtherSlot(i)) <> 0\n      MscSetupCurrent()\n",
        "    If XhciUseSlot(HidOtherSlot(i)) <> 0\n"),
    "bulk-ring-untranslated": ("RaspberryPi4/Lib/xhci.pi4",
        "  deq = xh_Dma(xh_ringBase[#XHCI_RING_BULK_IN]) | xh_ringCycle[#XHCI_RING_BULK_IN]",
        "  deq = xh_ringBase[#XHCI_RING_BULK_IN] | xh_ringCycle[#XHCI_RING_BULK_IN]"),
}


def make_mutant(name, work):
    rel, old, new = MUTANTS[name]
    tree = work / ("m_" + name)
    for r in LIBS + (REL_CURSOR,):
        text = (ROOT / r).read_bytes().decode("utf-8").replace("\r\n", "\n")
        if r == rel:
            if text.count(old) != 1:
                raise SystemExit(f"mutant {name}: anchor matched {text.count(old)} times in {rel}")
            text = text.replace(old, new, 1)
        dst = tree / r
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    for d in ("RaspberryPi4/Intrinsics",):
        (tree / d).mkdir(parents=True, exist_ok=True)
        for f in (ROOT / d).iterdir():
            if f.is_file():
                (tree / d / f.name).write_bytes(f.read_bytes())
    return tree


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--no-breaks", action="store_true")
    a = ap.parse_args(argv[1:])
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    cc = str(pathlib.Path(resolve_compiler(a.compiler)).resolve())
    cursor = (ROOT / REL_CURSOR).read_bytes().decode("utf-8").replace("\r\n", "\n")
    with tempfile.TemporaryDirectory(prefix="usb-msc-pi5-") as tmp:
        work = pathlib.Path(tmp)
        img = build(cc, work, ROOT, cursor)
        if K.GUARD_SEEN[0]:
            print("NOTE: cursor_input.pi4's UsbEnumerate still opens with the 2712 guard; "
                  "this run proves the path with it removed")
        red = 0
        for sc in SCENARIOS:
            f = run(img, sc)
            if f:
                red += 1
                print(f"FAIL {sc}:")
                for x in f:
                    print("   " + x)
            else:
                print(f"PASS {sc}")
        if red:
            print(f"FAILED: {red} scenario(s)")
            return 1
        if a.no_breaks:
            return 0
        print("mutants - each must go RED:")
        weak = []
        for name in MUTANTS:
            tree = make_mutant(name, work)
            try:
                mimg = build(cc, tree, tree, (tree / REL_CURSOR).read_text(encoding="utf-8"))
            except SystemExit:
                print(f"  {name:28s} refused at compile time (red)")
                continue
            f = run(mimg, "fat32", 60_000_000)
            print(f"  {name:28s} " + (f"red  e.g. {f[0][:90]}" if f else "*** STILL PASSED ***"))
            if not f:
                weak.append(name)
        if weak:
            print("GATE IS WEAK: " + ", ".join(weak))
            return 1
        print(f"PASS: {len(SCENARIOS)} scenarios; {len(MUTANTS)} of {len(MUTANTS)} mutants red.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
