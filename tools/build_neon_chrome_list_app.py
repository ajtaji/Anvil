#!/usr/bin/env python3
"""Build a pure prepared list/tree application for Anvil's resident graphics service."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target', choices=['pi4', 'pi3', 'unoq', 'rockpi4c'], required=True)
    ap.add_argument('--compiler', required=True)
    ap.add_argument('--scene',choices=['basic','scrolled'],required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    layout = state_proof_layout(a.target)
    paths = ['Anvil/Graphics/Tests/neon_chrome_list_app.pbi',
             'Anvil/Hal/neon_service_api.pbi','Anvil/Math/float32.pbi','Anvil/Graphics/neon_chrome_style.pbi','Anvil/Graphics/neon_chrome_hotzones.pbi',
             'Anvil/Math/float32_convert.pbi','Anvil/Graphics/neon_service_client.pbi',
             'Anvil/Graphics/neon_service_mapping.pbi','Anvil/Graphics/neon_chrome_list.pbi',
             'Anvil/Graphics/neon_service_chrome_list.pbi','Anvil/Graphics/neon_utf8.pbi','Anvil/Graphics/neon_chrome_scroll.pbi']
    before = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    (out / 'proof.pbi').write_text(
        f'#NLT_SCENE = {dict(basic=1,scrolled=2)[a.scene]}\n#NLT_REPORT = ${layout["report"]:08X}\nXIncludeFile "{paths[0]}"\n', encoding='utf8')
    q = subprocess.run([str(resolve_compiler(a.compiler)), '--compile', str(out / 'proof.pbi'),
                        '-t', a.target, '--load-addr', hex(layout['load']),
                        '--stack-addr', hex(layout['stack']), '--entry-returns',
                        '--wants-services', '-o', str(out / 'proof.img')],
                       env=dict(os.environ, PMF_ROOT=str(root)), capture_output=True,
                       text=True, encoding='utf8', timeout=180,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    log = q.stdout + q.stderr
    (out / 'compile.txt').write_text(log, encoding='utf8')
    print(log[-1800:])
    if q.returncode:
        raise SystemExit(q.returncode)
    assert before == {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    image = out / 'proof.img.pmf'
    identity = dict(target=a.target, graphics_protocol="1.4", scene=a.scene, bytes=image.stat().st_size,
                    sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                    checked_ranges=check_linked_layout(layout, log), source_hashes=before,
                    executed=False, scope='Pure application; resident graphics provider required at service ABI 1.8')
    identity['checked_ranges']['report']=[hex(layout['report']),hex(layout['report']+16383)]
    (out / 'identity.json').write_text(json.dumps(identity, indent=2), encoding='utf8')

if __name__ == '__main__':
    main()
