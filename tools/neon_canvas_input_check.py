"""Check the complete canvas-input report against the named case inventory."""
from pathlib import Path
import json,struct,argparse
PLAN=json.loads(Path(__file__).with_name('neon_canvas_input_cases.json').read_text(encoding='utf8'))
def check(report,picture=None):
    assert len(report)==8192
    count,failure=struct.unpack_from('<2q',report,16)
    if failure:
        assert 1<=failure<=count<=len(PLAN['cases'])
        row=PLAN['cases'][failure-1]
        actual,wanted=struct.unpack_from('<2q',report,128+16*(failure-1))
        raise AssertionError((failure,row['label'],actual,wanted))
    assert count==len(PLAN['cases'])
    expected=bytearray(8192);struct.pack_into('<4q',expected,0,0x4e434931,1,count,0)
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',expected,128+16*i,row['expected'],row['expected'])
    assert report==expected,'report bytes differ'
    return dict(checks=count,scope='Controlled native records executed on target CPU; no physical input claim')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes()),indent=2))
if __name__=='__main__':main()
