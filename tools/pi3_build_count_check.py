"""Prove experimental Pi3 builds count independently, using only temporary files."""
from pathlib import Path
import tempfile
import build_count as counter


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
    print('PASS: Pi3 independent count, duplicate protection, wrong-target/fixture exclusion; temporary files only.')


if __name__ == '__main__':
    main()
