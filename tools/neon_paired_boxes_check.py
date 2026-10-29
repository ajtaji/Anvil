"""Full-target paired native/Vulkan box oracle; no tolerance or cropping."""
import struct,statistics,hashlib
BYTES=4096000

def check(report,pixels,profile=False,detail=False,batch=False,scene="boxes"):
    if len(report)!=16384 or len(pixels)!=2*BYTES: raise ValueError('artifact length')
    if struct.unpack_from('<I',report,4)[0]!=0: raise ValueError('bootstrap status')
    if struct.unpack_from('<3Q',report,8192)!=(1,1,54000000): raise ValueError('completion or clock')
    if scene not in ('boxes','mixed'):raise ValueError('scene')
    if struct.unpack_from('<Q',report,8216)[0]!=int(scene=='mixed'):raise ValueError('scene identity')
    if any(report[8192+32:8192+64]) or any(report[8768:9216]) or any(report[9664:] if batch else report[9536:]) or (not detail and any(report[9472:9536])) or (not profile and any(report[9216:9472])): raise ValueError('reserved report bytes')
    rows=[]
    for index in range(8):
        kind,frame,build,gpu,boxes,error,cache,consume=struct.unpack_from('<8Q',report,8192+64+index*64)
        if (kind,frame,boxes,error,cache,consume)!=(index//4,index%4,3505,0,0x1005,index//4): raise ValueError(('frame state',index))
        if not 0<build<540000000 or not 0<gpu<540000000: raise ValueError(('timing',index))
        rows.append(dict(kind=kind,frame=frame,build_us=build/54,end_us=gpu/54,total_us=(build+gpu)/54))
    phases=[]
    if profile:
        for frame in range(4):
            p=struct.unpack_from('<8Q',report,9216+frame*64)
            if not 0<p[0] or any(p[i+1]<=p[i] for i in range(5)): raise ValueError('phase order')
            if p[5]-p[0]>rows[4+frame]['end_us']+10: raise ValueError('phase envelope')
            if not 1<=p[7]<=p[6]: raise ValueError('cache interval counts')
            phases.append(dict(frame=frame,validate_us=p[1]-p[0],prepare_us=p[2]-p[1],cache_us=p[3]-p[2],emit_us=p[4]-p[3],gpu_wait_us=p[5]-p[4],cache_inputs=p[6],cache_merged=p[7]))
    if detail:
        if not profile:raise ValueError('detail requires phases')
        for frame,p in enumerate(phases):
            stamps=struct.unpack_from('<6Q',report,9216+frame*64)
            allocated,built=struct.unpack_from('<2Q',report,9472+frame*16)
            if not stamps[1]<=allocated<=built<=stamps[2]:raise ValueError('preparation subphases')
            p.update(packet_allocation_us=allocated-stamps[1],slot_build_us=built-allocated,cache_collect_us=stamps[2]-built)
    if batch:
        for frame in range(4):
            if struct.unpack_from('<4Q',report,9536+frame*32)!=(439 if scene=='mixed' else 1,3505,3505,3505):raise ValueError('execution batch or logical counters')
    expected=bytearray(b'\x00\x00\x00\xff'*(800*1280))
    for i in range(3505):
        if scene=='boxes':
            x,y=(i%100)*7,(i//100)*7;x2,y2=x+4,y+4;colour=bytes((0x30,0x30,0x30,0xff))
        else:
            phase=(i//64)%2;cx,cy=20+phase*12,18+phase*8
            bx,by=16+(i%11)*3,14+((i//11)%7)*4
            x,y=max(bx,cx),max(by,cy);x2,y2=min(bx+80,cx+70),min(by+60,cy+50)
            colour=[bytes((0x66,0x44,0x22,0xff)),bytes((0xaa,0x88,0x66,0xff)),bytes((0x44,0x88,0xcc,0xff))][(i//8)%3]
        for row in range(y,y2):
            at=(row*800+x)*4;expected[at:at+(x2-x)*4]=colour*(x2-x)
    for kind in range(2):
        actual=pixels[kind*BYTES:(kind+1)*BYTES]
        if actual!=expected:
            diffs=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
            raise ValueError(('full target pixels',kind,len(diffs),diffs[:8]))
    return dict(phases=phases,rows=rows,exact_bytes=2*BYTES,sha256=hashlib.sha256(expected).hexdigest(),median_warm_us={str(k):statistics.median(x['total_us'] for x in rows if x['kind']==k and x['frame']>0) for k in (0,1)},scope=scene+' boxes only; three warm samples, not full engine or sustained performance qualification')
