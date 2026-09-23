"""Prove experimental Pi3 builds count independently, using only temporary files.

This also sweeps the Pi 3 tools themselves. Testing the mechanism proves the
mechanism; it says nothing about a tool that never calls it, and an uncounted
build is invisible unless something else changes underneath it. Every Pi 3 tool
that runs the compiler must therefore reach the counting mechanism, and that is
checked here rather than left for a reader to notice.
"""
from pathlib import Path
import tempfile
import build_count as counter

TOOLS = Path(__file__).resolve().parent


def sweep_compiling_tools() -> int:
    """Every Pi 3 tool that compiles a BOARD image must also count the build.

    A gate that compiles an isolated fixture out of the Tests tree is not
    building the monitor and has no number to raise; the counter excludes those
    by name already. What must never happen quietly is a tool that hands the
    compiler one of the three real Pi 3 board entry points and then walks past
    the counter, because the image it produced carries a number that no longer
    identifies anything.
    """
    boards = {name for target, path in counter.BOARDS.items()
              if target.startswith("pi3") for name in [path.name]}
    offenders = []
    swept = 0
    here = Path(__file__).resolve()
    for tool in sorted(TOOLS.glob("pi3_*.py")):
        # This file names the compiler flag and the board files only to look for
        # them, and compiles nothing itself.
        if tool.resolve() == here:
            continue
        text = tool.read_text(encoding="utf-8", errors="replace")
        if '"--compile"' not in text and "'--compile'" not in text:
            continue
        if not any(f"Board/{name}" in text or f'"{name}"' in text for name in boards):
            continue
        swept += 1
        # Either the counter directly, or the one Pi 3 gate helper that wraps it.
        if "build_count" not in text and "pi3_gate_build" not in text:
            offenders.append(tool.name)
    if offenders:
        raise SystemExit(
            "FAIL: these tools compile a Pi 3 board image without reaching the "
            "build counter, so their builds never raise the number or reach the "
            "ledger: " + ", ".join(offenders)
        )
    return swept


def main():
    with tempfile.TemporaryDirectory(prefix='pi3-build-count-') as temporary:
        root = Path(temporary)
        board = root / counter.BOARDS['pi3']
        board.parent.mkdir(parents=True)
        board.write_text('#ANVIL_BUILD = 1 ; pmf:build\n'
                         '#ANVIL_BUILD_DATE = 20260911 ; pmf:builddate\n'
                         '#ANVIL_BUILD_TIME = 120000 ; pmf:buildtime\n')
        image, compiler = root/'candidate.img', root/'PureMetalForge.exe'
        image.write_bytes(b'test artifact, not a boot image')
        compiler.write_bytes(b'test compiler identity, not executable')
        before = board.read_bytes()
        wrong = counter.record_build(board, 'pi4', image, compiler=compiler, root=root)
        assert not wrong.counted and board.read_bytes() == before
        fixture = counter.record_build('early_hardware.pi3', 'pi3', image, compiler=compiler, root=root)
        assert not fixture.counted and board.read_bytes() == before
        result = counter.record_build('copy/board.pi3', 'pi3', image,
                                      by='pi3_build_count_check', compiler=compiler, root=root)
        assert result.counted and result.new_value == 2
        assert '#ANVIL_BUILD = 2' in board.read_text()
        after = board.read_bytes()
        duplicate = counter.record_build('copy/board.pi3', 'pi3', image,
                                         by='pi3_build_count_check', compiler=compiler, root=root)
        assert duplicate.already and board.read_bytes() == after
        ledger = (root/counter.LEDGER_NAME).read_text()
        assert 'target=pi3' in ledger and 'RaspberryPi3/Board/board.pi3' in ledger
        assert counter.board_for('board.pi4', 'pi4', root) == root/counter.BOARDS['pi4']
    swept = sweep_compiling_tools()
    print('PASS: Pi3 independent count, duplicate protection, wrong-target/fixture exclusion; temporary files only.')
    print(f'PASS: {swept} Pi 3 tools invoke the compiler and every one of them counts the build.')


if __name__ == '__main__':
    main()
