"""Build a returning physical CPU proof of fragment register metadata limits."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Tests/Vulkan/vulkan_ir_v3d42_gate.pi4';original=(root/name).read_bytes()
 source=original.decode('utf8').split('Procedure.i Main()',1)[0]+r'''
Procedure.i Main(services.i)
  Protected m.AvkIrModule,t.AvkIrV3d42Target,r.AvkIrV3d42Result
  Protected trial.i,n.i,i.i,rc.i,b.i,expected.i,failed.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$46524731)
  For trial=0 To 4
    Select trial
      Case 0 : n=6
      Case 1 : n=7
      Case 2 : n=8
      Case 3 : n=15
      Case 4 : n=16
    EndSelect
    lgPass(@m,#ANVIL_IR_STAGE_FRAGMENT)
    m\nodeCount=n+3 : lgBlocks[0]\nodeCount=n+3
    For i=1 To n
      lgNode(i,30+i,#ANVIL_IR_SPV_FADD,#ANVIL_IR_OP_FADD,3,2)
      lgNodes[i]\operand0=29+i : lgNodes[i]\operand1=30
    Next
    lgNode(n+1,0,62,#ANVIL_IR_OP_STORE,0,2)
    lgNodes[n+1]\operand0=11 : lgNodes[n+1]\operand1=30+n
    lgNode(n+2,0,253,#ANVIL_IR_OP_RETURN,0,0)
    lgTarget(@t,0,#ANVIL_IR_V3D42_ROLE_FRAGMENT,10,4,11,4)
    lgFillTarget(@t) : r\registerCount=999
    rc=AnvilVkIrV3d42Lower(@m,@t,@r)
    expected=0 : If trial=4 : expected=#ANVIL_IR_V3D42_ERR_RANGE : EndIf
    b=$E1C00040+trial*64
    PokeI(b,n) : PokeI(b+8,rc) : PokeI(b+16,expected)
    PokeI(b+24,r\registerCount) : PokeI(b+32,r\codeBytes)
    PokeI(b+40,lgTargetUntouched(@t))
    PokeI(b+48,AnvilVkIrV3d42SourceId()) : PokeI(b+56,AnvilVkIrV3d42Stage())
    If rc<>expected : failed=failed+1 : EndIf
    If trial<4
      If r\registerCount<>4+n*4 Or r\codeBytes<=0 : failed=failed+1 : EndIf
    Else
      If r\registerCount<>0 Or lgMetadataEmpty(@r)=0 Or lgTargetUntouched(@t)=0 : failed=failed+1 : EndIf
    EndIf
  Next
  PokeI($E1C00008,5) : PokeI($E1C00010,failed)
  ProcedureReturn failed
EndProcedure
'''
 inputs={name:hashlib.sha256(original).hexdigest()};pending=[(source,None)]
 while pending:
  text,owner=pending.pop(0)
  for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',text):
   p=root/spelling
   if not p.is_file() and owner:p=(root/owner).parent/spelling
   p=p.resolve();assert p.is_relative_to(root);n=p.relative_to(root).as_posix()
   if n in inputs:continue
   blob=p.read_bytes();inputs[n]=hashlib.sha256(blob).hexdigest();pending.append((blob.decode('utf8'),n))
 (out/'proof.pi4').write_text(source,encoding='utf8',newline='\n');compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(out/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1200:]);assert q.returncode==0
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap');ranges['report']=['0xe1c00000','0xe1c03fff']
 assert inputs=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in inputs}
 blob=(out/'proof.img.pmf').read_bytes()
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
