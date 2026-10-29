#!/usr/bin/env python3
"""Build a returning CPU descriptor/cache probe, without running it."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from layering_check import strip_comments_only,strip_noncode

def build(out, compiler_path=None):
    root=Path(__file__).resolve().parents[1]
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    source=root/'RaspberryPi4/Tests/neon_coordinate_reuse_gate.pi4'
    compiler=resolve_compiler(compiler_path)
    assert compiler.is_file(),compiler
    env=os.environ.copy();env['PMF_ROOT']=str(root)
    args=[str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x1000000',
          '--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(out/'proof.img')]
    q=subprocess.run(args,cwd=root,env=env,capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8',newline='\n')
    assert q.returncode==0,log[-4000:]
    code=re.search(r'image [0-9]+ bytes, occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    bss=re.search(r' bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    pending=[source];seen=set();hashes={};missing=[];heap=[]
    lines=lambda s:s if isinstance(s,str) else '\n'.join(s)
    while pending:
        p=pending.pop(0).resolve()
        if p in seen:continue
        assert p.is_relative_to(root) and len(seen)<512;seen.add(p)
        data=p.read_bytes();name=p.relative_to(root).as_posix();hashes[name]=hashlib.sha256(data).hexdigest()
        text=data.decode('utf-8-sig')
        if re.search(r'\b(?:AllocateMemory|ReAllocateMemory|HeapAlloc)\s*\(',lines(strip_noncode(text)),re.I):heap.append(name)
        for literal in re.findall(r'^\s*(?:XIncludeFile|IncludeFile)\s+"([^"]+)"',lines(strip_comments_only(text)),re.I|re.M):
            a=(root/literal).resolve();b=(p.parent/literal).resolve()
            assert a.is_relative_to(root) or b.is_relative_to(root)
            if a.is_file():pending.append(a)
            elif b.is_file():pending.append(b)
            else:missing.append(dict(owner=name,literal=literal))
    payload=(out/'proof.img.pmf').read_bytes()
    ident=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),
        compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),source_hashes=hashes,
        source_graph_kind='Literal include superset including conditional branches',missing_references=missing,heap_calls=heap,
        gpu_execution=False,descriptor_fixture=True,ranges=dict(
            code=[int(v,16) for v in code.groups()],bss=[int(v,16) for v in bss.groups()],
            stack=[0x4e00000,0x4efffff],surface_descriptor_span=[0x3000000,0x3ffffff],
            pool_descriptor_span=[0x5000000,0x53fffff],x_table_guards=[0x60ffffc,0x610c00f],
            y_table_guards=[0x61ffffc,0x620c00f],report=[0xe1c00000,0xe1c9ffff]))
    assert not missing and not heap,(missing,heap)
    (out/'identity.json').write_text(json.dumps(ident,indent=2),encoding='utf8',newline='\n')
    print(json.dumps(dict(bytes=len(payload),sha256=ident['sha256'],source_count=len(hashes),ranges=ident['ranges']),indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--compiler')
    args=ap.parse_args();build(args.out,args.compiler)
