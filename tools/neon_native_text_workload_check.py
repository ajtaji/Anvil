"""Validate the bounded mixed native workload before reporting its timing."""
import struct
import statistics

def check(blob):
    assert len(blob) == 4096
    magic, version, hz, frames = struct.unpack_from('<4q', blob)
    assert (magic, frames) == (0x4E545731, 8) and version in (1, 2)
    assert hz == 54000000, 'Pi 4 architectural counter frequency'
    assert not any(blob[64+8*128:])
    states=struct.unpack_from('<4q',blob,32)
    assert states == ((0, 0, 0, 0) if version == 1 else (0, 0x1005, 0, 0))
    rows=[]
    for index in range(8):
        kind, frame, begin, boxes, text, end, total, nb, ng, ntg, nd, ntd, nv, ntv, error, runs = struct.unpack_from('<16q', blob, 64+index*128)
        assert (kind, frame) == (index//4, index%4)
        assert min(begin, boxes, text, end) > 0 and total == begin+boxes+text+end
        assert error == 0 and nb == 3505
        if kind == 0:
            assert (ng, ntg, nd, ntd, ntv) == (1434, 0, 3535, 0, 0)
            assert runs > 1434 and nv == (3505+runs)*6 and nv <= 262144
        else:
            assert (ng, ntg, nd, ntd, nv, ntv, runs) == (0, 1434, 3505, 30, 21030, 8604, 0)
        rows.append(dict(path='flat' if kind == 0 else 'textured', frame=frame,
                         begin_us=begin*1e6/hz, boxes_us=boxes*1e6/hz,
                         text_us=text*1e6/hz, end_us=end*1e6/hz,
                         total_us=total*1e6/hz, glyphs=1434, boxes=3505, runs=runs))
    summary={}
    for kind in ('flat','textured'):
        warm=[row for row in rows if row['path']==kind and row['frame']>0]
        summary[kind]={field:statistics.median(row[field] for row in warm)
                       for field in ('begin_us','boxes_us','text_us','end_us','total_us')}
    return dict(counter_hz=hz, cache_states=states, cache_measured=version==2, rows=rows, median_warm=summary,
                scope='Three warm samples per path; not paired Vulkan compatibility or endurance')
