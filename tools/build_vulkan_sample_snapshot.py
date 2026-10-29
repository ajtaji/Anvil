"""Build focused live-object snapshot/refusal tests on the state-only backend."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    fixture='RaspberryPi4/Tests/Vulkan/vulkan_descriptor_gate.pi4';original=(r/fixture).read_text(encoding='utf8')
    s=original[:original.index('Global Dim dgReport')]
    s+='Global Dim dgReport.i[512]\n'
    for n in ['dgPut','dgStop']:
        s+=re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\(.*?^EndProcedure',original)[0]+'\n'
    s+=r'''
Procedure SnapshotRow(row.i,set.i,binding.i,nullOut.i,nullRefs.i)
 Define base.i=$E1C10200+row*512
 Define out.i=base+64,refs.i=base+192,legacy.i=base+256
 If nullOut<>0 : out=0 : legacy=0 : EndIf
 If nullRefs<>0 : refs=0 : EndIf
 PokeI(base,AnvilVkDescriptorSetSampledImageSnapshot(set,binding,out,refs))
 PokeI(base+8,AnvilVkDescriptorSetSampledImage(set,binding,legacy))
EndProcedure
'''
    main=original[original.index('Procedure.i Main()'):original.index('  ; Pipeline layout and actual public pipeline')]
    main=main.replace('Procedure.i Main()','Procedure.i Main(services.i)\n Define ds.i,ss.i,iv.i,im.i,mslot.i,idx.i,saved.i,row.i,oldSampler.i')
    main=main.replace('  dgPut(0, #DG_MAGIC)', '  For i=0 To 81919 : PokeA($E1C00000+i,$A5) : Next\n  dgPut(0, #DG_MAGIC)',1)
    s+=main
    s+=r'''
 If AnvilVkFaultCode()<>0 : ProcedureReturn 91 : EndIf
 ds=avkDsSlot(dset) : ss=avkSamplerSlot(sampler) : iv=avkIvSlot(sampleView)
 im=avkImgSlot(sampleImg) : mslot=avkImgMemSlot[im]
 idx=ds*#ANVIL_VK_MAX_SET_BINDINGS+1
 PokeI($E1C10010,AnvilVkImageAddress(sampleImg))
 PokeI($E1C10018,sampleImg) : PokeI($E1C10020,sampler) : PokeI($E1C10028,sampleView)
 SnapshotRow(0,dset,1,0,0)
 avkDsGen[ds]=avkDsGen[ds]+1 : SnapshotRow(1,dset,1,0,0) : avkDsGen[ds]=avkDsGen[ds]-1
 SnapshotRow(2,dset,-1,0,0) : SnapshotRow(3,dset,2,0,0) : SnapshotRow(4,dset,0,0,0)
 avkSampGen[ss]=avkSampGen[ss]+1 : SnapshotRow(5,dset,1,0,0) : avkSampGen[ss]=avkSampGen[ss]-1
 avkIvGen[iv]=avkIvGen[iv]+1 : SnapshotRow(6,dset,1,0,0) : avkIvGen[iv]=avkIvGen[iv]-1
 avkImgGen[im]=avkImgGen[im]+1 : SnapshotRow(7,dset,1,0,0) : avkImgGen[im]=avkImgGen[im]-1
 saved=avkSampDev[ss] : avkSampDev[ss]=avkDevSlot(dev2) : SnapshotRow(8,dset,1,0,0) : avkSampDev[ss]=saved
 saved=avkIvDev[iv] : avkIvDev[iv]=avkDevSlot(dev2) : SnapshotRow(9,dset,1,0,0) : avkIvDev[iv]=saved
 saved=avkImgDev[im] : avkImgDev[im]=avkDevSlot(dev2) : SnapshotRow(10,dset,1,0,0) : avkImgDev[im]=saved
 saved=avkImgBound[im] : avkImgBound[im]=0 : SnapshotRow(11,dset,1,0,0) : avkImgBound[im]=saved
 saved=avkImgUsage[im] : avkImgUsage[im]=0 : SnapshotRow(12,dset,1,0,0) : avkImgUsage[im]=saved
 saved=avkImgLayout[im] : avkImgLayout[im]=0 : SnapshotRow(13,dset,1,0,0) : avkImgLayout[im]=saved
 saved=avkDsImageLayout[idx] : avkDsImageLayout[idx]=0 : SnapshotRow(14,dset,1,0,0) : avkDsImageLayout[idx]=saved
 saved=avkHeapReady : avkHeapReady=0 : SnapshotRow(15,dset,1,0,0) : avkHeapReady=saved
 SnapshotRow(16,dset,1,1,0) : SnapshotRow(17,dset,1,0,1)
 ; Rewrite through the API, then destroy/reuse a sampler generation.
 oldSampler=sampler
 If vkCreateSampler(dev,@sampci,0,@sampler)<>0 : ProcedureReturn 92 : EndIf
 PokeI($E1C10030,sampler)
 dii\sampler=sampler
 AnvilVkFaultClear() : vkUpdateDescriptorSets(dev,1,@writeSample,0,0)
 If AnvilVkFaultCode()<>0 : ProcedureReturn 93 : EndIf
 SnapshotRow(18,dset,1,0,0)
 vkDestroySampler(dev,sampler,0)
 SnapshotRow(19,dset,1,0,0)
 If vkCreateSampler(dev,@sampci,0,@sampler)<>0 : ProcedureReturn 94 : EndIf
 PokeI($E1C10038,sampler)
 SnapshotRow(20,dset,1,0,0)
 dii\sampler=sampler
 AnvilVkFaultClear() : vkUpdateDescriptorSets(dev,1,@writeSample,0,0)
 If AnvilVkFaultCode()<>0 : ProcedureReturn 95 : EndIf
 SnapshotRow(21,dset,1,0,0)
 PokeI($E1C10000,$534E5031) : PokeI($E1C10008,22)
 ProcedureReturn 0
EndProcedure
'''
    s=s.replace('#DG_OUT = $06100000','#DG_OUT = $E1C00000')
    (d/'proof.pi4').write_text(s,encoding='utf8');pending=[s];inputs={fixture:hashlib.sha256((r/fixture).read_bytes()).hexdigest()}
    while pending:
        for n in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',pending.pop()):
            if n in inputs:continue
            assert len(inputs)<256
            b=(r/n).read_bytes();inputs[n]=hashlib.sha256(b).hexdigest();pending.append(b.decode('utf-8-sig'))
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c13fff'],'heap':['0x06200000','0x062fffff']}
    intervals=[(n,*(int(x,16) for x in v)) for n,v in ranges.items()]
    for i,(n,x,y) in enumerate(intervals):
        for other,u,v in intervals[i+1:]:assert y<u or v<x,(n,other)
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs),indent=2),encoding='utf8')
if __name__=='__main__':main()
