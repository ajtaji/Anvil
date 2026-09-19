"""Desk compile of the HTTP-wired monitor; count the build, never deploy it."""
import argparse
from pathlib import Path
import subprocess
import os
import tempfile
import build_count
from build import staged_compiler

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if compiler.name.lower().startswith('pmfc'):
        raise SystemExit('Use the IDE application with --compile, not the retired compiler.')
    source = ROOT / 'RaspberryPi4/Board/board.pi4'
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit('Choose a new output path; existing candidates are preserved.')
    output.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PMF_ROOT'] = str(ROOT)
    with tempfile.TemporaryDirectory(prefix='http-monitor-compiler-') as stage:
        isolated = staged_compiler(str(compiler), Path(stage))
        result = subprocess.run([isolated, '--compile', str(source), '-t', 'pi4',
                                 '-o', str(output)], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode or not output.is_file():
            raise SystemExit(result.returncode or 1)
        count = build_count.record_build(source, 'pi4', output,
                                         by='tools/http_monitor_build_check.py', compiler=isolated)
    print(count.message)
    print('PASS: monitor compiles with HTTP service wiring. No deployment or hardware proof.')

if __name__ == '__main__':
    main()
