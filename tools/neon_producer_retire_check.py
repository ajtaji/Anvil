"""Strict controlled-idle retirement report; not a GPU fault oracle."""
import struct
def check(raw,plan):
    assert len(raw)==4096
    expected=bytearray(4096)
    for off,val in [(0,0x4e505231),(8,1),(24,len(plan))]:struct.pack_into('<q',expected,off,val)
    for i,row in enumerate(plan):struct.pack_into('<2q',expected,256+16*i,row['expected'],row['expected'])
    assert raw==expected,'controlled retirement status/guard/unused report mismatch'
    return {'passed':True,'checks':len(plan),'scope':'Exact production guard with controlled idle-call outcomes; no hardware GPU failure induced.'}
