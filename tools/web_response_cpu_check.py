"""Check physical response decoding, refusals, boundaries and input splits."""
import struct
def check(data,cases):
    assert len(data)==16384
    assert struct.unpack_from('<QQ',data)==(0x57525331,len(cases)*3)
    assert data[16:256]==bytes([0xA5])*240
    for i,c in enumerate(cases):
        for mode in range(3):
            at=256+(i*3+mode)*160
            rc,status,state,total,consumed,reusable,out=struct.unpack_from('<7q',data,at)
            assert (rc,status,state,total,reusable,out)==(c['error'],c['status'],-1 if c['error'] else 9,len(c['body']),c['reusable'],len(c['body'])),(i,mode,rc,status,state,total,reusable,out)
            if not c['error']:assert consumed==c['consumed'],(i,mode,'consumed',consumed)
            else:assert 0<consumed<=len(c['wire']),(i,mode,'error consumed',consumed)
            assert data[at+56:at+64]==bytes(8)
            assert data[at+64:at+128]==bytes(c['body'])+bytes(64-len(c['body'])),(i,mode,'body')
            assert data[at+128:at+160]==bytes(32)
    end=256+len(cases)*3*160
    assert data[end:]==bytes([0xA5])*(16384-end)
    return {'cases':len(cases),'input_output_schedules':3,'checked_rows':len(cases)*3,'report_bytes':len(data)}
