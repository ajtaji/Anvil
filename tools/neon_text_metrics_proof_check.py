#!/usr/bin/env python3
"""Strict metric-report oracle. Synthetic self-tests do not execute production."""
from pathlib import Path
import argparse,json
from neon_text_metrics_contract import expected_report,cases
def verify(raw,chip=2711,unbounded=False):
 assert raw==expected_report(chip,unbounded),'Metric report differs in header, observation, length or untouched tail.'
 return dict(observations=len(cases()[1]),shared_only=True,gpu_execution=False,expected_unbounded_width=unbounded)
def self_test(chip=2711,unbounded=False):
 raw=expected_report(chip,unbounded);verify(raw,chip,unbounded);n=len(cases()[1]);offsets=list(range(0,64+n*16,8))+[64+n*16,4095]
 for off in offsets:
  bad=bytearray(raw);bad[off]^=1
  try:verify(bytes(bad),chip,unbounded)
  except AssertionError:continue
  raise AssertionError('Corrupted metric observation accepted')
 for bad in [raw[:-1],raw+b'\0',expected_report(chip,not unbounded)]:
  try:verify(bad,chip,unbounded)
  except AssertionError:continue
  raise AssertionError('Wrong length or opposite metric contract accepted')
 return dict(checker_corruptions_rejected=len(offsets)+2,opposite_contract_rejected=True,synthetic_checker_test_only=True)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--chip',type=int,default=2711);ap.add_argument('--self-test',action='store_true');ap.add_argument('--expect-unbounded-width',action='store_true');a=ap.parse_args()
 if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
 result={}
 if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_unbounded_width))
 if a.self_test:result.update(self_test(a.chip,a.expect_unbounded_width))
 print(json.dumps(result))
if __name__=='__main__':main()
