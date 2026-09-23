"""Prove the Pi4 compatibility include changes no emitted FAT code."""
import argparse, hashlib, os, pathlib, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
    main='''
Procedure.i Main()
  FatSetRangeReader(0)
  FatSetRangeWriter(0)
  FatMount(1)
  FatOpen("ANVIL.IMG")
  FatRead($500000, 512)
  FatSeek(0)
  FatClose()
  ProcedureReturn FatLastError()
EndProcedure
'''
    with tempfile.TemporaryDirectory(prefix='fat-shared-') as td:
        work=pathlib.Path(td);images=[]
        for mode in ('flat','wrapper'):
            source=work/(mode+'.pi4');image=work/(mode+'.img')
            # The compatibility include must add nothing to the shared sources it
            # names. Until 2026-09-17 'flat' was the pre-extraction fat.pi4 pinned at
            # fa712c2; the FAT32 driver has since gained folders and long names
            # (forum 898), so that pin only proved old code is old.
            body=('XIncludeFile "Anvil/Storage/fat32.pbi"\nXIncludeFile "Anvil/Storage/exfat.pbi"\nXIncludeFile "Anvil/Storage/filesystem.pbi"\n') if mode=='flat' else 'XIncludeFile "RaspberryPi4/Lib/fat.pi4"\n'
            source.write_text(body+main,encoding='utf-8')
            env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
            r=subprocess.run([a.compiler,'--compile',str(source),'-t','pi4','--entry-returns','--load-addr','0x400000','--stack-addr','0x3000000','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
            if r.returncode or not image.exists():raise AssertionError(r.stdout+r.stderr)
            images.append(image.read_bytes())
        assert images[0]==images[1],'compatibility include changed emitted code'
        print('fat_shared_equivalence_check PASS:',len(images[0]),'byte-identical bytes;',hashlib.sha256(images[0]).hexdigest())
if __name__=='__main__':main()
