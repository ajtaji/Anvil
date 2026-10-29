from pathlib import Path
import subprocess,sys,os,re,json,hashlib
TAIL=' PokeI($E1C00008,avkV3dCacheIntervalCount)\n For i=0 To avkV3dCacheIntervalCount-1\n  PokeI($E1C00800+i*16,avkV3dCacheInterval[i]\\firstByte)\n  PokeI($E1C00808+i*16,avkV3dCacheInterval[i]\\endByte)\n Next\n ; Reset retains stale lookup indices: no previous-frame span may be lost.\n avkV3dCacheIntervalCount=0\n PokeI($E1C00010,avkV3dCacheIntervalAdd(32768,4096))\n PokeI($E1C00018,avkV3dCacheIntervalCount)\n PokeI($E1C00700,avkV3dCacheInterval[0]\\firstByte)\n PokeI($E1C00708,avkV3dCacheInterval[0]\\endByte)\n ; Capacity is reached only after storing the original span. A duplicate\n ; already in that list is safe; a new disjoint range must still refuse.\n avkV3dCacheIntervalCount=#ANVIL_VK_MAX_RECORDED_DRAWS*#AVK_V3D_CACHE_INTERVALS_PER_DRAW\n n=avkV3dCacheIntervalCount-1\n avkV3dCacheInterval[n]\\firstByte=$800000 : avkV3dCacheInterval[n]\\endByte=$800010\n PokeI($E1C00020,avkV3dCacheIntervalAdd($900000,16))\n PokeI($E1C00028,avkV3dCacheIntervalAdd(32768,4096))\n PokeI($E1C00030,avkV3dCacheIntervalCount)\n avkV3dCacheIntervalCount=0\n PokeI($E1C00000,$43494E31)\n ProcedureReturn 0\nEndProcedure\n'
import argparse
ap=argparse.ArgumentParser(description='Build a RAM-only test of the exact cache interval collector')
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
owner_path='RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4'
code=(r/owner_path).read_text(encoding='utf8');begin=code.index('Structure AvkV3dCacheInterval');end=code.index('\nProcedure.i avkV3dIntervalAfter',begin)
owner=code[begin:end]
assert re.search(r'^#ANVIL_VK_MAX_BINDINGS = 4$',(r/'Anvil/Graphics/Vulkan/vk_foundation.pbi').read_text(),re.M)
cases=json.loads((r/'tools/vulkan_cache_interval_cases.json').read_text())
prefix='XIncludeFile "RaspberryPi4/Lib/uart.pi4"\nXIncludeFile "Anvil/Hal/hal.pbi"\n#ANVIL_VK_MAX_BINDINGS=4\nXIncludeFile "Anvil/Graphics/Vulkan/vk_draw_limits.pbi"\n'+owner
main='\nProcedure.i Main(services.i)\n Protected i.i,n.i\n For i=0 To 8191 : PokeA($E1C00000+i,0) : Next\n'
for i,(first,size) in enumerate(cases):main+=f' PokeI($E1C00040+{i}*8,avkV3dCacheIntervalAdd({first},{size}))\n'
s=(prefix+main+TAIL).encode('utf8');(d/'proof.pi4').write_bytes(s)
pending=[s.decode()];inputs={}
while pending:
 for n in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',pending.pop(0)):
  if n in inputs:continue
  assert len(inputs)<64
  b=(r/n).read_bytes();inputs[n]=hashlib.sha256(b).hexdigest();pending.append(b.decode('utf-8-sig'))
inputs[owner_path]=hashlib.sha256((r/owner_path).read_bytes()).hexdigest()
inputs['tools/vulkan_cache_interval_cases.json']=hashlib.sha256((r/'tools/vulkan_cache_interval_cases.json').read_bytes()).hexdigest()
c=Path(a.compiler)
q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-2500:],flush=True);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c01fff']}
items=[(n,*(int(x,16) for x in p)) for n,p in ranges.items()]
for i,(n,a,b) in enumerate(items):
 assert a<=b
 for m,c1,c2 in items[i+1:]:assert b<c1 or c2<a,(n,m)
p=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_hashes=inputs,checked_ranges=ranges,source_sha256=hashlib.sha256(s).hexdigest()),indent=2))
