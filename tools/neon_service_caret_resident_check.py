"""Check the fixed expected results from the installed caret service test."""
from pathlib import Path
import json,struct
EXPECTED=json.loads(Path(__file__).with_name('neon_service_caret_resident_expected.json').read_text())
def check(report):
    assert len(report)==16384
    assert struct.unpack_from('<4q',report)==(0x4E435231,1,0,len(EXPECTED))
    assert not any(report[32:1024])
    for i,want in enumerate(EXPECTED):
        actual,declared=struct.unpack_from('<2q',report,1024+i*16)
        assert (actual,declared)==(want,want),(i+1,actual,declared,want)
    assert not any(report[1024+len(EXPECTED)*16:])
    return dict(checks=len(EXPECTED),scope='Installed service and pure client; no physical input or exact image claim')
