"""Check bounded TLS handles, per-connection buffers and cleanup on silicon."""
import struct

def check(raw,cases=None):
    top=struct.unpack_from('<7q',raw)
    assert top==(0x54504C31,-103,-102,5,-102,1,1),top
    rows=[]
    for i in range(4):
        row=struct.unpack_from('<7q',raw,256+i*64)
        assert row==(i+1,4,500+i,71+i,1,1,91+i),(i,row)
        sent=struct.unpack_from('<q',raw,2048+i*8)[0]
        assert sent==31+i,(i,sent)
        rows.append(row)
    return {'connections':4,'isolated_rows':rows,'stale_handle_refused':True,'all_snapshots_wiped_on_return':True}
