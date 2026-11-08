"""Independent checks of the final FAT32 bytes from the Zentaji storage proof."""
import datetime
import math
import struct


def check(medium,initial,payload):
    u16=lambda at:struct.unpack_from('<H',medium,at)[0]
    u32=lambda at:struct.unpack_from('<I',medium,at)[0]
    part=u32(454);boot=part*512
    assert part==63 and u16(boot+11)==512 and medium[boot+13]==1
    reserved=u16(boot+14);copies=medium[boot+16];fat_sectors=u32(boot+36)
    total=u32(boot+32);clusters=total-reserved-copies*fat_sectors
    fat=(part+reserved)*512;data=part+reserved+copies*fat_sectors
    assert copies==2 and clusters==65525 and fat_sectors==512
    assert medium[:boot+512]==initial[:boot+512]
    assert medium[fat:fat+fat_sectors*512]==medium[fat+fat_sectors*512:fat+2*fat_sectors*512]
    entry=lambda cl:u32(fat+cl*4)&0x0fffffff
    def chain(first):
        result=[];cl=first
        while True:
            assert 2<=cl<clusters+2 and cl not in result and len(result)<64,('chain',first,result,cl)
            result.append(cl);cl=entry(cl)
            if cl>=0x0ffffff8:return result
    def contents(first):
        return b''.join(medium[(data+cl-2)*512:(data+cl-1)*512] for cl in chain(first))
    def directory(first):
        raw=contents(first);result={};pieces={};checksum=None;last=0
        for at in range(0,len(raw),32):
            e=raw[at:at+32]
            if e[0]==0:break
            if e[0]==0xe5:pieces={};continue
            if e[11]==0x0f:
                order=e[0]&31
                if e[0]&64:pieces={};last=order;checksum=e[13]
                assert order==last-len(pieces) and order>0 and e[12]==0 and e[26:28]==b'\0\0'
                assert e[13]==checksum
                pieces[order]=[struct.unpack_from('<H',e,i)[0] for i in (1,3,5,7,9,14,16,18,20,22,24,28,30)]
                continue
            if e[11]&8:pieces={};continue
            short=e[:11];s=0
            for b in short:s=(((s&1)<<7)+(s>>1)+b)&255
            if pieces:
                assert len(pieces)==last and s==checksum
                units=sum((pieces[i] for i in range(1,last+1)),[])
                if 0 in units:
                    end=units.index(0);assert all(x==65535 for x in units[end+1:]);units=units[:end]
                name=struct.pack('<'+'H'*len(units),*units).decode('utf-16le')
            else:
                name=short[:8].decode('ascii').rstrip()
                ext=short[8:].decode('ascii').rstrip()
                if ext:name+='.'+ext
            assert name not in result
            result[name]=dict(cluster=(struct.unpack_from('<H',e,20)[0]<<16)|struct.unpack_from('<H',e,26)[0],size=struct.unpack_from('<I',e,28)[0],attr=e[11],entry=e)
            pieces={}
        assert not pieces
        return result
    root=directory(u32(boot+44));assert set(root)=={'Folder'},root
    folder=root['Folder'];assert folder['attr']&16 and folder['size']==0
    inside=directory(folder['cluster']);assert set(inside)=={'.','..','Long file name.bin'},inside
    assert inside['.']['cluster']==folder['cluster'] and inside['..']['cluster']==0
    file=inside['Long file name.bin'];assert not file['attr']&16 and file['size']==1800
    assert contents(file['cluster'])[:1800]==payload[:1800]
    assert len(chain(file['cluster']))==math.ceil(1800/512)
    allocated=set(chain(u32(boot+44)))|set(chain(folder['cluster']))|set(chain(file['cluster']))
    assert len(allocated)==6
    actual={cl for cl in range(2,clusters+2) if entry(cl)!=0}
    assert actual==allocated,('leaked or cross-linked allocations',actual,allocated)
    info=(part+u16(boot+48))*512
    assert u32(info)==0x41615252 and u32(info+484)==0x61417272 and u32(info+508)==0xaa550000
    assert u32(info+488)==clusters-len(allocated),('free count',u32(info+488))
    assert 2<=u32(info+492)<clusters+2
    assert entry(1)&0x08000000,'volume not clean after flush'
    date=datetime.datetime.fromtimestamp(1794009600,datetime.timezone.utc)
    fatdate=((date.year-1980)<<9)|(date.month<<5)|date.day
    fattime=(date.hour<<11)|(date.minute<<5)|(date.second//2)
    assert struct.unpack_from('<HH',file['entry'],22)==(fattime,fatdate),'wall-clock write timestamp'
    return 'MBR/BPB and FAT mirrors, exact nested long-name file bytes, LFN sequence/checksum, dot links, six reachable allocations without leaks, FSInfo free count, clean marker and independent UTC timestamp'
