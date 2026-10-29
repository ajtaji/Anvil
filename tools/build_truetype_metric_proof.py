"""Compile exact production metric procedures with signed-boundary/refusal cases."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target', choices=['pi4', 'unoq'], required=True)
    ap.add_argument('--compiler', required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    rel = 'Anvil/Graphics/truetype_layout.pbi'
    raw = (root / rel).read_bytes()
    source = raw.decode('utf-8-sig')
    bodies = []
    for name in ['anvil_ttl_Scale', 'AnvilTrueTypeScaleMetric']:
        matches = re.findall(r'(?ms)^Procedure\.\w+ ' + name + r'\(.*?^EndProcedure\s*$', source)
        assert len(matches) == 1, name
        bodies.append(matches[0])
    cases = []
    for value in [-2147483648, -32768, -1, 0, 1, 32767, 65535, 2147483647]:
        for pixels, units in [(1, 1), (512, 1), (16, 2048), (1, 3), (512, 65535)]:
            magnitude = abs(value) * pixels * 65536 // units
            cases.append((value, pixels, units, 0, 1, -magnitude if value < 0 else magnitude))
    for value, pixels, units, pointer in [
        (-2147483649, 16, 2048, 0), (2147483648, 16, 2048, 0),
        (1, 0, 2048, 0), (1, -1, 2048, 0), (1, 513, 2048, 0),
        (1, 16, 0, 0), (1, 16, -1, 0), (1, 16, 65536, 0),
        (1, 16, 2048, 1), (1, 16, 2048, 2), (1, 16, 2048, 3)]:
        cases.append((value, pixels, units, pointer, 0, 123456789))
    layout = state_proof_layout(a.target)
    s = '\n'.join(bodies) + '''
Global Dim metricCanary.q[3]
Global metricChecks.i,metricFailure.i
Procedure MetricCase(value.i,pixels.i,units.i,pointerMode.i,expectedRc.i,expected.q)
 Protected destination.i,rc.i
 metricCanary[0]=99887766 : metricCanary[1]=123456789 : metricCanary[2]=88776655
 destination=@metricCanary[1]
 If pointerMode=1 : destination=0 : EndIf
 If pointerMode=2 : destination=destination+1 : EndIf
 If pointerMode=3 : destination=-8 : EndIf
 rc=AnvilTrueTypeScaleMetric(value,pixels,units,destination)
 metricChecks=metricChecks+1
 If rc<>expectedRc Or metricCanary[1]<>expected Or metricCanary[0]<>99887766 Or metricCanary[2]<>88776655
  If metricFailure=0 : metricFailure=metricChecks : EndIf
 EndIf
EndProcedure
Procedure.i Main(services.i)
'''
    for case in cases:
        s += ' MetricCase(' + ','.join(map(str, case)) + ')\n'
    s += f' PokeI(${layout["report"]:X},$4D455452) : PokeI(${layout["report"]+8:X},metricChecks) : PokeI(${layout["report"]+16:X},metricFailure)\n ProcedureReturn metricFailure\nEndProcedure\n'
    d = a.out.resolve()
    d.mkdir(parents=True, exist_ok=False)
    (d / 'proof.pbi').write_text(s, encoding='utf8')
    (d / 'cases.json').write_text(json.dumps(cases, indent=2), encoding='utf8')
    env = os.environ.copy()
    env['PMF_ROOT'] = str(root)
    q = subprocess.run([str(resolve_compiler(a.compiler)), '--compile', str(d / 'proof.pbi'), '-t', a.target, '--load-addr', hex(layout['load']), '--stack-addr', hex(layout['stack']), '--entry-returns', '--wants-services', '-o', str(d / 'proof.img')], capture_output=True, text=True, encoding='utf8', env=env, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
    output = q.stdout + q.stderr
    (d / 'compile.txt').write_text(output, encoding='utf8')
    print(output[-1800:])
    assert q.returncode == 0
    payload = (d / 'proof.img.pmf').read_bytes()
    (d / 'identity.json').write_text(json.dumps(dict(target=a.target, checks=len(cases), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), source_hashes={rel:hashlib.sha256(raw).hexdigest()}, production_bodies=[hashlib.sha256(body.encode()).hexdigest() for body in bodies], checked_ranges=check_linked_layout(layout, output), executed=False), indent=2), encoding='utf8')

if __name__ == '__main__':
    main()
