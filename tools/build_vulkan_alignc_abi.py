#!/usr/bin/env python3
"""Compile the shared Vulkan AArch64 ABI probe via its board target entry.

Never uploads, resets, emulates or executes a board. A compile is not runtime
or Vulkan conformance acceptance. Entry still requires current map/ownership.
"""
from pathlib import Path
import argparse,os,subprocess,json,hashlib,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout

ENTRIES={'pi4':'RaspberryPi4/Tests/vulkan_alignc_abi.pi4','pi3':'RaspberryPi3/Tests/vulkan_alignc_abi.pi3','unoq':'ArduinoQ/Tests/vulkan_alignc_abi.unoq','rockpi4c':'RockPi4C/Tests/vulkan_alignc_abi.rockpi4c'}
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=list(ENTRIES),required=True);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);entry=ENTRIES[a.target];common='Anvil/Graphics/Vulkan/Tests/vulkan_alignc_abi.pbi'
text=(r/entry).read_text(encoding='utf8');assert '; pmf:target '+a.target in text and 'XIncludeFile "'+common+'"' in text
assert len(re.findall(r'ProcedureReturn [1-9][0-9]*',(r/common).read_text(encoding='utf8')))==12
layout=state_proof_layout(a.target);env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(r/entry),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'probe.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-800:]);assert q.returncode==0
image=d/'probe.img.pmf';(d/'identity.json').write_text(json.dumps(dict(target=a.target,entry=entry,shared=common,planned_assertions=12,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),entry_sha256=hashlib.sha256((r/entry).read_bytes()).hexdigest(),shared_sha256=hashlib.sha256((r/common).read_bytes()).hexdigest(),executed=False),indent=2))
