#!/usr/bin/env python3
"""Check the Rock Pi 4C adapter preserves Anvil's shared storage seams."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "RockPi4C" / "Lib" / "storage.pbi"
PROOF = ROOT / "RockPi4C" / "Lib" / "storage_proof.pbi"
UART = ROOT / "RockPi4C" / "Lib" / "uart2.pbi"


def fail(message: str) -> None:
    raise SystemExit("Rock Pi storage adapter gate: " + message)


def uncomment(text: str) -> str:
    return re.sub(r";[^\r\n]*", "", text)


def procedure(text: str, header: str) -> str:
    start = text.find(header)
    if start < 0:
        fail(f"missing {header}")
    end = text.find("\nEndProcedure", start)
    if end < 0:
        fail(f"unterminated {header}")
    return text[start:end]


def check(text: str, proof_text: str) -> list[str]:
    clean = uncomment(text)
    up = procedure(clean, "Procedure.i HwStorageUp()")
    if "RockSdInit()" not in up or "RockSdBlockCount()" not in up:
        fail("bring-up must initialize the SD driver and validate reported capacity")
    if "FsSetRangeReader(@RockSdReadBlocks)" not in up:
        fail("shared filesystem reader must use the driver's ranged callback")
    if "FsSetBlockFlusher(@RockSdFlush)" not in up:
        fail("shared filesystem must use the driver's bounded flush callback")
    if "For partition = 1 To #FS_MAX_PARTITION" not in up or "FsSelectPartition(partition)" not in up:
        fail("bring-up must attempt supported partition slots using the shared dispatcher")
    if "gHwFileMounted = 1" not in up:
        fail("mounted media must be exposed to HwFile as readable and read-only")
    if re.findall(r"\bgHwFileWritable\s*=\s*(\d+)", up) != ["0", "0"]:
        fail("every mounted state must remain read-only")
    if re.findall(r"\bgHwFileWriter\s*=\s*(\d+)", up) != ["0", "0"] or up.count("FsSetRangeWriter(0)") != 2:
        fail("writer must remain disarmed until separately validated")
    if "FsMount(" in up:
        fail("adapter must use FsSelectPartition rather than bypass the shared dispatcher")
    proof = uncomment(proof_text)
    listing = procedure(proof, "Procedure.i RockStorageProofList()")
    if "HwStorageUp()" not in listing or "HwDirOpen(0)" not in listing or "HwDirNext()" not in listing or "HwDirNameUtf8(" not in listing:
        fail("proof listing must mount through HwStorageUp and use the shared HwDir API")
    write = procedure(proof, "Procedure.i RockStorageProofWriteRead()")
    if "rock_storage_proof_attempted <> 0" not in write or "rock_storage_proof_attempted = 1" not in write:
        fail("proof writes must be one-shot")
    if "HwFileOpen(?rock_storage_proof_name)" not in write or "#HW_FILE_NOTFOUND" not in write:
        fail("proof must refuse an existing file and proceed only after not-found")
    if "HwFileWriteAll(?rock_storage_proof_name" not in write or "HwFileReadAt(0" not in write or "PeekA(?rock_storage_proof_data + index)" not in write:
        fail("proof must create, read back and compare the fixed pattern")
    if "FsUnmount() = 0" not in write or "FsSelectPartition(rock_storage_partition) = 0" not in write:
        fail("write proof must remount to discard format caches before readback")
    if write.count("gHwFileWritable = 0") != 2 or write.count("gHwFileWriter = 0") != 2:
        fail("proof must restore read-only state after both write outcomes")
    receive = procedure(proof, "Procedure.i RockStorageReceive(length.i, expectedCrc.i)")
    if "#ROCK_STORAGE_XFER_CHUNK" not in receive or "XFER ERROR" not in receive or "XFER DONE CHECKSUM PASS" not in receive:
        fail("binary transfer must be bounded, CRC checked and have terminal success/error status")
    if "rock_storage_resync()" not in receive:
        fail("failed binary transfer must drain/resynchronize before returning to text commands")
    if "#ROCK_STORAGE_XFER_CHUNK = 16384" not in proof or "RockUartReceiveBurst(" not in receive:
        fail("binary input must use 16-KiB acknowledged windows and the FIFO-draining receiver")
    if "RockStorageHex8(#ROCK_STORAGE_XFER_CHUNK)" not in receive:
        fail("READY must advertise the receiver window for protocol negotiation")
    uart = uncomment(UART.read_text(encoding="utf-8"))
    burst = procedure(uart, "Procedure.i RockUartReceiveBurst(*dst, capacity.i)")
    if "While count < capacity" not in burst or "#ROCK_UART_LSR_DR" not in burst or "PokeA(*dst + count" not in burst:
        fail("UART burst receiver must drain available bytes into a bounded caller buffer")
    trust = procedure(proof, "Procedure.i RockStorageTrustImageValid()")
    if "#ROCK_STORAGE_TRUST_SEGMENTS = 1" not in proof:
        fail("trust image validation must require one self-contained Anvil component")
    for token in ("#ROCK_STORAGE_TRUST_ANVIL_BASE", "#ROCK_STORAGE_TRUST_ANVIL_LIMIT", "(sectors & 3) <> 0"):
        if token not in trust:
            fail("trust image validation does not enforce fixed bounded 2 KiB-aligned components")
    updater = (ROOT / "tools/rockpi4c_update.py").read_text(encoding="utf-8")
    if "hashlib.sha256(padded).digest() != digest" not in updater or "def validate_trust_image" not in updater:
        fail("host updater must verify trust component metadata digests before serial writes")
    if "window = LEGACY_CHUNK if len(fields) == 3 else int(fields[3], 16)" not in updater:
        fail("host updater must negotiate new windows and retain the build-94 fallback")
    board = (ROOT / "RockPi4C/Board/board.rockpi4c").read_text(encoding="utf-8")
    for include in ("Anvil/Storage/fat32.pbi", "Anvil/Storage/exfat.pbi", "Anvil/Storage/filesystem.pbi", "Anvil/Hal/hal.pbi", "Anvil/Storage/hwfile.pbi", "RockPi4C/Lib/sdmmc.pbi", "RockPi4C/Lib/storage.pbi", "RockPi4C/Lib/storage_proof.pbi"):
        if f'XIncludeFile "{include}"' not in board:
            fail(f"board composition is missing {include}")
    recovery = uncomment((ROOT / "RockPi4C/Lib/recovery.pbi").read_text(encoding="utf-8"))
    finish = procedure(recovery, "Procedure RockRecoveryFinishLine()")
    if "If rock_recovery_fatal_mode<>0" not in finish or "RockStorageCommand(" not in finish:
        fail("storage dispatch must be explicitly excluded from fatal recovery")
    return [
        "RockSd ranged read and bounded flush callbacks are installed",
        "partition selection uses the shared FAT32/exFAT GPT-aware dispatcher",
        "HwFile mounts read-only by default; writes arm only within the explicit file operations",
        "isolated proof lists through HwDir and remounts before unique-file readback",
        "16-KiB FIFO-drained transport resynchronizes, checks CRC, and bounds trust writes",
        "host SHA-256 metadata checks and board command integration are present",
    ]


def main() -> int:
    text = ADAPTER.read_text(encoding="utf-8")
    proof_text = PROOF.read_text(encoding="utf-8")
    checks = check(text, proof_text)
    mutant = text.replace("gHwFileWritable = 0", "gHwFileWritable = 1", 1)
    try:
        check(mutant, proof_text)
    except SystemExit:
        pass
    else:
        fail("self-test did not reject enabling unvalidated SD writes")
    print("rockpi4c_storage_adapter_check: PASS - " + "; ".join(checks))
    print("  self-test: premature write enable rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
