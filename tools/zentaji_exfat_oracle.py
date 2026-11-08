"""Independent minimal exFAT image builder and persisted-byte storage oracle."""
import datetime
import struct


def checksum(data, bits=32, skip=()):
    value=0; mask=(1<<bits)-1
    for i,b in enumerate(data):
        if i not in skip:value=(((value>>1)|((value&1)<<(bits-1)))+b)&mask
    return value


def build(part=1):
    image=bytearray(((part+2048+7)&-8)*512)
    def put(at,fmt,*values):struct.pack_into('<'+fmt,image,at,*values)
    image[450]=7;put(454,'II',part,2048);put(510,'H',0xaa55)
    boot=part*512
    image[boot:boot+11]=b'\xeb\x76\x90EXFAT   '
    put(boot+64,'QQIIIIIIHH',part,2048,24,2,26,128,4,0x12345678,0x100,0)
    image[boot+108:boot+113]=bytes([9,0,1,0x80,2])
    for sector in range(11):put(boot+sector*512+510,'H',0xaa55)
    for cl in (2,3,4):put((part+24)*512+cl*4,'I',0xffffffff)
    image[(part+26)*512]=7
    table=list(range(97))+list(range(65,91))+[0xffff,65413]
    upcase=struct.pack('<125H',*table);image[(part+27)*512:(part+27)*512+250]=upcase
    root=(part+28)*512;image[root]=0x81;put(root+20,'IQ',2,16)
    image[root+32]=0x82;put(root+36,'I',checksum(upcase));put(root+52,'IQ',3,250)
    value=checksum(image[boot:boot+11*512],skip=(106,107,112))
    for offset in range(0,512,4):put(boot+11*512+offset,'I',value)
    image[(part+12)*512:(part+24)*512]=image[boot:(part+12)*512]
    return image


def check(medium,initial,payload,epoch_min=1794009600,epoch_max=None):
    u16=lambda data,at:struct.unpack_from('<H',data,at)[0]
    u32=lambda data,at:struct.unpack_from('<I',data,at)[0]
    u64=lambda data,at:struct.unpack_from('<Q',data,at)[0]
    part=u32(medium,454);base=part*512
    assert part in (1,4096)
    assert medium[:base]==initial[:base]
    assert medium[(part+12)*512:(part+24)*512]==initial[(part+12)*512:(part+24)*512]
    boot=medium[base:(part+12)*512]
    assert boot[:106]==initial[base:base+106] and boot[108:112]==initial[base+108:base+112]
    assert u16(boot,106)&0xa==0,'volume not clean'
    value=checksum(boot[:11*512],skip=(106,107,112))
    assert boot[11*512:]==struct.pack('<I',value)*128,'boot checksum'
    assert (u64(boot,64),u64(boot,72),u32(boot,80),u32(boot,84),u32(boot,88),u32(boot,92),u32(boot,96))==(part,2048,24,2,26,128,4)
    assert boot[108:111]==bytes([9,0,1])
    fat=medium[(part+24)*512:(part+26)*512];allocated=set()
    def stream(first,flags,length):
        clusters=[];cl=first
        for index in range((length+511)//512):
            assert 2<=cl<130 and cl not in clusters and cl not in allocated,('crosslink/chain',cl)
            clusters.append(cl)
            if index+1<(length+511)//512:
                cl=cl+1 if flags&2 else u32(fat,cl*4)
        if clusters and not flags&2:assert u32(fat,cl*4)>=0xfffffff8
        allocated.update(clusters)
        return b''.join(medium[(part+26+c-2)*512:(part+27+c-2)*512] for c in clusters)[:length]
    def directory(raw):
        result={};index=0
        while index*32<len(raw):
            entry=raw[index*32:(index+1)*32];kind=entry[0]
            if kind==0:break
            if kind in (0x81,0x82) or not kind&0x80:index+=1;continue
            assert kind==0x85,('unexpected live entry',kind)
            n=entry[1];entries=raw[index*32:(index+n+1)*32];assert len(entries)==32*(n+1)
            assert checksum(entries,16,(2,3))==u16(entry,2),'entry set checksum'
            ext=entries[32:64];assert ext[0]==0xc0 and ext[1]&1
            nameunits=[]
            for i in range(2,n+1):
                part=entries[i*32:(i+1)*32];assert part[0]==0xc1
                nameunits.extend(struct.unpack_from('<15H',part,2))
            assert all(x==0 for x in nameunits[ext[3]:]),'name padding'
            name=struct.pack('<'+'H'*ext[3],*nameunits[:ext[3]]).decode('utf-16le')
            assert checksum(name.upper().encode('utf-16le'),16)==u16(ext,4),'name hash'
            assert name not in result
            length=u64(ext,24);valid=u64(ext,8);assert valid<=length
            result[name]=(u16(entry,4),u32(ext,20),ext[1],length,valid,entry)
            index+=n+1
        return result
    rootraw=stream(4,0,512)
    assert rootraw[0]==0x81 and u32(rootraw,20)==2 and u64(rootraw,24)==16
    bitmap=stream(2,0,16)
    assert rootraw[32]==0x82 and u32(rootraw,52)==3 and u64(rootraw,56)==250
    upcase=stream(3,0,250);assert checksum(upcase)==u32(rootraw,36)
    assert upcase==initial[(part+27)*512:(part+27)*512+250]
    root=directory(rootraw);assert set(root)=={'Folder'},root
    folder=root['Folder'];assert folder[0]&16 and folder[3]==512
    inside=directory(stream(folder[1],folder[2],folder[3]))
    assert set(inside)=={'Long file name.bin'},inside
    file=inside['Long file name.bin'];assert not file[0]&16 and file[3:5]==(1800,1800)
    assert stream(file[1],file[2],file[3])==payload[:1800]
    actual={cl for cl in range(2,130) if bitmap[(cl-2)//8]&(1<<((cl-2)%8))}
    assert actual==allocated and len(allocated)==8,('bitmap leaks/crosslinks',actual,allocated)
    assert boot[112] in (len(actual)*100//128,255),'percent in use'
    if epoch_max is None:epoch_max=epoch_min
    assert 0<=epoch_max-epoch_min<=60,'timestamp bracket is too wide'
    packed=set()
    for epoch in range(epoch_min,epoch_max+1):
        dt=datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc)
        date=((dt.year-1980)<<9)|(dt.month<<5)|dt.day
        time=(dt.hour<<11)|(dt.minute<<5)|(dt.second//2)
        packed.add((time,date))
    assert struct.unpack_from('<HH',file[5],12) in packed,'write timestamp'
    assert file[5][23]==0x80,'UTC offset validity'
    return 'exFAT boot sums/clean flags, preserved backup, entry-set/name hashes, upcase table, exact nested file, eight reachable bitmap allocations without leaks and independent UTC timestamp'


def seed_file(image,payload,name='SEED.BIN'):
    """Seed an independent contiguous file; the guest must use its file APIs."""
    part=struct.unpack_from('<I',image,454)[0]
    assert 1<=len(payload)<=125*512 and 1<=len(name)<=15
    clusters=(len(payload)+511)//512
    entries=bytearray(96);entries[0]=0x85;entries[1]=2
    struct.pack_into('<H',entries,4,32)
    entries[32]=0xc0;entries[33]=3;entries[35]=len(name)
    struct.pack_into('<H',entries,36,checksum(name.upper().encode('utf-16le'),16))
    struct.pack_into('<Q',entries,40,len(payload));struct.pack_into('<I',entries,52,5);struct.pack_into('<Q',entries,56,len(payload))
    entries[64]=0xc1;entries[66:66+len(name)*2]=name.encode('utf-16le')
    struct.pack_into('<H',entries,2,checksum(entries,16,(2,3)))
    root=(part+28)*512;image[root+64:root+160]=entries
    image[(part+26)*512:(part+26)*512+16]=((1<<(clusters+3))-1).to_bytes(16,'little')
    image[part*512+112]=(clusters+3)*100//128
    image[(part+29)*512:(part+29)*512+len(payload)]=payload
