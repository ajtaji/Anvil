#!/usr/bin/env python3
"""Build a storage-free display isolation image; never opens a board connection.

The normal board source remains unchanged except for its mandatory build stamp.
A generated build input adds the tracked diagnostic at one checked seam. Its
source and artifacts remain under build/rockpi4c-isolation for exact inspection.
"""
import argparse
from pathlib import Path
import tempfile

import build
import build_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = build.find_compiler(args.compiler)
    root = build.ROOT
    board = root / "RockPi4C/Board/board.rockpi4c"
    directory = root / "build/rockpi4c-isolation"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "board.rockpi4c"
    output = directory / "anvil-flat.img"
    seam = '  If rock_uart_ready <> 0 : RockUartLine("ANVIL ROCK PI 4C FOUNDATION READY; IRQ STILL MASKED") : EndIf'
    with tempfile.TemporaryDirectory(prefix="anvil-isolation-compiler-") as temp:
        staged = build.staged_compiler(compiler, Path(temp))
        with build_count.build_identity(board, "rockpi4c", compiler=compiler,
                                       by="tools/rockpi4c_display_isolation_build.py",
                                       root=root) as identity:
            text = board.read_text(encoding="utf-8")
            if text.count(seam) != 1 or text.count('Procedure Main()') != 1:
                raise RuntimeError("Board composition changed; review the diagnostic insertion seam.")
            text = text.replace('Procedure Main()',
                'XIncludeFile "RockPi4C/Tests/display_isolation.pbi"\n\nProcedure Main()', 1)
            text = text.replace(seam, '  RockDisplayIsolationTest()\n' + seam, 1)
            source.write_text(text, encoding="utf-8")
            spec = dict(build.TARGETS["rockpi4c"])
            spec.update(source=source, output=output,
                        image_output=directory / "Image")
            spec["args"] = [*spec["args"], "-S"]
            publication = build._compile_and_publish(staged, "rockpi4c", source, output, spec)
            identity.register_publication(publication.rollback, publication.finalize)
            counted = identity.complete(output)
        print(counted.message)
    asm = Path(str(output) + ".asm").read_text(encoding="utf-8").lower()
    routine = asm.split("rockdisplayisolationtest:", 1)[1].split("main:", 1)[0]
    if routine.count("bl rockdisplayframetelemetry") != 3:
        raise RuntimeError("Emitted isolation image lost one of its three measurements.")
    print("ISOLATION IMAGE BUILT; SILICON NOT RUN")


if __name__ == "__main__":
    main()
