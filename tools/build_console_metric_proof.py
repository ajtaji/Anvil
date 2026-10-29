"""Build exact console metric consumers with controlled font-provider failures.

The font provider is a test double; arithmetic and both console consumers are
unchanged production procedure bodies. This is not a rasterizer or font-parser test.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    hashes={};bodies=[]
    for rel,names in [
        ('Anvil/Graphics/truetype_layout.pbi',['anvil_ttl_Scale','AnvilTrueTypeScaleMetric']),
        ('RaspberryPi4/Board/screen_cmd.pi4',['ScreenFontMetricCacheBuild','ScreenProportionalAdvance'])]:
        raw=(root/rel).read_bytes();hashes[rel]=hashlib.sha256(raw).hexdigest()
        text=raw.decode('utf-8-sig')
        if 'screen_cmd' in rel:
            globals_text=text[text.index('Global Dim gScreenGlyph.i'):text.index('; Measure every printable glyph')]
        for name in names:
            found=re.findall(r'(?ms)^Procedure\.\w+ '+name+r'\(.*?^EndProcedure\s*$',text)
            assert len(found)==1,name
            bodies.append(found[0])
    s=globals_text+'''
Global testSlot.i=0,testGeneration.i=1,testPixels.i=16,testUnits.i=2048
Global testMetric.i=1024,testMetricFail.i,testGlyphBad.i,testPairMode.i,testPairCalls.i
Global testChecks.i,testFailure.i
Procedure.i AnvilTrueTypeSlotSelected()
 ProcedureReturn testSlot
EndProcedure
Procedure.i AnvilTrueTypeSlotGeneration(slot.i)
 ProcedureReturn testGeneration
EndProcedure
Procedure.i AnvilTrueTypePixelHeight()
 ProcedureReturn testPixels
EndProcedure
Procedure.i AnvilTrueTypeUnitsPerEm()
 ProcedureReturn testUnits
EndProcedure
Procedure.i AnvilTrueTypeGlyphForCodepoint(cp.i)
 If testGlyphBad : ProcedureReturn 999 : EndIf
 ProcedureReturn cp
EndProcedure
Procedure.i AnvilTrueTypeGlyphCount()
 ProcedureReturn 128
EndProcedure
Procedure.i AnvilTrueTypeHorizontalMetric(glyph.i,advance.i,lsb.i)
 If testMetricFail : ProcedureReturn 0 : EndIf
 PokeI(advance,testMetric) : PokeI(lsb,0)
 ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypePairPosition(left.i,right.i,values.i)
 testPairCalls=testPairCalls+1
 If testPairMode=1 : ProcedureReturn 0 : EndIf
 If testPairMode=2 : ProcedureReturn 1 : EndIf
 If testPairMode=3 : PokeI(values+16,2147483648) : ProcedureReturn 1 : EndIf
 If testPairMode=4 : PokeI(values+16,-2048) : ProcedureReturn 1 : EndIf
 If testPairMode=5 : PokeI(values+16,16384) : ProcedureReturn 1 : EndIf
 PokeI(values+16,-128) : PokeI(values+48,64)
 ProcedureReturn 1
EndProcedure
Procedure Check(actual.i,expected.i)
 testChecks=testChecks+1
 If actual<>expected And testFailure=0 : testFailure=testChecks : EndIf
EndProcedure
'''+ '\n'.join(bodies)+ '\nProcedure.i Main(services.i)\n'
    steps=[
        'Check(ScreenFontMetricCacheBuild(),1)',
        'Check(gScreenGlyphAdvance[32],524288)',
        'Check(gScreenGlyphAdvance[126],524288)',
        'Check(ScreenProportionalAdvance(65,86),491520)',
        'Check(testPairCalls,1)',
        'Check(ScreenProportionalAdvance(65,86),491520)',
        'Check(testPairCalls,1)',
        'Check(gScreenPairErrors,0)',
        'testPairMode=1',
        'Check(ScreenProportionalAdvance(66,86),524288)',
        'Check(gScreenPairErrors,1)',
        'testPairMode=2',
        'Check(ScreenProportionalAdvance(67,86),524288)',
        'Check(gScreenPairErrors,1)',
        'testPairMode=3',
        'Check(ScreenProportionalAdvance(68,86),524288)',
        'Check(gScreenPairErrors,2)',
        'testPairMode=4',
        'Check(ScreenProportionalAdvance(69,86),524288)',
        'Check(gScreenPairErrors,3)',
        'testPairMode=5',
        'Check(ScreenProportionalAdvance(70,86),524288)',
        'Check(gScreenPairErrors,4)',
        'Check(ScreenProportionalAdvance(0,86),524288)',
        'Check(ScreenProportionalAdvance(65,31),0)',
        'testGeneration=2 : testMetric=512 : testPairMode=2',
        'Check(ScreenProportionalAdvance(65,86),262144)',
        'Check(gScreenMetricGeneration,2)',
        'testPixels=32',
        'Check(ScreenProportionalAdvance(65,86),524288)',
        'Check(gScreenMetricPixels,32)',
        'testSlot=1',
        'Check(ScreenProportionalAdvance(65,86),524288)',
        'Check(gScreenMetricSlot,1)',
        'testSlot=-1',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'Check(gScreenMetricSlot,-1)',
        'Check(ScreenProportionalAdvance(65,86),0)',
        'testSlot=0 : testPixels=513',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'Check(gScreenMetricSlot,-1)',
        'testPixels=16 : testUnits=65536',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'testUnits=2048 : testMetricFail=1',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'testMetricFail=0 : testGlyphBad=1',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'testGlyphBad=0 : testMetric=0',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'testMetric=16384',
        'Check(ScreenFontMetricCacheBuild(),0)',
        'testMetric=1024',
        'Check(ScreenFontMetricCacheBuild(),1)',
        'Check(ScreenProportionalAdvance(65,86),524288)',
    ]
    s+='\n'.join(' '+line for line in steps)
    layout=state_proof_layout('pi4')
    s+=f'\n PokeI(${layout["report"]:X},$434D4554) : PokeI(${layout["report"]+8:X},testChecks) : PokeI(${layout["report"]+16:X},testFailure)\n ProcedureReturn testFailure\nEndProcedure\n'
    d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    (d/'proof.pbi').write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t','pi4','--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    output=q.stdout+q.stderr;(d/'compile.txt').write_text(output,encoding='utf8');print(output[-1800:]);assert q.returncode==0
    payload=(d/'proof.img.pmf').read_bytes()
    (d/'identity.json').write_text(json.dumps(dict(target='pi4',checks=sum(line.startswith('Check(') for line in steps),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes=hashes,checked_ranges=check_linked_layout(layout,output),executed=False,scope='Exact console consumers and metric arithmetic; controlled font-provider double'),indent=2),encoding='utf8')

if __name__=='__main__':main()
