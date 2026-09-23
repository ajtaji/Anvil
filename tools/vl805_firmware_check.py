"""Cold firmware notification ordering; emitted routines, mocked mailbox wire."""
import argparse,hashlib,os,pathlib,re,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as b
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
def proc(text,name):
    return re.search(r'(?ms)^Procedure(?:\.i)? '+name+r'\([^\n]*\).*?^EndProcedure',text).group()
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    compiler=pathlib.Path(a.compiler);digest=hashlib.sha256(compiler.read_bytes()).hexdigest()
    pc=(b.ROOT/'RaspberryPi4/Lib/pcie.pi4').read_text()
    mb=(b.ROOT/'RaspberryPi4/Lib/mailbox.pi4').read_text()
    body=proc(mb,'MailboxNotifyVl805Reset')+'\n'+proc(pc,'PcieColdFirmwareReady')
    enum=proc(pc,'PcieEnumerate')
    assert enum.index('If PcieColdFirmwareReady() = 0')>enum.index('Configuration writes are not ownership proof')
    assert enum.index('If PcieColdFirmwareReady() = 0')<enum.index('pcie_enumerated = 1')
    model='''
#PCIE_ERR_VL805_FIRMWARE=-15
Global pcie_adopted.i
Global pcie_err.i
Global pcie_vl805Ready.i
Global mode.i
Global calls.i
Global ticks.i
Global hazard.i
Procedure.i MailboxBegin(tag.i,req.i,resp.i)
 If tag<>$30058 Or req<>4 Or resp<>4 : hazard=hazard+1 : EndIf
 If ticks<>0 : hazard=hazard+1 : EndIf
 calls=calls+1
 If mode=2 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure MailboxSetWord(slot.i,value.i)
 If slot<>0 Or value<>$100000 : hazard=hazard+1 : EndIf
EndProcedure
Procedure.i MailboxSend()
 If mode=3 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i pcie_TickHz()
 If mode=4 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1000000
EndProcedure
Procedure.i pcie_Ticks()
 ticks=ticks+100
 ProcedureReturn ticks
EndProcedure
'''
    entry='''
Procedure Main()
 Define i.i
 For i=0 To 5
  mode=i : calls=0 : ticks=0 : hazard=0 : pcie_err=0 : pcie_adopted=0 : pcie_vl805Ready=0
  If mode=1 : pcie_adopted=1 : EndIf
  Define ready.i
  ready=PcieColdFirmwareReady()
  If mode=5 And ready<>0 : ready=PcieColdFirmwareReady() : EndIf
  PokeI($6000000+i*40,ready)
  PokeI($6000008+i*40,calls)
  PokeI($6000010+i*40,pcie_err)
  PokeI($6000018+i*40,hazard)
  PokeI($6000020+i*40,ticks)
 Next
EndProcedure
'''
    interpreter=b.load_interpreter(b.INTERP)
    with tempfile.TemporaryDirectory(prefix='vl805-firmware-') as tmp:
      for mutation in ('none','missing','wrong_order'):
        candidate=body
        if mutation=='missing':candidate=candidate.replace('If MailboxNotifyVl805Reset() = 0','If 0 = 1')
        if mutation=='wrong_order':candidate=candidate.replace('  If MailboxNotifyVl805Reset() = 0','  started = pcie_Ticks()\n  If MailboxNotifyVl805Reset() = 0')
        source=pathlib.Path(tmp)/(mutation+'.pi4');image=source.with_suffix('.img');source.write_text(model+candidate+entry)
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=b.ROOT,env=dict(os.environ,PMF_ROOT=str(b.ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest()
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/vl805_firmware_check.py',compiler=str(compiler))
        cpu=interpreter.A64();cpu.memory.update({b.LOAD+i:v for i,v in enumerate(image.read_bytes())});cpu.pc=b.LOAD;cpu.sp=b.STACK;cpu.x[30]=b.RETURN_PC
        for steps in range(500000):
            if cpu.pc==b.RETURN_PC:break
            cpu.step()
        else:raise AssertionError('Gate exceeded bound.')
        result=[[b.u64(cpu,0x6000000+j*40+i*8) for i in range(5)] for j in range(6)]
        expected=[[1,1,0,0,300],[1,1,0,0,300],[0,1,2**64-15,0,0],[0,1,2**64-15,0,0],[0,0,2**64-15,0,0],[1,1,0,0,300]]
        if mutation=='none':assert result==expected,result
        else:assert result!=expected,'Mutation escaped: '+mutation
        print('PASS:',mutation,'emitted notification ordering / cold+adopt / once-per-boot / mailbox failure / clock refusal')
if __name__=='__main__':main()
