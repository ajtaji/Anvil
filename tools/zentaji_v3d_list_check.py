"""Run the existing V3D closed-list fixture on the native Zentaji CPU."""
# SPDX-License-Identifier: MIT
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from pmf_compiler import resolve_compiler
import vulkan_v3d_backend_list_check as gate

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zen-tools', type=Path, required=True)
    ap.add_argument('--keep', type=Path)
    a = ap.parse_args()
    cc = resolve_compiler(a.compiler)
    zt = a.zen_tools.resolve()
    sys.path.insert(0, str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    import zexpack
    s = gate.GATE.read_text(encoding='utf-8')
    assert s.count('#GATE_STRESS_DRAWS = 3505') == 1 and s.count('Fill(4096,0)') == 1
    s = s.replace('#GATE_STRESS_DRAWS = 3505', '#GATE_STRESS_DRAWS = 35').replace('Fill(4096,0)', 'Fill(40,0)')
    extra = r'''
  Fill(1,1) : draws[0]\blendMode=#ANVIL_VK_BLEND_ALPHA_ONE
  ResetObs() : rc=avkBackendSubmitDraw(@list)
  Put(162,rc) : Put(163,gateBegin) : Put(164,gateBlendCfg)
  Put(165,Bool((avkBackendCaps()&#ANVIL_VK_CAP_BLEND_ALPHA_ONE)<>0))
  Fill(1,1) : draws[0]\blendMode=3
  ResetObs() : rc=avkBackendSubmitDraw(@list)
  Put(166,rc) : Put(167,gateBegin) : Put(168,gateAlloc)
'''
    assert s.count('  ProcedureReturn #OUT') == 1
    s = s.replace('  ProcedureReturn #OUT', extra+'  ProcedureReturn #OUT', 1)

    def run(argv):
        p = subprocess.run([str(x) for x in argv], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        assert p.returncode == 0, (p.returncode, p.stdout[-6000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-v3d-list-native-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src = td/'probe.zentaji'
        image = td/'probe.zex'
        src.write_text(s, encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        print('Compiled existing V3D list contract for native Zentaji', flush=True)
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        m = F.Fixture(ram_size=128 << 20, cores=1)
        m.load_image(image.read_bytes())
        m.cores[0].r[255] = (128 << 20)-65536
        assert not F.capture(m, str(td))
        out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '100000000', '--ram', td/'final.bin'])
        (td/'native.txt').write_text(out, encoding='utf-8')
        end = next(x for x in out.splitlines() if x.startswith('END '))
        assert ' exit=7000000 ' in end, end
        ram = (td/'final.bin').read_bytes()

        class ObservationMemory:
            def get(self, address, default=0):
                return ram[address] if 0 <= address < len(ram) else default

        # The existing independent expected-property grader only reads bytes.
        # There is no A64 or Python CPU/device execution in this tool.
        bad = gate.grade(SimpleNamespace(memory=ObservationMemory()), gate.OUT, 35, 40)
        assert not bad, bad
        extra_result = struct.unpack_from('<7q', ram, gate.OUT+162*8)
        assert extra_result == (0, 1, 1, 1, -2, 0, 0), extra_result
        print('PASS native V3D list contract: existing independent properties at focused 35/40-list sizes plus7 ALPHA_ONE/hostile-mode properties; no Pi4 GPU execution claimed')


if __name__ == '__main__':
    main()
