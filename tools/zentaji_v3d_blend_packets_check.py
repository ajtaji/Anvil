"""Execute production V3D blend emission on native Zentaji; no GPU claim."""
# SPDX-License-Identifier: MIT
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
from zentaji_neon_pipeline_check import procedure

ROOT = Path(__file__).resolve().parents[1]
CASES = ((0,), (1,), (2,), (0, 2, 1, 0), (2, 2), (1, 2, 1, 2), (2, 0, 2))


def block(text, prefix):
    start = text.index(prefix)
    spaces = len(prefix)-len(prefix.lstrip())
    end = text.index('\n'+' '*spaces+'EndIf', start)+len('\n'+' '*spaces+'EndIf')
    return text[start:end]


def source():
    gpu = (ROOT/'RaspberryPi4/Lib/v3d.pi4').read_text(encoding='utf-8')
    backend = (ROOT/'RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4').read_text(encoding='utf-8')
    foundation = (ROOT/'Anvil/Graphics/Vulkan/vk_foundation.pbi').read_text(encoding='utf-8')
    from vulkan_v3d_backend_check import source_contract
    assert not source_contract(backend), source_contract(backend)
    # Keep metadata allowances narrow: retargeting either reviewed write, or
    # adding another CPU write, must still make the production source gate red.
    for old, new in (
        ('PokeI(*out + offset, PeekI(*in + offset))', 'PokeI(*in + offset, PeekI(*out + offset))'),
        ('PokeL(uniformAddr + 0, inputBase)', 'PokeL(outputBase + 0, inputBase)'),
    ):
        assert backend.count(old) == 1
        assert source_contract(backend.replace(old, new, 1)), old
    assert source_contract(backend+'\nProcedure BadWrite()\n PokeL(1,0)\nEndProcedure\n')
    names = ('V3D_OK', 'V3D_ERR_CL_ARGS', 'V3D_ERR_CL_NOBUF', 'V3D_ERR_CL_FULL',
             'V3D_CLE_READAHEAD', 'V3D_PKT_CFG_BITS', 'V3D_PKT_BLEND_ENABLES', 'V3D_PKT_BLEND_CFG',
             'V3D_BF_SRC_ALPHA', 'V3D_BF_INV_SRC_ALPHA', 'V3D_BF_ONE', 'V3D_BM_ADD',
             'AVK_V3D_CFG_FWD', 'AVK_V3D_CFG_REV', 'AVK_V3D_CFG_CW', 'AVK_V3D_CFG_DEPTH_ALWAYS',
             'ANVIL_VK_BLEND_DISABLED', 'ANVIL_VK_BLEND_SRC_OVER', 'ANVIL_VK_BLEND_ALPHA_ONE')
    s = ''
    for name in names:
        found = re.findall(r'^#'+name+r'\s*=.*$', gpu+'\n'+backend+'\n'+foundation, re.M)
        assert len(found) == 1, name
        s += found[0]+'\n'
    s += '''Structure PacketDraw
 blendMode.i
EndStructure
Global v3d_clBase.i,v3d_clPos.i,v3d_clCap.i,v3d_clOpen.i,v3d_clErr.i
Global Dim storage.a[512]
Global Dim results.a[14336]
Global Dim sequence.i[8]
'''
    for name in ('v3d_ClU8', 'v3d_ClU32', 'V3dCfgBitsWord', 'V3dClCfgBits', 'V3dClBlendEnables', 'V3dClBlendCfg'):
        s += procedure(gpu, name)
    for name, indent, part in (('EmitLegacy', '    ', 'avkV3dSubmitLegacyDraw'),
                               ('EmitList', '          ', 'avkBackendSubmitDraw')):
        body = procedure(backend, part)
        s += 'Procedure '+name+'(*d.PacketDraw)\n'
        s += block(body, indent+'If *d\\blendMode = #ANVIL_VK_BLEND_SRC_OVER')+'\nEndProcedure\n'
    budget = block(procedure(backend, 'avkV3dListPacketBytes'), '      If blend <> *d\\blendMode')
    s += '''Procedure.i BlendBudget(count.i)
 Define bytes.i,blend.i=-1,n.i,record.PacketDraw,*d.PacketDraw
 *d=@record
 For n=0 To count-1
  record\\blendMode=sequence[n]
'''+budget+'''
 Next
 ProcedureReturn bytes
EndProcedure
Procedure RunRow(index.i,count.i,cached.i)
 Define n.i,blend.i=-1,row.i,d.PacketDraw
 row=@results[0]+index*1024
 For n=0 To 1023 : PokeA(row+n,$A5) : Next
 For n=0 To 511 : storage[n]=$A5 : Next
 v3d_clBase=@storage[16] : v3d_clCap=480 : v3d_clPos=0 : v3d_clErr=0 : v3d_clOpen=1
 For n=0 To count-1
  d\\blendMode=sequence[n]
  If cached=0
   EmitLegacy(@d)
  ElseIf blend<>d\\blendMode
   EmitList(@d) : blend=d\\blendMode
  EndIf
 Next
 PokeQ(row,v3d_clPos) : PokeQ(row+8,v3d_clErr) : PokeQ(row+16,BlendBudget(count)) : PokeQ(row+24,count)
 For n=0 To 511 : PokeA(row+64+n,storage[n]) : Next
EndProcedure
Procedure.i Main()
'''
    for i, seq in enumerate(CASES):
        for n, mode in enumerate(seq):
            s += ' sequence[%d]=%d\n' % (n, mode)
        for cached in (0, 1):
            s += ' RunRow(%d,%d,%d)\n' % (i*2+cached, len(seq), cached)
    return s+' ProcedureReturn 42\nEndProcedure\n'


def packet(mode):
    cfg = 0x7003 | (0x80000 if mode else 0)
    out = bytes((96, cfg & 255, (cfg >> 8) & 255, cfg >> 16, 83, int(mode != 0)))
    if mode:
        # V3D4.2 BLEND_CFG: target0, RGB dst7/src6/ADD,
        # alpha dst7/src6 or1/ADD. Independent documented field packing.
        word = (1 << 24) | (7 << 20) | (6 << 16) | (7 << 8) | ((6 if mode == 1 else 1) << 4)
        out += bytes((84,))+struct.pack('<I', word)
    return out


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

    def run(argv):
        p = subprocess.run([str(x) for x in argv], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        assert p.returncode == 0, (p.returncode, p.stdout[-5000:], p.stderr)
        return p.stdout

    with tempfile.TemporaryDirectory(prefix='anvil-v3d-blend-wire-') as tmp:
        td = a.keep.resolve() if a.keep else Path(tmp)
        td.mkdir(parents=True, exist_ok=True)
        src = td/'probe.zentaji'
        image = td/'probe.zex'
        src.write_text(source(), encoding='utf-8')
        run([cc, '--compile', src, '-o', image])
        ref = A.Asm()
        org, data = ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes() == zexpack.header(org, org, data)+data
        m = F.Fixture(ram_size=2 << 20, cores=1)
        m.load_image(image.read_bytes())
        m.cores[0].r[255] = (2 << 20)-65536
        assert not F.capture(m, str(td))
        out = run([zt/'zenemu.exe', td/'machine.txt', '--max', '10000000', '--ram', td/'final.bin'])
        (td/'native.txt').write_text(out, encoding='utf-8')
        assert ' exit=2A ' in next(x for x in out.splitlines() if x.startswith('END ')), out
        ram = (td/'final.bin').read_bytes()
        for i, seq in enumerate(CASES):
            compact = tuple(mode for n, mode in enumerate(seq) if n == 0 or seq[n-1] != mode)
            budget = sum(len(packet(mode)) for mode in compact)
            for cached in (0, 1):
                wire = b''.join(packet(mode) for mode in (compact if cached else seq))
                expected = bytearray([0xA5])*1024
                struct.pack_into('<4Q', expected, 0, len(wire), 0, budget, len(seq))
                expected[80:80+len(wire)] = wire
                at = ref.sym['GLOBAL_RESULTS']+(i*2+cached)*1024
                assert ram[at:at+1024] == expected, (seq, cached, 'wire bytes, transition budget or guards')
        print('PASS V3D blend packet emission: 14 native cases, both production paths, disabled/SRC_ALPHA/ONE alpha, cached transitions, exact wire bytes and guards; no Pi4 GPU execution claimed')


if __name__ == '__main__':
    main()
