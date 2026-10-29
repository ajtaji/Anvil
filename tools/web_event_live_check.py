"""Validate live HTTPS events, including delivery before the response finishes."""
import json,struct

def check(raw,cases=None):
    magic,rc,status,count,total,eof,received=struct.unpack_from('<7q',raw)
    assert (magic,rc,status,count,eof)==(0x53534C31,1,200,3,0),(magic,rc,status,count,eof)
    rows=[]
    for i in range(count):
        p=256+i*256
        dl,el,at,step=struct.unpack_from('<4q',raw,p)
        data=json.loads(raw[p+32:p+32+dl])
        assert data['id']==i and isinstance(data['timestamp'],int),data
        assert raw[p+224:p+224+el]==b'ping'
        rows.append(dict(id=i,arrival_ms=at,response_complete=step==1))
    assert rows[0]['arrival_ms']<total-500 and not rows[0]['response_complete'],rows
    assert rows[1]['arrival_ms']>rows[0]['arrival_ms']+250,rows
    assert rows[2]['arrival_ms']>rows[1]['arrival_ms']+250,rows
    return dict(events=rows,total_ms=total,received=received)
