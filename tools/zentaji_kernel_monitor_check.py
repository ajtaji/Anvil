"""Boot real second-stage kernels through the production Zentaji Anvil prompt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

from anvilfs_image import build_image
from anvil_readback import parse_readback
from zentaji_package import catalog, signatures

ROOT = Path(__file__).resolve().parents[1]

def get_kernel(command, files):
    from concurrent.futures import ThreadPoolExecutor
    import tftpy
    server=tftpy.TftpServer(str(files))
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker=pool.submit(server.listen,"127.0.0.1",69,1)
        try:
            if not server.is_running.wait(3):
                worker.result(timeout=1)
                raise RuntimeError("The loopback TFTP listener did not start")
            command("dhcp","Lease accepted")
            command("settings set net.server 10.0.2.2","Set net.server to 10.0.2.2")
            command("get SHORT.BIN","Fetched ")
            command("booti","complete kernel body")
            command("get KERNEL.BIN","Fetched ")
        finally:
            server.stop(now=True)
            worker.result(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--sign-script", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True, help="Installed Forge for the two Zentaji payload fixtures")
    parser.add_argument("--get",action="store_true",help="Stage the host-file kernel through a real TFTP peer on loopback UDP port 69")
    parser.add_argument("--modules",action="store_true",help="Exercise native module admission, hardware calls, unload and manifest discovery")
    args = parser.parse_args()
    native = args.zen_tools.resolve()
    sys.path.insert(0, str(native))
    from zen_console import Console
    from zen_native_fixture import Fixture

    executable, assembler = native/"zenwin.exe", native/"zasm.exe"
    compiler=args.compiler.resolve()
    signatures("pwsh.exe", args.sign_script, executables=[executable, assembler,compiler])
    image = ROOT/"build/zentaji/anvil.zex"
    raw = image.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    meta = json.loads(Path(str(image)+".boot.json").read_text())
    assert sha == meta["image_sha256"]
    stage = (meta["image_end"]+4095) & -4096
    source = (ROOT/"Zentaji/Tests/second_stage.zen").read_text()
    result = {"image_sha256": sha, "kernels": {}}
    args.keep.mkdir()
    proofs = []
    payloads={}
    for name,options in (("PET",["--wants-services"]),("SLEEP",[])):
        path=args.keep/(name+".zex")
        subprocess.run([compiler,"--compile",ROOT/"Zentaji/Tests/deadman_service.zentaji",
                        "--entry-returns",*options,"--load-addr",hex(stage+8),
                        "--stack-addr",hex(stage+0x200000),"-o",path],cwd=ROOT,
                       env=dict(os.environ,PMF_ROOT=str(ROOT)),check=True)
        payloads[name+".PMF"]=Path(str(path)+".pmf").read_bytes()

    for cmd, address in (("booti", meta["load"]), ("bootm", stage+4096+48)):
        folder = args.keep/cmd
        files = folder/"seed"
        files.mkdir(parents=True)
        asm, binary = folder/"second.zen", folder/"second.zex"
        asm.write_text(f".equ KERNEL_BASE,${address:X}\n.equ KERNEL_STACK,$08000000\n"+source)
        subprocess.run([assembler,"--zex",asm,binary], capture_output=True, text=True, check=True)
        kernel = bytearray(binary.read_bytes())
        struct.pack_into("<Q",kernel,32,64)  # BSS
        struct.pack_into("<Q",kernel,40,0)   # ROM default stack at top of RAM
        header = bytes(kernel[:64])
        payload = bytes(kernel[64:])
        disk_image = cmd=="bootm"
        prefix = header + bytes(4032 if disk_image else 0)
        content = prefix+payload
        if disk_image:
            content += bytes((-len(content))%4096)
        (files/"KERNEL.BIN").write_bytes(content)
        def mutated(name, offset, value):
            data=bytearray(content)
            data[offset:offset+len(value)]=value
            (files/name).write_bytes(data)
        mutated("ISA.BIN",0,b"ARMIMAGE")
        mutated("CRC.BIN",len(prefix),bytes([payload[0]^1]))
        mutated("FLAGS.BIN",48,struct.pack("<Q",1))
        mutated("ENTRY.BIN",8,struct.pack("<Q",address+1))
        mutated("DEST.BIN",16,struct.pack("<Q",0x07FFFF00))
        (files/"SHORT.BIN").write_bytes(prefix+payload[:-8])
        for name,pmf in payloads.items():
            (files/name).write_bytes(pmf)
        if args.modules:
            from zentaji_module_monitor_check import seed_modules,check_modules
            seed_modules(files,assembler,compiler,stage,manifest=not disk_image)
        disk=folder/"data.img"
        build_image(disk,2<<20,files)
        guest=Fixture(ram_size=128<<20,cores=2 if disk_image else 1,display_modes=[(1024,768,60000)],
                      hostfiles=[["anvil.zex",raw,False]],disks={0:(disk.read_bytes(),False)})
        guest.power_on(0,0)
        guest.net_attached=args.get and not disk_image
        if args.modules:
            guest.serial_feed(1,b"Z!")
        config=guest.write(folder/"native")
        signatures("pwsh.exe",args.sign_script,catalogs=[catalog(config.parent/"inputs.cat",list(config.parent.iterdir()),True)])
        log=folder/"run.log"
        transcript=folder/"transcript.log"
        with log.open("wb") as output, transcript.open("wb") as serial:
            process=subprocess.Popen([executable,config,"--headless","--live","--fast","--serial-listen","0",
                                      "--max","12000000000","--live-seconds","140"],stdout=output,stderr=subprocess.STDOUT)
            client=None
            try:
                limit=time.monotonic()+20
                while True:
                    with log.open("rb") as stream:
                        listener=re.search(rb"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0",stream.read(512))
                    if listener:
                        break
                    if process.poll() is not None or time.monotonic()>limit:
                        raise RuntimeError(f"Missing UART listener in {log}")
                    time.sleep(0.05)
                client=Console(int(listener[1]),40)
                startup=client.prompt()
                assert b"Zentaji boot ROM" in startup
                serial.write(startup)
                def command(line,expected):
                    reply=client.command(line)
                    serial.write(reply)
                    serial.flush()
                    assert expected.encode() in reply, (line,reply)
                    return reply.decode("ascii")
                if args.modules:
                    check_modules(command,manifest=not disk_image)
                command("deadman","Deadman is off.")
                command("deadman 999","Maximum monitor deadman interval is 15 seconds.")
                command("deadman 1 extra","setting was preserved")
                command("deadman","next payload: 15 seconds")
                command("d off","Deadman is off.")
                command("deadman 1","next payload: 1 seconds")
                if disk_image:
                    command("boot PET.PMF","$0000000050455431")
                    command("deadman","Deadman is off.")
                    command("mmio FFFF000000050800","FFFF000000050800: 0000000000000000")
                    registers=command("mmio FFFF000000030140 7","pmf> ")
                    assert re.findall(r"(?m)^[0-9A-F]{16}: ([0-9A-F]{16})\r?$",registers)==["0"*16]*7,registers
                    command("deadman 1","next payload: 1 seconds")
                    reply=command("boot SLEEP.PMF","Zentaji boot ROM v1")
                    assert "The payload returned" not in reply
                    command("deadman","hardware watchdog caused the last machine reset")
                    command("mmio FFFF000000020058","FFFF000000020058: 0000000000000002")
                    result["deadman"]={"service_pet_return":"50455431","reset_cause":2}
                else:
                    command("boot PET.PMF","deadman needs a free secondary")
                    command("deadman","next payload: 1 seconds")
                    command("deadman off","Deadman is off.")
                    result["single_core_guard_refused"]=True
                for name,reason in (("ISA","ZENTAJI1 signature"),("CRC","CRC-32 mismatch"),("SHORT","complete kernel body"),
                                    ("ENTRY","kernel entry"),("DEST","kernel load range"),("FLAGS","supervisor flags")):
                    command("load "+name+".BIN", "bytes into memory")
                    command(cmd,reason)
                command(cmd+" FFFF000000100000", "outside staging RAM")
                if args.get and not disk_image:
                    get_kernel(command,files)
                    result["tftp_kernel_boot"]=True
                else:
                    command("load KERNEL.BIN","bytes into memory")
                if disk_image:
                    bss=address+len(payload)
                    command(f"fill {bss:X} A5A5A5A5 10","pmf> ")
                    readback=command(f"readback {bss:X} 40","readback end")
                    assert parse_readback(readback,bss,64)==bytes([0xA5])*64
                client.socket.sendall((cmd+"\r").encode())
                assert process.wait(timeout=45)==0
            finally:
                if client:
                    client.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
        text=log.read_text(encoding="utf-8",errors="replace")
        assert re.search(r"^END steps=\d+ exit=4B424F54 ",text,re.M), log
        uart=bytes.fromhex(re.search(r"^SERIAL0 ([0-9A-Fa-f]+)$",text,re.M)[1])
        assert b"Starting the Zentaji supervisor kernel." in uart and b"pmf> " not in uart.split(b"Starting the Zentaji supervisor kernel.")[-1]
        if args.modules:
            aux=re.search(r"^SERIAL1 ([0-9A-Fa-f]+)$",text,re.M)
            assert aux and bytes.fromhex(aux[1])==b"AUX1:Z!", log
            result.setdefault("modules",{})[cmd]=dict(manifest=not disk_image,uart1_hex=aux[1],released=True)
        result["kernels"][cmd]=dict(load_address=address,exit="4B424F54",checked_refusals=7)
        evidence=args.keep/(cmd+".cat")
        signatures("pwsh.exe",args.sign_script,catalogs=[catalog(evidence,[log,transcript,config.parent/"inputs.cat"],True)])
        proofs.append(evidence)
    report=args.keep/"result.json"
    report.write_text(json.dumps(result,indent=2)+"\n")
    signatures("pwsh.exe",args.sign_script,catalogs=[catalog(args.keep/"results.cat",[*proofs,report],True)])
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
