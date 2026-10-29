"""Check physical execution of the DNS TCP fallback owner with transport doubles."""
import struct


def check(data,cases):
    q=lambda p:struct.unpack_from('<q',data,p)[0]
    assert len(data)==16384 and q(0)==0x444e5431 and q(8)==16
    rows=[]
    for i in cases:
        row=[q(256+i*96+j*8) for j in range(11)]
        if i in (0,1,8):expected=[3,0,0x01020304,45,3 if i==8 else 1,1,1]
        elif i==15:expected=[0,0,0,0,1,1,1]
        else:expected=[4,-104 if i in (3,14) else -105,0,0,1,0 if i==9 else 1,1]
        assert row[:7]==expected,(i,row,expected)
        assert row[8:]==[0,0,1],(i,row)
        rows.append(dict(case=i,state=row[0],error=row[1],opens=row[4],closes=row[5],sent=row[7]))
    for i in range(3):
        assert [q(8192+i*24+j*8) for j in range(3)]==[1,2,1]
    return rows
