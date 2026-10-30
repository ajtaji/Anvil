"""Host transport recovery boundaries; controlled sockets, no hardware emulation."""
import json
import board_run as br

class Console:
    def __init__(self,answer=None,error=None,prompt=True):
        self.addr=('192.168.1.114',5555);self.answer=answer;self.error=error
        self.prompt=prompt;self.transcript=[];self.accepted_datagrams=[b'checked']
        self.closed=False;self.calls=[]
    def command(self,line,seconds):
        self.calls.append(line)
        if self.error:raise self.error
        return self.answer
    def at_prompt(self,timeout):
        self.prompt_timeout=timeout
        return self.prompt
    def close(self):self.closed=True

def main():
    checks=0;real=br.NetConsole
    timeout=lambda:br.CommandTimeout('last run',10,0,0,False)
    try:
        c=Console(answer='LASTRUN checked')
        out,text,detail=br.read_only_command_with_recovery(c,'last run',10)
        assert out is c and text=='LASTRUN checked' and detail is None and not c.closed;checks+=1
        for preserve in [False,True]:
            old=Console(error=timeout());fresh=Console(answer='LASTRUN checked');created=[]
            def make(ip,port):created.append((ip,port));return fresh
            br.NetConsole=make
            out,text,detail=br.read_only_command_with_recovery(old,'last run',10,preserve_console=preserve)
            assert text=='LASTRUN checked' and detail['command']=='last run' and detail['first_received_datagrams']==0
            assert created==[old.addr] and old.calls==fresh.calls==['last run']
            assert fresh.prompt_timeout==60.0
            assert out is (old if preserve else fresh)
            assert (old.closed,fresh.closed)==((False,True) if preserve else (True,False));checks+=1
        for fresh in [Console(prompt=False),Console(error=timeout())]:
            old=Console(error=timeout());br.NetConsole=lambda ip,port:fresh
            try:br.read_only_command_with_recovery(old,'last run',10)
            except br.StreamError:pass
            else:raise AssertionError('accepted incomplete recovery')
            assert fresh.closed and old.calls==['last run'] and len(fresh.calls)<=1;checks+=1
        for line in ['net recv 1000000','deadman 15','deadman off','boot mem 1000000 shot','save 1:/X 1000000 10','reset']:
            c=Console(answer='unexpected')
            try:br.read_only_command_with_recovery(c,line,10)
            except ValueError:pass
            else:raise AssertionError(('accepted mutation',line))
            assert c.calls==[];checks+=1
    finally:br.NetConsole=real
    print(json.dumps(dict(passed=True,checks=checks,scope='One fresh read-only retry; no upload/deadman/boot/save/reset replay'),indent=2))
if __name__=='__main__':main()
