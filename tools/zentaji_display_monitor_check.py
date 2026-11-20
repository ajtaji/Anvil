"""Qualify the native display connector against the actual GPU front buffer."""
import hashlib
import re
import time
from unittest.mock import patch

from pmfshot import png
import pmfshot_wifi


def check_display(command,client,port,folder):
    snap = command("display snapshot", "Display state before Anvil acquired")
    assert "pixels=1024x768 refresh_mHz=60000 format=0 stride=0 enabled=0" in snap, snap
    # A plain payload releases scanout. The first prompt on the new lease
    # can arrive before the first console frame reaches vertical blank.
    deadline = time.monotonic() + 30
    while True:
        live = command("dsi status", "Zentaji native display")
        if "enabled=1" in live:
            break
        if time.monotonic() >= deadline:
            queue = command("vkstat", "Native Vulkan queue sequence")
            raise AssertionError(f"No live scanout after payload return.\n{live}\n{queue}")
        time.sleep(0.25)
    assert "pixels=1024x768 refresh_mHz=60000 format=0 stride=4096 enabled=1" in live, live
    assert int(re.search(r"vsync=(\d+)", live)[1])>0
    device_id=int(re.search(r"ID=\$([0-9A-F]{16})",command("display id", "device ID="))[1],16)
    assert device_id & 65535 == 13
    command("dsi off", "Screen off.")
    command("display power", "enabled=0")
    command("display pattern", "could not present")
    command("display up", "Screen on.")
    command("display power", "enabled=1")
    command("dsi rails", "require a physical DSI controller")
    command("display pattern", "Native colour bars kept")
    with patch.object(pmfshot_wifi,"PORT",port):
        header,rows=pmfshot_wifi.grab_kept_reliable("127.0.0.1",timeout=90)
    client.prompt()
    w,h=header["w"],header["h"]
    assert (w,h)==(1024,768)
    expected=b"".join(bytes([255*((bits>>2)&1),255*((bits>>1)&1),255*(bits&1)])*(w//8)
                      for bits in range(7,-1,-1))
    assert len(rows)==h and all(row==expected for row in rows)
    (folder/"display-bars.png").write_bytes(png(w,h,rows))
    assert command("display snapshot","Display state before Anvil acquired")==snap
    return dict(device_id=device_id, pixels=w*h, rgb_sha256=hashlib.sha256(expected*h).hexdigest())
