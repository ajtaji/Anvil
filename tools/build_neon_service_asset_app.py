#!/usr/bin/env python3
"""Build a pure encoded-asset application for Anvil's resident graphics service."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, struct
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target', choices=['pi4', 'pi3', 'unoq', 'rockpi4c'], required=True)
    ap.add_argument('--compiler', required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    layout = state_proof_layout(a.target)
    paths = ['Anvil/Graphics/Tests/neon_service_asset_app.pbi',
             'Anvil/Hal/neon_service_api.pbi',
             'Anvil/Graphics/neon_service_client.pbi',
             'Anvil/Graphics/neon_service_sprite.pbi', 'Anvil/Math/float32.pbi',
             'Anvil/Graphics/neon_sprite_decode.pbi','Anvil/Graphics/neon_service_asset.pbi',
             'Anvil/Hal/file_service_client.pbi']
    before = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    def bmp(width,height,depth,pixels):
        rows=abs(height);pitch=((width*(depth//8)+3)//4)*4
        data=b''
        for row in range(rows):
            y=row if height<0 else rows-1-row
            payload=b''.join(bytes((b,g,r,a) if depth==32 else (b,g,r)) for r,g,b,a in pixels[y*width:(y+1)*width])
            data+=payload+bytes(pitch-len(payload))
        return struct.pack('<2sIHHI',b'BM',54+len(data),0,0,54)+struct.pack('<IiiHHIIiiII',40,width,height,1,depth,0,len(data),0,0,0,0)+data
    bmp24=bmp(3,2,24,[(255,0,0,255),(0,255,0,255),(0,0,255,255),(255,255,255,255),(255,255,0,255),(255,0,255,255)])
    bmp32=bmp(2,-2,32,[(255,255,255,0),(0,255,0,128),(0,0,255,255),(255,0,0,255)])
    assert len(bmp24)==78 and len(bmp32)==70
    (out/'fixture24.bmp').write_bytes(bmp24);(out/'fixture32.bmp').write_bytes(bmp32)
    data='DataSection\nnaeBmp24:\n  Data.a '+','.join(str(b) for b in bmp24)+'\nnaeBmp32:\n  Data.a '+','.join(str(b) for b in bmp32)+'\nEndDataSection\n'
    (out / 'proof.pbi').write_text(
        f'#NAE_REPORT = ${layout["report"]:08X}\nXIncludeFile "{paths[0]}"\n'+data, encoding='utf8')
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
    identity = dict(target=a.target, bytes=image.stat().st_size,
                    sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                    checked_ranges=check_linked_layout(layout, log), source_hashes=before,
                    executed=False, scope='Pure application; resident graphics provider required at service ABI 1.8')
    (out / 'identity.json').write_text(json.dumps(identity, indent=2), encoding='utf8')

if __name__ == '__main__':
    main()
