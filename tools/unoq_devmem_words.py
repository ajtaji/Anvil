#!/usr/bin/env python3
"""unoq_devmem_words.py - read the 11ae diff list from Debian on the UNO Q.

Runs ON THE BOARD.  Usage:  sudo python3 unoq_devmem_words.py <addrs.txt>

Prints one line per address, "0xADDRESS NAME = 0xVALUE", which is the form
the bare-metal probe prints too, so the two transcripts diff line for line.

Addresses after a bare "@gated" line are read only when the GPU domain is
powered - the caller is responsible for that, and passes --gated to say so.
Without it they are printed as "SKIPPED (gated)".

Each address is read in its own mmap of one page, and the address is
printed and flushed BEFORE the access.  On 2026-09-06 three reads reset
this SoC outright, so the last line of the output is the instrument's real
finding when it does not come back.
"""
import ctypes
import mmap
import os
import sys

PAGE = 4096


def read_word(libc, fd, addr):
    page = addr & ~(PAGE - 1)
    off = addr - page
    p = libc.mmap(None, PAGE, mmap.PROT_READ, mmap.MAP_SHARED, fd, page)
    if p in (None, 0) or p == ctypes.c_void_p(-1).value:
        return None
    try:
        return ctypes.cast(p + off, ctypes.POINTER(ctypes.c_uint32))[0]
    finally:
        libc.munmap(ctypes.c_void_p(p), PAGE)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gated_ok = "--gated" in sys.argv
    if len(args) not in (1, 2):
        sys.stderr.write(__doc__)
        return 2

    # The output goes to a real file, fsync'd line by line, because a read
    # that resets the SoC takes the page cache with it and the whole value
    # of this instrument is the line it did not get to finish.
    out = open(args[1], "w") if len(args) == 2 else sys.stdout

    def emit(text, end="\n"):
        out.write(text + end)
        out.flush()
        if out is not sys.stdout:
            os.fsync(out.fileno())

    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    gated = False
    try:
        for raw in open(args[0]):
            line = raw.split("#")[0].strip()
            if not line:
                continue
            if line == "@gated":
                gated = True
                emit("--- gated on the GPU domain being powered ---")
                continue
            parts = line.split()
            addr = int(parts[0], 0)
            name = parts[1] if len(parts) > 1 else ""
            if gated and not gated_ok:
                emit("%-12s %-26s SKIPPED (gated)" % (parts[0], name))
                continue
            # say what is about to be touched, and sync it, before touching it
            emit("%-12s %-26s = " % (parts[0], name), end="")
            v = read_word(libc, fd, addr)
            emit("MMAP-REFUSED" if v is None else "0x%08X" % v)
    finally:
        os.close(fd)
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
