#!/usr/bin/env python3
"""unoq_devmem_dump.py - dump a physical window from Debian on the UNO Q.

Runs ON THE BOARD.  Usage:  sudo python3 unoq_devmem_dump.py <base> <len> <out.bin>

Why this exists rather than `dd if=/dev/mem`: on arm64 /dev/mem's read()
path copies with an ordinary memcpy, and the window is mapped
Device-nGnRnE, so the first unaligned byte of that memcpy takes an
alignment fault and dd reports "Bad address" for every register window on
the SoC.  Measured 2026-09-06 on this board: every dd of a device window
returned EFAULT and produced a zero-length file.

So the window is mmap'd and read as aligned 32-bit loads, which is what
`busybox devmem` does one word at a time - just without paying a process
per word.

> DANGER: the NoC config windows (0x04480000 bimc, 0x01880000 system_noc,
> and by inference 0x01900000 config_noc) RESET THE SoC when read from the
> application processor.  Measured twice, 2026-09-06, each occurrence
> attributed by a synced progress file.  Never point this tool at them.
"""
import ctypes
import mmap
import os
import sys

PAGE = 4096


def main() -> int:
    if len(sys.argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    base = int(sys.argv[1], 0)
    length = int(sys.argv[2], 0)
    out = sys.argv[3]

    if base % PAGE or length % 4:
        sys.stderr.write("base must be page aligned and length a multiple of 4\n")
        return 2

    # Python's own mmap object will not hand out its address for a
    # read-only mapping, and opening /dev/mem O_RDWR to get around that
    # would put a writable mapping of the whole SoC one typo away from a
    # register write.  So the mapping is made through libc and stays
    # PROT_READ.
    span = (length + PAGE - 1) // PAGE * PAGE
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        addr = libc.mmap(None, span, mmap.PROT_READ, mmap.MAP_SHARED, fd, base)
    finally:
        os.close(fd)
    if addr in (None, 0) or addr == ctypes.c_void_p(-1).value:
        err = ctypes.get_errno()
        sys.stderr.write("mmap 0x%08X failed: %s\n" % (base, os.strerror(err)))
        return 1

    try:
        words = ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint32))
        buf = (ctypes.c_uint32 * (length // 4))()
        for i in range(length // 4):
            buf[i] = words[i]
        with open(out, "wb") as fh:
            fh.write(bytes(buf))
    finally:
        libc.munmap(ctypes.c_void_p(addr), span)

    sys.stdout.write("dumped 0x%08X +0x%X -> %s\n" % (base, length, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
