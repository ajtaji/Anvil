"""Check the physical counter report, timing bounds and complete guard area."""
import struct
def check(data):
    assert len(data)==16384
    magic,hz,ready,reads,delay_ok,delay_us,before,after,count,minimum,maximum,status=struct.unpack_from('<12Q',data)
    assert (magic,hz,ready,reads,delay_ok,count,status)==(0x434E5431,54000000,1,128,1,32,0)
    assert 1000<=delay_us<=100000 and before==after
    assert 0<minimum<=maximum<=hz//100
    assert data[96:]==bytes([0xA5])*(16384-96)
    return dict(frequency=hz,reads=reads,delay_us=delay_us,event_samples=count,event_min_ticks=minimum,event_max_ticks=maximum,control_restored=True)
