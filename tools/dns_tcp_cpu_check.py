"""Check physical execution of the DNS TCP fallback owner with transport doubles."""
import struct


def check(data,cases):
    q=lambda p:struct.unpack_from('<q',data,p)[0]
    assert len(data)==16384 and q(0)==0x444e5431 and q(8)==64
    rows=[]
    for index in cases:
        i=index%16
        row=[q(256+index*96+j*8) for j in range(12)]
        if i in (0,1,8):expected=[3,0,0x01020304,45,3 if i==8 else 1,1,1]
        elif i==15:expected=[0,0,0,0,1,1,1]
        else:expected=[4,-104 if i in (3,14) else -105,0,0,1,0 if i==9 else 1,1]
        if (index//16)%2==1:
            expected[2]=0
            assert data[10240+index*16:10256+index*16]==(bytes.fromhex('20010db800000000123456789abcdef0') if i in (0,1,8) else b'\0'*16)
        assert row[:7]==expected,(i,row,expected)
        assert row[8:11]==[0,0,1],(i,row)
        assert row[11]==(4 if index<32 else 6),(index,row)
        rows.append(dict(case=i,state=row[0],error=row[1],opens=row[4],closes=row[5],sent=row[7]))
    for i in range(3):
        assert [q(8192+i*24+j*8) for j in range(3)]==[1,2,1]
    assert [q(12288+i*8) for i in range(8)]==[-103,-110,-103,28,2,-105,0,-102]
    assert data[12352:12368]==b'\xa5'*16
    for i in range(8):
        p=13312+i*128
        row=[q(p+j*8) for j in range(8)]
        expected={0:[-110,5,6,1,0,0,0,6],1:[-110,5,6,1,0,0,0,6],
                  2:[-102,0,4,0,0,0,0,0],3:[-108,0,4,0,0,0,0,0],
                  4:[-102,0,4,0,0,0,0,0],5:[-108,0,4,0,0,1,0,0],
                  6:[-110,5,6,1,0,0,0,6],7:[-105,0,6,1,0,0,0,6]}[i]
        assert row==expected,(i,row,expected)
        if i in (0,1,6,7):assert data[p+64:p+80]==bytes(range(32,48))
        assert [q(p+j) for j in (80,88,96)]==[0,0,1 if i in (0,1) else 0]
    return dict(tcp_cases=rows,pending_type_checks=9,ipv6_start_cases=8)
