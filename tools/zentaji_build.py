"""Compile and wrap a counted Zentaji monitor as one reversible artifact set."""
import json
import os
from pathlib import Path
import subprocess
import uuid
import zentaji_boot_image as B


def compile_and_publish(compiler,source,output,*,root,publication_factory):
    token='%d-%s'%(os.getpid(),uuid.uuid4().hex)
    raw=output.with_name('.'+output.name+'.compiled-'+token+'.zex')
    stages=[]
    try:
        env=dict(os.environ,PMF_ROOT=str(root))
        command=[str(compiler),'--compile',str(source),'-t','zentaji','--entry-returns','-o',str(raw)]
        result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
        if result.stdout:print(result.stdout,end='' if result.stdout.endswith('\n') else '\n')
        if result.stderr:print(result.stderr,end='' if result.stderr.endswith('\n') else '\n')
        if result.returncode:raise SystemExit('Zentaji compile failed; build identity and prior artifacts are preserved.')
        zasm=Path(compiler).resolve().parent/'tools'/'zentaji'/('zasm.exe' if os.name=='nt' else 'zasm')
        if not zasm.is_file():raise SystemExit('The external compiler package is missing its Zentaji ASM assembler: '+str(zasm))
        mapping=json.loads(Path(str(raw)+'.zmap').read_text(encoding='utf-8-sig'))
        image,meta,assembly,source_map=B.pack(raw.read_bytes(),zasm,source_map=mapping)
        # The generic wrapper requires only stack/image separation. This
        # board also requires a full page in its rounded payload window.
        meta['startup_minimum_ram_bytes']=meta['minimum_ram_bytes']
        meta['minimum_ram_bytes']=max(meta['minimum_ram_bytes'],((meta['image_end']+4095)&-4096)+4096+meta['stack_bytes']+meta['rom_reserved_bytes'])
        contents=[(output,image),
            (Path(str(output)+'.boot.json'),(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode()),
            (Path(str(output)+'.asm'),assembly.encode()),
            (Path(str(output)+'.zmap'),(json.dumps(source_map,indent=2)+'\n').encode()),
            (Path(str(output)+'.compiled.zex'),raw.read_bytes()),
            (Path(str(output)+'.compiled.asm'),Path(str(raw)+'.asm').read_bytes())]
        for final,data in contents:
            stage=final.with_name('.'+final.name+'.build-stage-'+token)
            stages.append((stage,final));B.atomic(stage,data)
        publication=publication_factory(stages,token)
        publication.publish()
        print('Built %s (%d bytes), owned supervisor startup $%X.'%(output.relative_to(root),len(image),meta['entry']))
        return publication
    finally:
        # Only exact private files created by this invocation are removed.
        for path in [raw,Path(str(raw)+'.asm'),Path(str(raw)+'.zmap')]+[p for p,_ in stages]:
            if path.is_file():path.unlink()
