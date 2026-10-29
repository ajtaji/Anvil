#!/usr/bin/env python3
"""Native application idle integration raster and timing qualification."""
from pathlib import Path
import argparse,json,struct
from neon_service_composed_app_check import check as composed_check
def check(report,picture):
    assert len(report)==16384
    magic,caps,generation,events=struct.unpack_from('<4q',report,13120)
    assert magic==0x4e4e4131 and 1<=caps<=7 and 1<=generation<=2147483647
    assert events==0,'This raster baseline qualifies idle native integration; physical interactions need their own acceptance.'
    baseline=bytearray(report);baseline[13120:13152]=b'\0'*32
    result=composed_check(baseline,picture,False,True)
    result.update(native_input=True,capabilities=caps,generation=generation,native_records=events,scope='Actual resident native input and rendered application, no physical actuation claim')
    return result
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
