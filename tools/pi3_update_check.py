"""Actual Pi3 updater + FAT32 emission, sparse sector device and SHA service.

SHA calls use Python hashlib as an explicit dependency model to keep power-cut
enumeration fast. FAT parsing, extent admission, update/loader control and CRC
execute emitted code. Not an SDHOST hardware/timing/durability proof.
"""
import argparse, hashlib, os, pathlib, struct, subprocess, sys, tempfile, zlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base

ROOT=base.ROOT
DATA=2048+32+1024
FIRST=[3,19,35,36,37]
SIZES=[8192,8192,512,512,1024]
HEADER=256

def container(data):
    pmf=bytearray(128)
    struct.pack_into('<8sIIQQQQQII',pmf,0,b'PMFBOOT\0',2,128,0x200000,0x200000,len(data),0x1100000,4096,0,0)
    pmf[64:96]=hashlib.sha256(data).digest()
    struct.pack_into('<IIQ',pmf,96,1,2837,0x1f00000)
    pmf=bytes(pmf)+data
    header=bytearray(128)
    struct.pack_into('<8sIIIIQQ',header,0,b'P3SLOT\0\0',1,128,2837,64,0x1f00000,len(pmf))
    header[40:72]=hashlib.sha256(pmf).digest()
    return bytes(header)+pmf

def record(slot,generation,data,state=3):
    b=bytearray(512)
    struct.pack_into('<IIQQII',b,0,0x42413350,2,generation,len(data),slot,0x200000)
    b[32:64]=hashlib.sha256(data).digest()
    struct.pack_into('<I',b,64,state)
    struct.pack_into('<I',b,508,zlib.crc32(b[:508]))
    return bytes(b)

def volume(spc=1):
    disk={}
    sectors=32+1024+65525*spc
    mbr=bytearray(512);mbr[450]=0x0c
    struct.pack_into('<II',mbr,454,2048,sectors);mbr[510:]=b'\x55\xaa';disk[0]=bytes(mbr)
    v=bytearray(512);v[:3]=b'\xeb\x58\x90';v[3:11]=b'ANVIL   '
    struct.pack_into('<H',v,11,512);v[13]=spc;struct.pack_into('<H',v,14,32);v[16]=2
    v[21]=0xf8;struct.pack_into('<I',v,28,2048);struct.pack_into('<I',v,32,sectors)
    struct.pack_into('<I',v,36,512);struct.pack_into('<I',v,44,2)
    struct.pack_into('<HH',v,48,1,6);v[66]=0x29;v[82:90]=b'FAT32   ';v[510:]=b'\x55\xaa'
    disk[2048]=bytes(v)
    fat=bytearray(512)
    for cl,val in [(0,0xffffff8),(1,0xfffffff),(2,0xfffffff)]:struct.pack_into('<I',fat,cl*4,val)
    names=[b'ANVILA  BIN',b'ANVILB  BIN',b'P3CTRLA BIN',b'P3CTRLB BIN',b'KERNEL8 IMG']
    root=bytearray(512)
    for i,(first,size,name) in enumerate(zip(FIRST,SIZES,names)):
        clusters=(size+spc*512-1)//(spc*512)
        for cl in range(first,first+clusters):struct.pack_into('<I',fat,cl*4,cl+1 if cl<first+clusters-1 else 0xfffffff)
        at=i*32;root[at:at+11]=name;root[at+11]=0x20
        struct.pack_into('<H',root,at+26,first);struct.pack_into('<I',root,at+28,size)
    disk[2080]=bytes(fat);disk[2592]=bytes(fat);disk[DATA]=bytes(root)
    old=container(bytes((i*7+3)&255 for i in range(800)))
    for off in range(0,len(old),512):disk[DATA+(FIRST[0]-2)*spc+off//512]=old[off:off+512]
    disk[DATA+(FIRST[2]-2)*spc]=record(0,1,old)
    return disk,old

def fat_link(disk,cluster,value):
    """Set one FAT32 entry in both copies of the compact gate volume."""
    byte_off=cluster*4
    for base_lba in (2080,2592):
        lba=base_lba+byte_off//512
        sector=bytearray(disk.get(lba,bytes(512)))
        struct.pack_into('<I',sector,byte_off%512,value)
        disk[lba]=bytes(sector)

def nested_tree(disk,file_first=41,file_size=512,dot_self=40,dot_parent=2,
                include_dot=True,child_attr=0x20,child_first=None):
    """Add OVERLAYS/FILE.BIN with ordinary FAT dot entries."""
    root=bytearray(disk[DATA]);at=5*32
    root[at:at+11]=b'OVERLAYS   ';root[at+11]=0x10
    struct.pack_into('<H',root,at+26,40);disk[DATA]=bytes(root)
    fat_link(disk,40,0xfffffff)
    directory=bytearray(512);at=0
    if include_dot:
        directory[at:at+11]=b'.          ';directory[at+11]=0x10
        struct.pack_into('<H',directory,at+26,dot_self);at+=32
        directory[at:at+11]=b'..         ';directory[at+11]=0x10
        struct.pack_into('<H',directory,at+26,dot_parent);at+=32
    directory[at:at+11]=b'FILE    BIN';directory[at+11]=child_attr
    target=file_first if child_first is None else child_first
    struct.pack_into('<H',directory,at+26,target)
    struct.pack_into('<I',directory,at+28,0 if child_attr&0x10 else file_size)
    disk[DATA+40-2]=bytes(directory)
    return DATA+40-2

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi3-update-') as tmp:
        image=pathlib.Path(tmp)/'update.img'
        env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        cmd=[args.compiler,'--compile','RaspberryPi3/Tests/update_ab_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)]
        r=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True)
        if r.returncode or not image.exists():raise AssertionError(r.stdout+r.stderr)
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP)
        checks=0
        class Rig:
            def __init__(self,disk,cut=None,tear=False):
                self.disk=disk;self.cut=cut;self.tear=tear;self.writes=[];self.sha=None
                self.window=(0,0);self.windows=[]
                self.reads=0;self.read_fail_at=None;self.read_fail_lba=None;self.read_fail_occurrence=1;self.read_fail_hits=0;self.read_lbas=[];self.sha_calls=0
                self.cpu=a64.A64();self.cpu.sp=base.STACK
                self.cpu.memory={base.LOAD+i:b for i,b in enumerate(blob)}
            def get(self,p,n):return bytes(self.cpu.memory.get(p+i,0) for i in range(n))
            def put(self,p,data):
                for i,b in enumerate(data):self.cpu.memory[p+i]=b
            def call(self,name,*argv):
                c=self.cpu;c.pc=base.LOAD+sym[name.lower()];c.x[30]=base.RETURN_PC
                for i,v in enumerate(argv):c.x[i]=v
                hooks={base.LOAD+sym[n]:n for n in ['pi3sdreadblock','pi3sdwriteblock','pi3sdsetwritewindow','sha256begin','sha256update','sha256end','sha256of']}
                for step in range(5000000):
                    if c.pc==base.RETURN_PC:return c.x[0]
                    hook=hooks.get(c.pc)
                    if hook:
                        a,b,d=c.x[:3];result=1
                        if hook=='pi3sdreadblock':
                            self.reads+=1
                            self.read_lbas.append(a)
                            if self.reads==self.read_fail_at or (self.read_fail_lba is not None and a==self.read_fail_lba and sum(1 for x in self.read_lbas if x==a)==self.read_fail_occurrence):
                                self.read_fail_hits+=1;result=0
                            else:self.put(b,self.disk.get(a,bytes(512)))
                        elif hook=='pi3sdsetwritewindow':
                            assert (a==0 and b==0) or (a>0 and b>0), ('invalid fence',a,b)
                            self.window=(a,b);self.windows.append((a,b))
                        elif hook=='pi3sdwriteblock':
                            first,count=self.window
                            assert count>0 and first<=a<first+count, ('write outside armed fence',a,self.window)
                            self.writes.append(a)
                            if self.cut==len(self.writes):
                                if self.tear:self.disk[a]=self.get(b,256)+self.disk.get(a,bytes(512))[256:]
                                result=0
                            else:self.disk[a]=self.get(b,512)
                        elif hook=='sha256begin':self.sha=hashlib.sha256();self.sha_calls+=1
                        elif hook=='sha256update':self.sha.update(self.get(a,b))
                        elif hook=='sha256end':self.put(a,self.sha.digest())
                        elif hook=='sha256of':self.put(d,hashlib.sha256(self.get(a,b)).digest());self.sha_calls+=1
                        c.x[0]=result;c.pc=c.x[30]
                    else:c.step()
                raise AssertionError('unbounded '+name)
            def mount(self):
                assert self.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
                result=self.call('Pi3UpdateMount')
                assert result==1,('mount',self.call('Pi3UpdateError'))

        # Verify the native indirect mount-progress callback, including the
        # SD-read/hash split and final completion mark.
        disk,_=volume();progress=Rig(disk)
        assert progress.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert progress.call('Pi3UpdateMountProgressHandler',base.LOAD+sym['pi3testmountprogress'])==1
        assert progress.call('Pi3UpdateMount')==1
        phases=[progress.call('Pi3TestMountPhaseAt',i) for i in range(progress.call('Pi3TestMountPhaseCount'))]
        assert phases==[1,2,12,13,14,15,16,3,4,5,60,61,10,20,40,30,50,51,11,8],phases
        assert progress.call('Pi3UpdateMountProgressHandler',0)==1
        assert progress.call('Pi3UpdateWorkProgressHandler',base.LOAD+sym['pi3testworkprogress'])==1
        assert progress.call('Pi3UpdateMount')==1
        work_count=progress.call('Pi3TestWorkCount')
        assert work_count>0,work_count
        work_tokens=[progress.call('Pi3TestWorkTokenAt',i) for i in range(work_count)]
        assert all(a<b for a,b in zip(work_tokens,work_tokens[1:])),work_tokens
        assert work_tokens[-1] > 0,work_tokens[-1]
        assert progress.call('Pi3UpdateWorkToken') == work_tokens[-1]
        assert progress.call('Pi3UpdateWorkProgressHandler',0)==1
        checks+=7

        # A refused completed-work callback must abort the digest/read path
        # before any write is admitted.
        disk,old=volume();baseline=dict(disk);failed=Rig(disk)
        assert failed.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert failed.call('Pi3UpdateWorkProgressHandler',base.LOAD+sym['pi3testworkprogress'])==1
        assert failed.call('Pi3TestWorkFail',1)==1
        assert failed.call('Pi3UpdateWorkProgress',4096)==0
        failed_result=failed.call('Pi3UpdateMount')
        assert failed_result==0
        assert failed.call('Pi3TestWorkCount')>0
        assert failed.writes==[],failed.writes
        assert disk==baseline
        assert failed.call('Pi3UpdateWorkProgressHandler',0)==1
        checks+=5

        for cut in (None,1,2,3,4):
            for tear in (False,True):
                disk,old=volume();baseline=dict(disk);rig=Rig(disk,cut,tear);rig.mount();checks+=1
                new=container(bytes((i*13+11)&255 for i in range(1076)))
                rig.put(0x1800000,hashlib.sha256(new).digest());rig.put(0x1800100,new)
                assert rig.call('Pi3UpdateBegin',len(new),0x1800000)==1
                assert rig.call('Pi3UpdateChunk',0,0x1800100,700)==1
                assert rig.call('Pi3UpdateChunk',0,0x1800100,700)==1
                assert rig.call('Pi3UpdateReceived')==700
                assert rig.call('Pi3UpdateChunk',700,0x1800100+700,len(new)-700)==1
                result=rig.call('Pi3UpdateCommit');checks+=5
                assert result==(1 if cut is None else 0),(cut,tear,result,rig.call('Pi3UpdateError'))
                allowed={DATA+FIRST[1]-2+i for i in range(3)}|{DATA+FIRST[3]-2}
                assert set(rig.writes)<=allowed,rig.writes
                for lba,value in baseline.items():
                    if lba not in allowed:assert disk[lba]==value
                boot=Rig(disk);boot.mount();length=boot.call('Pi3UpdateLoad')
                loaded=boot.get(0x200000,length)
                assert loaded in (old[HEADER:],new[HEADER:]),(cut,tear,length)
                if cut is None:
                    assert loaded==new[HEADER:] and boot.call('Pi3UpdateGeneration')==2
                    # TRIED is durable before returning executable bytes. A
                    # reboot without monitor confirmation uses old confirmed.
                    reboot=Rig(disk);reboot.mount()
                    assert reboot.call('Pi3UpdateLoad')==len(old)-HEADER
                    assert reboot.get(0x200000,len(old)-HEADER)==old[HEADER:]
                    assert reboot.call('Pi3UpdateConfirm',1,99)==0
                    assert reboot.call('Pi3UpdateConfirm',1,2)==1
                    confirmed=Rig(disk);confirmed.mount()
                    assert confirmed.call('Pi3UpdateLoad')==len(new)-HEADER
                    assert confirmed.get(0x200000,len(new)-HEADER)==new[HEADER:]
                    assert confirmed.call('Pi3UpdateLoadFallback')==len(old)-HEADER
                    checks+=7
                checks+=4
        # The physical card allocates 4 KiB clusters but control records are
        # 512 bytes. Do not confuse allocation capacity with bytes to overwrite.
        disk,old=volume(8);baseline=dict(disk);rig=Rig(disk);rig.mount()
        assert rig.window==(0,0), 'mount left a write fence armed'
        new=container(bytes([0x71])*1076)
        rig.put(0x1800000,hashlib.sha256(new).digest());rig.put(0x1800100,new)
        assert rig.call('Pi3UpdateBeginFrom',1,len(new),0x1800000)==1
        assert rig.call('Pi3UpdateChunk',0,0x1800100,1024)==1
        assert rig.call('Pi3UpdateChunk',1024,0x1800500,len(new)-1024)==1
        assert rig.call('Pi3UpdateCommitFrom',1)==1
        slot_lba=DATA+(FIRST[1]-2)*8; record_lba=DATA+(FIRST[3]-2)*8
        assert rig.writes==[slot_lba,slot_lba+1,slot_lba+2,record_lba], rig.writes
        assert (record_lba,1) in rig.windows and rig.window==(0,0),rig.windows
        for lba,sector in baseline.items():
            if lba not in rig.writes: assert disk[lba]==sector, ('metadata changed',lba)
        boot=Rig(disk);boot.mount()
        assert boot.call('Pi3UpdateLoad')==len(new)-HEADER
        assert boot.window==(0,0) and boot.writes==[record_lba]
        assert boot.call('Pi3UpdateConfirm',1,2)==1 and boot.window==(0,0)
        assert boot.writes==[record_lba,record_lba]
        checks+=10
        # The loader's U -> mount path must admit the serial transport against
        # the ordinary confirmed baseline, before commit is allowed to mutate
        # either control record.
        disk,old=volume();rig=Rig(disk);rig.mount()
        control_before=(disk.get(DATA+FIRST[2]-2,bytes(512)),disk.get(DATA+FIRST[3]-2,bytes(512)))
        new=container(bytes([0x3c])*1076)
        rig.put(0x1800000,hashlib.sha256(new).digest())
        assert rig.call('Pi3UpdateBeginFrom',1,len(new),0x1800000)==1
        assert rig.call('Pi3UpdateReceived')==0
        assert (disk.get(DATA+FIRST[2]-2,bytes(512)),disk.get(DATA+FIRST[3]-2,bytes(512)))==control_before
        assert not rig.writes
        checks+=4
        # A mounted volume without any confirmed record is not an update
        # baseline. Mount must refuse it, and must leave both control records
        # byte-for-byte intact.
        disk,old=volume()
        control=bytearray(disk[DATA+FIRST[2]-2])
        struct.pack_into('<I',control,64,2)
        struct.pack_into('<I',control,508,zlib.crc32(control[:508]))
        disk[DATA+FIRST[2]-2]=bytes(control)
        control_before=(disk.get(DATA+FIRST[2]-2,bytes(512)),disk.get(DATA+FIRST[3]-2,bytes(512)))
        rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0
        assert rig.call('Pi3UpdateError')==(1<<64)-6,rig.call('Pi3UpdateError')
        assert (disk.get(DATA+FIRST[2]-2,bytes(512)),disk.get(DATA+FIRST[3]-2,bytes(512)))==control_before
        assert not rig.writes
        checks+=4
        # Container field mutations, including the header-as-code regression,
        # must refuse before publishing any sector. Refresh outer transfer SHA
        # deliberately: these are structural checks, not just checksum tests.
        for offset,value,width in [(16,2711,4),(20,32,4),(24,0x2000000,8),
                                   (128+16,0x80000,8),(128+24,0x200004,8),
                                   (128+32,1077,8),(128+40,0x1000000,8),
                                   (128+48,0xd00001,8),(128+56,1,4),
                                   (128+8,1,4),(128+12,96,4),(128+96,2,4),
                                   (128+100,2711,4),(128+104,0x2000000,8),
                                   (128+112,1,1),(72,1,1)]:
            disk,_=volume();rig=Rig(disk);rig.mount()
            bad=bytearray(container(bytes(1076)))
            bad[offset:offset+width]=value.to_bytes(width,'little')
            rig.put(0x1800000,hashlib.sha256(bad).digest());rig.put(0x1800100,bad)
            assert rig.call('Pi3UpdateBegin',len(bad),0x1800000)==1
            assert rig.call('Pi3UpdateChunk',0,0x1800100,1024)==1
            assert rig.call('Pi3UpdateChunk',1024,0x1800500,len(bad)-1024)==1
            assert rig.call('Pi3UpdateCommit')==0 and not rig.writes
            checks+=1
        # Power cuts in the TRIED and CONFIRMED record writes preserve the
        # old confirmed generation. A never-written TRIED remains pending and
        # may be tried on next boot; a torn TRIED cannot become confirmed.
        for phase in ('tried','confirmed'):
            for tear in (False,True):
                disk,old=volume();new=container(bytes([0xa5])*1076)
                for off in range(0,len(new),512):
                    disk[DATA+FIRST[1]-2+off//512]=new[off:off+512].ljust(512,b'\0')
                disk[DATA+FIRST[3]-2]=record(1,2,new,1)
                rig=Rig(disk);rig.mount()
                baseline=disk[DATA+FIRST[2]-2]
                if phase=='confirmed':assert rig.call('Pi3UpdateLoad')==1076
                rig.cut=len(rig.writes)+1;rig.tear=tear
                if phase=='tried':assert rig.call('Pi3UpdateLoad')==0
                else:assert rig.call('Pi3UpdateConfirm',1,2)==0
                assert disk[DATA+FIRST[2]-2]==baseline
                boot=Rig(disk);boot.mount();n=boot.call('Pi3UpdateLoad')
                assert boot.get(0x200000,n) in (old[HEADER:],new[HEADER:])
                if phase=='confirmed':assert boot.get(0x200000,n)==old[HEADER:]
                checks+=4
        # Foreign root files, including directory chains, cannot alias any
        # owned extent. No write fence/publication is reached on refusal.
        for owned in range(5):
            for attribute in (0x20,0x10):
                disk,_=volume();root=bytearray(disk[DATA]);at=5*32
                root[at:at+11]=b'FOREIGN BIN';root[at+11]=attribute
                struct.pack_into('<H',root,at+26,FIRST[owned]);struct.pack_into('<I',root,at+28,512)
                disk[DATA]=bytes(root);rig=Rig(disk)
                assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
                assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Empty foreign files are valid only with a zero first cluster; a
        # nonzero first cluster would make the directory metadata ambiguous.
        for first,size,accepted in ((0,0,True),(50,0,False)):
            disk,_=volume();root=bytearray(disk[DATA]);at=5*32
            root[at:at+11]=b'EMPTY   BIN';root[at+11]=0x20
            struct.pack_into('<H',root,at+26,first);struct.pack_into('<I',root,at+28,size)
            disk[DATA]=bytes(root);fat_link(disk,50,0xfffffff)
            rig=Rig(disk)
            assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
            assert rig.call('Pi3UpdateMount')==(1 if accepted else 0) and not rig.writes
            checks+=1
        # A fragmented foreign file is admitted when every run is disjoint.
        disk,_=volume();root=bytearray(disk[DATA]);at=5*32
        root[at:at+11]=b'FRAG    BIN';root[at+11]=0x20
        struct.pack_into('<H',root,at+26,50);struct.pack_into('<I',root,at+28,1024);disk[DATA]=bytes(root)
        fat_link(disk,50,52);fat_link(disk,52,0xfffffff)
        rig=Rig(disk);assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==1;checks+=1
        # The first run may be foreign, but a later run entering an owned
        # control extent must still refuse the volume.
        disk,_=volume();root=bytearray(disk[DATA]);at=5*32
        root[at:at+11]=b'INTO    BIN';root[at+11]=0x20
        struct.pack_into('<H',root,at+26,50);struct.pack_into('<I',root,at+28,1024);disk[DATA]=bytes(root)
        fat_link(disk,50,FIRST[2]);fat_link(disk,FIRST[2],0xfffffff)
        rig=Rig(disk);assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # A root directory chain that enters an owned data cluster is refused
        # before any write fence is published.
        disk,_=volume();fat_link(disk,2,FIRST[0]);rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Owned names are unique admission records, not a set of aliases.
        disk,_=volume();root=bytearray(disk[DATA]);at=5*32
        root[at:at+11]=b'ANVILA  BIN';root[at+11]=0x20
        struct.pack_into('<H',root,at+26,FIRST[0]);struct.pack_into('<I',root,at+28,SIZES[0]);disk[DATA]=bytes(root)
        rig=Rig(disk);assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # The complete nested tree is admitted, but nested files/directories
        # may never cross-link updater-owned data. Every mutant refuses before
        # a write window or publication can be reached.
        disk,_=volume();nested_lba=nested_tree(disk);fat_link(disk,41,0xfffffff)
        Rig(disk).mount();checks+=1
        for owned_cluster in (FIRST[0],FIRST[0]+7,FIRST[0]+15,FIRST[1],FIRST[2],FIRST[3],FIRST[4]):
            disk,_=volume();nested_tree(disk,file_first=owned_cluster);rig=Rig(disk)
            assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
            assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        disk,_=volume();nested_tree(disk,child_attr=0x10,child_first=FIRST[0]);rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Directory entry graph cycle: OVERLAYS points back to itself.
        disk,_=volume();nested_tree(disk,child_attr=0x10,child_first=40);rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Directory FAT chain cycle, including a mid-chain merge back to start.
        disk,_=volume();nested_tree(disk);fat_link(disk,40,41);fat_link(disk,41,40);rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # File size and FAT termination must agree exactly: short, long and
        # cyclic chains are all refused rather than partially trusted.
        for shape in ('short','long','cycle'):
            disk,_=volume()
            if shape=='short':
                nested_tree(disk,file_size=1024);fat_link(disk,41,0xfffffff)
            elif shape=='long':
                nested_tree(disk,file_size=512);fat_link(disk,41,42);fat_link(disk,42,0xfffffff)
            else:
                nested_tree(disk,file_size=1024);fat_link(disk,41,42);fat_link(disk,42,41)
            rig=Rig(disk)
            assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
            assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Dot links are structural ownership, not decoration.
        for dot_self,dot_parent,include_dot in ((41,2,True),(40,41,True),(40,2,False)):
            disk,_=volume();nested_tree(disk,dot_self=dot_self,dot_parent=dot_parent,include_dot=include_dot)
            fat_link(disk,41,0xfffffff);rig=Rig(disk)
            assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
            assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Nine nested directories exceed the fixed depth-eight contract.
        disk,_=volume();root=bytearray(disk[DATA]);at=5*32
        root[at:at+11]=b'DEPTH0     ';root[at+11]=0x10;struct.pack_into('<H',root,at+26,40);disk[DATA]=bytes(root)
        for depth,cluster in enumerate(range(40,50)):
            fat_link(disk,cluster,0xfffffff);directory=bytearray(512)
            directory[:11]=b'.          ';directory[11]=0x10;struct.pack_into('<H',directory,26,cluster)
            directory[32:43]=b'..         ';directory[43]=0x10;struct.pack_into('<H',directory,58,2 if depth==0 else cluster-1)
            if depth<9:
                directory[64:75]=b'CHILD      ';directory[75]=0x10;struct.pack_into('<H',directory,90,cluster+1)
            disk[DATA+cluster-2]=bytes(directory)
        rig=Rig(disk)
        assert rig.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        assert rig.call('Pi3UpdateMount')==0 and not rig.writes;checks+=1
        # Revalidation failures after TRIED must not lose the explicit
        # confirmed fallback. Inject against the semantic target operation,
        # because named filesystem reads add metadata traffic before the
        # record read and make an absolute read ordinal meaningless.
        record_b_lba=DATA+(FIRST[3]-2)
        slot_b_lba=DATA+(FIRST[1]-2)
        for failed in ('candidate-slot','tried-record-readback','second-slot-verify'):
            disk,old=volume();new=container(bytes([0xa5])*1076)
            for off in range(0,len(new),512):disk[DATA+FIRST[1]-2+off//512]=new[off:off+512].ljust(512,b'\0')
            disk[DATA+FIRST[3]-2]=record(1,2,new,1)
            rig=Rig(disk);rig.mount();rig.read_lbas=[]
            if failed=='candidate-slot':
                rig.read_fail_lba=slot_b_lba;rig.read_fail_occurrence=1
            elif failed=='tried-record-readback':
                rig.read_fail_lba=record_b_lba;rig.read_fail_occurrence=1
            else:
                rig.read_fail_lba=slot_b_lba;rig.read_fail_occurrence=2
            result=rig.call('Pi3UpdateLoad')
            assert rig.read_fail_hits==1,(failed,rig.read_lbas)
            if failed=='candidate-slot':
                # Candidate read failure can use confirmed baseline directly.
                assert result==len(old)-HEADER
            else:assert result==0
            if failed=='second-slot-verify':
                assert rig.call('Pi3UpdateLoadFallback')==len(old)-HEADER
                assert rig.get(0x200000,len(old)-HEADER)==old[HEADER:]
            checks+=1
        disk,old=volume();nested_lba=nested_tree(disk);fat_link(disk,41,0xfffffff)
        rig=Rig(disk);rig.mount();assert rig.call('Pi3UpdateLoad')==len(old)-HEADER
        assert rig.call('Pi3UpdatePrepareHandoff',0x1000000)==1
        page=rig.get(0x1ff0000,128)
        running=Rig(disk)
        assert running.call('Pi3UpdateConfigure',0x2000000,0x100000,0,0x8000000,0x1000000,0x1000)==1
        running.put(0x1ff0000,page)
        running.put(0x1ff0000+16,b'\x09')
        assert running.call('Pi3UpdateMountHandoff')==0 and not running.writes
        running.put(0x1ff0000,page)
        assert running.call('Pi3UpdateMountHandoff')==1
        assert running.call('Pi3UpdateConfirmHandoff')==1
        assert running.sha_calls==0
        assert not any(DATA+FIRST[i]-2<=lba<DATA+FIRST[i]-2+16 for i in (0,1) for lba in running.read_lbas)
        assert nested_lba not in running.read_lbas
        assert running.get(0x1ff0000,8)==bytes(8)
        assert running.call('Pi3UpdateConfirmHandoff')==0
        checks+=4
        # Maximum-capacity metadata-only candidate admission. The loader's
        # prior full hash is an explicit handoff precondition; this fixture
        # does not put 28 MiB of fake payload bytes on the sparse device.
        disk,_=volume();v=bytearray(disk[2048]);v[13]=64
        struct.pack_into('<I',v,32,1056+65525*64);disk[2048]=bytes(v)
        m=bytearray(disk[0]);struct.pack_into('<I',m,458,1056+65525*64);disk[0]=bytes(m)
        first=[3,451,899,900,901];sizes=[0xe00000,0xe00000,512,512,1024]
        fat=bytearray(4096);struct.pack_into('<III',fat,0,0xffffff8,0xfffffff,0xfffffff)
        root=bytearray(disk[DATA])
        for i,(cluster,size) in enumerate(zip(first,sizes)):
            count=(size+32767)//32768
            for cl in range(cluster,cluster+count):struct.pack_into('<I',fat,cl*4,cl+1 if cl<cluster+count-1 else 0xfffffff)
            struct.pack_into('<H',root,i*32+26,cluster);struct.pack_into('<I',root,i*32+28,size)
        disk[DATA]=bytes(root)
        for n in range(8):disk[2080+n]=bytes(fat[n*512:(n+1)*512]);disk[2592+n]=disk[2080+n]
        digest=bytes(range(32))
        for slot,state in ((0,3),(1,2)):
            rec=bytearray(record(slot,slot+1,b'x',state));struct.pack_into('<Q',rec,16,0xe00000);rec[32:64]=digest
            struct.pack_into('<I',rec,508,zlib.crc32(rec[:508]))
            disk[DATA+(first[slot+2]-2)*64]=bytes(rec)
        page=bytearray(128);struct.pack_into('<QIIQQI',page,0,0x0031464f483350,2,1,2,0x1000000,2)
        struct.pack_into('<Q',page,40,0xe00000);page[48:80]=digest;struct.pack_into('<I',page,124,zlib.crc32(page[:124]))
        running=Rig(disk);running.put(0x1ff0000,page)
        assert running.call('Pi3UpdateConfigure',0x2000000,0xe00000,0,0x8000000,0x1000000,0x1000)==1
        assert running.call('Pi3UpdateMountHandoff')==1
        assert running.call('Pi3UpdateConfirmHandoff')==1
        assert running.sha_calls==0
        assert not any(DATA+(first[i]-2)*64<=lba<DATA+(first[i]-2)*64+0xe00000//512 for i in (0,1) for lba in running.read_lbas)
        assert running.writes==[DATA+(first[3]-2)*64]
        assert running.call('Pi3UpdateResetReady')==1
        running.put(0x1800000,digest)
        assert running.call('Pi3UpdateBegin',512,0x1800000)==1
        assert running.call('Pi3UpdateResetReady')==0
        checks+=8
        print('pi3_update_check PASS:',checks,'checks; actual FAT/CRC/updater emission, ten power-cut/tear runs')
        print('compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
if __name__=='__main__':main()
