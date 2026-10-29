"""Independent fixture checks for physical WebSocket framing reports."""
import struct

def check(raw,cases):
    assert len(raw)==16384 and struct.unpack_from('<QQ',raw)==(0x57534631,len(cases))
    for i,c in enumerate(cases):
        p=256+i*384;rc,frames,plain,control,used,eof=struct.unpack_from('<6q',raw,p)
        assert (rc,frames)==(c['rc'],c['frames']),(c['name'],rc,frames,c)
        assert raw[p+64:p+64+plain].hex()==c['plain'],(c['name'],'plain')
        assert raw[p+208:p+208+control].hex()==c['control'],(c['name'],'control')
        if rc>=0:assert used==len(bytes.fromhex(c['wire']))
        if c['name'] in ('close','empty-close'):assert eof==0
        elif rc<0:assert eof==rc
        else:assert eof==-605
    return dict(passed=True,cases=len(cases))
