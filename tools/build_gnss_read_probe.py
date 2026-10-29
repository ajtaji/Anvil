"""Build the returning Pi 4 GNSS read/decode proof without receiver hardware."""
import argparse
import functools
import hashlib
import json
import operator
import os
from pathlib import Path
import re
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source=root/'RaspberryPi4/Tests/Vulkan/gnss_read_probe.pi4'
    wire=b'$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n'
    assert len(wire)==67 and functools.reduce(operator.xor,wire[1:wire.index(b'*')])==0x47
    suffix='\nDataSection\n testGga:\n Data.a '+','.join(map(str,wire))+'\n testGgaEnd:\nEndDataSection\n'
    data=source.read_bytes()+suffix.encode()
    (out/'proof.pi4').write_bytes(data)
    pending=[data.decode('utf8')];inputs={source.relative_to(root).as_posix():hashlib.sha256(source.read_bytes()).hexdigest()}
    while pending:
        for name in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',pending.pop(0)):
            if name in inputs:continue
            assert len(inputs)<64
            blob=(root/name).read_bytes();inputs[name]=hashlib.sha256(blob).hexdigest()
            pending.append(blob.decode('utf-8-sig'))
    command=[str(a.compiler.resolve()),'--compile',str(out/'proof.pi4'),'-t','pi4',
             '--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns',
             '--wants-services','-o',str(out/'proof.img')]
    q=subprocess.run(command,env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,
                     text=True,encoding='utf8',timeout=180,
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8')
    if q.returncode:raise RuntimeError(log)
    assert inputs=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in inputs}
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    assert code and bss
    spans={'code':['0x'+x for x in code.groups()], 'bss':['0x'+x for x in bss.groups()],
           'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c007ff']}
    pairs=[(n,*(int(v,16) for v in s)) for n,s in spans.items()]
    for i,(name,lo,hi) in enumerate(pairs):
        assert lo<=hi
        for other,a1,b1 in pairs[i+1:]:assert hi<a1 or b1<lo,(name,other)
    payload=(out/'proof.img.pmf').read_bytes()
    result=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),
                source_hashes=inputs,checked_ranges=spans,executed=False)
    (out/'identity.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(dict(bytes=result['bytes'],sha256=result['sha256'])))


if __name__=='__main__':main()
