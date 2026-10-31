"""Physical reassembly-to-TLS integration with the full shared TLS crypto fixture."""
from pathlib import Path
import argparse
from build_tls_quic_crypto_cpu import build

def transform(s,rows,names):
 names=names+['Anvil/Network/quic_tls_receive.pbi']
 sh=bytes.fromhex(rows[0]['input']);end=4+int.from_bytes(sh[1:4],'big');sh=sh[:end]
 rows+= [dict(name='initial-gap-does-not-feed-tls',mode=15,input=sh.hex(),error=0,state=2,consumed=0,phases=[1,1,1]),
          dict(name='gapped-old-level-cannot-be-abandoned',mode=16,input=sh.hex(),error=0,state=3,consumed=4,step_error=-3427,phases=[3,1,1]),
          dict(name='finished-cannot-abandon-handshake-tail',mode=17,input=rows[7]['input']+'00',error=0,state=7,consumed=4,step_error=-3427,phases=[1,3,1])]
 s=s.replace('mode=9 Or mode=10\n','mode=9 Or mode=10 Or mode=17\n')
 s=s.replace('Global Dim config.a[48]',r'''XIncludeFile "Anvil/Network/quic_tls_receive.pbi"
Global rx0.QuicCryptoRx,rx2.QuicCryptoRx,rx3.QuicCryptoRx
Global Dim rxData.a[12288]
Global Dim rxBits.a[1536]
Procedure Queue(stream.i,level.i,p.i,bytes.i)
 Define rc.i,half.i
 half=bytes/2
 rc=QuicCryptoRxPut(stream,level,half,p+half,bytes-half)
 rc=QuicCryptoRxPut(stream,level,0,p,half)
 rc=QuicCryptoRxPut(stream,level,0,p,bytes)
EndProcedure
Global Dim config.a[48]''')
 s=s.replace('maxTaken.i,rc.i','maxTaken.i,rc.i,first.i,stream.i,offset.i,again.i')
 marker=' If mode<8 Or mode=13\n'
 assert s.count(marker)==1
 s=s.replace(marker,r'''
 rc=QuicCryptoRxInit(@rx0,0,@rxData[0],4096,@rxBits[0],512)
 rc=QuicCryptoRxInit(@rx2,2,@rxData[4096],4096,@rxBits[512],512)
 rc=QuicCryptoRxInit(@rx3,3,@rxData[8192],4096,@rxBits[1024],512)
 first=bytes
 If mode=0 Or mode=1 Or mode=2
  first=4+(PeekA(@incoming[0]+1)<<16)+(PeekA(@incoming[0]+2)<<8)+PeekA(@incoming[0]+3)
 EndIf
 If mode=15
  rc=QuicCryptoRxPut(@rx0,0,1,@incoming[0]+1,bytes-1)
 ElseIf mode=16
  Queue(@rx0,0,@incoming[0],bytes)
  rc=QuicCryptoRxPut(@rx0,0,bytes+5,@incoming[0],1)
 ElseIf mode=17
  Queue(@rx2,2,@incoming[0],bytes)
 ElseIf mode=0
  Queue(@rx2,2,@incoming[0]+first,bytes-first)
  Queue(@rx0,0,@incoming[0],first)
 ElseIf mode=2
  Queue(@rx0,0,@incoming[0],bytes)
 ElseIf mode=3
  Queue(@rx2,2,@incoming[0],bytes)
 ElseIf mode=4
  Queue(@rx0,0,@incoming[0],2)
  Queue(@rx2,2,@incoming[0]+2,bytes-2)
 ElseIf mode=5 Or mode=6
  Queue(@rx3,3,@incoming[0],bytes)
 ElseIf mode=7
  Queue(@rx2,2,@incoming[0],bytes)
 ElseIf mode=13
  Queue(@rx0,0,@incoming[0],bytes)
 EndIf
 If mode<8 Or mode=13 Or mode>=15
''')
 old='   n=Tls13FeedQuic(level,@incoming[pos],offered)'
 assert s.count(old)==1
 s=s.replace(old,r'''
   stream=@rx2 : If level=0 : stream=@rx0 : EndIf
   If level=3 : stream=@rx3 : EndIf
   If mode=1
    offset=pos : If level=2 : offset=pos-first : EndIf
    rc=QuicCryptoRxPut(stream,level,offset,@incoming[pos],1)
   EndIf
   n=QuicCryptoTlsStep(stream)
   If n<0
    again=QuicCryptoTlsStep(stream)
    PokeI(p+56,again)
    again=QuicCryptoRxPut(stream,level,0,@incoming[0],1)
    PokeI(p+112,again)
   EndIf
''')
 s=s.replace(' PokeI(p,Tls13Err)',r'''
 PokeI(p+64,rx0\phase) : PokeI(p+72,rx2\phase) : PokeI(p+80,rx3\phase)
 PokeI(p+88,rx0\base) : PokeI(p+96,rx2\base) : PokeI(p+104,rx3\base)
 If mode=0 Or mode=1 : PokeI(p+120,QuicCryptoTlsStep(@rx0)) : EndIf
 PokeI(p,Tls13Err)''')
 # A transition can consume the final ServerHello fragment before discovering
 # forbidden trailing Initial bytes. Do not pretend the TLS state rolled back.
 rows[2].update(error=0,state=3,consumed=4,step_error=-3427)
 for i in [3,4,6,8,14]:rows[i]['step_error']=-3431
 rows[0]['phases']=[2,1,1];rows[1]['phases']=[2,1,1]
 rows[7]['phases']=[1,2,1]
 rows[2]['phases']=[3,1,1]
 rows[0]['bases']=[len(sh),len(bytes.fromhex(rows[0]['input']))-len(sh),0]
 rows[1]['bases']=rows[0]['bases']
 rows[2]['bases']=[len(sh),0,0]
 rows[3]['bases']=[0,0,0];rows[4]['bases']=[2,0,0]
 rows[7]['bases']=[0,36,0];rows[8]['bases']=[0,4,0]
 return s,rows,names

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--compiler',required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();build(a.compiler,a.out.resolve(),transform)
