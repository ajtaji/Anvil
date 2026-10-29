"""Compile actual float port capacity entry points with controlled callbacks; no execution."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',required=True,choices=['pi4','unoq']);ap.add_argument('--out',required=True,type=Path);ap.add_argument('--compiler',required=True);ap.add_argument('--port-source',type=Path);a=ap.parse_args()
 d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
 p=a.port_source or R/'Anvil/Graphics/Vulkan/neon_vk_port.pbi';port=p.read_text(encoding='utf8')
 head=port[:port.index('Procedure.i nvpRound')]
 names=['nvpRound','nvpChannel','NeonVkPortColour','NeonVkPortCanvas','NeonVkPortPolygon','NeonVkPortStaticLines']
 bodies=[]
 for name in names:
  m=re.search(r'^Procedure\.i '+name+r'\([^\n]*\n.*?^EndProcedure',port,re.M|re.S);assert m,name;bodies.append(m.group())

 for i,body in enumerate(bodies):
  for old,new in {'NeonFanBegin': 'NpcFanBegin', 'NeonFanPoint': 'NpcFanPoint', 'NeonFanEnd': 'NpcFanEnd', 'NeonLinesBegin': 'NpcLinesBegin', 'NeonLine': 'NpcLine', 'NeonLinesEnd': 'NpcLinesEnd'}.items():body=re.sub(r'\b'+old+r'\b',new,body)
  bodies[i]=body
 fixture=(R/'RaspberryPi4/Tests/neon_port_capacity_proof.pbi').read_text()
 cases=[]
 def line(n,limit=0,ptr='@npcXY[0]'):return f'NeonVkPortStaticLines({ptr},{n},1.0,1.0,1.0,1.0,{limit})'
 def poly(n,solid):return f'NeonVkPortPolygon(16.0,16.0,8.0,8.0,{n},1.0,1.0,1.0,1.0,{solid},0,1)'
 calls=[(77,line(262144)),(77,line(262146)),(77,line(262145)),(77,line(4098)),(0,line(3,3)),(77,line(0,ptr='0')),(77,line(-1)),(77,line(2,ptr='0')),(77,line(9223372036854775807)),(77,line(9223372036854775807,262144)),(77,poly(262142,1)),(77,poly(262143,1)),(77,poly(131072,0)),(77,poly(131073,0)),(77,poly(2,1)),(77,poly(2049,0)),(0,line(4098)),(0,poly(2049,1)),(0,poly(2049,0))]
 for i,(begin,call) in enumerate(calls):cases.append(f' NpcReset({begin}) : rc={call} : NpcRecord({i},rc)')
 source='EnableFloatingPoint\n#NPC_REPORT='+str(layout['report'])+'\n#NEON_MAX_VERTS=262144\n#NEON_OK=0\nXIncludeFile "Anvil/Graphics/neon_colour.pbi"\n'+fixture.replace('; NPC_ACTUAL_PORT',head+'\n'+'\n'.join(bodies)).replace('; NPC_CASES','\n'.join(cases))
 (d/'proof.pbi').write_text(source)
 env=os.environ.copy();env['PMF_ROOT']=str(R)
 q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,encoding='utf8',timeout=120)
 (d/'compile.txt').write_text(q.stdout+q.stderr);print((q.stdout+q.stderr)[-2200:]);assert q.returncode==0
 ranges=check_linked_layout(layout,q.stdout+q.stderr);payload=d/'proof.img.pmf'
 (d/'identity.json').write_text(json.dumps(dict(bytes=payload.stat().st_size,sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),layout=layout,checked_ranges=ranges,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()},controlled_backend=True),indent=2))
if __name__=='__main__':main()
