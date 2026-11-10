"""Wrap a compiled Zentaji guest in Anvil's own supervisor startup and vectors.

The original payload's addresses/bytes stay fixed. Its BSS becomes zero bytes
before the appended vector/startup slab. The startup owns a 16-byte-aligned
stack below the ROM's reserved top 1MB and checks actual RAM before entry.
This packs an architecture entry; it does not supply a monitor or device driver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib
import uuid
import re

ROOT=Path(__file__).resolve().parents[1]
STARTUP=ROOT/'Anvil/Kernel/Zentaji/startup.zen'
MAGIC=b'ZENTAJI1'
MAX_BYTES=64<<20


def inspect(image):
    if len(image)<64 or image[:8]!=MAGIC:raise ValueError('not a Zentaji executable header')
    entry,load,size,bss,stack,flags,crc,reserved=struct.unpack('<QQQQQQII',image[8:64])
    if size<1 or size!=len(image)-64 or size+bss>MAX_BYTES:raise ValueError('payload/BSS size is invalid or exceeds the 64MB pack limit')
    if load%8 or entry%8 or not load<=entry<load+size:raise ValueError('invalid load/entry alignment or entry extent')
    if load+size+bss>=(1<<63):raise ValueError('image address extent is unsupported')
    if stack%16 or flags or reserved:raise ValueError('Anvil requires supervisor flags=0, aligned stack and reserved=0')
    if zlib.crc32(image[64:])&0xffffffff!=crc:raise ValueError('compiled payload CRC mismatch')
    return dict(entry=entry,load=load,size=size,bss=bss,stack=stack)


def source(image,stack_bytes=65536):
    h=inspect(image)
    if not 16384<=stack_bytes<=1048576 or stack_bytes%16:raise ValueError('stack bytes must be a multiple of 16 in 16384..1048576')
    vector=(h['load']+h['size']+h['bss']+4095)&-4096
    payload=image[64:]
    padded=payload+bytes(-len(payload)%8)
    lines=[f'.equ ZEN_VECTOR_BASE,${vector:X}',f'.equ ZEN_COMPILED_ENTRY,${h["entry"]:X}',f'.equ ZEN_IMAGE_LOAD,${h["load"]:X}',f'.equ ZEN_STACK_BYTES,{stack_bytes}',f'.org ${h["load"]:X}']
    emitted=0
    for i in range(0,len(padded),64):
        block=padded[i:i+64]
        # Compiled globals include large zero-filled tables. Forward .org has
        # exactly the same zero-padding semantics without millions of literal
        # operands. Keep every nonzero payload byte and its address unchanged.
        if not any(block):continue
        if emitted!=i:lines.append(f'.org ${h["load"]+i:X}')
        lines.append('.word '+','.join(f'${int.from_bytes(block[j:j+8],"little"):016X}' for j in range(0,len(block),8)))
        emitted=i+len(block)
    if emitted!=len(padded):lines.append(f'.org ${h["load"]+len(padded):X}')
    h['startup_line_offset']=len(lines)
    lines.append(STARTUP.read_text(encoding='utf-8'))
    return '\n'.join(lines)+'\n',h,vector


def pack(image,zasm,stack_bytes=65536,source_map=None):
    assembly,h,vector=source(image,stack_bytes)
    with tempfile.TemporaryDirectory(prefix='anvil-zen-startup-') as tmp:
        src=Path(tmp)/'image.zen';binary=Path(tmp)/'payload.zex';src.write_text(assembly,encoding='utf-8')
        p=subprocess.run([str(zasm),'--zex',str(src),str(binary)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        if p.returncode or not p.stdout.startswith('ok: wrote '):raise ValueError('startup assembly failed: '+p.stdout+p.stderr)
        assembled=binary.read_bytes()
        if inspect(assembled)['load']!=h['load']:raise ValueError('assembler origin changed')
        payload=assembled[64:]
        startup_map=json.loads(Path(str(binary)+'.zmap').read_text(encoding='utf-8-sig'))
    if payload[:h['size']]!=image[64:]:raise ValueError('compiled payload changed during wrapping')
    if any(payload[h['size']:h['size']+h['bss']]):raise ValueError('original BSS was not preserved as zero')
    context=h['load']+len(payload)-128
    magic,version,size=struct.unpack_from('<QQQ',payload,len(payload)-128)
    payload_call=struct.unpack_from('<Q',payload,len(payload)-8)[0]
    if (magic,version,size)!=(0x4E455A4C49564E41,2,128) or payload_call%8 or not vector+4096<=payload_call<context:
        raise ValueError('assembled startup does not publish a valid version2 call boundary')
    entry=vector+4096
    output=MAGIC+struct.pack('<QQQQQQII',entry,h['load'],len(payload),0,0,0,zlib.crc32(payload)&0xffffffff,0)+payload
    meta=dict(schema=1,architecture='Zentaji',privilege='supervisor',load=h['load'],entry=entry,compiled_entry=h['entry'],vectors=vector,context=context,context_version=version,payload_call=payload_call,image_end=h['load']+len(payload),stack_bytes=stack_bytes,minimum_ram_bytes=max(2097152,(h['load']+len(payload)+stack_bytes+1048576+15)&-16),rom_reserved_bytes=1048576,compiled_sha256=hashlib.sha256(image).hexdigest(),image_sha256=hashlib.sha256(output).hexdigest(),startup_sha256=hashlib.sha256(STARTUP.read_bytes()).hexdigest())
    rows=[];sources={}
    if source_map is not None:
        if not isinstance(source_map,dict) or type(source_map.get('version')) is not int or source_map['version']!=1 or source_map.get('image')!=meta['compiled_sha256']:raise ValueError('compiler source map does not match the input image')
        if not isinstance(source_map.get('sources'),list) or not isinstance(source_map.get('code'),list):raise ValueError('invalid compiler source map arrays')
        for row in source_map['sources']:
            if not isinstance(row.get('path'),str) or not row['path'] or not isinstance(row.get('sha256'),str) or not re.fullmatch('[0-9a-fA-F]{64}',row['sha256']):raise ValueError('invalid compiler source identity')
            if row['path'] in sources:raise ValueError('duplicate compiler source identity')
            sources[row['path']]=row['sha256']
        for row in source_map['code']:
            if not isinstance(row.get('pc'),str) or not re.fullmatch('[0-9a-fA-F]{16}',row['pc']) or type(row.get('size')) is not int or type(row.get('line')) is not int:raise ValueError('invalid compiler instruction map fields')
            if int(row['pc'],16)+row['size']>h['load']+h['size']:raise ValueError('compiler instruction map exceeds the original payload')
            rows.append(row)
    startup_path=str(STARTUP.resolve())
    startup_hash=hashlib.sha256(STARTUP.read_bytes().replace(b'\r',b'')).hexdigest()
    if startup_path in sources and sources[startup_path]!=startup_hash:raise ValueError('startup source identity conflicts with the compiler map')
    sources[startup_path]=startup_hash
    for row in startup_map['code']:
        if int(row['pc'],16)<vector:raise ValueError('embedded guest data acquired an assembly breakpoint')
        row=dict(row,source=startup_path,line=row['line']-h['startup_line_offset'])
        if not 1<=row['line']<=len(STARTUP.read_text(encoding='utf-8').splitlines()):raise ValueError('startup source line is outside its source')
        rows.append(row)
    if not 1<=len(sources)<=4096 or len(rows)>1000000:raise ValueError('combined source map exceeds the supported entry limit')
    rows.sort(key=lambda row:int(row['pc'],16))
    previous=h['load']
    for row in rows:
        pc=int(row['pc'],16);size=row['size']
        if row['source'] not in sources or size not in (8,16) or pc%8 or pc<previous or pc+size>meta['image_end'] or not 1<=row['line']<=1000000:raise ValueError('invalid or overlapping merged instruction map')
        previous=pc+size
    mapping=dict(version=1,image=meta['image_sha256'],sources=[dict(path=p,sha256=v) for p,v in sorted(sources.items())],code=rows)
    return output,meta,assembly,mapping


def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def publish(output,image,meta,assembly,source_map):
    # Reuse Anvil's rollback transaction: image and descriptive sidecars are
    # one artifact set, even if an OS rename fails midway through publication.
    from build import PublishedArtifacts
    output=Path(output);token=uuid.uuid4().hex
    contents=[(output,image),(Path(str(output)+'.boot.json'),(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode('utf-8')),(Path(str(output)+'.asm'),assembly.encode('utf-8')),(Path(str(output)+'.zmap'),(json.dumps(source_map,indent=2)+'\n').encode('utf-8'))]
    pairs=[]
    try:
        for final,data in contents:
            stage=final.with_name('.'+final.name+'.build-stage-'+token)
            pairs.append((stage,final));atomic(stage,data)
        publication=PublishedArtifacts(pairs,token)
        publication.publish();publication.finalize()
    finally:
        for stage,final in pairs:
            if stage.exists():stage.unlink()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('compiled',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--zasm',type=Path,required=True);ap.add_argument('--stack-bytes',type=int,default=65536)
    a=ap.parse_args()
    destinations=[a.output,Path(str(a.output)+'.boot.json'),Path(str(a.output)+'.asm'),Path(str(a.output)+'.zmap')]
    protected=[a.compiled,Path(str(a.compiled)+'.zmap'),STARTUP]
    if {p.resolve() for p in protected}&{p.resolve() for p in destinations}:ap.error('wrapped output and sidecars must differ from the compiler inputs and startup source')
    try:
        source_map=json.loads(Path(str(a.compiled)+'.zmap').read_text(encoding='utf-8-sig'))
        output,meta,assembly,mapping=pack(a.compiled.read_bytes(),a.zasm,a.stack_bytes,source_map)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.TimeoutExpired) as e:raise SystemExit(str(e))
    try:publish(a.output,output,meta,assembly,mapping)
    except OSError as e:raise SystemExit(str(e))
    print(f'Packed {a.output.name}: {len(output)-64} payload bytes, startup ${meta["entry"]:X}, vectors ${meta["vectors"]:X}')


if __name__=='__main__':main()
