"""Check four overlapping verified HTTPS connections and streamed delivery."""
import struct,json

def check(raw,cases=None):
    magic,rc,events,total=struct.unpack_from('<4q',raw)
    assert (magic,rc,events)==(0x544D4C31,0,3),(magic,rc,events)
    handles=struct.unpack_from('<4q',raw,32)
    assert len(set(handles))==4 and min(handles)>0,handles
    rows=[]
    for i in range(4):
        p=256+i*512
        complete,status,at,n=struct.unpack_from('<4q',raw,p)
        assert (complete,status)==(1,200),(i,complete,status)
        if i:assert raw[p+64:p+64+n]==b'parallel HTTPS reply',(i,n)
        rows.append(dict(handle=handles[i],complete_ms=at))
    arrivals=[]
    for i in range(3):
        p=4096+i*256
        dl,el,at,step=struct.unpack_from('<4q',raw,p)
        event=json.loads(raw[p+32:p+32+dl]);assert event['id']==i,event
        assert raw[p+224:p+224+el]==b'ping'
        arrivals.append(at)
        if i==0:assert step==0
    assert arrivals[0]+500<rows[0]['complete_ms'],arrivals
    assert all(row['complete_ms']<rows[0]['complete_ms'] for row in rows[1:]),rows
    return dict(connections=rows,event_arrivals_ms=arrivals,total_ms=total)
