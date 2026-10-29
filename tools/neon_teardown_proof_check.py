#!/usr/bin/env python3
"""Strict full-report oracle for controlled Neon Vulkan teardown observations.

Checker self-tests use synthetic data; they do not execute the production
procedures or prove GPU/device recovery. Expected rows are an explicit contract.
"""
from pathlib import Path
import argparse,json,struct

def expected_rows():
 # rc, Chrome device/command/pending/ready/hooks, binder configured,
 # idle waits, WSI rollback calls, any release, present/draw clears,
 # mapped pointer, unmaps, console device/pool/frame/ready/unsafe/banner release.
 return [
 [-21202, 201, 102, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [-21202, 201, 102, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [2, 201, 102, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [-4, 201, 102, 1, 0, 1, 1, 2, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 3, 1, 1, 1, 1, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 201, 202, 203, 1, 0, 0],
 [16, 201, 102, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 0, 2, 1, 1, 1, 1, 0, 0, 201, 202, 203, 1, 0, 0],
 [16, 201, 102, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [16, 201, 102, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 201, 102, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 1, 0],
 [0, 201, 102, 1, 0, 1, 1, 2, 0, 0, 0, 0, 0, 0, 201, 202, 203, 1, 1, 0],
 [1, 0, 0, 0, 0, 0, 1, 2, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1],
 [-20004, 201, 102, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 2, 2, 1, 1, 1, 0, 0, 201, 202, 203, 1, 0, 0],
 [2, 201, 102, 0, 0, 1, 1, 1, 0, 0, 0, 0, 301, 0, 201, 202, 203, 1, 0, 0],
 [0, 0, 0, 0, 0, 0, 1, 2, 1, 1, 1, 1, 0, 1, 201, 202, 203, 1, 0, 0],
 ]

def expected_report(chip=2711):
 rows=expected_rows();records=[(100*(i+1)+j,v) for i,row in enumerate(rows) for j,v in enumerate(row)]
 assert len(records)==360 and all(len(row)==20 for row in rows)
 raw=struct.pack('<8q',0x41434450,0,chip,360,0,2,0,0x50444341)
 raw+=b''.join(struct.pack('<2q',*record) for record in records)
 return raw+bytes(8192-len(raw))

def verify(raw,chip=2711):
 wanted=expected_report(chip)
 if raw!=wanted:
  offsets=[i for i,(a,b) in enumerate(zip(raw,wanted)) if a!=b]
  raise AssertionError('Teardown report differs: length='+str(len(raw))+' first offsets='+str(offsets[:8]))
 return dict(observations=360,cases=18,controlled_providers=True,gpu_execution=False)

def self_test(chip=2711):
 raw=expected_report(chip);verify(raw,chip);offsets=list(range(0,64+360*16,8))+[64+360*16,8191]
 for off in offsets:
  bad=bytearray(raw);bad[off]^=1
  try:verify(bytes(bad),chip)
  except AssertionError:continue
  raise AssertionError('Accepted corrupt observation')
 for bad in [raw[:-1],raw+b'\0']:
  try:verify(bad,chip)
  except AssertionError:continue
  raise AssertionError('Accepted wrong length')
 return dict(checker_corruptions_rejected=len(offsets)+2,synthetic_checker_test_only=True)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--chip',type=int,default=2711);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 if not a.report and not a.self_test:ap.error('Provide a captured --report or --self-test.')
 result={}
 if a.report:result.update(verify(a.report.read_bytes(),a.chip))
 if a.self_test:result.update(self_test(a.chip))
 print(json.dumps(result))
if __name__=='__main__':main()
