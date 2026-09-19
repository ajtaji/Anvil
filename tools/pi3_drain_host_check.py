"""Native PB execution of exact drain procedure with a frozen timer.

The full two-million-iteration budget is exercised, not reduced for the test.
Framing/CRC/chunk behavior has a separate actual A64 emitted gate.
"""
import argparse,pathlib,re,subprocess,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--purebasic',default=r'C:\Users\rajta\AppData\Local\Programs\PureBasic\Compilers\pbcompiler.exe');a=p.parse_args()
    text=(ROOT/'RaspberryPi3/Lib/update_transport.pbi').read_text()
    body=re.search(r'(?ms)^Procedure pi3ut_DrainAfterFault\(\).*?^EndProcedure',text).group(0)
    prefix='''Global pi3_ut_rx_quarantine.i
Global reads.i
Procedure.i Pi3Micros() : ProcedureReturn 0 : EndProcedure
Procedure.i Pi3UartRead() : reads + 1 : ProcedureReturn -1 : EndProcedure
Procedure pi3ut_Idle() : EndProcedure
'''
    suffix='''
pi3ut_DrainAfterFault()
If pi3_ut_rx_quarantine <> 1 Or reads <> 2000000 : End 1 : EndIf
End 0
'''
    with tempfile.TemporaryDirectory(prefix='pi3-drain-') as d:
        source=pathlib.Path(d)/'gate.pb';exe=pathlib.Path(d)/'gate.exe';source.write_text(prefix+body+suffix)
        subprocess.run([a.purebasic,'/CONSOLE','/QUIET','/EXE',str(exe),str(source)],check=True,capture_output=True)
        subprocess.run([str(exe)],check=True,timeout=10)
    print('pi3_drain_host_check PASS: actual drain source, frozen timer, 2,000,000 reads, quarantine; native PB host only')
if __name__=='__main__':main()
