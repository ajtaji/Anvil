"""Build physical CPU old/new descriptor schema comparison and lookup counts."""
from pathlib import Path
import argparse,re,json,hashlib,subprocess,os,gzip
from pmf_compiler import resolve_compiler
from build_vulkan_viewport_packets import proc

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--previous',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Graphics/Vulkan/vk_pipeline.pbi','Anvil/Graphics/Vulkan/vk_descriptor.pbi','Anvil/Graphics/Vulkan/vk_foundation.pbi']
 pipeline,descriptor,foundation=[(r/n).read_text(encoding='utf8') for n in names]
 old=gzip.decompress(a.previous.read_bytes()).decode('utf8')
 constants=['ANVIL_VK_TYPE_DESCRIPTOR_SET','ANVIL_VK_SPRITE_RESOURCE_CAPACITY','ANVIL_VK_SPRITE_RESOURCE_SLOTS','ANVIL_VK_MAX_DESCRIPTOR_SETS','ANVIL_VK_MAX_SET_BINDINGS','ANVIL_VK_TOKEN_MAGIC','ANVIL_VK_TOKEN_MAGIC_MASK']
 s='\n'.join(re.search(r'(?m)^#'+n+r'\s*=.*$',foundation)[0] for n in constants)+'\n'
 for line in descriptor.splitlines():
  if re.match(r'Global Dim avkDs(Live|Gen|Dev|Count|Type|Stages)\.',line):s+=line+'\n'
 for name in ['avkPipeSetCount','avkPipeDev','avkPipeBindingCount']:s+=f'Global Dim {name}.i[2]\n'
 for name in ['avkPipeBindingType','avkPipeBindingStages']:s+=f'Global Dim {name}.i[3 * #ANVIL_VK_MAX_SET_BINDINGS]\n'
 s+='Global lookupCalls.i\n'
 for name in ['avkToken','avkTokenKind','avkTokenSlot','avkTokenGen','avkTokenShape']:s+=proc(foundation,name)+'\n'
 body=proc(descriptor,'avkDsSlot');body=body.replace('  s = avkTokenShape','  lookupCalls=lookupCalls+1\n  s = avkTokenShape');s+=body+'\n'
 for name in ['AnvilVkDescriptorSetDeviceSlot','AnvilVkDescriptorSetSchemaCount','AnvilVkDescriptorSetSchemaType','AnvilVkDescriptorSetSchemaStages']:s+=proc(descriptor,name)+'\n'
 s+=proc(old,'avkDrawSetMatchesPipe').replace('avkDrawSetMatchesPipe(', 'previousMatches(',1)+'\n'
 s+=proc(pipeline,'avkDrawSetMatchesPipe')+'\n'
 s+=r"""
Procedure Init()
 Define i.i
 avkPipeSetCount[1]=1 : avkPipeDev[1]=7 : avkPipeBindingCount[1]=2
 For i=0 To #ANVIL_VK_MAX_DESCRIPTOR_SETS
  avkDsLive[i]=1 : avkDsGen[i]=3 : avkDsDev[i]=7 : avkDsCount[i]=2
  avkDsType[i*2]=6 : avkDsType[i*2+1]=1 : avkDsStages[i*2]=17 : avkDsStages[i*2+1]=16
 Next
 avkPipeBindingType[2]=6 : avkPipeBindingType[3]=1
 avkPipeBindingStages[2]=17 : avkPipeBindingStages[3]=16
EndProcedure
Procedure Record(index.i,h.i)
 Define p.i,a.i,b.i,oldCalls.i
 lookupCalls=0 : a=previousMatches(h,1) : oldCalls=lookupCalls
 lookupCalls=0 : b=avkDrawSetMatchesPipe(h,1)
 p=$E1C00100+index*32
 PokeI(p,a) : PokeI(p+8,b) : PokeI(p+16,oldCalls) : PokeI(p+24,lookupCalls)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,h.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$53434831)
"""
 cases=[('', 'avkToken(19,1,3)',1,6),('', 'avkToken(19,#ANVIL_VK_MAX_DESCRIPTOR_SETS,3)',1,6),('', '0',0,1),('', 'avkToken(18,1,3)',0,1),('', 'avkToken(19,0,3)',0,1),('', 'avkToken(19,#ANVIL_VK_MAX_DESCRIPTOR_SETS+1,3)',0,1),('', 'avkToken(19,1,2)',0,1),('avkDsLive[1]=0','avkToken(19,1,3)',0,1),('avkDsDev[1]=8','avkToken(19,1,3)',0,1),('avkDsCount[1]=1','avkToken(19,1,3)',0,2),('avkDsType[2]=1','avkToken(19,1,3)',0,3),('avkDsStages[2]=16','avkToken(19,1,3)',0,4),('avkDsType[3]=6','avkToken(19,1,3)',0,5),('avkDsStages[3]=17','avkToken(19,1,3)',0,6),('avkPipeSetCount[1]=0','0',1,0),('avkDsCount[1]=1 : avkPipeBindingCount[1]=1','avkToken(19,1,3)',1,4),('avkDsGen[1]=65535','avkToken(19,1,65535)',1,6),('avkDsGen[1]=1','avkToken(19,1,65535)',0,1),('', '$1234',0,1),('avkPipeDev[1]=8','avkToken(19,1,3)',0,1)]
 expected=[]
 for i,(change,handle,result,calls) in enumerate(cases):
  s+=' Init() : '+(change+' : ' if change else '')+f'Record({i},{handle})\n'
  expected.append([result,result,calls,0 if calls==0 else 1])
 s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\n'
 source=d/'proof.pi4';source.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
 p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},case_count=len(cases),expected=expected,previous_sha256=hashlib.sha256(a.previous.read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
