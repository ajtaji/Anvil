#!/usr/bin/env python3
"""Fetch Anvil's exact Vulkan-Headers registry input; never substitute a new pin.

The v1.4.350 annotated tag object resolves to COMMIT below. Raw content URLs
require that commit, not the tag object's hash. The XML remains an external
build input; this tool neither generates vocabulary nor changes declarations.
"""
import argparse,hashlib,json,urllib.request
from pathlib import Path

TAG='v1.4.350'
TAG_OBJECT='a33416ed2ce6bf8ef48b4eda821825f66d1850d3'
COMMIT='8864cdc896bbc2a9b6eb36b3218fc9ef57908d77'
SHA256='50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08'
BYTES=3264809
URL=f'https://raw.githubusercontent.com/KhronosGroup/Vulkan-Headers/{COMMIT}/registry/vk.xml'

def verify(data):
    if len(data)!=BYTES or hashlib.sha256(data).hexdigest()!=SHA256:
        raise ValueError('the registry does not match the existing pinned size/SHA-256; nothing was replaced')

def fetch(out):
    out=Path(out).resolve()
    cached=out.exists()
    if cached:
        if out.stat().st_size!=BYTES:
            raise ValueError('the existing output has the wrong size; it was not replaced')
        verify(out.read_bytes())
    else:
        request=urllib.request.Request(URL,headers={'User-Agent':'Anvil-registry-verification'})
        with urllib.request.urlopen(request,timeout=45) as response:
            data=response.read(BYTES+1)
        verify(data)
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('xb') as stream:
            stream.write(data)
    return dict(tag=TAG,tag_object=TAG_OBJECT,commit=COMMIT,url=URL,
                bytes=BYTES,sha256=SHA256,cached=cached,path=str(out))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:
        result=fetch(args.out)
    except (OSError,ValueError) as error:
        ap.exit(1,f'fetch_vulkan_registry: {error}\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
