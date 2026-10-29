"""Host-only regression for exception reboot timing; no device or emulation."""
import socket
from unittest.mock import patch
import board_run as b

TEXT=(b.FATAL_MARKER+'\n'
      '   EL=0000000000000003 slot=0000000000000004 ESR=0000000096000000\n'
      '   PC=00000000010027A0 FAR=FFFFFFFFFFFFFFB7 SP=0000000004EFFFB0\n')

class Clock:
    now=0.0
    def monotonic(self):return self.now

def timing(late_prompt):
    clock=Clock();c=object.__new__(b.NetConsole);c.transcript=[]
    def receive():
        clock.now+=1
        if late_prompt and clock.now==95:return b'pmf>\n'
        raise socket.timeout()
    c._recv_peer=receive
    with patch.object(b.time,'monotonic',clock.monotonic):
        evidence,boundary=c.collect_exception(TEXT,cap=115,reset_wait=110)
    assert evidence.startswith(TEXT)
    assert clock.now==(97 if late_prompt else 110),(clock.now,boundary)
    assert boundary==('prompt+quiet' if late_prompt else 'deadman-window quiet (reset unobserved)')

def capture(deadman,boundary,reply,ready):
    calls=[]
    class Old:
        addr=('192.0.2.1',5555)
        transcript=[]
        accepted_datagrams=[TEXT.encode()]
        def collect_exception(self,initial,cap,reset_wait):
            calls.append(('collect',cap,reset_wait))
            assert cap==(115 if deadman else 30)
            assert reset_wait==(110 if deadman else 0)
            return initial,boundary
    class Fresh:
        def __init__(self,*args):
            assert calls and calls[0][0]=='collect'
            calls.append(('open',args));self.transcript=[]
        def command(self,line,seconds):
            calls.append(('command',line,seconds))
            if isinstance(reply,Exception):raise reply
            return reply
        def close(self):calls.append(('close',))
    record={};failures=[]
    with patch.object(b,'NetConsole',Fresh):
        b.capture_fatal_exception(Old(),TEXT,0,deadman,record,failures)
    assert len(failures)==1 and 'processor-exception' in failures[0]
    assert record['exception']['complete']
    if ready is None:
        assert 'recovery' not in record['exception'] and len(calls)==1
    else:
        assert record['exception']['recovery']['ready']==ready
        assert [c[1] for c in calls if c[0]=='command']==['version']
        assert calls[-1]==('close',)

if __name__=='__main__':
    timing(False);timing(True)
    capture(0,'complete-record parked quiet','',None)
    capture(15,'prompt+quiet','',None)
    capture(15,'deadman-window quiet (reset unobserved)',
            'version\nbuild 403 date 20261029 time 061053\npmf> ',True)
    capture(15,'timeout','version\npmf> ',False)
    capture(15,'timeout',b.StreamError('no reply'),False)
    print('exception reboot timing: 7 cases PASS; no boot/reset/write retry')
