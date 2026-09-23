#!/usr/bin/env python3
# ======================================================================
#  unoq_efi_wrap.py - wrap a flat A64 image as a minimal AArch64
#                     PE/COFF UEFI application for the Arduino UNO Q.
#
#  The compiler emits a flat, position-independent A64 image: every global is
#  reached with adrp/#:lo12: (PC-relative) and BSS lives at a fixed
#  RELATIVE offset above the code (load + 0x80000 by default), so the
#  image can be loaded at any address as long as code and BSS keep their
#  relative distance. That is exactly what a PE section preserves, so the
#  wrap needs NO base-relocation table.
#
#  UEFI enters an application at AddressOfEntryPoint with
#     x0 = EFI_HANDLE        ImageHandle
#     x1 = EFI_SYSTEM_TABLE* SystemTable
#  and reads EFI_STATUS back from x0. The compiler's --entry-returns _start
#  preserves x0/x1 into Main() and returns Main()'s value in x0, so this
#  is a well-formed EFI application entry.
#
#  Layout produced:
#     RVA 0x0000  PE headers (one .text section)
#     RVA 0x1000  flat image, _start first  ->  AddressOfEntryPoint
#                 section VirtualSize spans through __bss_end__; the tail
#                 past the file bytes is BSS (zero-filled by the loader,
#                 and re-zeroed by the compiler's _start).
#
#  Usage:
#     unoq_efi_wrap.py <flat.img> <out.efi> [--load-addr 0x70000000]
#                      [--sym <flat.img.sym>] [--bss-end 0x........]
#  The BSS end (image virtual extent) is read from the .sym file's
#  __bss_end__ if present, else from --bss-end, else defaults to the file
#  length (no BSS).
# ======================================================================
import sys, struct, os

IMAGE_FILE_MACHINE_ARM64 = 0xAA64
SUBSYSTEM_EFI_APPLICATION = 10
FILE_ALIGN = 0x200
SECT_ALIGN = 0x1000

def parse_args(argv):
    a = {"load": 0x70000000, "sym": None, "bss_end": None, "in": None, "out": None}
    pos = []
    i = 0
    while i < len(argv):
        t = argv[i]
        if t == "--load-addr":
            i += 1; a["load"] = int(argv[i], 0)
        elif t == "--sym":
            i += 1; a["sym"] = argv[i]
        elif t == "--bss-end":
            i += 1; a["bss_end"] = int(argv[i], 0)
        else:
            pos.append(t)
        i += 1
    if len(pos) < 2:
        sys.exit("usage: unoq_efi_wrap.py <flat.img> <out.efi> [--load-addr H] [--sym F] [--bss-end H]")
    a["in"], a["out"] = pos[0], pos[1]
    return a

def read_sym_bss_end(path):
    # The .sym file is "name=value" tokens (space and/or newline separated).
    try:
        txt = open(path, "r", errors="replace").read()
    except OSError:
        return None
    for tok in txt.replace("\n", " ").split():
        if tok.startswith("__bss_end__="):
            try:
                return int(tok.split("=", 1)[1], 10)
            except ValueError:
                return None
    return None

def align_up(v, a):
    return (v + a - 1) & ~(a - 1)

def main():
    a = parse_args(sys.argv[1:])
    data = open(a["in"], "rb").read()
    file_len = len(data)

    load = a["load"]
    bss_end_abs = a["bss_end"]
    if bss_end_abs is None:
        symp = a["sym"] or (a["in"] + ".sym")
        if os.path.exists(symp):
            bss_end_abs = read_sym_bss_end(symp)

    # Virtual extent of the image body, measured from the flat load base.
    if bss_end_abs is not None and bss_end_abs > load:
        virt_body = bss_end_abs - load
    else:
        virt_body = file_len
    if virt_body < file_len:
        virt_body = file_len

    # --- section geometry ------------------------------------------------
    headers_raw = 0x40 + 4 + 20 + 240 + 40          # DOS + sig + COFF + opt + 1 sect
    size_of_headers = align_up(headers_raw, FILE_ALIGN)   # 0x200
    text_rva = SECT_ALIGN                            # 0x1000
    ptr_raw = size_of_headers                        # 0x200
    size_raw = align_up(file_len, FILE_ALIGN)        # code, file-aligned
    virt_size = virt_body                            # spans code + BSS
    size_of_image = align_up(text_rva + virt_size, SECT_ALIGN)
    size_of_code = size_raw
    entry_rva = text_rva                             # _start is at flat offset 0

    # --- DOS header ------------------------------------------------------
    dos = bytearray(0x40)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)          # e_lfanew -> PE sig at 0x40

    # --- COFF file header ------------------------------------------------
    coff = struct.pack("<HHIIIHH",
        IMAGE_FILE_MACHINE_ARM64,
        1,                    # NumberOfSections
        0,                    # TimeDateStamp
        0,                    # PointerToSymbolTable
        0,                    # NumberOfSymbols
        240,                  # SizeOfOptionalHeader (PE32+ std24+win88+16*8)
        0x0022)               # EXECUTABLE_IMAGE | LARGE_ADDRESS_AWARE

    # --- optional header (PE32+) ----------------------------------------
    opt = b""
    opt += struct.pack("<H", 0x20B)                  # Magic PE32+
    opt += struct.pack("<BB", 0, 0)                  # linker ver
    opt += struct.pack("<I", size_of_code)           # SizeOfCode
    opt += struct.pack("<I", 0)                       # SizeOfInitializedData
    opt += struct.pack("<I", virt_size - file_len if virt_size > file_len else 0)  # SizeOfUninitializedData
    opt += struct.pack("<I", entry_rva)              # AddressOfEntryPoint
    opt += struct.pack("<I", text_rva)               # BaseOfCode
    opt += struct.pack("<Q", load)                   # ImageBase
    opt += struct.pack("<I", SECT_ALIGN)             # SectionAlignment
    opt += struct.pack("<I", FILE_ALIGN)             # FileAlignment
    opt += struct.pack("<HH", 0, 0)                  # OS ver
    opt += struct.pack("<HH", 0, 0)                  # Image ver
    opt += struct.pack("<HH", 0, 0)                  # Subsystem ver
    opt += struct.pack("<I", 0)                       # Win32VersionValue
    opt += struct.pack("<I", size_of_image)          # SizeOfImage
    opt += struct.pack("<I", size_of_headers)        # SizeOfHeaders
    opt += struct.pack("<I", 0)                       # CheckSum
    opt += struct.pack("<H", SUBSYSTEM_EFI_APPLICATION)
    opt += struct.pack("<H", 0)                       # DllCharacteristics
    opt += struct.pack("<Q", 0x10000)                # SizeOfStackReserve
    opt += struct.pack("<Q", 0x10000)                # SizeOfStackCommit
    opt += struct.pack("<Q", 0)                       # SizeOfHeapReserve
    opt += struct.pack("<Q", 0)                       # SizeOfHeapCommit
    opt += struct.pack("<I", 0)                       # LoaderFlags
    opt += struct.pack("<I", 16)                      # NumberOfRvaAndSizes
    opt += b"\x00" * (16 * 8)                        # data directories (none)
    assert len(opt) == 240, len(opt)

    # --- section header --------------------------------------------------
    name = b".text\x00\x00\x00"
    sect = name
    sect += struct.pack("<I", virt_size)             # VirtualSize
    sect += struct.pack("<I", text_rva)              # VirtualAddress
    sect += struct.pack("<I", size_raw)              # SizeOfRawData
    sect += struct.pack("<I", ptr_raw)               # PointerToRawData
    sect += struct.pack("<I", 0)                      # PointerToRelocations
    sect += struct.pack("<I", 0)                      # PointerToLinenumbers
    sect += struct.pack("<H", 0)                      # NumberOfRelocations
    sect += struct.pack("<H", 0)                      # NumberOfLinenumbers
    sect += struct.pack("<I", 0xE0000020)            # CODE|EXEC|READ|WRITE
    assert len(sect) == 40, len(sect)

    # --- assemble --------------------------------------------------------
    out = bytearray()
    out += dos
    out += b"PE\x00\x00"
    out += coff
    out += opt
    out += sect
    out += b"\x00" * (size_of_headers - len(out))    # pad to raw data
    out += data
    out += b"\x00" * (size_raw - file_len)           # pad code to file align

    open(a["out"], "wb").write(out)
    print("unoq_efi_wrap: %s -> %s" % (a["in"], a["out"]))
    print("  entry RVA        0x%X (x0=ImageHandle, x1=SystemTable)" % entry_rva)
    print("  ImageBase        0x%X (informational; image is PIC)" % load)
    print("  file bytes       %d (0x%X)" % (file_len, file_len))
    print("  .text VirtualSize 0x%X  RawData 0x%X (BSS is the zero tail)" % (virt_size, size_raw))
    print("  SizeOfImage      0x%X" % size_of_image)
    print("  out file size    %d bytes" % len(out))

if __name__ == "__main__":
    main()
