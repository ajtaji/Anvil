#!/usr/bin/env python3
"""Desk gate for Pi 3 SMSC9514 register, MAC and PHY transport."""
from __future__ import annotations
import argparse, hashlib, os, pathlib, re, subprocess, tempfile
from pi3_usb_enumeration_check import execute, load_interpreter, require
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT=pathlib.Path(__file__).resolve().parents[1]
HOST=ROOT/"RaspberryPi3"/"Tests"/"lan9514_transport_host.pb"
EMITTED=ROOT/"RaspberryPi3"/"Tests"/"lan9514_transport_emitted.pi3"
SOURCE=ROOT/"RaspberryPi3"/"Lib"/"lan9514_transport.pbi"
LOAD=0x02000000
STACK=0x03000000

def checked(command, env=None):
    result=subprocess.run(command,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if result.returncode: raise SystemExit("Pi3 LAN9514 transport gate failed:\n"+result.stdout)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler",default=os.environ.get("PMF_COMPILER") or r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
    parser.add_argument("--purebasic",default=os.environ.get("PB_COMPILER") or str(pathlib.Path.home()/"AppData/Local/Programs/PureBasic/Compilers/pbcompiler.exe"))
    args=parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler; compiler=require(pathlib.Path(args.compiler),"unified IDE compiler"); pb=require(pathlib.Path(args.purebasic),"host PureBasic compiler")
    text=SOURCE.read_text(encoding="utf-8")
    for name in ("Pi3LanRegisterStep","Pi3LanMacStep","Pi3LanPhyStep"):
        match=re.search(rf"Procedure(?:\.i)?\s+{name}\([^\n]*\)(.*?)EndProcedure",text,re.I|re.S)
        if not match: raise SystemExit("missing "+name)
        body="\n".join(line.split(";",1)[0] for line in match.group(1).splitlines())
        if re.search(r"\b(while|wend|repeat|until)\b",body,re.I): raise SystemExit(name+" hides a wait loop")
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-lan-") as td:
        temp=pathlib.Path(td); exe=temp/"host.exe"; image=temp/"emitted.img"
        checked([str(pb),"/CONSOLE","/QUIET","/EXE",str(exe),str(HOST)]); checked([str(exe)])
        env=os.environ.copy();env["PMF_ROOT"]=str(ROOT)
        checked([str(compiler),"--compile",str(EMITTED.relative_to(ROOT)).replace("\\","/"),"-t","pi3","--entry-returns","--load-addr",hex(LOAD),"--stack-addr",hex(STACK),"-o",str(image),"-s"],env)
        a64=load_interpreter(); expected=(None,((1<<11)|(3<<6)|1),1,0xEC001234); steps=0
        for op in range(1,4):
            actual,count=execute(a64,image,op);steps+=count
            if actual!=expected[op]: raise SystemExit(f"emitted op {op}: {actual:#x} != {expected[op]:#x}")
        print("PASS: host register/MAC/PHY hostile and ownership cases")
        print(f"PASS: 3 emitted A64 cases, {steps} interpreted instructions")
        print(f"Emitted SHA256: {hashlib.sha256(image.read_bytes()).hexdigest().upper()}")
        print(f"Compiler SHA256: {hashlib.sha256(compiler.read_bytes()).hexdigest().upper()}")
    return 0
if __name__=="__main__": raise SystemExit(main())
