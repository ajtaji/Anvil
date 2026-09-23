#!/usr/bin/env python3
"""Host execution of real HTTP monitor commands with explicitly fake providers.

No socket, board, target instruction or full prompt-loop proof.
"""
import pathlib
import re
import subprocess
import tempfile
import argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--purebasic', required=True, help='Path to the host PureBasic compiler.')
PB = pathlib.Path(parser.parse_args().purebasic).resolve()
monitor = (ROOT/'Anvil/Services/Http/monitor.pbi').read_text()
source = (ROOT/'Anvil/Core/tcp_cmd.pbi').read_text()
command = re.search(r'(?ms)^Procedure CmdHttp\(\).*?^EndProcedure',source).group()
prefix = r'''
OpenConsole()
#CAP_NET=1
Global ht_owned.i,ht_port.i,gWordAt.i,gPos.i,gWordLen.i
Global output.s,verb.s
Global nextArg.i,argCount.i,opened.i,started.i,polled.i,enginePolled.i,stopped.i
Global openResult.i=1,startResult.i=1,serviceResult.i=1,capResult.i=1
Global checks.i,failures.i
Global Dim args.i(4)
Procedure Capture(value.s)
  output+value
EndProcedure
Macro PrintN(value)
  Capture(value)
EndMacro
Macro Print(value)
  Capture(value)
EndMacro
Procedure PrintDec(value.i)
  output+Str(value)
EndProcedure
Procedure.i millis()
  ProcedureReturn 123
EndProcedure
Procedure.i ArgWord()
  Protected value.i
  If nextArg>=argCount : ProcedureReturn 0 : EndIf
  value=args(nextArg) : nextArg+1
  ProcedureReturn value
EndProcedure
Procedure.i HwLinkOpen(value.i)
  opened+1
  ProcedureReturn openResult
EndProcedure
Procedure.i HtStart(port.i)
  started+1
  If startResult : ht_owned=1 : ht_port=port : EndIf
  ProcedureReturn startResult
EndProcedure
Procedure.i HtService(now.i)
  polled+1
  ProcedureReturn serviceResult
EndProcedure
Procedure HsPoll(now.i)
  enginePolled+1
EndProcedure
Procedure HsStop()
  stopped+1
EndProcedure
Procedure HtStop()
  stopped+1 : ht_owned=0
EndProcedure
Procedure.i RequireCap(cap.i,name.s,reason.s)
  ProcedureReturn capResult
EndProcedure
Procedure SkipSpace()
EndProcedure
Procedure SkipWord()
EndProcedure
Procedure.i WordIs(word.s)
  ProcedureReturn Bool(verb=word)
EndProcedure
Procedure http_Get()
  output+"GET"
EndProcedure
'''
suffix = r'''
Procedure Check(actual.i,expected.i)
  checks+1
  If actual<>expected
    failures+1
    Capture("FAILED "+Str(checks))
  EndIf
EndProcedure
Procedure ResetCase(first.s,second.s="")
  Protected n.i
  For n=0 To 3
    If args(n) : FreeMemory(args(n)) : args(n)=0 : EndIf
  Next
  argCount=0 : nextArg=0
  If first<>"<absent>"
    args(0)=AllocateMemory(StringByteLength(first,#PB_Ascii)+1)
    PokeS(args(0),first,-1,#PB_Ascii) : argCount=1
  EndIf
  If second<>""
    args(1)=AllocateMemory(StringByteLength(second,#PB_Ascii)+1)
    PokeS(args(1),second,-1,#PB_Ascii) : argCount=2
  EndIf
  output="" : verb="serve" : opened=0 : started=0 : polled=0
  enginePolled=0 : stopped=0 : ht_owned=0 : ht_port=0
  openResult=1 : startResult=1 : serviceResult=1 : capResult=1
EndProcedure
ResetCase("<absent>") : CmdHttp()
Check(ht_port,8080) : Check(started,1) : Check(opened,1)
Check(polled,1) : Check(enginePolled,1)
ResetCase("1") : CmdHttp() : Check(ht_port,1)
ResetCase("65535") : CmdHttp() : Check(ht_port,65535)
Define n.i
Define Dim invalid.s(6)
invalid(0)="0" : invalid(1)="65536" : invalid(2)="123456"
invalid(3)="-1" : invalid(4)="12x" : invalid(5)="" : invalid(6)="+80"
For n=0 To 6
  ResetCase(invalid(n)) : CmdHttp()
  Check(started,0) : Check(opened,0) : Check(Bool(FindString(output,"HTTP error 1:")),1)
Next
ResetCase("80","extra") : CmdHttp()
Check(started,0) : Check(opened,0)
ResetCase("80") : ht_owned=1 : CmdHttp()
Check(started,0) : Check(opened,0) : Check(Bool(FindString(output,"already running")),1)
ResetCase("80") : openResult=0 : CmdHttp()
Check(opened,1) : Check(started,0)
ResetCase("80") : startResult=0 : CmdHttp()
Check(started,1) : Check(polled,0) : Check(Bool(FindString(output,"HTTP error 3:")),1)
ResetCase("80") : capResult=0 : CmdHttp() : Check(opened,0)
ResetCase("<absent>") : verb="status" : CmdHttp()
Check(Bool(FindString(output,"stopped")),1) : Check(started,0)
ResetCase("<absent>") : verb="stop" : ht_owned=1 : CmdHttp()
Check(stopped,2) : Check(ht_owned,0)
ResetCase("extra") : verb="stop" : ht_owned=1 : CmdHttp()
Check(stopped,0) : Check(ht_owned,1)
ResetCase("extra") : verb="status" : CmdHttp()
Check(Bool(FindString(output,"Extra arguments")),1)
ResetCase("<absent>") : verb="get" : CmdHttp()
Check(Bool(output="GET"),1) : Check(started,0)
ResetCase("<absent>") : serviceResult=0 : HttpServerPoll()
Check(polled,1) : Check(enginePolled,0)
ResetCase("<absent>") : verb="unknown" : CmdHttp()
Check(started,0) : Check(stopped,0)
UndefineMacro PrintN
PrintN(Str(checks)+" command checks; failures="+Str(failures))
End failures
'''
with tempfile.TemporaryDirectory(prefix='anvil-http-command-') as folder:
    folder=pathlib.Path(folder)
    probe=folder/'probe.pb'; exe=folder/'probe.exe'
    probe.write_text(prefix+monitor+command+suffix)
    build=subprocess.run([str(PB),str(probe),'/CONSOLE','/EXE',str(exe)],capture_output=True,text=True)
    assert build.returncode==0,build.stdout+build.stderr
    run=subprocess.run([str(exe)],capture_output=True,text=True)
    print(run.stdout,end='')
    assert run.returncode==0,run.stdout+run.stderr
print('PASS: real command procedures; fake arguments/link/TCP/engine. No hardware proof.')
