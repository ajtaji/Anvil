"""Build a pure client for resident offscreen target qualification."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source='XIncludeFile "Anvil/Graphics/Tests/neon_service_target_load.pbi"\nProcedure.i Main(services.i)\n  Protected i.i\n  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next\n  ProcedureReturn NeonServiceTargetLoadProof(services,$E1C00000)\nEndProcedure\n'
    (out/'proof.pi4').write_text(source,encoding='utf8',newline='\n')
    pending=[source];inputs={}
    while pending:
        for name in re.findall(r'(?mi)^\s*XIncludeFile\s+"([^"]+)"',pending.pop(0)):
            p=(root/name).resolve();assert p.is_relative_to(root)
            if name in inputs:continue
            b=p.read_bytes();inputs[name]=hashlib.sha256(b).hexdigest();pending.append(b.decode('utf-8-sig'))
    compiler=Path(resolve_compiler(a.compiler));compiler_sha=hashlib.sha256(compiler.read_bytes()).hexdigest()
    q=subprocess.run([str(compiler),'--compile',str(out/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8',newline='\n')
    assert q.returncode==0,log[-4000:]
    assert inputs=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in inputs}
    assert compiler_sha==hashlib.sha256(compiler.read_bytes()).hexdigest()
    ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges['report']=['0xe1c00000','0xe1c03fff']
    b=(out/'proof.img.pmf').read_bytes()
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),compiler_sha256=compiler_sha,source_hashes=inputs,checked_ranges=ranges,executed=False,scope='Pure graphics client; resident minor11 preserved target service required; no driver linked'),indent=2),encoding='utf8',newline='\n')
    print(len(b),hashlib.sha256(b).hexdigest())
if __name__=='__main__':main()
