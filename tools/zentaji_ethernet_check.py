"""Check the Zentaji Ethernet driver against native timed RX and real rings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
XIncludeFile "Zentaji/Board/prompt_idle.pbi"
XIncludeFile "Zentaji/Board/ethernet.pbi"

Global Dim frame.a[1514]

Procedure.i Main()
 Protected i.i,j.i
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3)
 PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)=0 Or ZentajiEthernetPresent()=0 : ProcedureReturn 1 : EndIf
 If ZentajiEthernetCarrier()=0
  If ZentajiEthernetOpen()<>0 Or PeekQ(#ZEN_ETH_BASE+$10)<>0 : ProcedureReturn 2 : EndIf
  ProcedureReturn $2A
 EndIf
 PokeQ(#ZEN_ETH_BASE+$50,$20000)
 If ZentajiEthernetOpen()<>0 Or PeekQ(#ZEN_ETH_BASE+$50)<>$20000 : ProcedureReturn 3 : EndIf
 PokeQ(#ZEN_ETH_BASE+$50,0)
 If ZentajiEthernetOpen()=0 Or ZentajiEthernetOwned()=0 : ProcedureReturn 4 : EndIf
 If ZentajiEthernetReceive(@frame[0],1514,0)<>0 : ProcedureReturn 5 : EndIf
 For j=0 To 11
  If ZentajiEthernetReceive(@frame[0],1514,15)<>64 : ProcedureReturn 6 : EndIf
  For i=0 To 63
   If frame[i]<>((i*7+j*31)&255) : ProcedureReturn 7 : EndIf
  Next
  If ZentajiEthernetSend(@frame[0],64)=0 : ProcedureReturn 8 : EndIf
 Next
 If ZentajiEthernetReceive(@frame[0],32,15)<>0 Or zeRxRejects<>1 : ProcedureReturn 9 : EndIf
 If ZentajiEthernetReceive(@frame[0],1514,3)<>0 : ProcedureReturn 10 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$98)<>0 Or ZentajiEthernetClose()=0 : ProcedureReturn 11 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$10)<>0 Or PeekQ(#ZEN_ETH_BASE+$50)<>0 Or PeekQ(#ZEN_ETH_BASE+$70)<>0 : ProcedureReturn 12 : EndIf
 If ZentajiEthernetOpen()=0 Or ZentajiEthernetReceive(@frame[0],1514,0)<>0 Or ZentajiEthernetClose()=0 : ProcedureReturn 13 : EndIf
 ProcedureReturn $2A
EndProcedure
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--compiler")
    parser.add_argument("--probe", type=Path, help="Run an already compiled guest probe")
    args = parser.parse_args()
    tools, output = args.zen_tools.resolve(), args.keep.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(tools))
    from zen_native_fixture import Fixture

    probe = args.probe
    if probe is None:
        source, probe = output / "ethernet.zentaji", output / "ethernet.zex"
        source.write_text(SOURCE, encoding="ascii")
        built = subprocess.run(
            [str(resolve_compiler(args.compiler)), "--compile", str(source), "-o", str(probe)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True, timeout=120,
        )
        (output / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        assert built.returncode == 0, built.stdout[-3000:] + built.stderr
    image = probe.read_bytes()

    for attached in (False, True):
        label = "attached" if attached else "disconnected"
        fixture = Fixture(ram_size=2 << 20, cores=2)
        fixture.net_attached = attached
        if attached:
            for j in range(13):
                fixture.net_feed(200000 + 100000 * j, bytes((i * 7 + j * 31) & 255 for i in range(64)))
        fixture.load_image(image)
        folder = output / label
        config = fixture.write(folder)
        emulator = tools / ("zenemu.exe" if os.name == "nt" else "zenemu")
        native = subprocess.run([str(emulator), str(config), "--max", "3000000"],
                                capture_output=True, text=True, timeout=45)
        (folder / "run.log").write_text(native.stdout + native.stderr, encoding="utf-8")
        assert native.returncode == 0 and re.search(r"^END .* exit=2A ", native.stdout, re.M), label
    (output / "result.json").write_text(json.dumps({
        "probe_sha256": hashlib.sha256(image).hexdigest(), "received_frames": 12,
        "rejected_oversized_delivery": True, "foreign_ring_preserved": True,
        "reopened": True, "disconnected_refused": True,
    }, indent=2) + "\n", encoding="utf-8")
    print("PASS native Zentaji Ethernet ring wrap, timed RX, dropped delivery and reopen")


if __name__ == "__main__":
    main()
