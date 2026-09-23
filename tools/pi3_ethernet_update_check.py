#!/usr/bin/env python3
"""Execute the Pi 3 Ethernet updater protocol at its A/B and UDP seams."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_net_update as wire
sys.path.insert(0, str(Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base


ROOT = Path(__file__).resolve().parents[1]
LOAD = 0x200000
INPUT = 0x5000000
MASK = (1 << 64) - 1


def static_contract() -> None:
    board = (ROOT / "RaspberryPi3/Board/updater.pi3").read_text(encoding="utf-8")
    service = (ROOT / "RaspberryPi3/Board/ethernet_update.pbi").read_text(encoding="utf-8")
    hal = (ROOT / "Anvil/Hal/hal.pbi").read_text(encoding="utf-8")
    if 'XIncludeFile "Anvil/Network/net.pbi"' not in board or 'XIncludeFile "Anvil/Network/dhcp.pbi"' not in board:
        raise SystemExit("Pi3 updater does not compose the shared network codecs")
    if not re.search(r"#HW_LINK_NONE\s*=\s*0\b", hal) or not re.search(r"#HW_LINK_NONE\s*=\s*0\b", board):
        raise SystemExit("Pi3 network composition disagrees with the canonical no-link value")
    idle = re.search(r"Procedure\.i Pi3EthernetIdle\(\)(.*?)EndProcedure", service, re.I | re.S)
    if not idle:
        raise SystemExit("Pi3 Ethernet idle step is missing")
    executable = "\n".join(line.split(";", 1)[0] for line in idle.group(1).splitlines())
    if re.search(r"\b(while|wend|repeat|until|for|next)\b", executable, re.I):
        raise SystemExit("Pi3 Ethernet idle step hides a loop")
    for fact in (
        "Pi3UpdateBeginFrom(#PI3_UPDATE_SOURCE_ETHERNET",
        "Pi3UpdateChunkFrom(#PI3_UPDATE_SOURCE_ETHERNET",
        "Pi3UpdateCommitFrom(#PI3_UPDATE_SOURCE_ETHERNET",
        "Pi3UpdateAbortFrom(#PI3_UPDATE_SOURCE_ETHERNET",
        "p3net_peer_ip", "p3net_peer_port", "p3net_session",
        "Pi3LanBulkRxNext()", "DhcpClientTick(", "NetArpRequest(",
    ):
        if fact not in service:
            raise SystemExit("Pi3 Ethernet contract missing " + fact)


class Harness:
    def __init__(self, image: Path):
        self.blob = image.read_bytes()
        self.sym = base.parse_symbols(image)
        self.a64 = base.load_interp(base.INTERP)
        self.cpu = self.a64.A64()
        self.cpu.memory = {LOAD + i: b for i, b in enumerate(self.blob)}
        self.cpu.sp = 0x1F00000
        self.source = 0
        self.received = 0
        self.error = 0
        self.pending = -1
        self.generation = 0
        self.calls: list[tuple] = []
        self.responses: list[bytes] = []
        names = (
            "pi3updatesource", "pi3updatebeginfrom", "pi3updatechunkfrom",
            "pi3updatecommitfrom", "pi3updateabortfrom", "pi3updateerror",
            "pi3updatereceived", "pi3updateslot", "pi3updatependingslot",
            "pi3updatependinggeneration", "pi3updateresetready", "pi3micros",
            "netudpbuild", "pi3nettx",
        )
        self.hooks = {LOAD + self.sym[name]: name for name in names}

    def _return(self, value: int) -> None:
        self.cpu.x[0] = value & MASK
        self.cpu.pc = self.cpu.x[30]

    def _hook(self, name: str) -> None:
        c = self.cpu
        if name == "pi3updatesource":
            value = self.source
        elif name == "pi3updatebeginfrom":
            self.calls.append((name, c.x[0], c.x[1], c.x[2]))
            assert c.x[0] == 2 and c.x[1] > 0 and c.x[2] != 0
            self.source = 2; self.received = 0; value = 1
        elif name == "pi3updatechunkfrom":
            self.calls.append((name, c.x[0], c.x[1], c.x[3]))
            assert c.x[0] == 2 and c.x[1] <= self.received and 1 <= c.x[3] <= 1024
            self.received = max(self.received, c.x[1] + c.x[3]); value = 1
        elif name == "pi3updatecommitfrom":
            self.calls.append((name, c.x[0]))
            assert c.x[0] == 2
            self.source = 0; self.pending = 1; self.generation = 12; value = 1
        elif name == "pi3updateabortfrom":
            self.calls.append((name, c.x[0]))
            assert c.x[0] == 2
            self.source = 0; self.received = 0; value = 1
        elif name == "pi3updateerror": value = self.error
        elif name == "pi3updatereceived": value = self.received
        elif name == "pi3updateslot": value = 0
        elif name == "pi3updatependingslot": value = self.pending
        elif name == "pi3updatependinggeneration": value = self.generation
        elif name == "pi3updateresetready": value = 1
        elif name == "pi3micros": value = 10_000_000
        elif name == "netudpbuild":
            assert c.x[0] == 1 and c.x[3] == wire.PORT and c.x[5] == wire.REPLY.size
            self.responses.append(bytes(c.load(c.x[4] + i, 1) for i in range(c.x[5])))
            value = 1
        elif name == "pi3nettx": value = 1
        else: raise AssertionError(name)
        self._return(value)

    def call(self, packet: bytes, ip: int = 0xC0A80164, port: int = 41000):
        c = self.cpu
        for i, value in enumerate(packet): c.store(INPUT + i, value, 1)
        c.x[0] = INPUT; c.x[1] = len(packet); c.x[2] = ip; c.x[3] = port
        c.x[30] = base.RETURN_PC; c.pc = LOAD + self.sym["pi3netupdatepacket"]
        before = len(self.responses)
        for _ in range(500000):
            if c.pc == base.RETURN_PC: break
            hook = self.hooks.get(c.pc)
            if hook: self._hook(hook)
            else: c.step()
        else: raise AssertionError("Pi3NetUpdatePacket did not return")
        assert len(self.responses) == before + 1
        return wire.REPLY.unpack(self.responses[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    static_contract()
    h = Harness(Path(args.image))
    session = 0x1122334455667788
    digest = bytes(range(32))

    r = h.call(wire.request(wire.STATUS, 0))
    assert r[0] == b"P3R1" and r[1] == wire.STATUS and r[4] == 0
    bad = bytearray(wire.request(wire.STATUS, 0)); bad[0] ^= 1
    assert h.call(bytes(bad))[4] == -2001

    assert h.call(wire.request(wire.BEGIN, session, 4096, digest))[4] == 0
    assert h.source == 2 and h.received == 0
    payload = bytes(range(251))
    assert h.call(wire.request(wire.DATA, session, 0, payload))[3] == len(payload)
    # Exact retransmit is handed to the A/B layer; a different peer/session is not.
    before = len([c for c in h.calls if c[0] == "pi3updatechunkfrom"])
    assert h.call(wire.request(wire.DATA, session ^ 1, len(payload), payload))[4] == -2002
    assert len([c for c in h.calls if c[0] == "pi3updatechunkfrom"]) == before
    assert h.call(wire.request(wire.DATA, session, 0, payload))[4] == 0

    h.received = 4096
    assert h.call(wire.request(wire.COMMIT, session, 4096))[4] == 0
    assert h.pending == 1 and h.generation == 12
    commits = len([c for c in h.calls if c[0] == "pi3updatecommitfrom"])
    assert h.call(wire.request(wire.COMMIT, session, 4096))[4] == 0
    assert len([c for c in h.calls if c[0] == "pi3updatecommitfrom"]) == commits
    assert h.call(wire.request(wire.RESET, session))[4] == 0
    reset_pending = h.cpu.load(h.sym["global_p3net_reset_pending"], 8)
    assert reset_pending == 1

    # Fresh transaction can be explicitly disarmed only by its bound peer.
    h2 = Harness(Path(args.image))
    assert h2.call(wire.request(wire.BEGIN, session, 2048, digest))[4] == 0
    assert h2.call(wire.request(wire.ABORT, session), port=41001)[4] == -2002
    assert h2.source == 2
    assert h2.call(wire.request(wire.ABORT, session))[4] == 0 and h2.source == 0

    print("pi3_ethernet_update_check PASS: 12 emitted peer/session/A-B/replay cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
