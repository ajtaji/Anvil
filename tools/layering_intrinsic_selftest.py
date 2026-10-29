"""Prove intrinsic/test-double resolution without weakening private boundaries."""
from pathlib import Path
import tempfile
import layering_check as gate

def main():
    checks = 0
    for board, (registry, target) in gate.INTRINSIC_REGISTRIES.items():
        for case in ['builtin', 'missing', 'wrong-target', 'incomplete',
                     'ordinary-private', 'production-owner', 'test-caller',
                     'shared-caller', 'other-board-owner']:
            with tempfile.TemporaryDirectory(prefix='intrinsic-boundary-') as temp:
                root = Path(temp)
                name = 'cpu_private' if case == 'ordinary-private' else 'cpu_barrier'
                caller = board + 'Lib/consumer.pbi'
                if case == 'test-caller':
                    caller = board + 'Tests/consumer.pbi'
                if case == 'shared-caller':
                    caller = 'Anvil/Graphics/consumer.pbi'
                sources = {
                    board + 'Tests/recorder.pbi': 'Procedure cpu_barrier()\nEndProcedure\n',
                    caller: 'Procedure Consumer()\n '+name+'()\nEndProcedure\n',
                }
                if case == 'ordinary-private':
                    sources[board + 'Lib/private.pbi'] = 'Procedure cpu_private()\nEndProcedure\n'
                if case == 'production-owner':
                    sources[board + 'Lib/owner.pbi'] = 'Procedure cpu_barrier()\nEndProcedure\n'
                if case == 'other-board-owner':
                    other = next(b for b in gate.BOARD_ROOTS if b != board)
                    sources[other+'Tests/recorder.pbi'] = 'Procedure cpu_barrier()\nEndProcedure\n'
                for path, text in sources.items():
                    p = root/path
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text, encoding='utf8')
                if case != 'missing':
                    p = root/board/registry
                    p.parent.mkdir(parents=True, exist_ok=True)
                    actual = 'UNKNOWN' if case == 'wrong-target' else target
                    text = '@TARGET '+actual+'\n@INTRINSIC cpu_barrier\n@ARGS 0\n@ASM\n nop\n'
                    if case != 'incomplete':
                        text += '@END\n'
                    p.write_text(text, encoding='utf8')
                tree = gate.Tree(root, source_paths=list(sources))
                findings, _ = gate.rule_private_namespace(tree)
                present = name in findings.get(caller, {})
                assert present == (case != 'builtin'), (board, case, findings)
                if case == 'shared-caller':
                    downward, _ = gate.rule_downward_call(tree)
                    assert name in downward.get(caller, {}), downward
                checks += 1
    print('Intrinsic ownership controls PASS:', checks,
          'cases across four targets; real private/shared/test crossings retained')

if __name__ == '__main__':
    main()
