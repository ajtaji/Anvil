#!/usr/bin/env python3
"""Build two native fallback frames around a real Vulkan widget frame; no boot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from pmf_compiler import resolve_compiler

ap = argparse.ArgumentParser()
ap.add_argument('--out', type=Path, required=True)
ap.add_argument('--compiler', required=True)
a = ap.parse_args()
r = Path(__file__).resolve().parents[1]
d = a.out.resolve()
d.mkdir(parents=True, exist_ok=False)
main = r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4'
helper = r/'RaspberryPi4/Tests/neon_native_dispatch_gpu_proof.pbi'
s = main.read_text()
assert s.count('#NW_PROOF_MODE        = 0') == 1
s = s.replace('#NW_PROOF_MODE        = 0', '#NW_PROOF_MODE        = 1')
at = s.index('Procedure.i Main()')
s = s[:at]+helper.read_text()+'\n'+s[at:]
s = s.replace('Procedure.i Main()', 'Procedure.i NdgVulkanScene()', 1)
before = '  NeonStateReset()\n'
assert s.count(before) == 1
s = s.replace(before, before+'  PokeI($E1C02000, NdgNativeFrame(0))\n', 1)
after = '  vkDestroyInstance(inst, 0)\n  NeonShutdown()'
assert s.count(after) == 1
s = s.replace(after, '  vkDestroyInstance(inst, 0)\n  PokeI($E1C02080, NdgNativeFrame(1))\n  NeonShutdown()', 1)
s += '''
Procedure.i Main(services.i)
  Protected report.i, i.i
  For i = 0 To 255 : PokeA($E1C02000+i, 0) : Next
  PokeI($E1C02000, -1) : PokeI($E1C02080, -1)
  report = NdgVulkanScene()
  If report = 0 : ProcedureReturn 199 : EndIf
  For i = 0 To 255 : PokeA($E1C00000+i, PeekA(report+i)) : Next
  If PeekL($E1C00004) <> 0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
  If PeekI($E1C02000) <> 0 : ProcedureReturn 2000+PeekI($E1C02000) : EndIf
  If PeekI($E1C02080) <> 0 : ProcedureReturn 3000+PeekI($E1C02080) : EndIf
  ProcedureReturn 0
EndProcedure
'''
(d/'proof.pi4').write_text(s, encoding='utf8')
env = os.environ.copy()
env['PMF_ROOT'] = str(r)
q = subprocess.run([str(resolve_compiler(a.compiler)), '--compile', str(d/'proof.pi4'),
                    '-t', 'pi4', '--load-addr', '0x1000000', '--stack-addr', '0x4F00000',
                    '--entry-returns', '--wants-services', '-o', str(d/'proof.img')],
                   env=env, capture_output=True, text=True, encoding='utf8', timeout=180)
(d/'compile.txt').write_text(q.stdout+q.stderr, encoding='utf8')
print((q.stdout+q.stderr)[-1600:])
assert q.returncode == 0
inputs = [main, helper, r/'Anvil/Graphics/Vulkan/neon_vk_prepared_lifecycle.pbi', r/'Anvil/Graphics/neon_frontend.pbi', r/'RaspberryPi4/Lib/neon.pi4',
          r/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi', r/'RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4']
p = d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}), indent=2))
