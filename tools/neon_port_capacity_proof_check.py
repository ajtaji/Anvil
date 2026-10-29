"""Check all report bytes against native capacity and callback contracts."""
import argparse,struct
from pathlib import Path
def expected(before=False):
 b=bytearray(4096);struct.pack_into('<2q',b,0,0x4E504343,19)
 denied=(-21307,0,0,0,0,0,0,0x55AA);entered=(77,1,0,0,0,0,0,0x55AA)
 rows=[entered,denied,entered,entered,(0,1,2,1,4,4,1,0x55AA),(0,0,0,0,0,0,0,0x55AA),(-21306,0,0,0,0,0,0,0x55AA),(-21306,0,0,0,0,0,0,0x55AA),denied,entered,entered,denied,entered,denied,(0,0,0,0,0,0,0,0x55AA),entered,(0,1,4098,1,28,8,2049,0x55AA),(0,1,2051,1,24,16,0,0x55AA),(0,1,4098,1,24,16,2049,0x55AA)]
 if before:
  for i in [0,2,3,9,10,12,15,16,17,18]:rows[i]=denied
 for i,row in enumerate(rows):struct.pack_into('<8q',b,256+i*64,*row)
 return bytes(b)
def check(raw,before=False):
 assert raw==expected(before),'Capacity/callback report differs from the complete 4096-byte oracle'
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--before',action='store_true');ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 if a.self_test:
  for before in [False,True]:
   raw=expected(before);check(raw,before)
   for i in range(512):
    mutated=bytearray(raw);mutated[i*8]^=1
    try:check(mutated,before)
    except AssertionError:pass
    else:raise AssertionError('Corruption accepted')
  print('PASS 1024 corrupted report words rejected')
 if a.report:check(a.report.read_bytes(),a.before);print('PASS 19 capacity/callback cases; 4096 exact report bytes; controlled backend')
if __name__=='__main__':main()
